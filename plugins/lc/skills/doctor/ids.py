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

A page that came back inline - under the tool's size limit, so it was never saved
to disk - is not re-typed into a file. Give its rows on the command line instead,
as short values that can be stated exactly, and say how many rows it held:

    --inline-page COUNT HAS_MORE   the inline page: its row count, and its has_more
    --row ID STATUS URL BLOCKERS   one per row of it, in order; BLOCKERS is the
                                   Blocked by URLs comma-separated, or - for none

The inline page is read after every PAGE file, so it is the last page. It is
checked loudly: a --row count that differs from COUNT, a URL with no page id, a
blocker that is not a Notion URL or a HAS_MORE that is not true/false is a FAIL,
never an answer. The whole read may be inline, with no PAGE files at all.

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


STATUSES = {"Backlog", "Ready", "In Progress", "Blocked", "In Review", "Done"}


def inline_rows(count, has_more, given):
    """The inline page's rows from --inline-page and --row, validated. Each check is
    one way a stated row goes wrong: a dropped or extra row, a mangled URL, a
    blocker list that lost its separators, a status misread."""
    try:
        n = int(count)
    except ValueError:
        raise PageError(f"--inline-page COUNT must be a whole number, not {count!r}") from None
    if has_more not in ("true", "false"):
        raise PageError(f"--inline-page HAS_MORE must be true or false, not {has_more!r}")
    if len(given) != n:
        raise PageError(f"--inline-page says {n} row(s) but {len(given)} --row given - "
                        f"a dropped row is a wrong answer, so state every row of the inline page")
    rows = []
    for sid, status, url, blockers in given:
        if not page_id(url):
            raise PageError(f"--row {sid}: no Notion page id in URL {url!r}")
        if status not in STATUSES:
            raise PageError(f"--row {sid}: status {status!r} is not one of {', '.join(sorted(STATUSES))}")
        urls = [] if blockers == "-" else [b.strip() for b in blockers.split(",")]
        bad = [b for b in urls if not page_id(b)]
        if bad:
            raise PageError(f"--row {sid}: blocker {bad[0]!r} has no Notion page id "
                            f"(BLOCKERS is comma-separated URLs, or - for none)")
        rows.append({"id": sid if sid != "-" else "", "status": status, "url": url, "blockedBy": urls})
    return rows, has_more == "false"


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
        p.add_argument("pages", nargs="*", metavar="PAGE")
        p.add_argument("--inline-page", nargs=2, metavar=("COUNT", "HAS_MORE"),
                       help="the last page came back inline: its row count and has_more")
        p.add_argument("--row", nargs=4, action="append", default=[], metavar=("ID", "STATUS", "URL", "BLOCKERS"),
                       help="one row of the inline page; BLOCKERS comma-separated URLs or -")
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
        if args.row and not args.inline_page:
            raise PageError("--row given without --inline-page COUNT HAS_MORE")
        if not args.pages and not args.inline_page:
            raise PageError("no pages - pass the saved view pages, an --inline-page, or both")
        rows, args.complete = read_rows(args.pages) if args.pages else ([], True)
        if args.inline_page:
            more, args.complete = inline_rows(*args.inline_page, args.row)
            rows += more
    except PageError as e:
        print(f"FAIL  {e}")
        return 1
    return {"list": cmd_list, "find": cmd_find, "next": cmd_next,
            "dependents": cmd_dependents, "prefix-free": cmd_prefix_free}[args.cmd](rows, args)


if __name__ == "__main__":
    sys.exit(main())
