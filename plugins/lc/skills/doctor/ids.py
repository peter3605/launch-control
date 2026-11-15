#!/usr/bin/env python3
"""Launch Control - answer board questions from saved view-mode pages.

    ids.py list       PAGE...                      Story ID, Status, page URL, blockers
    ids.py find       PAGE... --id ID              the one row carrying ID
    ids.py next       PAGE... --prefix P [--backlog]  the next free ID in a sequence
    ids.py dependents PAGE... --url PAGE_URL       rows whose Blocked by holds PAGE_URL
    ids.py prefix-free PAGE... --prefix P          is a prefix unused board-wide?

Why this exists: Notion's free plan meters SQL and rows-mode queries out of one
workspace allowance, and view mode not at all. So every board read the commands
make is a saved view queried in view mode, and the filtering a rows-mode query
used to do happens here instead. View results are large - tens of rows run to
hundreds of thousands of characters and get saved to a file - so they are read
by this script, never by eye.

Each PAGE is one view-mode result, in either form the tool leaves it: the JSON
object itself ({"results": [...], "has_more": ..., "next_cursor": ...}), or the
saved-to-file form, a list of content blocks whose text is that object. Pass the
pages in the order they were read. The last one must say has_more false: an
answer from a view that was not read to the end is refused, because the row that
would have changed it is exactly the one that was not read.

Exit codes: 0 answered; 1 a failure or a negative answer (not found, taken, no
next ID because the read was incomplete); 2 a Story ID on more than one row.
"""
import argparse
import json
import os
import re
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from boardcheck import unwrap_saved  # noqa: E402


class PageError(Exception):
    pass


def page_id(url):
    """The 32-hex page id in any form of Notion page URL, dashes stripped, so an
    app.notion.com/p/... link and a www.notion.so/...-<id> link compare equal."""
    path = (url or "").split("?", 1)[0].replace("-", "").lower()
    # The id is the LAST 32 hex characters: a title slug ending in a hex letter
    # ("...-Title-3d10...") runs straight into it once the dashes are gone.
    m = re.findall(r"[0-9a-f]{32,}", path)
    return m[-1][-32:] if m else ""


def relation(value):
    """A relation property as a list of URLs. View mode renders it as a JSON string
    ('["https://..."]'), and omits the key altogether when the relation is empty."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return [str(v) for v in parsed] if isinstance(parsed, list) else [str(parsed)]
    return []


def load_page(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise PageError(f"view page not found: {path}") from None
    except json.JSONDecodeError as e:
        raise PageError(f"view page is not valid JSON - half-written? {path} ({e.msg})") from None
    data = unwrap_saved(data)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise PageError(f"view page holds a content block whose text is not valid JSON - "
                            f"truncated? {path} ({e.msg})") from None
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise PageError(f"not a view-mode result (no `results` list): {path}")
    return data


def read_rows(paths):
    """Every row across the pages, and whether the last page closed the view."""
    rows, complete = [], True
    for p in paths:
        data = load_page(p)
        for r in data["results"]:
            if not isinstance(r, dict):
                raise PageError(f"a row is not an object: {p}")
            rows.append({
                "id": str(r.get("Story ID") or ""),
                "status": str(r.get("Status") or ""),
                "url": str(r.get("url") or ""),
                "blockedBy": relation(r.get("Blocked by")),
            })
        complete = not data.get("has_more")
    return rows, complete


def need_complete(complete, what):
    if not complete:
        print(f"FAIL  the view was not read to the end (the last page says has_more) - "
              f"page on with next_cursor before {what}")
        sys.exit(1)


def seq(story_id, prefix, backlog):
    """The number in ID if it is in this sequence: PREFIX-<n>, or PREFIX-B<n>."""
    m = re.fullmatch(re.escape(prefix) + (r"-B(\d+)" if backlog else r"-(\d+)"), story_id)
    return int(m.group(1)) if m else None


def cmd_list(rows, args):
    for r in rows:
        print("\t".join([r["id"] or "-", r["status"] or "-", r["url"] or "-",
                         ",".join(r["blockedBy"]) or "-"]))
    return 0


def cmd_find(rows, args):
    hits = [r for r in rows if r["id"] == args.id]
    if len(hits) > 1:
        print(f"DUPLICATE  {args.id} is on {len(hits)} rows:")
        for r in hits:
            print(f"  {r['url']}  {r['status']}")
        return 2
    if not hits:
        # Only a complete read can say "not there".
        need_complete(args.complete, f"saying {args.id} does not exist")
        print(f"NOT FOUND  {args.id}")
        return 1
    r = hits[0]
    print(f"{r['id']}\t{r['status']}\t{r['url']}\t{','.join(r['blockedBy']) or '-'}")
    return 0


def cmd_next(rows, args):
    need_complete(args.complete, "allocating an ID")
    mine = [r["id"] for r in rows if seq(r["id"], args.prefix, args.backlog) is not None]
    nums = [seq(i, args.prefix, args.backlog) for i in mine]
    for d in sorted({i for i in mine if mine.count(i) > 1}):
        print(f"warn  {d} is on more than one row - one of them lost a race and needs renumbering")
    n = max(nums, default=0) + 1
    print(f"{args.prefix}-{'B' if args.backlog else ''}{n}")
    return 0


def cmd_dependents(rows, args):
    need_complete(args.complete, "listing dependents - a missed page is a missed promotion")
    target = page_id(args.url)
    if not target:
        print(f"FAIL  no Notion page id in {args.url!r}")
        return 1
    for r in rows:
        if target in {page_id(u) for u in r["blockedBy"]}:
            print(f"{r['id'] or '-'}\t{r['status'] or '-'}\t{r['url']}\t{','.join(r['blockedBy'])}")
    return 0


def cmd_prefix_free(rows, args):
    need_complete(args.complete, "calling a prefix free")
    taken = [r["id"] for r in rows if r["id"].startswith(args.prefix + "-")]
    if taken:
        print(f"TAKEN  {args.prefix} is used by {len(taken)} row(s), e.g. {taken[0]}")
        return 1
    print(f"FREE  no row's Story ID starts with {args.prefix}-")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "find", "next", "dependents", "prefix-free"):
        p = sub.add_parser(name)
        p.add_argument("pages", nargs="+", metavar="PAGE")
        if name == "find":
            p.add_argument("--id", required=True)
        if name in ("next", "prefix-free"):
            p.add_argument("--prefix", required=True)
        if name == "next":
            p.add_argument("--backlog", action="store_true", help="the -B series, not plain numbers")
        if name == "dependents":
            p.add_argument("--url", required=True)
    args = ap.parse_args(argv)
    try:
        rows, args.complete = read_rows(args.pages)
    except PageError as e:
        print(f"FAIL  {e}")
        return 1
    return {"list": cmd_list, "find": cmd_find, "next": cmd_next,
            "dependents": cmd_dependents, "prefix-free": cmd_prefix_free}[args.cmd](rows, args)


if __name__ == "__main__":
    sys.exit(main())
