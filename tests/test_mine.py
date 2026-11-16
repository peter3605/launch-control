"""The lead-time arithmetic in mine.py, pinned.

The README sells /lc:mine on "the arithmetic shown, not judged by eye". These
tests are what makes that sentence checkable: every number the report prints is
asserted here against a hand-computed value, so a change to the arithmetic has
to be a deliberate one that updates a test, not a silent one.

Stdlib only, on purpose. The plugin ships no requirements file and should not
start now, so the suite it is tested by does not get to have dependencies either.
"""
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINE_DIR = os.path.join(REPO, "plugins", "lc", "skills", "mine")
DOCTOR_DIR = os.path.join(REPO, "plugins", "lc", "skills", "doctor")
sys.dont_write_bytecode = True
for d in (MINE_DIR, DOCTOR_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import mine  # noqa: E402
from doctor import CheckError, load_result  # noqa: E402

TODAY = "2026-01-01"


def u(sid):
    """A stable notion-shaped URL per story id - page_id() wants 32 hex chars."""
    return "https://app.notion.com/p/" + hashlib.md5(sid.encode()).hexdigest()


def row(sid, gating="Self-serve", lo=None, hi=None, status="Ready",
        estimate="", blocked_by=(), lead_text="", name=None, started=None):
    r = {
        "Story ID": sid,
        "Name": name if name is not None else f"{sid} does a thing",
        "Gating": gating,
        "Lead days min": lo,
        "Lead days max": hi,
        "Status": status,
        "Estimate": estimate,
        "Lead time": lead_text,
        "Blocked by": [u(b) for b in blocked_by],
        "url": u(sid),
    }
    if started is not None:
        r["Started"] = started
    return r


def clock(sid, lo=None, hi=None, **kw):
    """An External row - the only kind that carries real lead days."""
    return row(sid, gating="External", lo=lo, hi=hi, **kw)


def board(*rows):
    return mine.Board(list(rows))


class Helpers(unittest.TestCase):
    def test_page_id_takes_the_last_hex_run_and_ignores_query(self):
        h, g = hashlib.md5(b"x").hexdigest(), hashlib.md5(b"y").hexdigest()
        self.assertEqual(mine.page_id(f"https://app.notion.com/p/{h}?pvs=204"), h)
        # The dashed UUID form Notion also hands out.
        dashed = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        self.assertEqual(mine.page_id(f"https://app.notion.com/p/{dashed}"), h)
        # A workspace slug in front of the page id: the page id is the last run.
        self.assertEqual(mine.page_id(f"https://app.notion.com/{g}/{h}"), h)
        self.assertEqual(mine.page_id(""), "")
        self.assertEqual(mine.page_id(None), "")

    def test_relation_accepts_a_list_or_a_json_string(self):
        h = hashlib.md5(b"a").hexdigest()
        self.assertEqual(mine.relation([f"https://n.so/{h}"]), [h])
        self.assertEqual(mine.relation(json.dumps([f"https://n.so/{h}"])), [h])
        for empty in (None, "", [], "not json"):
            self.assertEqual(mine.relation(empty), [])

    def test_number_treats_blank_as_unknown_not_zero(self):
        # The distinction the whole floor-marking rests on.
        self.assertIsNone(mine.number(""))
        self.assertIsNone(mine.number(None))
        self.assertIsNone(mine.number("abc"))
        self.assertEqual(mine.number(0), 0.0)
        self.assertEqual(mine.number("7"), 7.0)

    def test_plain_unwraps_the_links_notion_makes_out_of_file_names(self):
        self.assertEqual(mine.plain("[deploy.sh](http://deploy.sh) runs"), "deploy.sh runs")
        self.assertEqual(mine.plain(None), "")

    def test_span_collapses_an_equal_range(self):
        self.assertEqual(mine.span(3, 3), "3")
        self.assertEqual(mine.span(3, 5), "3-5")
        self.assertEqual(mine.days(2.5), "2.5")
        self.assertEqual(mine.days(4.0), "4")


class StraightChain(unittest.TestCase):
    """A <- B <- C: C waits on B waits on A, all External with known leads."""

    def setUp(self):
        self.b = board(
            clock("EF-1", 5, 5),
            clock("EF-2", 3, 3, blocked_by=["EF-1"]),
            clock("EF-3", 2, 2, blocked_by=["EF-2"]),
        )

    def test_finish_accumulates_down_the_chain(self):
        self.assertEqual(self.b.finish(u_id("EF-1")), (5.0, 5.0, True))
        self.assertEqual(self.b.finish(u_id("EF-2")), (8.0, 8.0, True))
        self.assertEqual(self.b.finish(u_id("EF-3")), (10.0, 10.0, True))

    def test_chain_runs_the_other_way_through_the_dependents(self):
        self.assertEqual(self.b.chain(u_id("EF-3"))[:3], (2.0, 2.0, True))
        self.assertEqual(self.b.chain(u_id("EF-2"))[:3], (5.0, 5.0, True))
        self.assertEqual(self.b.chain(u_id("EF-1"))[:3], (10.0, 10.0, True))

    def test_chain_reports_the_path_it_measured(self):
        path = self.b.chain(u_id("EF-1"))[3]
        self.assertEqual([self.b.items[p]["id"] for p in path], ["EF-1", "EF-2", "EF-3"])

    def test_ranges_stay_separate_on_each_bound(self):
        b = board(clock("EF-1", 2, 6), clock("EF-2", 1, 10, blocked_by=["EF-1"]))
        self.assertEqual(b.finish(u_id("EF-2")), (3.0, 16.0, True))


class BranchingWaits(unittest.TestCase):
    def test_finish_takes_the_latest_blocker_not_their_sum(self):
        # Two blockers run concurrently. Waiting for both takes as long as the
        # slower one, not as long as both - the bug that would inflate every date.
        b = board(
            clock("EF-1", 5, 5),
            clock("EF-2", 7, 7),
            clock("EF-3", 1, 1, blocked_by=["EF-1", "EF-2"]),
        )
        self.assertEqual(b.finish(u_id("EF-3")), (8.0, 8.0, True))

    def test_chain_takes_the_longest_run_of_dependents(self):
        # EF-1 feeds a 2-day branch and a 9-day branch; its chain follows the 9.
        b = board(
            clock("EF-1", 1, 1),
            clock("EF-2", 2, 2, blocked_by=["EF-1"]),
            clock("EF-3", 9, 9, blocked_by=["EF-1"]),
        )
        lo, hi, known, path = b.chain(u_id("EF-1"))
        self.assertEqual((lo, hi, known), (10.0, 10.0, True))
        self.assertEqual([b.items[p]["id"] for p in path], ["EF-1", "EF-3"])

    def test_a_blocker_outside_the_view_adds_nothing(self):
        # Rows not in the view are Done or agent work. They must not be invented.
        b = board(clock("EF-2", 3, 3, blocked_by=["EF-MISSING"]))
        self.assertEqual(b.items[u_id("EF-2")]["open_blockers"], [])
        self.assertEqual(b.finish(u_id("EF-2")), (3.0, 3.0, True))


class SelfServeCostsNoCalendarDays(unittest.TestCase):
    def test_desk_work_contributes_zero_lead_and_stays_known(self):
        b = board(row("EF-1", estimate="XL"))
        self.assertEqual(b.items[u_id("EF-1")]["lead"], (0.0, 0.0))
        self.assertEqual(b.lead(u_id("EF-1")), (0.0, 0.0, True))

    def test_self_serve_ignores_lead_days_if_someone_filled_them_in(self):
        b = board(row("EF-1", lo=99, hi=99))
        self.assertEqual(b.lead(u_id("EF-1")), (0.0, 0.0, True))


class UnrankedClock(unittest.TestCase):
    """External with no lead days: counted as 0, and the total marked a floor."""

    def test_lead_is_unknown_not_zero(self):
        b = board(clock("EF-1"))
        self.assertIsNone(b.items[u_id("EF-1")]["lead"])
        self.assertEqual(b.lead(u_id("EF-1")), (0.0, 0.0, False))

    def test_one_unknown_lead_marks_the_whole_finish_a_floor(self):
        b = board(clock("EF-1"), clock("EF-2", 4, 4, blocked_by=["EF-1"]))
        lo, hi, known = b.finish(u_id("EF-2"))
        self.assertEqual((lo, hi), (4.0, 4.0))
        self.assertFalse(known, "an unknown lead in the chain must mark the total a floor")

    def test_one_unknown_lead_marks_the_whole_chain_a_floor(self):
        b = board(clock("EF-1"), clock("EF-2", 4, 4, blocked_by=["EF-1"]))
        self.assertFalse(b.chain(u_id("EF-1"))[2])

    def test_a_single_filled_bound_is_mirrored_onto_the_other(self):
        self.assertEqual(board(clock("EF-1", lo=6))  .lead(u_id("EF-1")), (6.0, 6.0, True))
        self.assertEqual(board(clock("EF-1", hi=6))  .lead(u_id("EF-1")), (6.0, 6.0, True))

    def test_bounds_given_backwards_are_ordered(self):
        self.assertEqual(board(clock("EF-1", 9, 2)).lead(u_id("EF-1")), (2.0, 9.0, True))


class Cycles(unittest.TestCase):
    """A cycle must raise, never guess a number."""

    def setUp(self):
        self.b = board(
            clock("EF-1", 1, 1, blocked_by=["EF-3"]),
            clock("EF-2", 1, 1, blocked_by=["EF-1"]),
            clock("EF-3", 1, 1, blocked_by=["EF-2"]),
        )

    def test_finish_raises_and_names_the_loop(self):
        with self.assertRaises(ValueError) as e:
            self.b.finish(u_id("EF-1"))
        self.assertIn("EF-1", str(e.exception))
        self.assertIn("->", str(e.exception))

    def test_chain_raises_too(self):
        with self.assertRaises(ValueError):
            self.b.chain(u_id("EF-1"))

    def test_a_row_blocked_by_itself_is_a_cycle(self):
        b = board(clock("EF-1", 1, 1, blocked_by=["EF-1"]))
        with self.assertRaises(ValueError):
            b.finish(u_id("EF-1"))


class SavedResultForms(unittest.TestCase):
    """LC-07's input shapes: the tool writes a result two different ways."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, text):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_plain_object(self):
        p = self.write("a.json", json.dumps({"results": [{"Story ID": "EF-1"}]}))
        self.assertEqual(load_result(p)["results"][0]["Story ID"], "EF-1")

    def test_list_of_content_blocks(self):
        # The large-result form: a JSON list whose blocks' text IS the payload.
        payload = json.dumps({"results": [{"Story ID": "EF-1"}], "has_more": False})
        p = self.write("b.json", json.dumps([{"type": "text", "text": payload}]))
        self.assertEqual(load_result(p)["results"][0]["Story ID"], "EF-1")

    def test_payload_split_across_several_blocks(self):
        payload = json.dumps({"results": [{"Story ID": "EF-1"}]})
        half = len(payload) // 2
        p = self.write("c.json", json.dumps([
            {"type": "text", "text": payload[:half]},
            {"type": "text", "text": payload[half:]},
        ]))
        self.assertEqual(load_result(p)["results"][0]["Story ID"], "EF-1")

    def test_mine_reads_the_block_form_end_to_end(self):
        payload = json.dumps({"results": [clock("EF-1", 4, 4)]})
        p = self.write("d.json", json.dumps([{"type": "text", "text": payload}]))
        rows = mine.load([p])
        self.assertEqual(rows[0]["Story ID"], "EF-1")

    def test_a_truncated_block_says_which_layer_failed(self):
        p = self.write("e.json", json.dumps([{"type": "text", "text": '{"results": ['}]))
        with self.assertRaises(CheckError) as e:
            load_result(p)
        self.assertIn("content block", str(e.exception))

    def test_a_missing_file_is_a_sentence_not_a_traceback(self):
        with self.assertRaises(CheckError):
            load_result(os.path.join(self.tmp.name, "nope.json"))

    def test_a_json_list_that_is_not_blocks_is_rejected(self):
        p = self.write("f.json", json.dumps([1, 2, 3]))
        with self.assertRaises(CheckError):
            load_result(p)


class Report(unittest.TestCase):
    """main() end to end - the numbers a human actually reads."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_mine(self, rows, *extra):
        p = os.path.join(self.tmp.name, "view.json")
        with open(p, "w") as f:
            json.dump({"results": list(rows)}, f)
        argv = ["mine.py", "--view", p, "--today", TODAY, *extra]
        buf = io.StringIO()
        old = sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(buf):
                code = mine.main()
        finally:
            sys.argv = old
        return code, buf.getvalue()

    def test_no_rows_exits_one(self):
        code, out = self.run_mine([])
        self.assertEqual(code, 1)
        self.assertIn("No rows", out)

    def test_a_cycle_exits_one_and_ranks_nothing(self):
        code, out = self.run_mine([
            clock("EF-1", 1, 1, blocked_by=["EF-2"]),
            clock("EF-2", 1, 1, blocked_by=["EF-1"]),
        ])
        self.assertEqual(code, 1)
        self.assertIn("dependency cycle", out)
        self.assertNotIn("START TODAY", out)

    def test_dates_are_today_plus_the_finish(self):
        code, out = self.run_mine([clock("EF-1", 3, 5)])
        self.assertEqual(code, 0)
        self.assertIn("2026-01-04 .. 2026-01-06", out)
        self.assertIn("lead     3-5", out)

    def test_an_unranked_clock_is_listed_never_guessed(self):
        code, out = self.run_mine([clock("EF-1", lead_text="about a fortnight")])
        self.assertEqual(code, 0)
        self.assertIn("Unranked", out)
        self.assertIn("about a fortnight", out)

    def test_the_floor_marker_lands_on_the_date_not_just_the_legend(self):
        code, out = self.run_mine([
            clock("EF-1"),
            clock("EF-2", 4, 4, blocked_by=["EF-1"]),
        ])
        self.assertEqual(code, 0)
        # The legend always prints a '+', so assert it on the date itself.
        self.assertIn("2026-01-05 .. 2026-01-05+", out)

    def test_slack_arithmetic_is_printed_and_correct(self):
        # EF-1 (2) -> EF-2 (6) is the only run: chain(EF-1) = 8, and the project
        # ends no sooner than finish(EF-2) = 8, so slack = 8 - 8 = 0.
        code, out = self.run_mine([
            clock("EF-1", 2, 2),
            clock("EF-2", 6, 6, blocked_by=["EF-1"]),
        ])
        self.assertEqual(code, 0)
        self.assertIn("EF-1 2 + EF-2 6 = 8 days", out)
        self.assertIn("slack = 8 - 8 = 0", out)
        self.assertIn("Every day this waits moves that launch a day", out)

    def test_the_pick_is_least_slack_even_when_another_chain_is_longer(self):
        # EF-0 is already running and ends at 20, so EF's launch is 20 out and
        # EF-1's 5-day chain has 15 days of slack. GH-1's 3-day chain IS its
        # whole project, so slack 0. The shorter chain wins: it is the one whose
        # delay moves a launch. A pick that sorted on chain length picks EF-1.
        code, out = self.run_mine([
            clock("EF-0", 20, 20, status="In Progress"),
            clock("EF-1", 5, 5),
            clock("GH-1", 3, 3),
        ])
        self.assertEqual(code, 0)
        self.assertIn("START TODAY\n  GH-1", out)
        self.assertIn("slack = 3 - 3 = 0", out)
        self.assertIn("EF-1     slack   15", out)

    def test_equal_slack_breaks_to_the_longer_chain(self):
        # Both at slack 0; EF-1 heads 10 days of waiting and GH-1 heads 3.
        code, out = self.run_mine([
            clock("EF-1", 4, 4),
            clock("EF-2", 6, 6, blocked_by=["EF-1"]),
            clock("GH-1", 3, 3),
        ])
        self.assertEqual(code, 0)
        self.assertIn("START TODAY\n  EF-1", out)
        self.assertIn("Runners-up", out)

    def test_prefix_hides_a_blocker_from_the_report_but_still_counts_it(self):
        # EF-2 waits on another project's clock. Narrowing to EF must not make
        # that wait disappear from EF-2's date - the rows are filtered after
        # loading precisely so a blocker still counts, whoever owns it.
        code, out = self.run_mine([
            clock("GH-1", 7, 7, status="In Progress"),
            clock("EF-2", 6, 6, status="In Progress", blocked_by=["GH-1"]),
        ], "--prefix", "EF")
        self.assertEqual(code, 0)
        self.assertNotIn("GH-1", out)
        # 6 of its own + 7 it is waiting on = 13 days out, not 6.
        self.assertIn("2026-01-14 .. 2026-01-14", out)

    def test_prefix_is_case_and_dash_insensitive(self):
        rows = [clock("EF-1", 4, 4), clock("GH-1", 9, 9)]
        for p in ("ef", "EF-", "ef-"):
            code, out = self.run_mine(rows, "--prefix", p)
            self.assertEqual(code, 0)
            self.assertNotIn("GH-1", out, f"--prefix {p} should have hidden GH-1")

    def test_ready_but_blocked_is_flagged_and_kept_out_of_the_pick(self):
        # A board bug: Ready means unblocked, so a Ready row waiting on an open
        # one is a contradiction that would otherwise poison the pick.
        code, out = self.run_mine([
            clock("EF-1", 3, 3, status="In Progress"),
            clock("EF-2", 5, 5, status="Ready", blocked_by=["EF-1"]),
        ])
        self.assertEqual(code, 0)
        self.assertIn("Ready but blocked", out)
        self.assertIn("EF-2 waits on EF-1", out)

    def test_desk_lists_self_serve_smallest_first_with_in_progress_ahead(self):
        code, out = self.run_mine([
            row("EF-1", estimate="L"),
            row("EF-2", estimate="XS"),
            row("EF-3", estimate="XL", status="In Progress"),
            row("EF-4", estimate="S", status="Done"),
        ])
        self.assertEqual(code, 0)
        desk = out.split("YOUR DESK")[1].split("\n\n")[0]
        self.assertLess(desk.index("EF-3"), desk.index("EF-2"), "in progress comes first")
        self.assertLess(desk.index("EF-2"), desk.index("EF-1"), "then smallest first")
        self.assertNotIn("EF-4", desk, "Done is not on your desk")

    def test_nothing_ready_heads_a_known_run(self):
        code, out = self.run_mine([clock("EF-1", status="Ready")])
        self.assertEqual(code, 0)
        self.assertIn("Nothing Ready heads a run of known lead days", out)


def u_id(sid):
    return mine.page_id(u(sid))


class StartedClock(unittest.TestCase):
    """LC-29: an In Progress clock is projected from the day it started, not from
    today. TODAY is 2026-01-01; 2025-12-04 is 28 days before it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    run_mine = Report.run_mine

    def test_started_28_days_ago_with_lead_42_finishes_in_14(self):
        code, out = self.run_mine([clock("EF-1", 42, 42, status="In Progress", started="2025-12-04")])
        self.assertEqual(code, 0, out)
        # 42 - 28 = 14 days from 2026-01-01, not 42.
        self.assertIn("earliest finish 2026-01-15 .. 2026-01-15", out)
        self.assertIn("started 2025-12-04, 28 days in", out)
        self.assertNotIn("2026-02-12", out)  # today + 42, the old projection

    def test_the_remaining_lead_carries_through_the_blocker_chain(self):
        b = mine.Board([clock("EF-1", 42, 42, status="In Progress", started="2025-12-04"),
                        clock("EF-2", 3, 5, status="Backlog", blocked_by=["EF-1"])],
                       datetime.date(2026, 1, 1))
        self.assertEqual(b.finish(u_id("EF-1")), (14.0, 14.0, True))
        self.assertEqual(b.finish(u_id("EF-2")), (17.0, 19.0, True))
        self.assertEqual(b.chain(u_id("EF-1"))[:3], (17.0, 19.0, True))

    def test_part_way_through_a_range_only_the_max_still_has_days_left(self):
        b = mine.Board([clock("EF-1", 14, 42, status="In Progress", started="2025-12-04")],
                       datetime.date(2026, 1, 1))
        self.assertEqual(b.lead(u_id("EF-1")), (0.0, 14.0, True))

    def test_started_longer_ago_than_lead_max_is_overdue_not_a_past_date(self):
        # Started 2025-11-01: 61 days in, against a 42-day max.
        code, out = self.run_mine([clock("EF-1", 14, 42, status="In Progress", started="2025-11-01")])
        self.assertEqual(code, 0, out)
        line = [l for l in out.splitlines() if l.startswith("  EF-1")][0]
        self.assertIn("earliest finish overdue", line)
        self.assertIn("61 days in - past its 42-day max", line)
        self.assertNotIn("2025-12", line)  # no date in the past
        self.assertNotRegex(line, r"-\d+ days|\.\. -")  # no negative number
        b = mine.Board([clock("EF-1", 14, 42, status="In Progress", started="2025-11-01")],
                       datetime.date(2026, 1, 1))
        self.assertEqual(b.lead(u_id("EF-1")), (0.0, 0.0, True))

    def test_started_blank_keeps_todays_behaviour(self):
        code, out = self.run_mine([clock("EF-1", 42, 42, status="In Progress")])
        self.assertEqual(code, 0, out)
        self.assertIn("earliest finish 2026-02-12 .. 2026-02-12", out)
        self.assertIn("no Started, so projected from today", out)

    def test_started_is_ignored_on_a_clock_that_is_not_running(self):
        code, out = self.run_mine([clock("EF-1", 42, 42, status="Ready", started="2025-12-04")])
        self.assertEqual(code, 0, out)
        self.assertIn("earliest finish 2026-02-12 .. 2026-02-12", out)
        self.assertNotIn("days in", out)

    def test_a_started_in_the_future_has_run_no_days(self):
        b = mine.Board([clock("EF-1", 10, 10, status="In Progress", started="2026-01-05")],
                       datetime.date(2026, 1, 1))
        self.assertEqual(b.lead(u_id("EF-1")), (10.0, 10.0, True))

    def test_a_view_read_gives_the_date_in_its_expanded_column(self):
        r = clock("EF-1", 42, 42, status="In Progress")
        r["date:Started:start"] = "2025-12-04"
        code, out = self.run_mine([r])
        self.assertEqual(code, 0, out)
        self.assertIn("earliest finish 2026-01-15 .. 2026-01-15", out)

    def test_a_malformed_started_in_a_view_file_exits_one(self):
        code, out = self.run_mine([clock("EF-1", 42, 42, status="In Progress", started="04/12/2025")])
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL", out)
        self.assertIn("'04/12/2025' is not a YYYY-MM-DD date", out)


class InlinePage(unittest.TestCase):
    """LC-B16: an inline page of Your turn is given in a short checked form, never
    re-typed whole into a file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_mine(self, saved_rows, inline):
        argv = ["mine.py", "--today", TODAY]
        if saved_rows is not None:
            p = os.path.join(self.tmp.name, "view.json")
            with open(p, "w") as f:
                json.dump({"results": saved_rows, "has_more": True}, f)
            argv += ["--view", p]
        q = os.path.join(self.tmp.name, "inline.json")
        with open(q, "w") as f:
            f.write(inline if isinstance(inline, str) else json.dumps(inline))
        argv += ["--inline", q]
        buf, old = io.StringIO(), sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = mine.main()
        finally:
            sys.argv = old
        return code, buf.getvalue()

    def test_saved_pages_plus_an_inline_last_page_rank_as_one_board(self):
        """The chain crosses the page boundary: EF-1 is saved, EF-2 waits on it inline."""
        code, out = self.run_mine([clock("EF-1", 3, 5)],
                                  {"count": 1, "hasMore": False, "rows": [clock("EF-2", 2, 2, blocked_by=["EF-1"])]})
        self.assertEqual(code, 0, out)
        self.assertIn("EF-2", out)
        self.assertIn("2026-01-06 .. 2026-01-08", out)  # 3-5 days then 2: finish 5..7 from 2026-01-01

    def test_an_inline_row_carries_started(self):
        code, out = self.run_mine(None, {"count": 1, "hasMore": False, "rows": [
            clock("EF-1", 42, 42, status="In Progress", started="2025-12-04")]})
        self.assertEqual(code, 0, out)
        self.assertIn("earliest finish 2026-01-15 .. 2026-01-15", out)

    def test_a_whole_read_inline_needs_no_view_file(self):
        code, out = self.run_mine(None, {"count": 1, "hasMore": False, "rows": [clock("EF-1", 3, 5)]})
        self.assertEqual(code, 0, out)
        self.assertIn("2026-01-04 .. 2026-01-06", out)

    def test_malformed_inline_pages_fail_loudly(self):
        good = clock("EF-1", 3, 5)
        cases = [
            ({"count": 2, "hasMore": False, "rows": [good]}, "count 2 but gives 1"),
            ({"hasMore": False, "rows": [good]}, "needs `count`"),
            ({"count": 1, "rows": [good]}, "needs `hasMore`"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, **{"Notes and traps": "x"})]}, "unexpected key(s) Notes and traps"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, url="EF-1")]}, "no Notion page id"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, Status="Waiting")]}, "Status 'Waiting'"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, Gating="Outside")]}, "Gating 'Outside'"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, **{"Lead days max": "ten"})]}, "is not a number"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, **{"Blocked by": ["EF-0"]})]}, "Blocked by must be"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, Started="2025-13-45")]}, "Started '2025-13-45' is not a YYYY-MM-DD date"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, Started="last month")]}, "Started 'last month' is not a YYYY-MM-DD date"),
            ({"count": 1, "hasMore": False, "rows": [dict(good, Started=20251204)]}, "Started 20251204 is not a YYYY-MM-DD date"),
            ('{"count": 1, "hasMore": false, "rows": [{"Story ID"', "not valid JSON"),
        ]
        for inline, needle in cases:
            with self.subTest(needle=needle):
                code, out = self.run_mine(None, inline)
                self.assertEqual(code, 1, out)
                self.assertIn("FAIL", out)
                self.assertIn(needle, out)
                self.assertNotIn("START TODAY", out)


if __name__ == "__main__":
    unittest.main()


class ShippedSample(unittest.TestCase):
    """LC-B11: the README tells a stranger to run mine.py on examples/sample-board.json.

    Run it the way the README says, as a subprocess against the real file, so a
    change to mine.py's input format that orphans the sample turns the build red
    instead of breaking the first thing a visitor tries. --today pins the dates;
    the README's command omits it, so the headings are what is asserted, plus the
    few facts the README's prose claims about the sample.
    """

    SAMPLE = os.path.join(REPO, "examples", "sample-board.json")

    def run_sample(self, *extra):
        return subprocess.run(
            [sys.executable, "-B", os.path.join(MINE_DIR, "mine.py"), "--view", self.SAMPLE, *extra],
            capture_output=True, text=True, cwd=REPO,
        )

    def test_the_readme_command_prints_all_three_sections(self):
        for extra in ((), ("--today", "2026-09-16")):
            p = self.run_sample(*extra)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            for heading in ("CLOCKS", "YOUR DESK", "START TODAY"):
                self.assertIn(heading, p.stdout, f"{heading} missing with args {extra}")

    def test_the_sample_shows_what_the_readme_says_it_shows(self):
        p = self.run_sample("--today", "2026-09-16")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        out = p.stdout
        # A ranked clock with a blocker chain behind it.
        self.assertIn("waits on HX-15, HX-19", out)
        # An External item with no Lead days, listed rather than guessed.
        self.assertIn("Unranked", out)
        # Two self-serve desk items, and a pick with its arithmetic.
        desk = out.split("YOUR DESK", 1)[1].split("START TODAY", 1)[0]
        self.assertEqual(len([l for l in desk.splitlines() if l.startswith("  HX-")]), 2, desk)
        self.assertIn("slack = 42 - 42 = 0", out)
        # LC-29: a clock already running, projected from the day it started.
        self.assertIn("HX-11    lead    5-30  earliest finish 2026-09-16 .. 2026-09-25  "
                      "[In Progress, started 2026-08-26, 21 days in]", out)

    def test_the_sample_carries_no_real_notion_ids(self):
        # Public repo: every page id in the sample is a visible placeholder.
        with open(self.SAMPLE) as f:
            text = f.read()
        ids = set(re.findall(r"[0-9a-f]{32}", text))
        self.assertTrue(ids)
        for i in ids:
            self.assertTrue(i.startswith("5a3b1e0000000000"), f"{i} does not look like a placeholder id")
