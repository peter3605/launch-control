#!/usr/bin/env python3
"""Launch Control - check a repo's config for the regressions that fail silently.

    doctor.py [--repo DIR] --views FILE     full check
    doctor.py [--repo DIR] --local-only     config and git only, no board

Exits 1 if any check fails, 0 if every check that ran passed.

This script cannot reach Notion: the plugin talks to the board through the MCP
connection, which only the session has. So /lc:doctor queries the views and hands
the results over in FILE, a JSON object keyed by view name. Each value is one page,
or a list of pages in order, and each page is one of:

    {"error": "<what the query said>"}         the view did not resolve
    {"file": "<path>"}                         a saved raw view-mode result
    {"rows": [["APP-1", "Done"], ...], "hasMore": false}   Story ID and Status

Every check here was a real failure that went unnoticed until someone tripped on it.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

VIEW_KEYS = ("ready", "inProgress", "inReview", "waitingExternal", "yourTurn", "board", "road")

failures = []


def ok(msg):
    print(f"  ok    {msg}")


def fail(msg):
    failures.append(msg)
    print(f"  FAIL  {msg}")


def skip(msg):
    print(f"  skip  {msg}")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def notion_id(url):
    """The 32-hex database id in a notion.so URL, dashes stripped."""
    path = (url or "").split("?", 1)[0].replace("-", "")
    m = re.findall(r"[0-9a-f]{32}", path)
    return m[-1] if m else ""


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def remote_default_branch(repo):
    """Ask the remote first. origin/HEAD is only as fresh as the last clone or
    `git remote set-head`, and a rename on the host does not update it."""
    out = git(repo, "ls-remote", "--symref", "origin", "HEAD")
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", out, re.M)
    if m:
        return m.group(1), "remote"
    local = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if local.startswith("origin/"):
        return local[len("origin/"):], "origin/HEAD, remote unreachable"
    return "", ""


def read_page(page, base):
    """Return ([(story_id, status)], has_more, error) for one page of a view result."""
    if "error" in page:
        return None, False, str(page["error"])
    if "file" in page:
        path = os.path.join(base, page["file"])
        raw = load_json(path)
        # A saved MCP tool result is a list of content blocks whose text is the JSON.
        if isinstance(raw, list):
            raw = json.loads("".join(b.get("text", "") for b in raw if isinstance(b, dict)))
        rows = raw.get("results", [])
        rows = [(str(r.get("Story ID") or ""), str(r.get("Status") or "")) for r in rows]
        return rows, bool(raw.get("has_more")), None
    if "rows" in page:
        return [(str(i or ""), str(s or "")) for i, s in page["rows"]], bool(page.get("hasMore")), None
    return None, False, f"unrecognised page entry {sorted(page)}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--views", help="JSON file of view query results, see above")
    mode.add_argument("--local-only", action="store_true", help="skip every check that needs the board")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    claude = os.path.join(repo, ".claude")
    print(f"Launch Control doctor -> {repo}")

    try:
        cfg = load_json(os.path.join(claude, "launch-control.json"))
    except FileNotFoundError:
        print("  FAIL  .claude/launch-control.json not found")
        return 1
    except ValueError as e:
        print(f"  FAIL  .claude/launch-control.json is not valid JSON: {e}")
        return 1
    local = {}
    local_path = os.path.join(claude, "launch-control.local.json")
    if os.path.exists(local_path):
        try:
            local = load_json(local_path)
        except ValueError as e:
            fail(f"launch-control.local.json is not valid JSON: {e}")

    prefix = cfg.get("prefix") or ""
    if not prefix:
        fail("no `prefix` - every command filters on it")

    # ------------------------------------------------------------------ views
    print("\nViews in config")
    views = cfg.get("views") or {}
    missing = [k for k in VIEW_KEYS if not views.get(k)]
    if missing:
        fail(f"missing view keys: {', '.join(missing)}")
    else:
        ok("all seven view keys present")
    db = notion_id((cfg.get("stories") or {}).get("database"))
    for k in VIEW_KEYS:
        url = views.get(k)
        if url and db and notion_id(url) != db:
            fail(f"views.{k} points at a database other than stories.database")
        if url and "v=" not in url:
            fail(f"views.{k} has no ?v= view id - it opens the database, not a view")

    # -------------------------------------------------------------------- git
    print("\nGit")
    g = cfg.get("git") or {}
    if g.get("enabled") is False:
        skip("git.enabled is false - base branch not used")
    elif not git(repo, "rev-parse", "--git-dir"):
        fail("not a git repository, but git.enabled is not false")
    else:
        base = g.get("baseBranch") or ""
        actual, source = remote_default_branch(repo)
        if not actual:
            fail("could not determine the default branch (no reachable origin, no origin/HEAD)")
        elif base != actual:
            fail(f"git.baseBranch is {base or '(unset)'!r} but the default branch is {actual!r} ({source})")
        else:
            ok(f"git.baseBranch {base!r} matches the default branch ({source})")

    # ------------------------------------------------------------------ board
    print("\nBoard")
    status = None  # Story ID -> Status on this project's road, once read
    if args.local_only:
        skip("view resolution, road scoping and duplicate IDs - run with --views for a full check")
    else:
        base_dir = os.path.dirname(os.path.abspath(args.views))
        results = load_json(args.views)
        for k in VIEW_KEYS:
            if not views.get(k):
                continue
            pages = results.get(k)
            if pages is None:
                fail(f"views.{k} was not queried - a check that did not run is not a pass")
                continue
            pages = pages if isinstance(pages, list) else [pages]
            rows, has_more, error = [], False, None
            for p in pages:
                page_rows, has_more, error = read_page(p, base_dir)
                if error:
                    break
                rows += page_rows
            if error:
                fail(f"views.{k} did not resolve: {error}")
                continue
            if k != "road":
                # The other six are shared across projects by design, so they may be
                # empty and may hold other prefixes. Resolving is all they owe.
                ok(f"views.{k} resolves ({len(rows)} row{'' if len(rows) == 1 else 's'})")
                continue
            if has_more:
                fail("views.road was not read to the last page - duplicates cannot be ruled out")
            if not rows:
                fail("views.road returned zero rows - a scoping bug reads exactly like a clean board")
                continue
            ids = [i for i, _ in rows]
            foreign = sorted({i or "(blank)" for i in ids if not i.startswith(f"{prefix}-")})
            if foreign:
                fail(f"views.road returned Story IDs outside {prefix}-: {', '.join(foreign)}")
            else:
                ok(f"views.road resolves, {len(rows)} rows, all {prefix}-")
            dupes = sorted(i for i, n in collections.Counter(i for i in ids if i).items() if n > 1)
            if dupes:
                fail(f"Story ID on more than one row: {', '.join(dupes)}")
            else:
                ok("no Story ID appears on two rows")
            status = dict(rows)

    # ---------------------------------------------------------------- notices
    print("\nStanding notices")
    # Notices are read as current fact at the start of every session. Naming a story
    # that is already Done is the signature of in-flight state that outlived its
    # flight: "until that lands" about something that landed. An open story is a
    # fair pointer, so only finished or unknown ones fail.
    id_re = re.compile(rf"\b{re.escape(prefix)}-[A-Z]?\d+\b") if prefix else None
    clean = True
    for label, text in (
        ("launch-control.json notice", cfg.get("notice")),
        ("launch-control.local.json notice", local.get("notice")),
        ("git.notes", g.get("notes")),
    ):
        ids = sorted(set(id_re.findall(text or ""))) if id_re else []
        if not ids:
            continue
        if status is None:
            clean = False
            skip(f"{label} names {', '.join(ids)} - whether they are Done needs the board")
            continue
        done = [i for i in ids if status.get(i) == "Done"]
        unknown = [i for i in ids if i not in status]
        if done:
            clean = False
            fail(f"{label} names Done stories {', '.join(done)} - reword it as a standing fact, or drop it")
        if unknown:
            clean = False
            fail(f"{label} names {', '.join(unknown)}, which the road view does not have")
        still_open = [f"{i} ({status[i]})" for i in ids if i in status and status[i] != "Done"]
        if still_open:
            ok(f"{label} also names open stories, which is fine: {', '.join(still_open)}")
    if clean:
        ok("no notice names a finished story")

    print()
    if failures:
        print(f"{len(failures)} problem(s).")
        return 1
    print("Clean." if not args.local_only else "Clean locally. The board was not checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
