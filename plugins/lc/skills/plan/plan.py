#!/usr/bin/env python3
"""Launch Control - the deterministic half of /lc:plan.

    plan.py clocks   --repo DIR [--source FILE]          which external clocks this launch has
    plan.py lint     PROPOSAL [--repo DIR] [--source FILE] [--epics A,B,...]
    plan.py order    PROPOSAL --state STATE               drafts left to file, blockers first
    plan.py next-id  PROPOSAL --state STATE --draft D --board FILE --prefix P
    plan.py payload  PROPOSAL --state STATE --draft D --id ID --project-url URL
    plan.py record   --state STATE --draft D --id ID --url URL [--replace]
    plan.py verify   --state STATE --board FILE --prefix P
    plan.py config   --repo DIR --from SIBLING_CONFIG --project KEY --prefix P
                     --project-page URL --road URL

Every subcommand exits 1 on a failure and 0 otherwise, so the verdict is the
script's and not the session's. Like doctor.py it cannot reach Notion: the skill
queries the board and hands the results over, in doctor's page format -
{"file": path} | {"rows": [[id, status], ...], "hasMore": bool} | {"error": text},
or a list of those pages.

PROPOSAL is the backlog the session drafted and the user reviewed:

    {"project": {"key", "name", "prefix", "repo", "kind"},
     "source": "<what was read>",
     "claims": [{"claim", "verdict": "holds|false|partial|unverifiable", "evidence"}],
     "clocksDeclined": {"<clock key>": "<why this launch does not need it>"},
     "stories": [{"draft": "D1", "name", "type", "epic", "estimate", "gating",
                  "agent": true|false, "leadTime", "leadDays": [min, max],
                  "doneWhen", "notes",
                  "blockedBy": ["D0"], "clock": "<clock key, if it is one>",
                  "leadDaysReason": "<why this clock's leadDays differ from clocks.json>",
                  "agentOverride": "<why an agent can do it despite the wording>"}]}

A story with `clock` set is held to that entry in clocks.json: its leadDays must
match unless leadDaysReason says why, and an omitted epic or estimate is the clock's.

STATE is this run's ledger of what has been filed ({draft: {"id", "url"}}). It is
what makes a run resumable after a failure, and it is counted when allocating
IDs, because a row created a second ago may not be in a view yet.
"""
import argparse
import fnmatch
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # importing doctor must not litter the installed plugin
sys.path.insert(0, os.path.join(HERE, "..", "doctor"))
from doctor import CheckError, read_json, read_page, remote_default_branch, git  # noqa: E402


class MissingDraft(CheckError):
    """A proposed story with no `draft` ID. Deliberately not a ValueError: lint
    reads a ValueError out of topo() as a dependency cycle, which this is not."""


TYPES = ("Launch Blocker", "Backlog", "Chore")
ESTIMATES = ("XS", "S", "M", "L", "XL")
GATINGS = ("Self-serve", "External")
VERDICTS = ("holds", "false", "partial", "unverifiable")
SKIP_DIRS = {".git", "node_modules", "Pods", "build", "dist", ".venv", "venv", "__pycache__",
             "DerivedData", ".gradle", ".next", "target", "vendor", ".build"}

# Wording that means a human has to be there. A story marked agent-doable that says
# one of these fails lint unless it carries an agentOverride explaining why the
# wording misleads ("implement the login screen" is agent work; "log in to App Store
# Connect" is not). The override is the point: it forces the decision to be made.
HUMAN_WORK = [
    r"\bapp store connect\b", r"\bplay console\b", r"\bsign (in|up) (to|for|at|with)\b",
    r"\blog ?in to\b", r"\bcredit card\b", r"\bpay (for|the)\b", r"\benrol(l|ment)\b",
    r"\bd-u-n-s\b", r"\bphysical device\b", r"\bon a (real )?device\b", r"\blawyer\b",
    r"\battorney\b", r"\blegal review\b", r"\bsign the\b", r"\btax (form|info)",
    r"\bbank(ing)? (account|details)\b", r"\bregistrar\b", r"\bsupport ticket\b",
    r"\brequest access\b", r"\bapproval from\b", r"\bin the gui\b",
    r"\bverify (your|the) identity\b", r"\bphone call\b", r"\bnotari",
    r"\bfile (a|the) (form|application)\b",
]
# Things a checkable Done-when tends to contain: a command, an observable result,
# a place to look. A Done-when with none of them is usually a restated title.
CHECKABLE = re.compile(
    r"`|\bexits?\b|\breturns?\b|\bshows?\b|\bcontains?\b|\bpass(es)?\b|\bresponds?\b|"
    r"\blists?\b|\bprints?\b|\bdisplays?\b|\bappears?\b|\bmatch(es)?\b|\bstatus\b|"
    r"\b[0-9]+\b|https?://|\.[a-z]{2,4}\b|\bno (errors?|warnings?)\b|\bgreen\b|\bmerged\b|"
    r"\bapproved\b|\bverified\b|\bactive\b|\bissued\b|\bgranted\b|\bpublished\b|\breceives?\b",
    re.I,
)
# Notion turns a bare file name whose extension is also a TLD into a link to a web
# host of that name: `DESIGN.md` is stored as [DESIGN.md](http://DESIGN.md). Inside
# backticks it survives. Rather than track which extensions are TLDs, all must be quoted. Every Notes-and-traps field that was read out verbatim afterwards carried
# the broken link, so it fails lint rather than warning.
BARE_FILE = re.compile(r"(?<![`\w/.-])([\w./-]*\w\.(?:md|py|js|ts|tsx|jsx|json|ya?ml|toml|swift|kt|go|rs|rb|sh|txt|tf|gradle|lock|env|cfg|ini))\b(?![`\w/-])")
STOP = set("a an the and or of to for in on with is are be it its this that as at by from "
           "into when so all any each can do does done has have not no yes via per".split())

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


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_state(path):
    return read_json(path, "the --state ledger") if path and os.path.exists(path) else {}


def filed(state):
    """The stories in a state file. Keys starting with _ are the run's provisioning
    records (_project, _road), not stories."""
    return {d: v for d, v in state.items() if not d.startswith("_")}


def board_ids(board_path):
    """Every Story ID in a board query result, and whether it was read to the end."""
    raw = read_json(board_path, "the --board query result")
    pages = raw if isinstance(raw, list) else [raw]
    ids, complete = [], True
    base = os.path.dirname(os.path.abspath(board_path))
    for p in pages:
        rows, has_more, error = read_page(p, base)
        if error:
            raise SystemExit(f"board query failed: {error}")
        ids += [i for i, _ in rows]
        complete = not has_more
    return ids, complete


def lead_days(story):
    """(min, max) from a story's leadDays, or None if it is missing or malformed."""
    v = story.get("leadDays")
    if not (isinstance(v, list) and len(v) == 2):
        return None
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in v):
        return None
    return (v[0], v[1]) if 0 <= v[0] <= v[1] else None


def words(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 1}


# ------------------------------------------------------------------ clocks
def load_clocks():
    path = os.path.join(HERE, "clocks.json")
    clocks = read_json(path, "clocks.json").get("clocks")
    if not isinstance(clocks, list):
        raise CheckError(f"clocks.json has no `clocks` list - the plugin install is damaged: {path}")
    return clocks


def with_clock(story, by_key):
    """The story with its clock's epic and estimate filled in where the draft left them out."""
    clock = by_key.get(story.get("clock"))
    if not clock:
        return story
    return {**{k: clock[k] for k in ("epic", "estimate") if clock.get(k)},
            **{k: v for k, v in story.items() if v not in (None, "")}}


def diverges(story, clock):
    """The clock's (min, max) if the story's leadDays differ from it, else None."""
    theirs = tuple(clock["leadDays"])
    return theirs if lead_days(story) is not None and lead_days(story) != theirs else None


def repo_files(repo, limit=20000):
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        rel_root = os.path.relpath(root, repo)
        for name in list(dirs) + files:
            rel = name if rel_root == "." else os.path.join(rel_root, name)
            out.append(rel)
            if len(out) >= limit:
                return out
    return out


def match_glob(rel, pattern):
    return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(os.path.basename(rel), pattern)


def detect_clocks(repo, source):
    """[(clock, reason)] for every clock this repo or source document triggers."""
    files = repo_files(repo) if repo else []
    text = ""
    if source and os.path.isfile(source):
        with open(source, errors="replace") as f:
            text = f.read()
    cache = {}

    def read(rel):
        if rel not in cache:
            path = os.path.join(repo, rel)
            try:
                if os.path.isfile(path) and os.path.getsize(path) < 1_000_000:
                    with open(path, errors="replace") as f:
                        cache[rel] = f.read()
                else:
                    cache[rel] = ""
            except OSError:
                cache[rel] = ""
        return cache[rel]

    hits = []
    for clock in load_clocks():
        d = clock.get("detect", {})
        reason = None
        for pat in d.get("files", []):
            m = next((f for f in files if match_glob(f, pat)), None)
            if m:
                reason = f"repo has {m}"
                break
        if not reason:
            for pat, rx in d.get("content", []):
                r = re.compile(rx, re.I | re.M)
                m = next((f for f in files if match_glob(f, pat) and r.search(read(f))), None)
                if m:
                    reason = f"{m} matches /{rx}/"
                    break
        if not reason and text:
            for rx in d.get("text", []):
                m = re.search(rx, text, re.I)
                if m:
                    reason = f"source mentions {m.group(0)!r}"
                    break
        if reason:
            hits.append((clock, reason))

    # A clock's blockers are filed with it, so they trigger with it: a repo that
    # takes payments needs the entity before Stripe whether or not it says "LLC".
    by_key = {c["key"]: c for c in load_clocks()}
    found = {c["key"] for c, _ in hits}
    i = 0
    while i < len(hits):
        clock = hits[i][0]
        for b in clock["blockedBy"]:
            if b not in found:
                found.add(b)
                hits.append((by_key[b], f"blocks {clock['key']}"))
        i += 1
    order = list(by_key)
    hits.sort(key=lambda h: order.index(h[0]["key"]))
    return hits


def cmd_clocks(args):
    hits = detect_clocks(args.repo, args.source)
    print(f"External clocks -> {args.repo}" + (f" + {args.source}" if args.source else ""))
    if not hits:
        print("  none triggered. Say so in the proposal; do not invent one.")
        return 0
    for clock, reason in hits:
        dep = f"  after {', '.join(clock['blockedBy'])}" if clock["blockedBy"] else ""
        print(f"\n  {clock['key']}  ({reason}){dep}")
        print(f"    {clock['name']}")
        print(f"    Lead time:  {clock['leadTime']}")
        print(f"    Lead days:  {clock['leadDays'][0]}-{clock['leadDays'][1]} calendar")
        print(f"    Done when:  {clock['doneWhen']}")
        print(f"    Notes:      {clock['notes']}")
        for url in clock.get("sources", []):
            print(f"    Source:     {url}")
    print(f"\n{len(hits)} clock(s). File each as Gating External, agent unchecked, with `clock` set to its key -")
    print("or list it in clocksDeclined with the reason this launch does not need it.")
    return 0


# -------------------------------------------------------------------- lint
def topo(stories):
    """Drafts ordered blockers-first, or raise ValueError naming a cycle.

    The proposal JSON is written by hand (see plan/`SKILL.md`), so a story with no
    `draft` is an expected mistake, not a broken invariant. lint reports it before
    calling here; this check is what keeps the other subcommands from a KeyError."""
    missing = [s.get("name") or "(unnamed)" for s in stories if not s.get("draft")]
    if missing:
        raise MissingDraft(f"{len(missing)} story{'' if len(missing) == 1 else 's'} with no "
                           f"`draft` ID: {', '.join(repr(n[:40]) for n in missing[:3])}"
                           f"{', ...' if len(missing) > 3 else ''} - run `plan.py lint` for the full list")
    by = {s["draft"]: s for s in stories}
    seen, done, order = set(), set(), []

    def visit(d, path):
        if d in done:
            return
        if d in seen:
            raise ValueError(" -> ".join(path + [d]))
        seen.add(d)
        for b in by[d].get("blockedBy") or []:
            if b in by:
                visit(b, path + [d])
        done.add(d)
        order.append(d)

    for s in stories:
        visit(s["draft"], [])
    return order


def cmd_lint(args):
    p = read_json(args.proposal, "the proposal")
    print(f"Launch Control plan lint -> {args.proposal}")
    proj = p.get("project") or {}
    by_key = {c["key"]: c for c in load_clocks()}
    drafted = p.get("stories") or []
    stories = [with_clock(s, by_key) for s in drafted]
    epics = [e.strip() for e in args.epics.split(",")] if args.epics else None

    print("\nProject")
    prefix = proj.get("prefix") or ""
    if not re.fullmatch(r"[A-Z][A-Z0-9]{1,5}", prefix):
        fail(f"prefix {prefix!r} should be 2-6 capitals/digits, e.g. APP")
    for k in ("key", "name"):
        if not proj.get(k):
            fail(f"project.{k} is empty")
    if not problems:
        ok(f"{proj.get('key')} / {prefix}")

    print("\nClaims checked against the repo")
    claims = p.get("claims") or []
    if not claims:
        fail("no claims recorded - a document that was not checked against the repo writes a fictional backlog")
    for c in claims:
        if c.get("verdict") not in VERDICTS:
            fail(f"claim {c.get('claim')!r} has verdict {c.get('verdict')!r}, not one of {', '.join(VERDICTS)}")
        elif c.get("verdict") != "unverifiable" and not (c.get("evidence") or "").strip():
            fail(f"claim {c.get('claim')!r} is marked {c['verdict']} with no evidence")
    if claims and not any(c.get("verdict") in ("false", "partial") for c in claims):
        warn("every claim held - plausible, but re-check any 'not built yet' claim against git log before believing it")
    if claims and not problems:
        ok(f"{len(claims)} claim(s), each with a verdict and evidence")

    print("\nStories")
    if not stories:
        fail("no stories")
        return finish()
    drafts = [s.get("draft") for s in stories]
    # Everything below keys on `draft` - the dependency graph, the filing order, the
    # payloads. A story without one is the expected hand-authoring slip, so it is
    # named here rather than surfacing as a KeyError from topo().
    nodraft = [(s.get("name") or "(unnamed)") for s in stories if not s.get("draft")]
    for n in nodraft:
        fail(f"{n[:50]!r}: no `draft` ID - every story needs one (D1, D2, ...); "
             "blockedBy and the filing order are written in terms of it")
    dupes = sorted({d for d in drafts if d and drafts.count(d) > 1})
    if dupes:
        fail(f"draft IDs used twice: {', '.join(map(str, dupes))}")
    names = [(s.get("name") or "").strip().lower() for s in stories]
    for n in sorted({n for n in names if n and names.count(n) > 1}):
        fail(f"two stories named {n!r}")
    known = set(drafts)
    before = len(problems)
    for s in stories:
        d = s.get("draft") or "?"
        name = (s.get("name") or "").strip()
        tag = f"{d} {name[:50]!r}"
        if not name:
            fail(f"{d}: no name")
        if s.get("type") not in TYPES:
            fail(f"{tag}: type {s.get('type')!r} is not one of {', '.join(TYPES)}")
        if s.get("estimate") not in ESTIMATES:
            fail(f"{tag}: estimate {s.get('estimate')!r} is not one of {', '.join(ESTIMATES)}")
        if s.get("gating") not in GATINGS:
            fail(f"{tag}: gating {s.get('gating')!r} is not one of {', '.join(GATINGS)}")
        if epics is not None and s.get("epic") not in epics:
            fail(f"{tag}: epic {s.get('epic')!r} is not an option on the board")
        if "," in (s.get("epic") or ""):
            fail(f"{tag}: select options cannot contain commas")
        if not isinstance(s.get("agent"), bool):
            fail(f"{tag}: agent must be true or false, and decided - not left out")

        # Done when
        dw = (s.get("doneWhen") or "").strip()
        if not dw:
            fail(f"{tag}: Done when is empty")
        else:
            extra = words(dw) - words(name)
            if len(extra) < 3:
                fail(f"{tag}: Done when restates the name - say what someone would run or look at")
            elif not CHECKABLE.search(dw):
                fail(f"{tag}: Done when names nothing checkable (a command, a result, a place that shows it)")

        # Agent can do this
        blob = " ".join([name, dw]).lower()
        if s.get("agent") is True:
            said = [m.group(0) for rx in HUMAN_WORK for m in [re.search(rx, blob)] if m]
            if said and not (s.get("agentOverride") or "").strip():
                fail(f"{tag}: marked agent-doable but says {', '.join(repr(x) for x in said[:3])} - "
                     "uncheck it, or add agentOverride saying why an agent can do it anyway")
            if s.get("gating") == "External":
                fail(f"{tag}: External gating means a third party holds the clock - agent must be false")
        if s.get("gating") == "External":
            if not (s.get("leadTime") or "").strip():
                fail(f"{tag}: External with no lead time - say why the outside world takes as long as it does")
            if lead_days(s) is None:
                fail(f"{tag}: External needs leadDays [min, max], calendar days with 0 <= min <= max - "
                     "/lc:mine computes with these and lists a clock without them as unranked")
        if s.get("agent") is False and s.get("type") != "Launch Blocker":
            warn(f"{tag}: human work typed {s.get('type')!r} - boards built before the yourTurn view "
                 "dropped its Type filter still hide this from /lc:mine. Fix the view (board.json's "
                 "yourTurn has the current filter), do NOT retype the story to suit it")

        for field in ("name", "doneWhen", "notes", "leadTime"):
            outside = re.sub(r"`[^`]*`", "", s.get(field) or "")
            bare = sorted(set(BARE_FILE.findall(outside)))
            if bare:
                fail(f"{tag}: {field} has bare file names {', '.join(bare)} - wrap them in backticks, "
                     "or Notion may store them as links to http://<name> (it does for any extension that is also a TLD, like .md and .py)")

        for b in s.get("blockedBy") or []:
            if b not in known:
                fail(f"{tag}: blocked by unknown draft {b!r}")
            if b == d:
                fail(f"{tag}: blocked by itself")
    if len(problems) == before:
        ok(f"{len(stories)} stories: fields valid, Done-when checkable, agent flags justified")
    if nodraft:
        warn("dependency graph not checked - it is drawn in `draft` IDs, and some are missing")
    else:
        try:
            topo(stories)
            ok("dependency graph has no cycle")
        except ValueError as e:
            fail(f"dependency cycle: {e}")

    humans = [s for s in stories if s.get("agent") is False]
    if not humans:
        warn("every story is agent-doable - that is rare for a launch and empties /lc:mine; re-read each one")

    print("\nExternal clocks")
    # A filed clock is only as good as the numbers it carries: /lc:mine ranks by leadDays
    # and a wrong figure produces a confident wrong pick, not an error. So the story must
    # say what clocks.json says, or say why this launch differs.
    for raw, s in zip(drafted, stories):
        k = s.get("clock")
        if not k:
            continue
        tag = f"{s.get('draft')} clock {k!r}"
        clock = by_key.get(k)
        if not clock:
            fail(f"{tag} is not in clocks.json - leave `clock` off a clock the dataset does not know")
            continue
        theirs = diverges(s, clock)
        reason = (s.get("leadDaysReason") or "").strip()
        if theirs and len(reason.split()) < 3:
            fail(f"{tag}: leadDays {list(lead_days(s))} but clocks.json says {list(theirs)} - "
                 "match it, or give leadDaysReason saying why this launch differs")
        elif theirs:
            ok(f"{tag}: leadDays {list(lead_days(s))} differ from clocks.json {list(theirs)}: {reason}")
        elif reason:
            warn(f"{tag}: leadDaysReason given but leadDays match clocks.json - drop it")
        for field in ("epic", "estimate"):
            if raw.get(field) and clock.get(field) and raw[field] != clock[field]:
                warn(f"{tag}: {field} {raw[field]!r} overrides the clock's {clock[field]!r}")
    if args.repo or args.source:
        declined = p.get("clocksDeclined") or {}
        filed = {s.get("clock") for s in stories if s.get("clock")}
        hits = detect_clocks(args.repo, args.source)
        if not hits:
            ok("none triggered")
        for clock, reason in hits:
            k = clock["key"]
            if k in filed:
                ok(f"{k} filed")
            elif (declined.get(k) or "").strip():
                ok(f"{k} declined: {declined[k]}")
            else:
                fail(f"{k} triggered ({reason}) but neither filed nor declined with a reason")
        for s in stories:
            if s.get("clock") and s.get("gating") != "External":
                fail(f"{s.get('draft')}: is clock {s['clock']!r} but gating is not External")
    else:
        warn("no --repo or --source given, so clocks were not checked")

    return finish("Clean. Present it for review.")


# ------------------------------------------------------------------- filing
def series_of(story):
    return "plain" if story.get("type") == "Launch Blocker" else "B"


def id_number(prefix, series, sid):
    rx = rf"{re.escape(prefix)}-(\d+)" if series == "plain" else rf"{re.escape(prefix)}-B(\d+)"
    m = re.fullmatch(rx, sid or "")
    return int(m.group(1)) if m else None


def cmd_order(args):
    p = read_json(args.proposal, "the proposal")
    state = filed(load_state(args.state))
    for d in topo(p["stories"]):
        if d not in state:
            print(d)
    return 0


def cmd_next_id(args):
    p = read_json(args.proposal, "the proposal")
    state = filed(load_state(args.state))
    story = next((s for s in p["stories"] if s["draft"] == args.draft), None)
    if not story:
        print(f"no draft {args.draft!r} in the proposal", file=sys.stderr)
        return 1
    ids, complete = board_ids(args.board)
    if not complete:
        print("board was not read to the last page - the highest ID cannot be known", file=sys.stderr)
        return 1
    # This read is also the read-back of every earlier create: an ID this run filed
    # that now sits on two rows lost a race, and must be renumbered before going on.
    dupes = [(d, v["id"]) for d, v in state.items() if ids.count(v["id"]) > 1]
    if dupes:
        for d, sid in dupes:
            print(f"{sid} ({d}) is on {ids.count(sid)} rows - renumber the row this run created "
                  f"({state[d]['url']}), not the other, then `record --replace`", file=sys.stderr)
        return 2
    series = series_of(story)
    taken = ids + [v["id"] for v in state.values()]
    nums = [n for n in (id_number(args.prefix, series, i) for i in taken) if n is not None]
    n = max(nums, default=0) + 1
    print(f"{args.prefix}-{n:02d}" if series == "plain" else f"{args.prefix}-B{n}")
    return 0


def cmd_payload(args):
    p = read_json(args.proposal, "the proposal")
    state = filed(load_state(args.state))
    stories = p["stories"]
    by_key = {c["key"]: c for c in load_clocks()}
    story = next((with_clock(s, by_key) for s in stories if s["draft"] == args.draft), None)
    if not story:
        print(f"no draft {args.draft!r} in the proposal", file=sys.stderr)
        return 1
    notes = story.get("notes") or ""
    theirs = diverges(story, by_key[story["clock"]]) if story.get("clock") in by_key else None
    if theirs:
        # On the board, so a reader can tell a researched departure from an invented number.
        lo, hi = lead_days(story)
        notes = (f"Lead days {lo}-{hi} differ from the `clocks.json` figure {theirs[0]}-{theirs[1]}: "
                 f"{story.get('leadDaysReason', '').strip()}" + (f"\n\n{notes}" if notes else ""))
    blockers = []
    for b in story.get("blockedBy") or []:
        if b not in state:
            print(f"{args.draft} is blocked by {b}, which has not been filed yet - file in `order` order",
                  file=sys.stderr)
            return 1
        blockers.append(state[b]["url"])
    seq = topo(stories).index(args.draft) + 1
    props = {
        "Name": story["name"],
        "Story ID": args.id,
        "Project": [args.project_url],
        "Type": story["type"],
        "Epic": story.get("epic"),
        "Estimate": story["estimate"],
        "Gating": story["gating"],
        "Agent can do this": "__YES__" if story["agent"] else "__NO__",
        "Lead time": story.get("leadTime") or "",
        "Lead days min": (lead_days(story) or (None, None))[0],
        "Lead days max": (lead_days(story) or (None, None))[1],
        "Done when": story["doneWhen"],
        "Notes and traps": notes,
        "Seq": seq,
        "Blocked by": blockers,
        # Every blocker in a fresh plan is a story this run just filed, so none is Done.
        "Status": "Backlog" if blockers else "Ready",
    }
    print(json.dumps({k: v for k, v in props.items() if v is not None}, indent=2))
    return 0


def cmd_record(args):
    state = load_state(args.state)
    if args.draft in state and state[args.draft]["id"] != args.id and not args.replace:
        print(f"{args.draft} was already recorded as {state[args.draft]['id']}", file=sys.stderr)
        return 1
    state[args.draft] = {"id": args.id, "url": args.url}
    save_json(args.state, state)
    print(f"recorded {args.draft} = {args.id}")
    return 0


def cmd_verify(args):
    state = filed(load_state(args.state))
    ids, complete = board_ids(args.board)
    print(f"Launch Control plan verify -> {len(state)} filed")
    if not complete:
        fail("board was not read to the last page")
    foreign = sorted({i or "(blank)" for i in ids if not i.startswith(f"{args.prefix}-")})
    if foreign:
        fail(f"road returned Story IDs outside {args.prefix}-: {', '.join(foreign)}")
    for draft, v in state.items():
        n = ids.count(v["id"])
        if n == 1:
            ok(f"{v['id']} ({draft}) is on the board once")
        elif n == 0:
            fail(f"{v['id']} ({draft}) is not on the road view - lag, or the create did not land; re-read before retrying")
        else:
            fail(f"{v['id']} ({draft}) is on {n} rows - lost a race; renumber the row this run created, not the other")
    return finish()


# ------------------------------------------------------------------- config
GITIGNORE = (".claude/launch-control.local.json", ".claude/.current-story", ".claude/.nudged", ".claude/lc-plan/")


def cmd_config(args):
    repo = os.path.abspath(args.repo)
    claude = os.path.join(repo, ".claude")
    target = os.path.join(claude, "launch-control.json")
    sib = read_json(args.from_, "the --from sibling config")
    print(f"Launch Control plan config -> {target}")

    page_id = re.findall(r"[0-9a-f]{32}", args.project_page.replace("-", ""))
    page_id = page_id[-1] if page_id else args.project_page
    if os.path.exists(target):
        have = read_json(target, "the existing launch-control.json")
        if have.get("prefix") == args.prefix and (have.get("projectPageId") or "").replace("-", "") == page_id:
            ok("already written for this project - leaving it as it is")
            return finish()
        fail(f"{target} exists for project {have.get('project')!r} / {have.get('prefix')!r} - refusing to overwrite")
        return finish()

    for k in ("stories", "projects", "views"):
        if not sib.get(k):
            fail(f"sibling config has no `{k}` - it cannot describe the board")
    missing = [k for k in ("ready", "inProgress", "inReview", "waitingExternal", "yourTurn", "board")
               if not (sib.get("views") or {}).get(k)]
    if missing:
        fail(f"sibling config is missing shared views: {', '.join(missing)}")
    if "v=" not in args.road:
        fail("--road has no ?v= view id")
    if problems:
        return finish()

    version = read_json(os.path.join(HERE, "..", "..", ".claude-plugin", "plugin.json"),
                        "the plugin's plugin.json").get("version", "")
    is_git = bool(git(repo, "rev-parse", "--git-dir"))
    base, source = remote_default_branch(repo) if is_git else ("", "")
    if is_git and not base:
        base = git(repo, "symbolic-ref", "--short", "HEAD") or "main"
        warn(f"no reachable origin - baseBranch set to the current branch {base!r}; check it before /lc:done")

    views = {k: v for k, v in sib["views"].items() if k != "road"}
    views["road"] = args.road
    cfg = {
        "project": args.project,
        "prefix": args.prefix,
        "hub": sib.get("hub", ""),
        "projectPageId": page_id,
        "stories": sib["stories"],
        "projects": sib["projects"],
        "views": views,
    }
    for k in ("note", "dependencies", "viewContract"):
        if sib.get(k):
            cfg[k] = sib[k]
    cfg["installedVersion"] = version
    cfg["git"] = {
        "enabled": is_git,
        "baseBranch": base,
        "mergeMethod": "squash",
        # Conservative until the owner says otherwise: /lc:done stops at a green PR.
        "autoMerge": False,
        "mergeIsDeploy": False,
        "ciTimeoutMinutes": 20,
        "extraChecks": [],
        "notes": "",
    }
    os.makedirs(claude, exist_ok=True)
    save_json(target, cfg)
    ok(f"wrote config for {args.project} / {args.prefix}" + (f", baseBranch {base!r} ({source})" if source else ""))

    gi = os.path.join(repo, ".gitignore")
    raw = open(gi).read() if os.path.exists(gi) else ""
    add = [line for line in GITIGNORE if line not in raw.splitlines()]
    if add:
        with open(gi, "a") as f:
            f.write(("\n" if raw and not raw.endswith("\n") else "") + "\n".join(add) + "\n")
        ok(f".gitignore: added {', '.join(add)}")
    return finish()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clocks")
    c.add_argument("--repo", required=True)
    c.add_argument("--source")

    c = sub.add_parser("lint")
    c.add_argument("proposal")
    c.add_argument("--repo")
    c.add_argument("--source")
    c.add_argument("--epics", help="comma-separated Epic options from the board schema")

    c = sub.add_parser("order")
    c.add_argument("proposal")
    c.add_argument("--state", required=True)

    c = sub.add_parser("next-id")
    c.add_argument("proposal")
    c.add_argument("--state", required=True)
    c.add_argument("--draft", required=True)
    c.add_argument("--board", required=True)
    c.add_argument("--prefix", required=True)

    c = sub.add_parser("payload")
    c.add_argument("proposal")
    c.add_argument("--state", required=True)
    c.add_argument("--draft", required=True)
    c.add_argument("--id", required=True)
    c.add_argument("--project-url", required=True)

    c = sub.add_parser("record")
    c.add_argument("--state", required=True)
    c.add_argument("--draft", required=True, help="a draft ID, or _project / _road")
    c.add_argument("--id", default="")
    c.add_argument("--url", required=True)
    c.add_argument("--replace", action="store_true", help="renumbering a row that lost an ID race")

    c = sub.add_parser("verify")
    c.add_argument("--state", required=True)
    c.add_argument("--board", required=True)
    c.add_argument("--prefix", required=True)

    c = sub.add_parser("config")
    c.add_argument("--repo", required=True)
    c.add_argument("--from", dest="from_", required=True)
    c.add_argument("--project", required=True)
    c.add_argument("--prefix", required=True)
    c.add_argument("--project-page", required=True)
    c.add_argument("--road", required=True)

    args = ap.parse_args()
    return {
        "clocks": cmd_clocks, "lint": cmd_lint, "order": cmd_order, "next-id": cmd_next_id,
        "payload": cmd_payload, "record": cmd_record, "verify": cmd_verify, "config": cmd_config,
    }[args.cmd](args)


def cli():
    """Every subcommand exits 1 on a failure - and says what failed.

    A traceback keeps the exit code's promise while breaking the useful half of it,
    so the anticipated failures come back through here as a FAIL line instead."""
    try:
        return main()
    except CheckError as e:
        print(f"  FAIL  {e}")
        return 1
    except KeyboardInterrupt:
        print("\n  FAIL  interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(cli())
