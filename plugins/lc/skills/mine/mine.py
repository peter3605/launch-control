#!/usr/bin/env python3
"""Launch Control - rank the work only a human can do by what waiting costs.

    mine.py --view FILE [--view FILE ...] [--prefix APP] [--today YYYY-MM-DD]

Each FILE is one page of a view-mode query of the Your turn view, as the tool
returned it: a JSON object with a "results" list, or the list of content blocks
the tool saves a large result as. Pass every page.

Exits 1 if the rows cannot be ranked honestly (a dependency cycle, or no rows),
0 otherwise. Rows it cannot rank are listed, never guessed.

The arithmetic, all in calendar days:

  lead(X)    External: Lead days min..max. Self-serve: 0..0 - desk work is
             hours, and this ranks by the days the outside world takes.
  finish(X)  lead(X) + the latest finish among X's open blockers. Blockers
             that are not in the view are Done or agent work, and add nothing.
  chain(X)   lead(X) + the longest run of leads through the items waiting on X.
             Starting X one day late pushes the end of that run one day.
  slack(X)   the project's latest finish - chain(X). Days X can wait before
             it moves that project's launch at all.

The pick is the Ready item with the least slack, then the longest chain, both
on the max bound: the item whose delay moves a launch soonest and furthest.
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True  # importing doctor must not litter the installed plugin
sys.path.insert(0, os.path.join(HERE, "..", "doctor"))
from doctor import load_result  # noqa: E402

EST_ORDER = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4}


def page_id(url):
    m = re.findall(r"[0-9a-f]{32}", (url or "").split("?", 1)[0].replace("-", ""))
    return m[-1] if m else ""


def relation(value):
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [page_id(u) for u in value if page_id(u)]


def number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def plain(text):
    """Notion turns bare file names into links: '[deploy.sh](http://deploy.sh)' -> 'deploy.sh'."""
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")


def days(n):
    return f"{n:g}"


def span(lo, hi):
    return days(lo) if lo == hi else f"{days(lo)}-{days(hi)}"


def load(paths):
    rows = []
    for path in paths:
        data = load_result(path)
        if data.get("has_more"):
            print(f"  WARN  {path} says has_more - pass every page, or rows are missing", file=sys.stderr)
        rows.extend(data.get("results", []))
    return rows


class Board:
    def __init__(self, rows):
        self.items = {}
        for r in rows:
            pid = page_id(r.get("url"))
            if not pid:
                continue
            external = r.get("Gating") == "External"
            lo, hi = number(r.get("Lead days min")), number(r.get("Lead days max"))
            if not external:
                lead = (0.0, 0.0)
            elif lo is None and hi is None:
                lead = None
            else:
                lo = hi if lo is None else lo
                hi = lo if hi is None else hi
                lead = (min(lo, hi), max(lo, hi))
            self.items[pid] = {
                "id": r.get("Story ID") or "?",
                "name": plain(r.get("Name")),
                "status": r.get("Status") or "",
                "external": external,
                "estimate": r.get("Estimate") or "",
                "leadText": plain(r.get("Lead time")),
                "lead": lead,
                "blockers": relation(r.get("Blocked by")),
            }
        for it in self.items.values():
            it["open_blockers"] = [b for b in it["blockers"] if b in self.items]
            it["dependents"] = []
        for pid, it in self.items.items():
            for b in it["open_blockers"]:
                self.items[b]["dependents"].append(pid)
        self._finish, self._chain = {}, {}

    def project(self, pid):
        return self.items[pid]["id"].split("-", 1)[0]

    def lead(self, pid):
        """(min, max, known) - an unknown lead counts as 0 and marks the total a floor."""
        lead = self.items[pid]["lead"]
        return (0.0, 0.0, False) if lead is None else (lead[0], lead[1], True)

    def finish(self, pid, stack=()):
        if pid in self._finish:
            return self._finish[pid]
        if pid in stack:
            raise ValueError(" -> ".join(self.items[p]["id"] for p in stack + (pid,)))
        lo, hi, known = self.lead(pid)
        blo = bhi = 0.0
        for b in self.items[pid]["open_blockers"]:
            flo, fhi, fknown = self.finish(b, stack + (pid,))
            blo, bhi, known = max(blo, flo), max(bhi, fhi), known and fknown
        self._finish[pid] = (lo + blo, hi + bhi, known)
        return self._finish[pid]

    def chain(self, pid, stack=()):
        """(min, max, known, path) along the dependents with the longest max run."""
        if pid in self._chain:
            return self._chain[pid]
        if pid in stack:
            raise ValueError(" -> ".join(self.items[p]["id"] for p in stack + (pid,)))
        lo, hi, known = self.lead(pid)
        best = (0.0, 0.0, True, [])
        for d in self.items[pid]["dependents"]:
            c = self.chain(d, stack + (pid,))
            if (c[1], c[0]) > (best[1], best[0]):
                best = c
        self._chain[pid] = (lo + best[0], hi + best[1], known and best[2], [pid] + best[3])
        return self._chain[pid]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--view", action="append", required=True, help="a saved view-mode page of Your turn")
    ap.add_argument("--prefix", help="narrow to one project's Story ID prefix")
    ap.add_argument("--today", help="YYYY-MM-DD, default today")
    args = ap.parse_args()

    today = datetime.date.fromisoformat(args.today) if args.today else datetime.date.today()
    rows = load(args.view)
    if args.prefix:
        # Narrow after loading so a blocker in the view still counts, whoever owns it.
        keep = args.prefix.rstrip("-").upper()
    board = Board(rows)
    if not board.items:
        print("No rows. Either nothing is waiting on a human, or the query returned nothing - check the view.")
        return 1

    try:
        for pid in board.items:
            board.finish(pid)
            board.chain(pid)
    except ValueError as cycle:
        print(f"  FAIL  dependency cycle: {cycle}. Nothing can be ranked until one of those edges is removed.")
        return 1

    def shown(pid):
        return not args.prefix or board.project(pid) == keep

    def date(n):
        return (today + datetime.timedelta(days=n)).isoformat()

    def floor(known):
        return "" if known else "+"

    items = board.items
    print(f"As of {today.isoformat()}. All figures are calendar days.\n")

    # Clocks
    clocks = [p for p in items if items[p]["external"] and shown(p)]
    ranked = sorted((p for p in clocks if items[p]["lead"]),
                    key=lambda p: (-items[p]["lead"][1], -items[p]["lead"][0], items[p]["id"]))
    unranked = sorted((p for p in clocks if not items[p]["lead"]), key=lambda p: items[p]["id"])

    print("CLOCKS - start these, then walk away")
    if not ranked:
        print("  (none with lead days)")
    for p in ranked:
        it = items[p]
        flo, fhi, fknown = board.finish(p)
        waiting = [items[b]["id"] for b in it["open_blockers"]]
        state = it["status"]
        if state == "In Progress":
            state += ", running - projected from today, so the dates are late-side"
        elif waiting:
            state += ", waits on " + ", ".join(waiting)
        print(f"  {it['id']:8} lead {span(*it['lead']):>7}  earliest finish "
              f"{date(flo)} .. {date(fhi)}{floor(fknown)}  [{state}]")
        print(f"           {it['name']}")
    if unranked:
        print("\n  Unranked - External with no Lead days, so nothing can compute with them:")
        for p in unranked:
            it = items[p]
            print(f"  {it['id']:8} [{it['status']}] {it['name']}")
            print(f"           Lead time says: {it['leadText'] or '(blank)'}")

    # Desk
    desk = sorted((p for p in items if not items[p]["external"] and shown(p)
                   and items[p]["status"] in ("Ready", "In Progress")),
                  key=lambda p: (items[p]["status"] != "In Progress",
                                 EST_ORDER.get(items[p]["estimate"], 9), items[p]["id"]))
    print("\nYOUR DESK - self-serve and unblocked, smallest first")
    if not desk:
        print("  (none)")
    for p in desk:
        it = items[p]
        tag = " (in progress)" if it["status"] == "In Progress" else ""
        print(f"  {it['id']:8} {it['estimate'] or '-':2}  {it['name']}{tag}")

    # Board bugs that would poison the pick
    bugs = [p for p in items if shown(p) and items[p]["status"] == "Ready"
            and any(items[b]["status"] != "Done" for b in items[p]["open_blockers"])]
    if bugs:
        print("\n  WARN  Ready but blocked by an open item in this view - excluded from the pick:")
        for p in bugs:
            print(f"        {items[p]['id']} waits on "
                  + ", ".join(items[b]["id"] for b in items[p]["open_blockers"]))

    # The pick
    ends = {}
    for p in items:
        lo, hi, known = board.finish(p)
        proj = board.project(p)
        e = ends.get(proj, (0.0, 0.0, True))
        ends[proj] = (max(e[0], lo), max(e[1], hi), e[2] and known)

    candidates = []
    for p in items:
        if not shown(p) or items[p]["status"] != "Ready" or p in bugs:
            continue
        clo, chi, cknown, path = board.chain(p)
        if chi == 0:
            continue
        end = ends[board.project(p)]
        candidates.append((end[1] - chi, -chi, -clo, items[p]["id"], p, path, clo, chi, cknown, end))

    print("\nSTART TODAY")
    if not candidates:
        print("  Nothing Ready heads a run of known lead days. Fill Lead days on the unranked clocks above.")
        return 0
    candidates.sort()
    slack, _, _, _, p, path, clo, chi, cknown, end = candidates[0]
    it = items[p]
    print(f"  {it['id']} - {it['name']}")
    terms = [f"{items[q]['id']} {span(*board.lead(q)[:2])}{'' if board.lead(q)[2] else '?'}" for q in path]
    print(f"  Chain:  {' + '.join(terms)} = {span(clo, chi)}{floor(cknown)} days")
    print(f"  {board.project(p)} ends no sooner than {span(end[0], end[1])}{floor(end[2])} days out "
          f"({date(end[0])} .. {date(end[1])}), so slack = {days(end[1])} - {days(chi)} = {days(slack)}.")
    if slack <= 0:
        print("  Every day this waits moves that launch a day.")
    else:
        print(f"  Nothing Ready is on a critical path; this one has the least slack.")
    if len(candidates) > 1:
        print("\n  Runners-up (slack, chain on the max bound):")
        for c in candidates[1:4]:
            print(f"    {c[3]:8} slack {days(c[0]):>4}  chain {span(c[6], c[7])}{floor(c[8])}")
    print("\n  ? = unknown lead counted as 0.  + = a floor, because an unknown lead sits in that chain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
