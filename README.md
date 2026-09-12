# Launch Control

A backlog for people shipping real software with coding agents.

Most agent task tools help an agent decide what to write next. This one is built
around a different observation: **when a solo developer is late, it is usually not
because code is unwritten.** It is because a D-U-N-S number takes seven business
days, an SES production request is still in sandbox, an App Store review now runs
one to four weeks, and nobody started any of them.

So Launch Control tracks two kinds of work in one board:

- **What the agent can do** — surfaced by `/lc:next`, one story at a time, never
  started until its blockers are genuinely closed.
- **What the agent *cannot* do** — surfaced by `/lc:mine`, split into *clocks*
  (external, with a lead time you cannot compress) and *your desk* (self-serve,
  smallest first), and it names the single item that buys back the most calendar
  time if you start it today.

The second one is the point. Nothing else reports it.

## The other half: a story is Done when it is checked

Every story carries a **Done when** field that must be checkable by someone who
was not in the conversation — a command that exits 0, a file containing a value,
a screen showing a thing. `/lc:done` runs that check before it ticks anything off,
and `/lc:reconcile` periodically re-audits the board against the actual repo,
requiring evidence to close anything. Marking something Done that is not is worse
than leaving it open: it removes the only check that would have caught the gap
before submission.

## Install

```
/plugin marketplace add peter3605/launch-control
/plugin install lc@launch-control
```

Then in each repo, create `.claude/launch-control.json` from
[`examples/launch-control.example.json`](examples/launch-control.example.json)
and run:

```
./install.sh /path/to/your/repo            # dry run
./install.sh /path/to/your/repo --apply
```

You will also need a board. [`docs/notion-schema.md`](docs/notion-schema.md)
describes the two databases, the properties that carry weight, and the views each
command reads.

## Commands

| Command | What it does |
|---|---|
| `/lc:next` | Hands you the next unblocked story this session can actually do, traps read out in full |
| `/lc:start <ID>` | Binds the session to a story: status, branch, `.current-story` |
| `/lc:done` | Verifies the criteria, ships through a PR, merges by policy, records, unblocks dependents |
| `/lc:mine` | The work only a human can do, longest external lead time first |
| `/lc:status` | Where every project stands |
| `/lc:groom <what>` | Files something newly discovered, with real acceptance criteria |
| `/lc:reconcile` | Audits the board against the repo; evidence required to close anything |
| `/lc:doctor [repo]` | Checks the config hasn't quietly broken: view keys, road scoping, base branch, duplicate IDs, notices naming finished stories. Exits non-zero on any |

Two hooks do the rest: `SessionStart` tells a session which story it is bound to
and reads out that repo's standing warnings; `Stop` refuses a silent exit while a
story is still claimed — once per story, so it nudges but never traps you.

## Per-repo policy

The commands are identical everywhere. Everything that differs between repos lives
in the `git` block of `.claude/launch-control.json`: base branch, merge method,
whether auto-merge is allowed at all, and — importantly — whether **merging is
deploying**. Where it is, `/lc:done` stops at a green PR and leaves the decision
to you. See [`docs/config-reference.md`](docs/config-reference.md).

## Status

v0.1.0, and honest about it: this was extracted from a working setup managing five
projects, and has one real user. The Notion schema is provisioned by hand today.
Persistence and dependency graphs are also available natively in Claude Code Tasks
— what this adds on top is acceptance verification, board-vs-repo reconciliation,
and the human-work critical path.

MIT.
