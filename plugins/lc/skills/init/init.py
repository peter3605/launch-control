#!/usr/bin/env python3
"""Launch Control - the deterministic half of /lc:init.

    init.py preflight --repo DIR [--new-board]         may this repo get a new board?
    init.py ddl projects                               CREATE TABLE for Projects
    init.py ddl stories --projects-ds DS               CREATE TABLE for Stories
    init.py ddl blocked-by --stories-ds DS             the self-relation, added after create
    init.py views                                      the six shared views, as JSON
    init.py views --road --key KEY --project-url URL   this project's road view, as JSON
    init.py record --state STATE --key KEY --url URL [--data-source DS]
    init.py check --state STATE --stories FILE --projects FILE [--view FILE ...]
    init.py board --state STATE --out FILE             a board file for plan.py config --from

Every subcommand exits 1 on a failure and 0 otherwise, so the verdict is the
script's and not the session's. Like doctor.py it cannot reach Notion: the skill
makes the calls, records what they created, and hands fetch results back.

board.json is the board. The DDL and view configs are generated from it, and
`check` reads the board back and compares it with the same file, so what is
created and what is verified cannot drift apart.

STATE is this run's ledger ({"hub", "projects", "stories", "blockedBy", "views":
{key: url}, "project", "road"}). It is what makes a failed run resumable instead of
a second board, and it lives in .claude/lc-init/, which ignores itself: it holds
Notion IDs, and in a public repo those stay out of history.

FILE for `check` is a Notion fetch result for the database - saved to disk by the
tool when large, or written verbatim from an inline result. The data-source schema
and every view's configuration are parsed out of it. A --view FILE is a fetch of one
view, and overrides that view's entry - so a view fixed or added after the database
fetch can be re-checked without fetching the whole database again.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # importing doctor must not litter the installed plugin
sys.path.insert(0, os.path.join(HERE, "..", "doctor"))
from doctor import load_json, unwrap_saved, git  # noqa: E402

SHARED_VIEWS = ("ready", "inProgress", "inReview", "waitingExternal", "yourTurn", "board")
DDL_TYPES = {"title": "TITLE", "text": "RICH_TEXT", "number": "NUMBER", "checkbox": "CHECKBOX"}
# Standing notes every config carries, so a session reading only the config knows
# the traps. The same wording the example config ships with.
NOTES = {
    "note": "Prefer querying data sources in VIEW mode - it is unmetered on the free Notion plan. SQL mode is billed.",
    "dependencies": "'Blocked by' is a RELATION (pass page URLs, not story IDs). Resolve blockers by fetching the linked pages. Status=Ready already means unblocked.",
    "viewContract": "Every project has its own 'road' view, filtered to that project and nothing else. Commands MUST scope by views.road - never by a shared browse view, whose filters anyone can change in the Notion UI.",
}

problems = []


def ok(msg):
    print(f"  ok    {msg}")


def fail(msg):
    problems.append(msg)
    print(f"  FAIL  {msg}")


def warn(msg):
    print(f"  warn  {msg}")


def finish(clean_msg="Clean."):
    print()
    if problems:
        print(f"{len(problems)} problem(s).")
        return 1
    print(clean_msg)
    return 0


def spec():
    return load_json(os.path.join(HERE, "board.json"))


def hex_id(s):
    """The last 32-hex id in a URL or UUID, dashes stripped."""
    m = re.findall(r"[0-9a-f]{32}", (s or "").split("?", 1)[0].replace("-", "").lower())
    return m[-1] if m else ""


def view_id(s):
    m = re.search(r"[?&]v=([0-9a-f-]{32,36})", s or "") or re.search(r"view://([0-9a-f-]{32,36})", s or "")
    return m.group(1).replace("-", "") if m else hex_id(s)


def ds_uuid(s):
    h = hex_id(s)
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}" if h else ""


def sql(s):
    return "'" + str(s).replace("'", "''") + "'"


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# --------------------------------------------------------------- preflight
def cmd_preflight(args):
    repo = os.path.abspath(args.repo)
    print(f"Launch Control init preflight -> {repo}")
    cfg = os.path.join(repo, ".claude", "launch-control.json")
    state = os.path.join(repo, ".claude", "lc-init", "state.json")
    # The config is the last thing a run writes, so it wins over a leftover ledger:
    # a run that got that far has nothing left to create.
    if os.path.exists(cfg):
        board = (load_json(cfg).get("stories") or {}).get("database", "")
        fail(f"{cfg} exists - this repo is already on a board ({board or 'unknown'}). Nothing to provision"
             + (f"; {os.path.dirname(state)} is a finished run's ledger and can be deleted" if os.path.exists(state) else ""))
        return finish()
    if os.path.exists(state):
        ok(f"an earlier run stopped part way - resume from {state}")
        return finish()
    ok("no config here yet")

    boards = {}
    for path in sorted(glob.glob(os.path.join(repo, "..", "*", ".claude", "launch-control.json"))):
        try:
            ds = (load_json(path).get("stories") or {}).get("dataSource")
        except ValueError:
            continue
        if ds:
            boards.setdefault(ds, os.path.normpath(path))
    if boards and not args.new_board:
        for path in boards.values():
            fail(f"a board already exists ({path}) - add this repo to it with "
                 f"/lc:plan <doc or repo> --board {path}, or pass --new-board to create a separate one")
    elif boards:
        warn(f"{len(boards)} existing board(s) nearby; creating a separate one as asked")
    else:
        ok("no sibling repo is on a board")

    if not git(repo, "rev-parse", "--git-dir"):
        warn("not a git repository - the config will set git.enabled false")
    return finish()


# --------------------------------------------------------------------- ddl
def column(p, ds):
    t = p["type"]
    if t in DDL_TYPES:
        out = DDL_TYPES[t]
    elif t == "select":
        out = "SELECT(" + ", ".join(f"{sql(n)}:{c}" for n, c in p["options"]) + ")"
    elif t == "relation":
        out = f"RELATION({sql(ds[p['target']])}" + (f", DUAL {sql(p['dual'])}" if p.get("dual") else "") + ")"
    else:
        raise SystemExit(f"board.json: unsupported type {t!r} on {p['name']!r}")
    if p.get("description"):
        out += f" COMMENT {sql(p['description'])}"
    return f'"{p["name"]}" {out}'


def cmd_ddl(args):
    s = spec()
    if args.what == "projects":
        cols = [column(p, {}) for p in s["projects"]["properties"]]
    elif args.what == "stories":
        if not args.projects_ds:
            raise SystemExit("ddl stories needs --projects-ds")
        # Blocked by is a self-relation, which needs the Stories data source id,
        # which does not exist until this CREATE has run.
        ds = {"projects": ds_uuid(args.projects_ds)}
        cols = [column(p, ds) for p in s["stories"]["properties"] if p.get("target") != "stories"]
    else:
        if not args.stories_ds:
            raise SystemExit("ddl blocked-by needs --stories-ds")
        ds = {"stories": ds_uuid(args.stories_ds)}
        print("; ".join(f"ADD COLUMN {column(p, ds)}" for p in s["stories"]["properties"] if p.get("target") == "stories"))
        return 0
    print("CREATE TABLE (" + ", ".join(cols) + ")")
    return 0


# ------------------------------------------------------------------- views
def dsl_value(v):
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return f'"{v}"'


def configure(v):
    parts = []
    for prop, op, value in v["filters"]:
        # For a relation, = means contains in the view DSL.
        parts.append(f'FILTER "{prop}" {"!=" if op == "is_not" else "="} {dsl_value(value)}')
    if v.get("groupBy"):
        parts.append(f'GROUP BY "{v["groupBy"]}"')
    if v.get("sorts"):
        parts.append("SORT BY " + ", ".join(f'"{p}" {d}' for p, d in v["sorts"]))
    if v.get("show"):
        parts.append("SHOW " + ", ".join(f'"{p}"' for p in v["show"]))
    return "; ".join(parts)


def road_spec(key, project_url):
    r = json.loads(json.dumps(spec()["road"]))
    r["name"] = r["name"].format(key=key)
    r["filters"] = [[p, o, v.format(project_url=project_url) if isinstance(v, str) else v] for p, o, v in r["filters"]]
    return r


def cmd_views(args):
    if args.road:
        if not (args.key and args.project_url):
            raise SystemExit("views --road needs --key and --project-url")
        views = [road_spec(args.key, args.project_url)]
    else:
        views = spec()["views"]
    print(json.dumps([{"key": v["key"], "name": v["name"], "type": v["type"], "configure": configure(v)}
                      for v in views], indent=2, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ record
def cmd_record(args):
    path = args.state
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    ignore = os.path.join(os.path.dirname(os.path.abspath(path)), ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w") as f:
            f.write("*\n")
    state = load_json(path) if os.path.exists(path) else {}

    key = args.key
    if key in ("projects", "stories"):
        if not args.data_source:
            raise SystemExit(f"record {key} needs --data-source")
        value = {"database": f"https://www.notion.so/{hex_id(args.url)}", "dataSource": f"collection://{ds_uuid(args.data_source)}"}
    elif key.startswith("views.") or key == "road":
        db = hex_id((state.get("stories") or {}).get("database"))
        if not db:
            raise SystemExit("record the stories database before any view")
        vid = view_id(args.url)
        if not vid:
            raise SystemExit(f"no view id in {args.url!r}")
        value = f"https://www.notion.so/{db}?v={vid}"
    elif key in ("hub", "project"):
        value = f"https://www.notion.so/{hex_id(args.url)}"
    elif key == "blockedBy":
        value = True
    else:
        raise SystemExit(f"unknown key {key!r}")

    if key.startswith("views."):
        state.setdefault("views", {})[key.split(".", 1)[1]] = value
    else:
        state[key] = value
    save_json(path, state)
    print(f"recorded {key} = {value}")
    return 0


# ------------------------------------------------------------------- check
def fetch_text(path):
    raw = open(path).read()
    try:
        data = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(data, list):
        data = unwrap_saved(data)
        try:
            data = json.loads(data)
        except ValueError:
            return data
    if isinstance(data, dict):
        return data.get("text", "")
    return str(data)


def parse_views(text):
    return {vid.replace("-", ""): json.loads(body)
            for vid, body in re.findall(r'<view url="\{\{view://([0-9a-f-]+)\}\}">\s*(.*?)\s*</view>', text, re.S)}


def parse_database(path):
    """(data source state, {view id: view config}) from a database fetch result."""
    text = fetch_text(path)
    m = re.search(r"<data-source-state>\s*(.*?)\s*</data-source-state>", text, re.S)
    if not m:
        raise ValueError(f"{path}: no <data-source-state> - is this a fetch of the database?")
    return json.loads(m.group(1)), parse_views(text)


def check_properties(label, want, have, ds_urls):
    schema = have.get("schema") or {}
    for p in want["properties"]:
        got = schema.get(p["name"])
        if not got:
            fail(f"{label}: property {p['name']!r} is missing")
            continue
        if got.get("type") != p["type"]:
            fail(f"{label}: {p['name']!r} is {got.get('type')!r}, not {p['type']!r}")
            continue
        if p["type"] == "select":
            names = {o.get("name") for o in got.get("options") or []}
            lost = [n for n, _ in p["options"] if n not in names]
            if lost:
                fail(f"{label}: {p['name']!r} is missing options {', '.join(lost)}")
                continue
        if p["type"] == "relation":
            target = ds_uuid(ds_urls.get(p["target"]))
            if ds_uuid(got.get("dataSourceUrl")) != target:
                fail(f"{label}: {p['name']!r} relates to {got.get('dataSourceUrl')!r}, not {p['target']}")
                continue
        ok(f"{label}: {p['name']} ({p['type']})")


def flatten(node):
    """The AND-ed leaf filters of a view's filter tree. An OR is not something any
    Launch Control view uses, so it is reported rather than approximated."""
    if node.get("type") == "group":
        if node.get("operator") == "or" and len(node.get("filters") or []) > 1:
            raise ValueError("an OR group")
        return [leaf for child in node.get("filters") or [] for leaf in flatten(child)]
    return [node]


def canonical(leaf):
    op, value, prop = leaf.get("operator"), (leaf.get("value") or {}).get("value"), leaf.get("property")
    if op in ("enum_is", "status_is"):
        return (prop, "is", value)
    if op in ("enum_is_not", "status_is_not"):
        return (prop, "is_not", value)
    if op == "checkbox_is":
        return (prop, "is", bool(value))
    if op == "checkbox_is_not":
        return (prop, "is", not value)
    if op == "relation_contains":
        return (prop, "contains", hex_id(value))
    return (prop, op, json.dumps(value))


def check_view(key, want, url, views):
    got = views.get(view_id(url))
    if got is None:
        fail(f"views.{key}: {url} is not a view of the Stories database")
        return
    try:
        leaves = flatten(got.get("advancedFilter") or {"type": "group", "operator": "and", "filters": []})
        leaves += [f["filter"] for f in got.get("simpleFilters") or [] if (f.get("filter") or {}).get("value", {}).get("value") is not None]
        have = sorted(map(canonical, leaves), key=repr)
    except ValueError as e:
        fail(f"views.{key}: filter has {e}, which no Launch Control view uses")
        return
    expect = sorted(((p, o, hex_id(v) if o == "contains" else v) for p, o, v in want["filters"]), key=repr)
    wrong = []
    if got.get("type") != want["type"]:
        wrong.append(f"type is {got.get('type')!r}, not {want['type']!r}")
    if have != [tuple(e) for e in expect]:
        wrong.append(f"filter is {have or 'none'}, not {[tuple(e) for e in expect] or 'none'}")
    sorts = [(s.get("property"), "DESC" if s.get("direction") == "descending" else "ASC") for s in got.get("sorts") or []]
    want_sorts = [tuple(s) for s in want.get("sorts") or []]
    if sorts != want_sorts:
        wrong.append(f"sort is {sorts}, not {want_sorts}")
    if want.get("groupBy") and (got.get("groupBy") or {}).get("property") != want["groupBy"]:
        wrong.append(f"not grouped by {want['groupBy']!r}")
    if wrong:
        fail(f"views.{key} ({got.get('name')!r}): " + "; ".join(wrong))
    else:
        ok(f"views.{key} ({got.get('name')!r}): filter, sort{', grouping' if want.get('groupBy') else ''} as specified")


def cmd_check(args):
    s = spec()
    state = load_json(args.state)
    print(f"Launch Control init check -> {args.state}")
    for k in ("projects", "stories"):
        if not state.get(k):
            fail(f"state has no {k} database - nothing to check")
    if problems:
        return finish()
    ds_urls = {k: state[k]["dataSource"] for k in ("projects", "stories")}

    print("\nProperties")
    parsed = {}
    for k, path in (("projects", args.projects), ("stories", args.stories)):
        try:
            parsed[k] = parse_database(path)
        except (OSError, ValueError) as e:
            fail(f"{k}: could not read the fetch result: {e}")
            continue
        have_ds = ds_uuid(parsed[k][0].get("url"))
        if have_ds != ds_uuid(ds_urls[k]):
            fail(f"{k}: {path} is data source {have_ds or '(unknown)'}, but this run created {ds_uuid(ds_urls[k])}")
            del parsed[k]
            continue
        check_properties(s[k]["title"], s[k], parsed[k][0], ds_urls)
    if not state.get("blockedBy"):
        fail("Blocked by was never recorded as added - run the blocked-by DDL, then record blockedBy")

    print("\nViews")
    if "stories" in parsed:
        views = dict(parsed["stories"][1])
        for path in args.view or []:
            try:
                one = parse_views(fetch_text(path))
            except (OSError, ValueError) as e:
                fail(f"could not read the view fetch {path}: {e}")
                continue
            if not one:
                fail(f"{path} holds no view")
            views.update(one)
        recorded = state.get("views") or {}
        for v in s["views"]:
            if not recorded.get(v["key"]):
                fail(f"views.{v['key']} was never created")
                continue
            check_view(v["key"], v, recorded[v["key"]], views)
        if state.get("road"):
            # The name is not checked, only the filter, so the key does not matter here.
            check_view("road", road_spec("", state.get("project", "")), state["road"], views)
        elif state.get("project"):
            fail("the project row exists but its road view was never created")
    return finish()


# ------------------------------------------------------------------- board
def cmd_board(args):
    state = load_json(args.state)
    print(f"Launch Control init board -> {args.out}")
    missing = [k for k in ("hub", "projects", "stories") if not state.get(k)]
    missing += [f"views.{k}" for k in SHARED_VIEWS if not (state.get("views") or {}).get(k)]
    if missing:
        fail(f"state is missing {', '.join(missing)} - the board is not fully provisioned")
        return finish()
    board = {"hub": state["hub"], "stories": state["stories"], "projects": state["projects"],
             "views": {k: state["views"][k] for k in SHARED_VIEWS}, **NOTES}
    save_json(args.out, board)
    ok("board file written - pass it to plan.py config --from")
    return finish()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("preflight")
    c.add_argument("--repo", required=True)
    c.add_argument("--new-board", action="store_true")

    c = sub.add_parser("ddl")
    c.add_argument("what", choices=("projects", "stories", "blocked-by"))
    c.add_argument("--projects-ds")
    c.add_argument("--stories-ds")

    c = sub.add_parser("views")
    c.add_argument("--road", action="store_true")
    c.add_argument("--key")
    c.add_argument("--project-url")

    c = sub.add_parser("record")
    c.add_argument("--state", required=True)
    c.add_argument("--key", required=True, help="hub, projects, stories, blockedBy, views.<key>, project, road")
    c.add_argument("--url", required=True)
    c.add_argument("--data-source")

    c = sub.add_parser("check")
    c.add_argument("--state", required=True)
    c.add_argument("--stories", required=True)
    c.add_argument("--projects", required=True)
    c.add_argument("--view", action="append", help="a fetch of one view, newer than the database fetch")

    c = sub.add_parser("board")
    c.add_argument("--state", required=True)
    c.add_argument("--out", required=True)

    args = ap.parse_args()
    return {"preflight": cmd_preflight, "ddl": cmd_ddl, "views": cmd_views, "record": cmd_record,
            "check": cmd_check, "board": cmd_board}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
