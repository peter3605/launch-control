"""doctor.py's check of an existing board against board.json - pinned.

When board.json changes, boards already provisioned do not. LC-B12 made /lc:doctor
compare the board this repo is on - every Stories and Projects property, every view
in the config - with board.json, using the comparison `init.py check` uses.

The fixture boards are test_init's: built from board.json in the shape the Notion
fetch tool returns, written inline and saved-to-file, every id a hash of a label.
Reusing them means doctor and init are held to one independent writing of that
shape, not two that could disagree.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from tests.test_init import (Board, PROJECT_PAGE, PROJECTS_DS, STORIES_DB,
                             VIEW_IDS, fails, hx, leaf, state)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCTOR = os.path.join(REPO, "plugins", "lc", "skills", "doctor", "doctor.py")


def config():
    st = state()
    return {
        "project": "my-app",
        "prefix": "APP",
        "projectPageId": hx("project-row"),
        "stories": st["stories"],
        "projects": st["projects"],
        "views": dict(st["views"], road=st["road"], next=st["next"], open=st["open"]),
        "git": {"enabled": False},
    }


def views_file(tmp, nxt=None, override=None):
    """Every view resolves; the road holds this project's stories alone."""
    results = {k: {"resolved": True} for k in VIEW_IDS}
    results["road"] = {"count": 2, "rows": [["APP-1", "Ready"], ["APP-2", "Done"]], "hasMore": False}
    nxt = nxt if nxt is not None else [["APP-1", "Ready"]]
    results["next"] = {"count": len(nxt), "rows": nxt, "hasMore": False}
    results["open"] = {"count": 1, "rows": [["APP-1", "Ready"]], "hasMore": False}
    results.update(override or {})
    path = os.path.join(tmp, "views.json")
    with open(path, "w") as f:
        json.dump(results, f)
    return path


def doctor(board, tmp, saved=False, cfg=None, schema=True, nxt=None, override=None, blocks=False):
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, ".claude"), exist_ok=True)
    with open(os.path.join(repo, ".claude", "launch-control.json"), "w") as f:
        json.dump(cfg if cfg is not None else config(), f)
    _, stories, projects = board.write(tmp, saved)
    if blocks:
        stories, projects = blocks_only(stories, tmp, "stories"), blocks_only(projects, tmp, "projects")
    extra = ("--stories", stories, "--projects", projects) if schema else ()
    return subprocess.run([sys.executable, "-B", DOCTOR, "--repo", repo, "--views", views_file(tmp, nxt, override), *extra],
                          capture_output=True, text=True, timeout=60)


def blocks_only(fetch_path, tmp, name, cut=None):
    """What /lc:doctor writes for a fetch that came back inline: its <data-source-state>
    and <view> blocks as text, and nothing else (LC-B15). `cut` truncates the text."""
    with open(fetch_path) as f:
        text = json.load(f)["text"]
    parts = re.findall(r"<data-source-state>.*?</data-source-state>|<view url=.*?</view>", text, re.S)
    out = "\n".join(parts)
    if cut is not None:
        out = out[:cut]
    path = os.path.join(tmp, f"{name}-blocks.txt")
    with open(path, "w") as f:
        f.write(out)
    return path


class InlineInput(unittest.TestCase):
    """LC-B15: nothing inline is re-typed whole. Each short form is checked loudly."""

    def test_blocks_only_fetches_pass_like_the_whole_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = doctor(Board(), tmp, blocks=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("views.next ('Next — test'): filter, sort as specified", r.stdout)

    def test_truncated_blocks_fail_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, stories, _ = Board().write(tmp)
            with open(blocks_only(stories, tmp, "s")) as f:
                whole = f.read()
            for cut, needle in ((len(whole) - 20, "opened but"), (200, "<data-source-state>")):
                with self.subTest(cut=cut):
                    path = blocks_only(stories, tmp, "s", cut=cut)
                    proj = blocks_only(Board().write(tmp)[2], tmp, "p")
                    repo = os.path.join(tmp, "repo")
                    os.makedirs(os.path.join(repo, ".claude"), exist_ok=True)
                    with open(os.path.join(repo, ".claude", "launch-control.json"), "w") as f:
                        json.dump(config(), f)
                    r = subprocess.run([sys.executable, "-B", DOCTOR, "--repo", repo, "--views", views_file(tmp),
                                        "--stories", path, "--projects", proj], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 1, r.stdout)
                    self.assertTrue(any(x.startswith("stories: could not read the fetch result") and needle in x
                                        for x in fails(r)), fails(r))

    def test_inline_road_without_a_count_or_with_the_wrong_one_fails(self):
        cases = (({"rows": [["APP-1", "Ready"]], "hasMore": False}, "needs `count`"),
                 ({"count": 3, "rows": [["APP-1", "Ready"], ["APP-2", "Done"]], "hasMore": False}, "count 3 but gives 2"),
                 ({"count": 1, "rows": [["APP-1", "Ready"]]}, "needs `hasMore`"))
        for page, needle in cases:
            with self.subTest(needle=needle), tempfile.TemporaryDirectory() as tmp:
                r = doctor(Board(), tmp, override={"road": page})
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(any(x.startswith("views.road did not resolve") and needle in x for x in fails(r)), fails(r))

    def test_resolved_cannot_stand_in_for_road_or_next(self):
        for k in ("road", "next", "open"):
            with self.subTest(k=k), tempfile.TemporaryDirectory() as tmp:
                r = doctor(Board(), tmp, override={k: {"resolved": True}})
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(any(x.startswith(f"views.{k} was given as") for x in fails(r)), fails(r))


class BoardSchema(unittest.TestCase):
    def test_matching_board_passes_inline_and_saved(self):
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                r = doctor(Board(), tmp, saved=saved)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(fails(r), [])
                self.assertIn("Board schema against board.json", r.stdout)
                self.assertIn("views.yourTurn ('Your turn'): filter, sort as specified", r.stdout)
                self.assertIn("views.road", r.stdout)
                self.assertIn("Stories: Estimate (select)", r.stdout)
                self.assertTrue(r.stdout.rstrip().endswith("Clean."))

    def test_your_turn_still_filtering_on_type_is_named_with_its_fix(self):
        """The board LC-11 changed: built before yourTurn dropped its Type filter, it
        hides human work typed anything but Launch Blocker from /lc:mine."""
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                b = Board()
                b.views[VIEW_IDS["yourTurn"]]["advancedFilter"]["filters"].append(
                    leaf("Type", "is", "Launch Blocker", b.spec))
                r = doctor(b, tmp, saved=saved)
                self.assertEqual(r.returncode, 1, r.stdout)
                f = fails(r)
                self.assertEqual(len(f), 1, f)
                self.assertTrue(f[0].startswith("views.yourTurn ('Your turn'): filter is"), f[0])
                self.assertIn("('Type', 'is', 'Launch Blocker')", f[0])
                self.assertIn('configure it as `FILTER "Agent can do this" = FALSE; FILTER "Status" != "Done"', f[0])
                self.assertIn("init.py views` prints every view's configure line", f[0])

    def test_board_view_filtered_on_type_is_named_with_a_fix_that_clears_it(self):
        """LC-B14, found on the live board: `board` filtered on Type silently drops
        Backlog and Chore rows from /lc:done's dependents and /lc:plan's prefix check.
        board.json gives it no filter, so the fix must clear one, not omit it."""
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                b = Board()
                b.views[VIEW_IDS["board"]]["advancedFilter"]["filters"].append(
                    leaf("Type", "is", "Launch Blocker", b.spec))
                r = doctor(b, tmp, saved=saved)
                self.assertEqual(r.returncode, 1, r.stdout)
                f = fails(r)
                self.assertEqual(len(f), 1, f)
                self.assertTrue(f[0].startswith("views.board ('Board'): filter is"), f[0])
                self.assertIn('fix: configure it as `CLEAR FILTER; GROUP BY "Status"', f[0])
                self.assertIn("clear any it has", f[0])
                self.assertIn("a line with no FILTER clause leaves an existing filter in place", f[0])

    def test_a_filtered_view_fix_has_no_clear(self):
        """A FILTER clause replaces the old filter, so a filtered view's fix needs no
        CLEAR and must not claim the view should have none."""
        with tempfile.TemporaryDirectory() as tmp:
            b = Board()
            b.views[VIEW_IDS["ready"]]["advancedFilter"]["filters"].pop()
            r = doctor(b, tmp)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertNotIn("CLEAR FILTER", f[0])
        self.assertNotIn("clear any it has", f[0])

    def test_missing_property_is_named_with_its_fix(self):
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                b = Board()
                del b.stories_schema["Estimate"]
                r = doctor(b, tmp, saved=saved)
                self.assertEqual(r.returncode, 1, r.stdout)
                f = fails(r)
                self.assertEqual(len(f), 1, f)
                self.assertTrue(f[0].startswith("Stories: property 'Estimate' is missing - "), f[0])
                self.assertIn(f"init.py ddl stories --projects-ds collection://{PROJECTS_DS}", f[0])

    def test_a_board_without_started_is_told_the_exact_column_to_add(self):
        """LC-29 added Started to board.json. A board provisioned before it fails
        with the one statement that brings it up to date, not just a pointer."""
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                b = Board()
                del b.stories_schema["Started"]
                r = doctor(b, tmp, saved=saved)
                self.assertEqual(r.returncode, 1, r.stdout)
                f = fails(r)
                self.assertEqual(len(f), 1, f)
                self.assertTrue(f[0].startswith("Stories: property 'Started' is missing - "), f[0])
                self.assertIn("update-data-source on stories.dataSource with "
                              "`ADD COLUMN \"Started\" DATE COMMENT 'the day an External clock was started", f[0])

    def test_lost_projects_select_option_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Board()
            b.projects_schema["Kind"]["options"] = b.projects_schema["Kind"]["options"][:-1]
            r = doctor(b, tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("Projects: 'Kind' is missing options Library"), f[0])
        self.assertIn("init.py ddl projects", f[0])

    def test_road_filtered_to_another_project_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Board()
            b.views[VIEW_IDS["road"]]["advancedFilter"]["filters"][0]["value"]["value"] = \
                f"https://www.notion.so/{hx('another-project')}"
            r = doctor(b, tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("views.road"), f[0])
        self.assertIn(f"--project-url https://www.notion.so/{hx('project-row')}", f[0])

    def test_wrong_sort_is_named(self):
        """/lc:next picks the first Ready row, so a view out of Seq order picks wrong."""
        with tempfile.TemporaryDirectory() as tmp:
            b = Board()
            b.views[VIEW_IDS["ready"]]["sorts"] = []
            r = doctor(b, tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("views.ready") and "sort is []" in f[0], f[0])

    def test_road_without_project_page_id_is_skipped_not_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config()
            del cfg["projectPageId"]
            r = doctor(Board(), tmp, cfg=cfg)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("skip  views.road filter - no projectPageId", r.stdout)

    def test_fetch_of_another_board_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config()
            cfg["stories"] = {"database": f"https://www.notion.so/{STORIES_DB}",
                              "dataSource": f"collection://{hx('other-board-ds')}"}
            r = doctor(Board(), tmp, cfg=cfg)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any(x.startswith("stories:") and "stories.dataSource is" in x for x in fails(r)), fails(r))

    def test_a_full_run_without_the_database_fetches_fails(self):
        """A check that did not run is not a pass."""
        with tempfile.TemporaryDirectory() as tmp:
            r = doctor(Board(), tmp, schema=False)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(fails(r), ["board schema was not checked - pass --stories and --projects "
                                    "(a check that did not run is not a pass)"])

    def test_local_only_skips_the_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            os.makedirs(os.path.join(repo, ".claude"))
            with open(os.path.join(repo, ".claude", "launch-control.json"), "w") as f:
                json.dump(config(), f)
            r = subprocess.run([sys.executable, "-B", DOCTOR, "--repo", repo, "--local-only"],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skip  properties and view filters", r.stdout)

    def test_next_filtered_to_another_project_is_named(self):
        """LC-28: next is what /lc:next reads. Scoped to the wrong project, it hands out
        another repo's work - or, scoped to none, every project's, the overflow LC-28 fixed."""
        with tempfile.TemporaryDirectory() as tmp:
            b = Board()
            b.views[VIEW_IDS["next"]]["advancedFilter"]["filters"].pop(0)
            r = doctor(b, tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("views.next ('Next — test'): filter is"), f[0])
        self.assertIn(f'configure it as `FILTER "Project" = "{PROJECT_PAGE}"; FILTER "Status" = "Ready"', f[0])
        self.assertIn("views --next --key my-app", f[0])

    def test_config_without_next_fails_with_the_migration(self):
        """A board provisioned before 0.10.0 has no next view. That is a FAIL that says
        exactly what to create, not a silent pass on the shared ready view."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config()
            del cfg["views"]["next"]
            r = doctor(Board(with_next=False), tmp, cfg=cfg)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("views.next is missing - a board provisioned before 0.10.0"), f[0])
        self.assertIn("named 'Next — my-app'", f[0])
        self.assertIn(f'`FILTER "Project" = "{PROJECT_PAGE}"; FILTER "Status" = "Ready"; '
                      'FILTER "Agent can do this" = TRUE; SORT BY "Seq" ASC', f[0])
        self.assertIn("add its URL to views.next", f[0])
        self.assertNotIn("all eight view keys present", r.stdout)

    def test_next_rows_from_another_project_or_not_ready_fail(self):
        for rows, needle in (([["APP-1", "Ready"], ["OTH-3", "Ready"]], "outside APP-: OTH-3"),
                             ([["APP-1", "Backlog"]], "not Ready: APP-1")):
            with self.subTest(needle=needle), tempfile.TemporaryDirectory() as tmp:
                r = doctor(Board(), tmp, nxt=rows)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(any(needle in x and x.startswith("views.next returned") for x in fails(r)), fails(r))

    def test_config_without_open_fails_with_the_migration(self):
        """LC-30: a board provisioned before 0.14.0 has no open view, and /lc:start falls
        back to the whole road. A FAIL naming the view to create, not a silent pass."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config()
            del cfg["views"]["open"]
            r = doctor(Board(with_open=False), tmp, cfg=cfg)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("views.open is missing - a board provisioned before 0.14.0"), f[0])
        self.assertIn("named 'Open — my-app'", f[0])
        self.assertIn(f'`FILTER "Project" = "{PROJECT_PAGE}"; FILTER "Status" != "Done"; SORT BY "Seq" ASC', f[0])
        self.assertIn("add its URL to views.open", f[0])
        self.assertIn("views --open --key my-app", f[0])

    def test_config_without_dependents_fails_with_the_migration(self):
        """The shared view is one per board, so the line says to add it to every config."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config()
            del cfg["views"]["dependents"]
            r = doctor(Board(), tmp, cfg=cfg)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("views.dependents is missing - a board provisioned before 0.14.0"), f[0])
        self.assertIn("named 'Waiting on a blocker'", f[0])
        self.assertIn('`FILTER "Status" != "Done"; FILTER "Blocked by" IS NOT EMPTY; SORT BY "Seq" ASC', f[0])
        self.assertIn("in every repo config on this board", f[0])

    def test_open_rows_from_another_project_or_done_fail(self):
        for rows, needle in (([["APP-1", "Ready"], ["OTH-3", "Ready"]], "outside APP-: OTH-3"),
                             ([["APP-1", "Ready"], ["APP-2", "Done"]], "Done stories: APP-2")):
            with self.subTest(needle=needle), tempfile.TemporaryDirectory() as tmp:
                r = doctor(Board(), tmp, override={"open": {"count": len(rows), "rows": rows, "hasMore": False}})
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(any(needle in x and x.startswith("views.open returned") for x in fails(r)), fails(r))

    def test_an_empty_open_view_passes(self):
        """Every story Done is a finished project, not a scoping bug - the road catches those."""
        with tempfile.TemporaryDirectory() as tmp:
            r = doctor(Board(), tmp, override={"open": {"count": 0, "rows": [], "hasMore": False}})
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("views.open resolves (0 rows, all APP- and not Done)", r.stdout)

    def test_an_empty_next_is_not_a_failure(self):
        """Unlike the road, nothing Ready is an ordinary state, not a scoping bug."""
        with tempfile.TemporaryDirectory() as tmp:
            r = doctor(Board(), tmp, nxt=[])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("views.next resolves (0 rows, all APP- and Ready)", r.stdout)

    def test_fixture_road_filters_on_the_configured_project(self):
        """Guard on the fixture itself: the road view test_init builds filters on the
        page config()'s projectPageId names, or the road tests above prove nothing."""
        self.assertEqual(PROJECT_PAGE, f"https://www.notion.so/{config()['projectPageId']}")


if __name__ == "__main__":
    unittest.main()
