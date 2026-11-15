"""ids.py - the board reads the commands make without a metered query (LC-25).

Every fixture id is an md5 of a label, so nothing here is a real Notion id (the
repo is public). Both forms a view-mode result is left in are exercised: the JSON
object itself, and the saved-to-file list of content blocks wrapping it.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDS = os.path.join(REPO, "plugins", "lc", "skills", "doctor", "ids.py")
sys.path.insert(0, os.path.dirname(IDS))
import ids  # noqa: E402


def hexid(label):
    return hashlib.md5(label.encode()).hexdigest()


def url(label):
    return f"https://app.notion.com/p/{hexid(label)}"


def row(sid, status="Ready", blocked=()):
    r = {"Story ID": sid, "Status": status, "url": url(sid), "Name": f"story {sid}"}
    if blocked:  # view mode leaves the key out entirely when the relation is empty
        r["Blocked by"] = json.dumps([url(b) for b in blocked])
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.n = 0

    def page(self, rows, has_more=False, saved=False):
        self.n += 1
        body = {"results": rows, "has_more": has_more}
        if has_more:
            body["next_cursor"] = "cursor-%d" % self.n
        data = [{"type": "text", "text": json.dumps(body)}] if saved else body
        path = os.path.join(self.tmp.name, f"page{self.n}.json")
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def run_ids(self, *argv):
        p = subprocess.run([sys.executable, "-B", IDS, *argv], capture_output=True, text=True)
        return p.returncode, p.stdout


class PageId(unittest.TestCase):
    def test_every_url_form_reduces_to_the_same_id(self):
        h = hexid("x")
        dashed = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        for u in (f"https://app.notion.com/p/{h}", f"https://www.notion.so/{h}?pvs=4",
                  f"https://www.notion.so/ws/Some-Title-{h}", dashed, h):
            self.assertEqual(ids.page_id(u), h, u)

    def test_a_title_ending_in_a_hex_letter_does_not_shift_the_id(self):
        h = hexid("y")
        self.assertEqual(ids.page_id(f"https://www.notion.so/Release-Code-{h}"), h)


class Relation(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(ids.relation(None), [])
        self.assertEqual(ids.relation(""), [])
        self.assertEqual(ids.relation('["a", "b"]'), ["a", "b"])
        self.assertEqual(ids.relation(["a"]), ["a"])


class Find(Base):
    def test_found_across_pages_and_both_forms(self):
        p1 = self.page([row("AB-1"), row("AB-2")], has_more=True, saved=True)
        p2 = self.page([row("AB-3", "Done", blocked=["AB-1"])])
        code, out = self.run_ids("find", p1, p2, "--id", "AB-3")
        self.assertEqual(code, 0, out)
        self.assertIn(url("AB-3"), out)
        self.assertIn("Done", out)
        self.assertIn(url("AB-1"), out)

    def test_not_found_is_exit_1(self):
        code, out = self.run_ids("find", self.page([row("AB-1")]), "--id", "AB-9")
        self.assertEqual(code, 1)
        self.assertIn("NOT FOUND", out)

    def test_not_found_on_an_incomplete_read_is_refused_not_answered(self):
        code, out = self.run_ids("find", self.page([row("AB-1")], has_more=True), "--id", "AB-9")
        self.assertEqual(code, 1)
        self.assertIn("not read to the end", out)

    def test_duplicate_is_exit_2(self):
        r2 = dict(row("AB-1"), url=url("other"))
        code, out = self.run_ids("find", self.page([row("AB-1"), r2]), "--id", "AB-1")
        self.assertEqual(code, 2)
        self.assertIn("DUPLICATE", out)


class Next(Base):
    def rows(self):
        return [row("AB-1"), row("AB-7"), row("AB-B3"), row("AB-B12"), row("ABC-40"), row("XY-99")]

    def test_plain_sequence_ignores_the_b_series_and_other_prefixes(self):
        code, out = self.run_ids("next", self.page(self.rows()), "--prefix", "AB")
        self.assertEqual((code, out.strip().splitlines()[-1]), (0, "AB-8"))

    def test_backlog_sequence(self):
        code, out = self.run_ids("next", self.page(self.rows()), "--prefix", "AB", "--backlog")
        self.assertEqual((code, out.strip().splitlines()[-1]), (0, "AB-B13"))

    def test_empty_sequence_starts_at_one(self):
        code, out = self.run_ids("next", self.page([row("XY-1")]), "--prefix", "AB")
        self.assertEqual(out.strip(), "AB-1")

    def test_highest_on_a_later_page_counts(self):
        p1 = self.page([row("AB-1")], has_more=True)
        p2 = self.page([row("AB-30")])
        code, out = self.run_ids("next", p1, p2, "--prefix", "AB")
        self.assertEqual(out.strip(), "AB-31")

    def test_refuses_an_incomplete_read(self):
        code, out = self.run_ids("next", self.page(self.rows(), has_more=True), "--prefix", "AB")
        self.assertEqual(code, 1)
        self.assertNotIn("AB-8", out)

    def test_warns_on_a_duplicate_in_the_sequence(self):
        rows = self.rows() + [dict(row("AB-7"), url=url("dup"))]
        code, out = self.run_ids("next", self.page(rows), "--prefix", "AB")
        self.assertIn("AB-7 is on more than one row", out)


class Dependents(Base):
    def test_finds_dependents_across_projects_and_url_forms(self):
        h = hexid("AB-1")
        rows = [row("AB-1", "Done"), row("AB-2", "Backlog", blocked=["AB-1"]),
                row("CD-5", "Backlog", blocked=["ZZ-1", "AB-1"]), row("AB-3", blocked=["AB-2"]),
                row("AB-4")]
        p = self.page(rows, saved=True)
        code, out = self.run_ids("dependents", p, "--url", f"https://www.notion.so/ws/Title-{h}")
        self.assertEqual(code, 0, out)
        got = [line.split("\t")[0] for line in out.strip().splitlines()]
        self.assertEqual(got, ["AB-2", "CD-5"])

    def test_none(self):
        code, out = self.run_ids("dependents", self.page([row("AB-1")]), "--url", url("AB-1"))
        self.assertEqual((code, out.strip()), (0, ""))

    def test_refuses_an_incomplete_read(self):
        p = self.page([row("AB-2", blocked=["AB-1"])], has_more=True)
        code, out = self.run_ids("dependents", p, "--url", url("AB-1"))
        self.assertEqual(code, 1)
        self.assertIn("not read to the end", out)


class PrefixFree(Base):
    def test_taken_and_free(self):
        p = self.page([row("AB-1"), row("ABC-2")])
        self.assertEqual(self.run_ids("prefix-free", p, "--prefix", "AB")[0], 1)
        self.assertEqual(self.run_ids("prefix-free", p, "--prefix", "XY")[0], 0)
        # ABC- is not AB-: a longer prefix sharing letters does not take a shorter one
        self.assertEqual(self.run_ids("prefix-free", self.page([row("ABC-2")]), "--prefix", "AB")[0], 0)

    def test_refuses_an_incomplete_read(self):
        p = self.page([row("XY-1")], has_more=True)
        self.assertEqual(self.run_ids("prefix-free", p, "--prefix", "AB")[0], 1)


class BadInput(Base):
    def test_truncated_saved_file(self):
        path = os.path.join(self.tmp.name, "bad.json")
        with open(path, "w") as f:
            json.dump([{"type": "text", "text": '{"results": [{"Story ID"'}], f)
        code, out = self.run_ids("list", path)
        self.assertEqual(code, 1)
        self.assertIn("truncated", out)

    def test_not_a_view_result(self):
        path = os.path.join(self.tmp.name, "x.json")
        with open(path, "w") as f:
            json.dump({"rows": []}, f)
        code, out = self.run_ids("list", path)
        self.assertEqual(code, 1)
        self.assertIn("not a view-mode result", out)


if __name__ == "__main__":
    unittest.main()
