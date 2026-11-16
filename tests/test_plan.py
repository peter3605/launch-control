"""plan.py - the deterministic half of /lc:plan - pinned.

/lc:plan files a whole backlog in one go, and plan.py is what stands between a
drafted proposal and the board: lint decides what may be filed, next-id and the
ledger decide what each row is called, payload decides what it says, and verify
reads the board back. These tests drive it as the skill does - a subprocess, judged
by exit code and FAIL lines.

Board reads reach plan.py in doctor's page format, so both are covered: the inline
{"rows": ...} page, and a {"file": ...} page naming a saved view-mode result - which
is itself written in BOTH forms the tool produces, the result object and a list of
content blocks wrapping it. Every URL is a hash of a label, never a real Notion id.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(REPO, "plugins", "lc", "skills", "plan", "plan.py")
CLOCKS = os.path.join(REPO, "plugins", "lc", "skills", "plan", "clocks.json")


def url(label):
    return "https://www.notion.so/" + hashlib.md5(label.encode()).hexdigest()


def run(*args):
    return subprocess.run([sys.executable, "-B", PLAN, *args], capture_output=True, text=True, timeout=60)


def fails(r):
    return [line.strip()[len("FAIL"):].strip() for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]


def clock(key):
    with open(CLOCKS) as f:
        return next(c for c in json.load(f)["clocks"] if c["key"] == key)


def story(draft, name, **kw):
    s = {"draft": draft, "name": name, "type": "Launch Blocker", "epic": "Product", "estimate": "S",
         "gating": "Self-serve", "agent": True, "leadTime": "", "notes": "",
         "doneWhen": f"`make test` exits 0 and the {draft.lower()} screen shows the saved record", "blockedBy": []}
    s.update(kw)
    return s


def proposal():
    """A proposal lint passes clean. Every failure test breaks exactly one thing in it."""
    domain = clock("domain")
    return {
        "project": {"key": "my-app", "name": "My App", "prefix": "XY", "repo": "/tmp/my-app", "kind": "Web App"},
        "source": "a design document",
        "claims": [{"claim": "login is built", "verdict": "partial", "evidence": "`auth/` has no logout route"}],
        "clocksDeclined": {},
        "stories": [
            story("D1", "Add a logout route"),
            story("D2", "Persist sessions across restarts", blockedBy=["D1"], type="Backlog"),
            story("D3", "Register the production domain", gating="External", agent=False,
                  epic="Third-party access", estimate="XS", clock="domain",
                  leadTime="Registrar propagation", leadDays=list(domain["leadDays"]),
                  doneWhen="`dig +short example.test` returns the server address from two resolvers"),
        ],
    }


class Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = self._td.name

    def tearDown(self):
        self._td.cleanup()

    def put(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def prop(self, p=None):
        return self.put("proposal.json", p if p is not None else proposal())

    def ledger(self, entries):
        return self.put("state.json", {d: {"id": i, "url": url(i)} for d, i in entries.items()})

    def rows(self, *ids, more=False):
        return self.put("board.json", {"count": len(ids), "rows": [[i, "Ready"] for i in ids], "hasMore": more})

    def saved_board(self, *ids, wrapped):
        result = {"results": [{"Story ID": i, "Status": "Ready", "url": url(i)} for i in ids], "has_more": False}
        self.put("road.json", [{"type": "text", "text": json.dumps(result)}] if wrapped else result)
        return self.put("board.json", {"file": "road.json"})


# -------------------------------------------------------------------- lint
class Lint(Tmp):
    def lint(self, p):
        return run("lint", self.prop(p))

    def test_the_fixture_proposal_is_clean(self):
        r = self.lint(proposal())
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(fails(r), [])

    def test_bare_file_name_outside_backticks_fails(self):
        p = proposal()
        p["stories"][0]["notes"] = "The route table lives in routes.py, next to the session store."
        r = self.lint(p)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertIn("notes has bare file names routes.py", f[0])

    def test_bare_file_name_in_done_when_and_name_fail_too(self):
        p = proposal()
        p["stories"][0]["doneWhen"] = "DESIGN.md lists the logout route and `make test` exits 0 on main"
        r = self.lint(p)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("doneWhen has bare file names DESIGN.md", fails(r)[0])

    def test_file_name_inside_backticks_passes(self):
        p = proposal()
        p["stories"][0]["notes"] = "The route table lives in `routes.py`; see `docs/DESIGN.md`."
        r = self.lint(p)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_done_when_that_restates_the_title_fails(self):
        p = proposal()
        p["stories"][0]["doneWhen"] = "The logout route is added"
        r = self.lint(p)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertIn("Done when restates the name", f[0])

    def test_done_when_with_nothing_checkable_fails(self):
        p = proposal()
        p["stories"][0]["doneWhen"] = "Users feel confident leaving shared computers behind them"
        r = self.lint(p)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("names nothing checkable", fails(r)[0])

    def test_clock_lead_days_diverging_without_reason_fail(self):
        p = proposal()
        lo, hi = clock("domain")["leadDays"]
        p["stories"][2]["leadDays"] = [lo + 5, hi + 10]
        r = self.lint(p)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertIn(f"but clocks.json says {[lo, hi]}", f[0])

    def test_clock_lead_days_diverging_with_a_reason_pass(self):
        p = proposal()
        lo, hi = clock("domain")["leadDays"]
        p["stories"][2]["leadDays"] = [lo + 5, hi + 10]
        p["stories"][2]["leadDaysReason"] = "this TLD needs a manual registry check first"
        r = self.lint(p)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("differ from clocks.json", r.stdout)

    def test_a_clock_takes_its_epic_and_estimate_when_left_out(self):
        p = proposal()
        del p["stories"][2]["epic"], p["stories"][2]["estimate"]
        self.assertEqual(self.lint(p).returncode, 0)

    def test_agent_story_that_needs_a_human_fails_without_override(self):
        p = proposal()
        p["stories"][0]["doneWhen"] = "Log in to App Store Connect and the build shows as Ready to Submit"
        r = self.lint(p)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("marked agent-doable but says", fails(r)[0])

    def test_dependency_cycle_fails(self):
        p = proposal()
        p["stories"][0]["blockedBy"] = ["D2"]
        r = self.lint(p)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any(x.startswith("dependency cycle") for x in fails(r)), fails(r))


# ----------------------------------------------------------------- next-id
class NextId(Tmp):
    def next_id(self, draft, board, ledger=None):
        return run("next-id", self.prop(), "--state", ledger or self.ledger({}), "--draft", draft,
                   "--board", board, "--prefix", "XY")

    def test_next_after_the_highest_on_the_board(self):
        r = self.next_id("D1", self.rows("XY-01", "XY-07", "XY-B3"))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "XY-08"), r.stderr)

    def test_skips_ids_already_in_this_runs_ledger(self):
        """A row created a second ago may not be in the view yet. The ledger is what
        keeps the next draft from being given the same ID."""
        r = self.next_id("D1", self.rows("XY-01", "XY-02"), self.ledger({"D0": "XY-03", "D9": "XY-04"}))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "XY-05"), r.stderr)

    def test_backlog_stories_take_the_b_series(self):
        r = self.next_id("D2", self.rows("XY-01", "XY-B2"), self.ledger({"D7": "XY-B3"}))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "XY-B4"), r.stderr)

    def test_reads_a_saved_board_in_both_forms(self):
        for wrapped in (False, True):
            with self.subTest(wrapped=wrapped):
                r = self.next_id("D1", self.saved_board("XY-01", "XY-11", wrapped=wrapped),
                                 self.ledger({"D0": "XY-12"}))
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "XY-13"), r.stderr)

    def test_exits_2_when_a_filed_id_is_on_two_rows(self):
        r = self.next_id("D1", self.rows("XY-01", "XY-02", "XY-02"), self.ledger({"D0": "XY-02"}))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn("XY-02 (D0) is on 2 rows", r.stderr)
        self.assertIn(url("XY-02"), r.stderr)

    def test_a_duplicate_this_run_did_not_file_is_not_its_race(self):
        r = self.next_id("D1", self.rows("XY-01", "XY-01"), self.ledger({"D0": "XY-02"}))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "XY-03"), r.stderr)

    def test_refuses_a_board_not_read_to_the_end(self):
        r = self.next_id("D1", self.rows("XY-01", more=True))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not read to the last page", r.stderr)

    def test_unknown_draft(self):
        r = self.next_id("D99", self.rows())
        self.assertEqual(r.returncode, 1)


# ----------------------------------------------------------------- payload
class Payload(Tmp):
    def payload(self, draft, ledger):
        r = run("payload", self.prop(), "--state", ledger, "--draft", draft, "--id", "XY-09",
                "--project-url", url("project"))
        return r, (json.loads(r.stdout) if r.returncode == 0 else None)

    def test_no_blockers_is_ready(self):
        r, p = self.payload("D1", self.ledger({}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(p["Status"], "Ready")
        self.assertEqual(p["Blocked by"], [])
        self.assertEqual(p["Story ID"], "XY-09")
        self.assertEqual(p["Project"], [url("project")])
        self.assertEqual(p["Agent can do this"], "__YES__")

    def test_any_blocker_is_backlog_and_links_the_filed_row(self):
        r, p = self.payload("D2", self.ledger({"D1": "XY-01"}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(p["Status"], "Backlog")
        self.assertEqual(p["Blocked by"], [url("XY-01")])
        self.assertEqual(p["Seq"], 2)

    def test_a_blocker_not_yet_filed_is_refused(self):
        r, _ = self.payload("D2", self.ledger({}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("has not been filed yet", r.stderr)

    def test_a_clock_carries_its_lead_days_and_is_human_work(self):
        r, p = self.payload("D3", self.ledger({}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p["Lead days min"], p["Lead days max"]], clock("domain")["leadDays"])
        self.assertEqual(p["Agent can do this"], "__NO__")
        self.assertEqual(p["Gating"], "External")


# ------------------------------------------------------------------- order
class Order(Tmp):
    def test_blockers_come_before_dependents(self):
        p = proposal()
        p["stories"] = [story("D3", "Third thing", blockedBy=["D2"]), story("D2", "Second thing", blockedBy=["D1"]),
                        story("D4", "Fourth thing", blockedBy=["D1", "D3"]), story("D1", "First thing")]
        r = run("order", self.prop(p), "--state", self.ledger({}))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["D1", "D2", "D3", "D4"])

    def test_filed_drafts_are_left_out(self):
        r = run("order", self.prop(), "--state", self.ledger({"D1": "XY-01"}))
        self.assertEqual(r.stdout.split(), ["D2", "D3"])


# ------------------------------------------------------------------ verify
class Verify(Tmp):
    def verify(self, board, ledger):
        return run("verify", "--state", ledger, "--board", board, "--prefix", "XY")

    def test_every_filed_id_once_is_clean(self):
        r = self.verify(self.rows("XY-01", "XY-02", "XY-B1"), self.ledger({"D1": "XY-01", "D2": "XY-B1"}))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_an_inline_page_without_a_true_count_or_with_resolved_is_refused(self):
        """LC-B15: an inline page states its row count, and a dropped row fails loudly."""
        ledger = self.ledger({"D1": "XY-01"})
        for page, needle in (({"rows": [["XY-01", "Ready"]], "hasMore": False}, "needs `count`"),
                             ({"count": 2, "rows": [["XY-01", "Ready"]], "hasMore": False}, "count 2 but gives 1"),
                             ({"resolved": True}, "carries no rows")):
            with self.subTest(needle=needle):
                r = self.verify(self.put("board.json", page), ledger)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertIn(needle, r.stdout + r.stderr)

    def test_catches_a_missing_id(self):
        r = self.verify(self.rows("XY-01"), self.ledger({"D1": "XY-01", "D2": "XY-02"}))
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("XY-02 (D2) is not on the road view"), f[0])

    def test_catches_a_duplicate(self):
        r = self.verify(self.rows("XY-01", "XY-02", "XY-02"), self.ledger({"D1": "XY-01", "D2": "XY-02"}))
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("XY-02 (D2) is on 2 rows"), f[0])

    def test_catches_another_projects_rows_on_the_road(self):
        r = self.verify(self.rows("XY-01", "EF-04"), self.ledger({"D1": "XY-01"}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("outside XY-: EF-04", fails(r)[0])

    def test_provisioning_records_are_not_stories(self):
        st = self.put("state.json", {"_project": {"id": "", "url": url("p")}, "D1": {"id": "XY-01", "url": url("a")}})
        self.assertEqual(self.verify(self.rows("XY-01"), st).returncode, 0)


# ------------------------------------------------------------------ record
class Record(Tmp):
    def test_will_not_silently_renumber(self):
        st = os.path.join(self.tmp, "state.json")
        self.assertEqual(run("record", "--state", st, "--draft", "D1", "--id", "XY-01", "--url", url("a")).returncode, 0)
        self.assertEqual(run("record", "--state", st, "--draft", "D1", "--id", "XY-02", "--url", url("a")).returncode, 1)
        self.assertEqual(run("record", "--state", st, "--draft", "D1", "--id", "XY-02", "--url", url("a"),
                             "--replace").returncode, 0)
        with open(st) as f:
            self.assertEqual(json.load(f)["D1"]["id"], "XY-02")


# ------------------------------------------------------------------ config
class Config(Tmp):
    def sibling(self):
        return self.put("sibling.json", {
            "project": "old-app", "prefix": "OLD", "hub": url("hub"),
            "stories": {"database": url("stories"), "dataSource": "collection://" + "1" * 8 + "-1111-1111-1111-" + "1" * 12},
            "projects": {"database": url("projects"), "dataSource": "collection://" + "2" * 8 + "-2222-2222-2222-" + "2" * 12},
            "views": {k: f"{url('stories')}?v={hashlib.md5(k.encode()).hexdigest()}"
                      for k in ("ready", "inProgress", "inReview", "waitingExternal", "yourTurn", "board", "dependents",
                                "road", "next", "open")},
            "viewContract": "scope by road",
        })

    def config(self, repo, prefix="XY", page=None):
        return run("config", "--repo", repo, "--from", self.sibling(), "--project", "my-app", "--prefix", prefix,
                   "--project-page", page or url("my-app-row"), "--road", f"{url('stories')}?v={'a' * 32}",
                   "--next", f"{url('stories')}?v={'c' * 32}", "--open", f"{url('stories')}?v={'d' * 32}")

    def test_refuses_to_overwrite_another_projects_config(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".claude"))
        target = os.path.join(repo, ".claude", "launch-control.json")
        theirs = {"project": "other-app", "prefix": "OTH", "projectPageId": "b" * 32}
        with open(target, "w") as f:
            json.dump(theirs, f)
        r = self.config(repo)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("refusing to overwrite", fails(r)[0])
        with open(target) as f:
            self.assertEqual(json.load(f), theirs)

    def test_writes_a_fresh_config_and_is_idempotent(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        r = self.config(repo)
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(os.path.join(repo, ".claude", "launch-control.json")) as f:
            cfg = json.load(f)
        self.assertEqual((cfg["project"], cfg["prefix"]), ("my-app", "XY"))
        self.assertEqual(cfg["views"]["road"], f"{url('stories')}?v={'a' * 32}")
        self.assertEqual(cfg["views"]["next"], f"{url('stories')}?v={'c' * 32}",
                         "the sibling's next is its own project's and must not be copied")
        self.assertEqual(cfg["views"]["open"], f"{url('stories')}?v={'d' * 32}",
                         "the sibling's open is its own project's and must not be copied")
        self.assertEqual(cfg["views"]["dependents"], f"{url('stories')}?v={hashlib.md5(b'dependents').hexdigest()}",
                         "dependents is shared across the board, so it is copied")
        self.assertEqual(cfg["projectPageId"], hashlib.md5(b"my-app-row").hexdigest())
        self.assertFalse(cfg["git"]["enabled"], "a temp dir is not a git repo")
        self.assertFalse(cfg["git"]["autoMerge"])
        with open(os.path.join(repo, ".gitignore")) as f:
            self.assertIn(".claude/.current-story", f.read().splitlines())
        r = self.config(repo)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("already written for this project", r.stdout)

    def test_same_prefix_for_a_different_project_page_is_refused(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        self.assertEqual(self.config(repo).returncode, 0)
        r = self.config(repo, page=url("someone-elses-row"))
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_a_road_without_a_view_id_is_refused(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        r = run("config", "--repo", repo, "--from", self.sibling(), "--project", "my-app", "--prefix", "XY",
                "--project-page", url("row"), "--road", url("stories"), "--next", f"{url('stories')}?v={'c' * 32}",
                "--open", f"{url('stories')}?v={'d' * 32}")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(repo, ".claude", "launch-control.json")))

    def test_next_is_required_and_must_be_a_view_of_its_own(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        road = f"{url('stories')}?v={'a' * 32}"
        base = ("config", "--repo", repo, "--from", self.sibling(), "--project", "my-app", "--prefix", "XY",
                "--project-page", url("row"), "--road", road, "--open", f"{url('stories')}?v={'d' * 32}")
        self.assertNotEqual(run(*base).returncode, 0, "a config without --next must not be written")
        r = run(*base, "--next", road)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("same view", fails(r)[0])
        r = run(*base, "--next", url("stories"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("--next has no ?v= view id", fails(r)[0])
        self.assertFalse(os.path.exists(os.path.join(repo, ".claude", "launch-control.json")))

    def test_open_is_required_and_must_be_a_view_of_its_own(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        road, nxt = f"{url('stories')}?v={'a' * 32}", f"{url('stories')}?v={'c' * 32}"
        base = ("config", "--repo", repo, "--from", self.sibling(), "--project", "my-app", "--prefix", "XY",
                "--project-page", url("row"), "--road", road, "--next", nxt)
        self.assertNotEqual(run(*base).returncode, 0, "a config without --open must not be written")
        for same, flag in ((road, "--road"), (nxt, "--next")):
            r = run(*base, "--open", same)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertTrue(any(flag in f and "--open" in f and "same view" in f for f in fails(r)), fails(r))
        r = run(*base, "--open", url("stories"))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("--open has no ?v= view id", fails(r)[0])
        self.assertFalse(os.path.exists(os.path.join(repo, ".claude", "launch-control.json")))


if __name__ == "__main__":
    unittest.main()
