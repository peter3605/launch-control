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
import shutil
import subprocess
import sys

VIEW_KEYS = ("ready", "inProgress", "inReview", "waitingExternal", "yourTurn", "board", "road")

failures = []


class CheckError(Exception):
    """A failure this script anticipated, phrased for the person reading the output.

    These scripts set the exit code, so the verdict is theirs and not the session's.
    A traceback satisfies "exits non-zero" while telling the reader nothing about
    what to fix, so every expected failure is raised as this and printed as a FAIL.
    """


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


def read_json(path, what):
    """load_json, but every way it can fail comes back as a sentence naming `what`.

    The saved view files are written by the session from an MCP result, so missing
    and half-written are both routine - a truncated file is the one that used to
    surface as a bare JSONDecodeError twenty frames down."""
    try:
        return load_json(path)
    except FileNotFoundError:
        raise CheckError(f"{what} not found: {path}") from None
    except IsADirectoryError:
        raise CheckError(f"{what} is a directory, not a file: {path}") from None
    except UnicodeDecodeError as e:
        raise CheckError(f"{what} is not text: {path} ({e})") from None
    except json.JSONDecodeError as e:
        raise CheckError(f"{what} is not valid JSON - truncated or half-written? "
                         f"{path} (line {e.lineno} column {e.colno}: {e.msg})") from None
    except OSError as e:
        raise CheckError(f"{what} could not be read: {path} ({e.strerror or e})") from None


def unwrap_saved(data):
    """A large MCP tool result is saved to disk as a list of content blocks whose
    text is the payload. Return that text; return anything else unchanged."""
    if isinstance(data, list):
        return "".join(b.get("text", "") for b in data if isinstance(b, dict))
    return data


def load_result(path, what="saved view result"):
    """A saved query result as a JSON object, from either form the tool writes."""
    data = unwrap_saved(read_json(path, what))
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            # The outer file parsed, so the payload string inside it is the truncated
            # half. Say which layer failed - they look identical from the error alone.
            raise CheckError(f"{what} holds a content block whose text is not valid JSON - "
                             f"truncated? {path} (line {e.lineno} column {e.colno}: {e.msg})") from None
    if not isinstance(data, dict):
        raise CheckError(f"{what} is {type(data).__name__}, not a query result object: {path}")
    return data


def notion_id(url):
    """The 32-hex database id in a notion.so URL, dashes stripped."""
    path = (url or "").split("?", 1)[0].replace("-", "")
    m = re.findall(r"[0-9a-f]{32}", path)
    return m[-1] if m else ""


def git_env():
    """An environment where git cannot stop and ask a human anything.

    doctor runs unattended inside a session. GIT_TERMINAL_PROMPT=0 makes git fail
    instead of prompting for HTTPS credentials; ssh does its own prompting for a
    passphrase-locked key and ignores that, so BatchMode covers the SSH remotes.
    An already-set GIT_SSH_COMMAND is the user's, so it is left alone."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def git(repo, *args):
    """git's stdout, or "" if the command failed for any reason.

    Callers treat "" as "could not determine", which is the honest answer whether
    git is missing, the remote hung, or the command simply returned non-zero. Every
    one of these used to leave the script as a stack trace."""
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                           timeout=30, stdin=subprocess.DEVNULL, env=git_env())
    except subprocess.TimeoutExpired:
        return ""          # a network call to an unreachable remote
    except (FileNotFoundError, NotADirectoryError):
        return ""          # git is not installed, or --repo is not a directory
    except OSError:
        return ""          # no permission to exec, fork failed, ...
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
    """Return ([(story_id, status)], has_more, error) for one page of a view result.

    Never raises: the caller turns `error` into a FAIL naming the view, which is more
    use than a traceback from inside a JSON parse two files away."""
    if not isinstance(page, dict):
        return None, False, f"page entry is {type(page).__name__}, not an object"
    if "error" in page:
        return None, False, str(page["error"])
    if "file" in page:
        path = os.path.join(base, str(page["file"]))
        try:
            raw = load_result(path)
        except CheckError as e:
            return None, False, str(e)
        rows = raw.get("results")
        if not isinstance(rows, list):
            return None, False, (f"saved view result has no `results` list "
                                 f"({'missing' if rows is None else type(rows).__name__}): {path}")
        if not all(isinstance(r, dict) for r in rows):
            return None, False, f"saved view result has a row that is not an object: {path}"
        rows = [(str(r.get("Story ID") or ""), str(r.get("Status") or "")) for r in rows]
        return rows, bool(raw.get("has_more")), None
    if "rows" in page:
        pairs = page["rows"]
        if not isinstance(pairs, list) or not all(
                isinstance(p, (list, tuple)) and len(p) == 2 for p in pairs):
            return None, False, "`rows` must be a list of [story id, status] pairs"
        return [(str(i or ""), str(s or "")) for i, s in pairs], bool(page.get("hasMore")), None
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
        cfg = read_json(os.path.join(claude, "launch-control.json"), ".claude/launch-control.json")
    except CheckError as e:
        print(f"  FAIL  {e}")
        return 1
    if not isinstance(cfg, dict):
        print(f"  FAIL  .claude/launch-control.json must be an object, not {type(cfg).__name__}")
        return 1
    local = {}
    local_path = os.path.join(claude, "launch-control.local.json")
    if os.path.exists(local_path):
        try:
            local = read_json(local_path, "launch-control.local.json")
        except CheckError as e:
            fail(str(e))
        if not isinstance(local, dict):
            fail(f"launch-control.local.json must be an object, not {type(local).__name__}")
            local = {}

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
    elif shutil.which("git") is None:
        # Distinguished from the next branch on purpose: both used to arrive as the
        # same "not a git repository", which sends the reader to fix the wrong thing.
        fail("git is not on PATH, but git.enabled is not false - install git, or set git.enabled false")
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
        results = read_json(args.views, "the --views file")
        if not isinstance(results, dict):
            raise CheckError(f"the --views file must be an object keyed by view name, "
                             f"not {type(results).__name__}: {args.views}")
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


def cli():
    """Backstop: an anticipated failure raised anywhere below is still a FAIL line.

    The specific call sites phrase their own errors; this only guarantees that none
    of them can reach the user as a traceback if a new one is added without one."""
    try:
        return main()
    except CheckError as e:
        print(f"\n  FAIL  {e}")
        return 1
    except KeyboardInterrupt:
        print("\n  FAIL  interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(cli())
