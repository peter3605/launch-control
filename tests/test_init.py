"""init.py - the deterministic half of /lc:init - pinned.

/lc:init is the first thing a stranger runs, and init.py is what decides whether
the board it built is the board board.json describes. These tests drive the script
the way the skill does: as a subprocess, judged by its exit code and its FAIL lines.

FIXTURES. The fetch results here are built from board.json in the shape the Notion
fetch tool returns - a JSON object whose `text` holds the <data-source-state> and
<view> blocks - and are written to disk in BOTH forms the session hands over: inline
(the object itself) and saved-to-file (a list of content blocks wrapping it), because
unwrap_saved handles both and both have broken before. Every id is a hash of a label,
never a real Notion id: this repository is public.

The translation from board.json to Notion's shape below is written out by hand
(Status `is` -> select `enum_is`, a sort ASC -> `ascending`, ...), so a test passing
means init.py's reading of that shape agrees with an independent writing of it, not
with itself.
"""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(REPO, "plugins", "lc", "skills")
INIT = os.path.join(SKILLS, "init", "init.py")
BOARD = os.path.join(SKILLS, "init", "board.json")
SHARED = ("ready", "inProgress", "inReview", "waitingExternal", "yourTurn", "board")


def hx(label):
    """A fake 32-hex Notion id, stable per label."""
    return hashlib.md5(label.encode()).hexdigest()


def dashed(h):
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-B", *args], capture_output=True, text=True,
                          timeout=60, cwd=cwd)


def load_board():
    with open(BOARD) as f:
        return json.load(f)


# ---------------------------------------------------------------- fixtures
PROJECTS_DB, STORIES_DB = hx("projects-db"), hx("stories-db")
PROJECTS_DS, STORIES_DS = dashed(hx("projects-ds")), dashed(hx("stories-ds"))
PROJECT_PAGE = f"https://www.notion.so/{hx('project-row')}"
VIEW_IDS = {k: hx(f"view-{k}") for k in SHARED + ("road",)}


def state():
    """A finished run's ledger, as `init.py record` writes it."""
    return {
        "hub": f"https://www.notion.so/{hx('hub')}",
        "projects": {"database": f"https://www.notion.so/{PROJECTS_DB}", "dataSource": f"collection://{PROJECTS_DS}"},
        "stories": {"database": f"https://www.notion.so/{STORIES_DB}", "dataSource": f"collection://{STORIES_DS}"},
        "blockedBy": True,
        "views": {k: f"https://www.notion.so/{STORIES_DB}?v={VIEW_IDS[k]}" for k in SHARED},
        "project": PROJECT_PAGE,
        "road": f"https://www.notion.so/{STORIES_DB}?v={VIEW_IDS['road']}",
    }


def schema_of(section, ds):
    """The data source's schema as Notion reports it."""
    out = {}
    for p in section["properties"]:
        s = {"type": p["type"]}
        if p["type"] == "select":
            s["options"] = [{"name": n, "color": c} for n, c in p["options"]]
        if p["type"] == "relation":
            s["dataSourceUrl"] = f"collection://{ds[p['target']]}"
        out[p["name"]] = s
    return out


def leaf(prop, op, value, board):
    """One board.json filter as a Notion advancedFilter leaf."""
    types = {p["name"]: p["type"] for p in board["stories"]["properties"]}
    t = types[prop]
    if t == "checkbox":
        return {"type": "property", "property": prop, "propertyType": "checkbox",
                "operator": "checkbox_is", "value": {"type": "exact", "value": value}}
    if t == "relation":
        return {"type": "property", "property": prop, "propertyType": "relation",
                "operator": "relation_contains", "value": {"type": "exact", "value": value}}
    return {"type": "property", "property": prop, "propertyType": "select",
            "operator": "enum_is_not" if op == "is_not" else "enum_is",
            "value": {"type": "exact", "value": value}}


def view_config(v, board, project_url=None):
    filters = []
    for prop, op, value in v["filters"]:
        if isinstance(value, str) and "{project_url}" in value:
            value = value.format(project_url=project_url)
        filters.append(leaf(prop, op, value, board))
    cfg = {"name": v["name"], "type": v["type"],
           "advancedFilter": {"type": "group", "operator": "and", "filters": filters},
           "sorts": [{"property": p, "direction": "descending" if d == "DESC" else "ascending"}
                     for p, d in v.get("sorts") or []]}
    if v.get("groupBy"):
        cfg["groupBy"] = {"property": v["groupBy"]}
    return cfg


def fetch_text(title, db, ds_uuid, schema, views):
    parts = [f'<database url="{{{{https://www.notion.so/{db}}}}}">',
             f"The title of this Database is: {title}",
             "<data-sources>", f'<data-source url="{{{{collection://{ds_uuid}}}}}">',
             "<data-source-state>",
             json.dumps({"name": title, "url": f"collection://{ds_uuid}", "schema": schema}, indent=2),
             "</data-source-state>", "</data-source>", "</data-sources>"]
    if views:
        parts.append("<views>")
        for vid, cfg in views.items():
            parts += [f'<view url="{{{{view://{dashed(vid)}}}}}">', json.dumps(cfg, indent=2), "</view>"]
        parts.append("</views>")
    parts.append("</database>")
    return "\n".join(parts)


def view_fetch_text(vid, cfg):
    return f'<view url="{{{{view://{dashed(vid)}}}}}">\n{json.dumps(cfg, indent=2)}\n</view>'


def fetch_result(title, text):
    return {"metadata": {"type": "database"}, "title": title,
            "url": f"https://www.notion.so/{hx(title)}", "text": text}


def write_fetch(path, obj, saved):
    """Inline: the result object, verbatim. Saved: a list of content blocks wrapping it."""
    data = [{"type": "text", "text": json.dumps(obj)}] if saved else obj
    with open(path, "w") as f:
        json.dump(data, f)
    return path


class Board:
    """A fetch pair that matches board.json exactly; tests break it one thing at a time."""

    def __init__(self, with_road=True):
        self.spec = load_board()
        ds = {"projects": PROJECTS_DS, "stories": STORIES_DS}
        self.projects_schema = schema_of(self.spec["projects"], ds)
        self.stories_schema = schema_of(self.spec["stories"], ds)
        self.views = {VIEW_IDS[v["key"]]: view_config(v, self.spec) for v in self.spec["views"]}
        if with_road:
            road = dict(self.spec["road"], name="Road — test")
            self.views[VIEW_IDS["road"]] = view_config(road, self.spec, PROJECT_PAGE)

    def write(self, tmp, saved=False, st=None):
        sp = os.path.join(tmp, "state.json")
        with open(sp, "w") as f:
            json.dump(st if st is not None else state(), f)
        stories = write_fetch(os.path.join(tmp, "stories.json"), fetch_result(
            "Stories", fetch_text("Stories", STORIES_DB, STORIES_DS, self.stories_schema, self.views)), saved)
        projects = write_fetch(os.path.join(tmp, "projects.json"), fetch_result(
            "Projects", fetch_text("Projects", PROJECTS_DB, PROJECTS_DS, self.projects_schema, {})), saved)
        return sp, stories, projects

    def check(self, tmp, saved=False, extra=(), st=None):
        sp, stories, projects = self.write(tmp, saved, st)
        return run(INIT, "check", "--state", sp, "--stories", stories, "--projects", projects, *extra)


def fails(r):
    return [line.strip()[len("FAIL"):].strip() for line in r.stdout.splitlines() if line.strip().startswith("FAIL")]


# ------------------------------------------------------------------- tests
class Ddl(unittest.TestCase):
    def test_projects_ddl_names_every_property(self):
        r = run(INIT, "ddl", "projects")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("CREATE TABLE ("))
        for p in load_board()["projects"]["properties"]:
            self.assertIn(f'"{p["name"]}"', r.stdout)
        self.assertIn("'Internal Tool':gray", r.stdout)

    def test_stories_ddl_points_project_at_the_projects_data_source_and_leaves_out_blocked_by(self):
        r = run(INIT, "ddl", "stories", "--projects-ds", f"collection://{PROJECTS_DS}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"\"Project\" RELATION('{PROJECTS_DS}', DUAL 'Stories')", r.stdout)
        self.assertNotIn('"Blocked by"', r.stdout)
        self.assertIn("\"Agent can do this\" CHECKBOX", r.stdout)
        self.assertIn("'In Review':purple", r.stdout)

    def test_stories_ddl_without_the_projects_data_source_refuses(self):
        r = run(INIT, "ddl", "stories")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--projects-ds", r.stderr)

    def test_blocked_by_is_a_self_relation_added_after_create(self):
        r = run(INIT, "ddl", "blocked-by", "--stories-ds", f"collection://{STORIES_DS}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), f"ADD COLUMN \"Blocked by\" RELATION('{STORIES_DS}')")

    def test_ddl_is_generated_from_board_json(self):
        """A property added to a fixture board.json appears in the DDL: the DDL is not
        a second copy of the schema that could drift from the one `check` reads."""
        with tempfile.TemporaryDirectory() as tmp:
            for skill in ("init", "doctor"):
                os.makedirs(os.path.join(tmp, skill))
                shutil.copy(os.path.join(SKILLS, skill, f"{skill}.py"), os.path.join(tmp, skill))
            shutil.copy(os.path.join(SKILLS, "doctor", "boardcheck.py"), os.path.join(tmp, "doctor"))
            b = load_board()
            b["projects"]["properties"].append({"name": "Fixture owner", "type": "text", "description": "added by a test"})
            b["stories"]["properties"].append({"name": "Fixture risk", "type": "select", "options": [["Low", "green"], ["High", "red"]]})
            with open(os.path.join(tmp, "init", "board.json"), "w") as f:
                json.dump(b, f)
            init = os.path.join(tmp, "init", "init.py")
            r = run(init, "ddl", "projects")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("\"Fixture owner\" RICH_TEXT COMMENT 'added by a test'", r.stdout)
            r = run(init, "ddl", "stories", "--projects-ds", PROJECTS_DS)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("\"Fixture risk\" SELECT('Low':green, 'High':red)", r.stdout)


class Views(unittest.TestCase):
    def test_every_shared_view_key_is_printed_with_a_configure(self):
        r = run(INIT, "views")
        self.assertEqual(r.returncode, 0, r.stderr)
        views = json.loads(r.stdout)
        self.assertEqual(sorted(v["key"] for v in views), sorted(SHARED))
        by = {v["key"]: v for v in views}
        for v in views:
            self.assertTrue(v["name"] and v["type"] and v["configure"], v)
        self.assertEqual(by["ready"]["configure"].split("; ")[:2],
                         ['FILTER "Status" = "Ready"', 'FILTER "Agent can do this" = TRUE'])
        self.assertIn('FILTER "Status" != "Done"', by["waitingExternal"]["configure"])
        self.assertIn('GROUP BY "Status"', by["board"]["configure"])
        self.assertEqual(by["board"]["type"], "board")

    def test_a_view_with_no_filters_clears_any_it_has(self):
        """A configure line with no FILTER clause leaves an existing filter in place
        (verified on a throwaway board, LC-B14), so a view board.json gives no filter
        must say CLEAR FILTER - and only such a view, since a FILTER clause replaces."""
        by = {v["key"]: v for v in json.loads(run(INIT, "views").stdout)}
        self.assertTrue(by["board"]["configure"].startswith("CLEAR FILTER; "), by["board"]["configure"])
        for k in SHARED:
            if k != "board":
                self.assertNotIn("CLEAR FILTER", by[k]["configure"], k)

    def test_road_view_filters_on_this_project(self):
        r = run(INIT, "views", "--road", "--key", "my-app", "--project-url", PROJECT_PAGE)
        self.assertEqual(r.returncode, 0, r.stderr)
        views = json.loads(r.stdout)
        self.assertEqual(len(views), 1)
        self.assertEqual(views[0]["key"], "road")
        self.assertEqual(views[0]["name"], "Road — my-app")
        self.assertTrue(views[0]["configure"].startswith(f'FILTER "Project" = "{PROJECT_PAGE}"'),
                        views[0]["configure"])

    def test_road_view_needs_key_and_project_url(self):
        r = run(INIT, "views", "--road", "--key", "my-app")
        self.assertNotEqual(r.returncode, 0)


class Check(unittest.TestCase):
    def test_matching_board_passes_inline_and_saved(self):
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                r = Board().check(tmp, saved=saved)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(fails(r), [])
                self.assertIn("views.road", r.stdout)
                self.assertTrue(r.stdout.rstrip().endswith("Clean."))

    def test_missing_property_is_named(self):
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                b = Board()
                del b.stories_schema["Estimate"]
                r = b.check(tmp, saved=saved)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertEqual(fails(r), ["Stories: property 'Estimate' is missing"])

    def test_wrong_select_option_is_named(self):
        b = Board()
        b.stories_schema["Status"]["options"] = [o for o in b.stories_schema["Status"]["options"]
                                                 if o["name"] != "In Review"] + [{"name": "Reviewing", "color": "purple"}]
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(fails(r), ["Stories: 'Status' is missing options In Review"])

    def test_wrong_property_type_is_named(self):
        b = Board()
        b.projects_schema["Kind"] = {"type": "text"}
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(fails(r), ["Projects: 'Kind' is 'text', not 'select'"])

    def test_relation_to_the_wrong_data_source_is_named(self):
        b = Board()
        b.stories_schema["Blocked by"]["dataSourceUrl"] = f"collection://{dashed(hx('elsewhere'))}"
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(len(fails(r)), 1)
        self.assertIn("'Blocked by' relates to", fails(r)[0])

    def test_view_with_a_wrong_filter_is_named(self):
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                b = Board()
                b.views[VIEW_IDS["ready"]]["advancedFilter"]["filters"][0]["value"]["value"] = "Backlog"
                r = b.check(tmp, saved=saved)
                self.assertEqual(r.returncode, 1, r.stdout)
                f = fails(r)
                self.assertEqual(len(f), 1, f)
                self.assertTrue(f[0].startswith("views.ready ('Ready for Claude Code'): filter is"), f[0])

    def test_board_view_filtered_on_type_is_named_with_a_fix_that_clears_it(self):
        """LC-B14: the live board's shared `board` view filtered on Type, though
        board.json gives it none. The fix must remove that filter, not reprint a line
        that leaves it in place."""
        b = Board()
        b.views[VIEW_IDS["board"]]["advancedFilter"]["filters"].append(
            leaf("Type", "is", "Launch Blocker", b.spec))
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertTrue(f[0].startswith("views.board ('Board'): filter is"), f[0])
        self.assertIn('fix: configure it as `CLEAR FILTER; GROUP BY "Status"', f[0])
        self.assertIn("clear any it has", f[0])
        self.assertIn("a line with no FILTER clause leaves an existing filter in place", f[0])

    def test_view_with_a_dropped_filter_is_named(self):
        """A missing leaf is as wrong as a changed one: yourTurn without its Done filter
        shows finished work as yours."""
        b = Board()
        b.views[VIEW_IDS["yourTurn"]]["advancedFilter"]["filters"].pop()
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(len(fails(r)), 1)
        self.assertTrue(fails(r)[0].startswith("views.yourTurn"))

    def test_checkbox_filter_inverted_is_named(self):
        b = Board()
        b.views[VIEW_IDS["ready"]]["advancedFilter"]["filters"][1]["value"]["value"] = False
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(fails(r)[0].startswith("views.ready"))

    def test_road_filtered_to_another_project_is_named(self):
        b = Board()
        b.views[VIEW_IDS["road"]]["advancedFilter"]["filters"][0]["value"]["value"] = \
            f"https://www.notion.so/{hx('another-project')}"
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(len(fails(r)), 1)
        self.assertTrue(fails(r)[0].startswith("views.road"))

    def test_wrong_sort_and_missing_grouping_are_named(self):
        b = Board()
        b.views[VIEW_IDS["inProgress"]]["sorts"] = []
        del b.views[VIEW_IDS["board"]]["groupBy"]
        with tempfile.TemporaryDirectory() as tmp:
            r = b.check(tmp)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 2, f)
        self.assertTrue(any(x.startswith("views.inProgress") and "sort is []" in x for x in f), f)
        self.assertTrue(any(x.startswith("views.board") and "not grouped by 'Status'" in x for x in f), f)

    def test_a_view_fetch_overrides_the_database_fetch(self):
        """Step 10's repair loop: the database fetch is stale, a fresh fetch of the one
        fixed view is passed with --view, and the check goes clean."""
        for saved in (False, True):
            with self.subTest(saved=saved), tempfile.TemporaryDirectory() as tmp:
                b = Board()
                good = copy.deepcopy(b.views[VIEW_IDS["ready"]])
                b.views[VIEW_IDS["ready"]]["advancedFilter"]["filters"] = []
                self.assertEqual(b.check(tmp, saved=saved).returncode, 1)
                vf = write_fetch(os.path.join(tmp, "ready.json"),
                                 {"metadata": {"type": "view"}, "text": view_fetch_text(VIEW_IDS["ready"], good)}, saved)
                r = b.check(tmp, saved=saved, extra=("--view", vf))
                self.assertEqual(r.returncode, 0, r.stdout)

    def test_road_created_after_the_database_fetch_needs_a_view_fetch(self):
        """Step 13: a database fetch from before the road existed does not list it."""
        with tempfile.TemporaryDirectory() as tmp:
            full = Board()
            b = Board(with_road=False)
            r = b.check(tmp)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertTrue(any(f.startswith("views.road") and "is not a view" in f for f in fails(r)), fails(r))
            vf = write_fetch(os.path.join(tmp, "road.json"), {"text": view_fetch_text(
                VIEW_IDS["road"], full.views[VIEW_IDS["road"]])}, saved=True)
            self.assertEqual(b.check(tmp, extra=("--view", vf)).returncode, 0)

    def test_fetch_of_the_wrong_data_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = state()
            st["projects"]["dataSource"] = f"collection://{dashed(hx('some-other-board'))}"
            r = Board().check(tmp, st=st)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertTrue(any(f.startswith("projects:") and "this run created" in f for f in fails(r)), fails(r))

    def test_unrecorded_blocked_by_and_view_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = state()
            del st["blockedBy"]
            del st["views"]["inReview"]
            r = Board().check(tmp, st=st)
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertTrue(any("Blocked by was never recorded" in x for x in f), f)
        self.assertIn("views.inReview was never created", f)

    def test_a_file_that_is_not_a_database_fetch_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = Board()
            sp, stories, projects = b.write(tmp)
            with open(stories, "w") as f:
                json.dump({"text": "<page>nothing here</page>"}, f)
            r = run(INIT, "check", "--state", sp, "--stories", stories, "--projects", projects)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(any("no <data-source-state>" in x for x in fails(r)), fails(r))


class Preflight(unittest.TestCase):
    def _tree(self, tmp, sibling=True):
        repo = os.path.join(tmp, "new-app")
        os.makedirs(repo)
        if sibling:
            os.makedirs(os.path.join(tmp, "old-app", ".claude"))
            with open(os.path.join(tmp, "old-app", ".claude", "launch-control.json"), "w") as f:
                json.dump({"prefix": "OLD", "stories": {"database": f"https://www.notion.so/{STORIES_DB}",
                                                        "dataSource": f"collection://{STORIES_DS}"}}, f)
        return repo

    def test_refuses_when_a_sibling_repo_holds_a_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run(INIT, "preflight", "--repo", self._tree(tmp))
        self.assertEqual(r.returncode, 1, r.stdout)
        f = fails(r)
        self.assertEqual(len(f), 1, f)
        self.assertIn("a board already exists", f[0])
        self.assertIn("old-app", f[0])
        self.assertIn("--new-board", f[0])

    def test_new_board_overrides_the_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run(INIT, "preflight", "--repo", self._tree(tmp), "--new-board")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("creating a separate one as asked", r.stdout)

    def test_no_sibling_board_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = run(INIT, "preflight", "--repo", self._tree(tmp, sibling=False))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("no sibling repo is on a board", r.stdout)

    def test_a_repo_already_on_a_board_is_refused_even_with_new_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._tree(tmp, sibling=False)
            os.makedirs(os.path.join(repo, ".claude"))
            with open(os.path.join(repo, ".claude", "launch-control.json"), "w") as f:
                json.dump({"stories": {"database": "x"}}, f)
            r = run(INIT, "preflight", "--repo", repo, "--new-board")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("already on a board", fails(r)[0])

    def test_a_half_finished_run_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._tree(tmp)
            os.makedirs(os.path.join(repo, ".claude", "lc-init"))
            with open(os.path.join(repo, ".claude", "lc-init", "state.json"), "w") as f:
                json.dump({"hub": "x"}, f)
            r = run(INIT, "preflight", "--repo", repo)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("resume from", r.stdout)


class RecordAndBoard(unittest.TestCase):
    def test_record_normalises_urls_and_ignores_its_own_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            sp = os.path.join(tmp, "lc-init", "state.json")
            r = run(INIT, "record", "--state", sp, "--key", "views.ready",
                    "--url", f"view://{dashed(VIEW_IDS['ready'])}")
            self.assertNotEqual(r.returncode, 0, "a view before the stories database must be refused")
            self.assertEqual(run(INIT, "record", "--state", sp, "--key", "stories",
                                 "--url", f"https://www.notion.so/ws/Stories-{STORIES_DB}?pvs=4",
                                 "--data-source", f"collection://{STORIES_DS}").returncode, 0)
            self.assertEqual(run(INIT, "record", "--state", sp, "--key", "views.ready",
                                 "--url", f"view://{dashed(VIEW_IDS['ready'])}").returncode, 0)
            with open(sp) as f:
                st = json.load(f)
            with open(os.path.join(tmp, "lc-init", ".gitignore")) as f:
                self.assertEqual(f.read(), "*\n")
        self.assertEqual(st["stories"], {"database": f"https://www.notion.so/{STORIES_DB}",
                                         "dataSource": f"collection://{STORIES_DS}"})
        self.assertEqual(st["views"]["ready"], f"https://www.notion.so/{STORIES_DB}?v={VIEW_IDS['ready']}")

    def test_board_file_needs_every_shared_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            sp, out = os.path.join(tmp, "state.json"), os.path.join(tmp, "board.json")
            st = state()
            with open(sp, "w") as f:
                json.dump(st, f)
            r = run(INIT, "board", "--state", sp, "--out", out)
            self.assertEqual(r.returncode, 0, r.stdout)
            with open(out) as f:
                b = json.load(f)
            self.assertEqual(sorted(b["views"]), sorted(SHARED))
            self.assertIn("viewContract", b)
            del st["views"]["board"]
            with open(sp, "w") as f:
                json.dump(st, f)
            r = run(INIT, "board", "--state", sp, "--out", os.path.join(tmp, "b2.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("views.board", fails(r)[0])


if __name__ == "__main__":
    unittest.main()
