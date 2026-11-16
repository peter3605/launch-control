"""Launch Control - compare a board read back from Notion with board.json.

Shared by `init.py check` (does the board this run built match the contract?) and
`doctor.py` (does the board this repo is on still match it, now that the plugin
may have moved on?). One comparison, two callers, so what /lc:init provisions and
what /lc:doctor holds a board to cannot drift apart.

This module imports nothing from either caller. init.py imports doctor.py, and
doctor.py imports this, so anything here that reached back into either of them
would be an import cycle.

The check_* functions report through the `ok` and `fail` callables they are given,
so each caller keeps its own output and its own exit-code bookkeeping.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD_JSON = os.path.join(HERE, "..", "init", "board.json")


def spec(path=BOARD_JSON):
    with open(path) as f:
        return json.load(f)


def unwrap_saved(data):
    """A large MCP tool result is saved to disk as a list of content blocks whose
    text is the payload. Return that text; return anything else unchanged."""
    if isinstance(data, list):
        return "".join(b.get("text", "") for b in data if isinstance(b, dict))
    return data


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


# ------------------------------------------------------------- view configs
def dsl_value(v):
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return f'"{v}"'


def configure(v):
    """A board.json view as the view DSL's configure line.

    A view with no filters starts with CLEAR FILTER. Through the Notion MCP's
    update-view tool, a FILTER clause replaces a view's whole filter, but a line
    with no FILTER clause leaves an existing filter in place - so without the
    CLEAR, the repair for a view that should have no filter changes nothing.
    create-view accepts the CLEAR on a new view. Verified on a throwaway board,
    2026-11-15 (docs/troubleshooting.md)."""
    parts = [] if v["filters"] else ["CLEAR FILTER"]
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


def repair(v):
    """The fix a view FAIL names: its configure line, plus, for a view that should
    have no filter, the instruction to remove the one it has."""
    line = f"fix: configure it as `{configure(v)}`"
    if not v["filters"]:
        line += (" - this view has no filter in board.json, so clear any it has: keep the CLEAR FILTER, "
                 "because a line with no FILTER clause leaves an existing filter in place")
    return line


# The views each project gets for itself, filtered on its own Projects row. `road`
# is every story in the project; `next` is its Ready, agent-doable ones, which is
# what /lc:next reads.
PROJECT_VIEWS = ("road", "next")


def project_view_spec(which, key, project_url, s=None):
    r = json.loads(json.dumps((s or spec())[which]))
    r["name"] = r["name"].format(key=key)
    r["filters"] = [[p, o, v.format(project_url=project_url) if isinstance(v, str) else v] for p, o, v in r["filters"]]
    return r


def road_spec(key, project_url, s=None):
    return project_view_spec("road", key, project_url, s)


# ----------------------------------------------------------- fetch results
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
    """{view id: view config} from the <view> blocks in a fetch result.

    Loud on anything short of a whole block: an opened <view> with no matching
    close, or a body that is not a JSON object, is a ValueError. A truncated copy of
    an inline result must not read as a board with one view fewer."""
    found = re.findall(r'<view url="\{\{view://([0-9a-f-]+)\}\}">\s*(.*?)\s*</view>', text, re.S)
    opened = len(re.findall(r"<view url=", text))
    if opened != len(found):
        raise ValueError(f"{opened} <view> block(s) opened but {len(found)} closed - truncated?")
    views = {}
    for vid, body in found:
        try:
            cfg = json.loads(body)
        except ValueError as e:
            raise ValueError(f"view {vid}: its block is not valid JSON - truncated or mis-copied? ({e})") from None
        if not isinstance(cfg, dict) or "type" not in cfg:
            raise ValueError(f"view {vid}: its block is not a view configuration (no `type`)")
        views[vid.replace("-", "")] = cfg
    return views


def parse_database(path):
    """(data source state, {view id: view config}) from a database fetch result.

    The result is the file the tool saved, or, for one that came back inline, a
    text file holding only its <data-source-state> and <view> blocks: nothing else
    in a fetch is read, so nothing else needs copying (LC-B15)."""
    text = fetch_text(path)
    m = re.search(r"<data-source-state>\s*(.*?)\s*</data-source-state>", text, re.S)
    if not m:
        raise ValueError(f"{path}: no <data-source-state> - is this a fetch of the database?")
    try:
        state = json.loads(m.group(1))
    except ValueError as e:
        raise ValueError(f"{path}: <data-source-state> is not valid JSON - truncated or mis-copied? ({e})") from None
    if not isinstance(state, dict) or not isinstance(state.get("schema"), dict) or not state.get("url"):
        raise ValueError(f"{path}: <data-source-state> has no `schema` object or no `url` - not a whole data source")
    return state, parse_views(text)


# --------------------------------------------------------------------- ddl
# One property's definition in the DDL Notion's create-database and
# update-data-source tools take. init.py builds a whole board from it; doctor.py
# names it as the exact repair for a property an older board is missing.
DDL_TYPES = {"title": "TITLE", "text": "RICH_TEXT", "number": "NUMBER", "checkbox": "CHECKBOX", "date": "DATE"}


def sql(s):
    return "'" + str(s).replace("'", "''") + "'"


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


# -------------------------------------------------------------- comparison
def check_properties(label, want, have, ds_urls, ok, fail, missing_fix=None):
    """missing_fix(p), when given, is appended to a missing property's FAIL - the
    exact statement that adds it, so a board that predates a property can be
    brought up to board.json without working the definition out by hand."""
    schema = have.get("schema") or {}
    for p in want["properties"]:
        got = schema.get(p["name"])
        if not got:
            fail(f"{label}: property {p['name']!r} is missing" + (f" - {missing_fix(p)}" if missing_fix else ""))
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


def check_view(key, want, url, views, ok, fail):
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
