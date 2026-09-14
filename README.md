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
  time if you start it today — computed from each clock's lead days and the
  blocker chain behind it, with the arithmetic shown, not judged by eye.

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

No board yet? Run `/lc:init` in your first repo: it creates the Notion databases,
every property and view the commands read, and that repo's config, then checks
what it built against the schema. For every repo after that, run
`/lc:plan <design doc or repo path> --board <first repo>/.claude/launch-control.json`
in it: it creates the project, its road view and `.claude/launch-control.json`, and
files the backlog. To bring over a repo that used the older copied-files layout,
create `.claude/launch-control.json` from
[`examples/launch-control.example.json`](examples/launch-control.example.json)
and run:

```
./install.sh /path/to/your/repo            # dry run
./install.sh /path/to/your/repo --apply
```

`--apply` refuses, changing nothing, while that repo has a story bound in
`.claude/.current-story` or uncommitted changes under `.claude/` or to `.gitignore`:
a live session editing the same files can undo the install's ignore lines.

[`docs/notion-schema.md`](docs/notion-schema.md) describes the two databases, the
properties that carry weight, and the views each command reads.

## Commands

| Command | What it does |
|---|---|
| `/lc:init [page]` | Creates the board from nothing — both databases, every property, all seven views — checks it against the schema, and puts this repo on it |
| `/lc:plan <doc or repo>` | Turns a design doc or a repo into a project and its whole backlog: provisions the project, checks every claim against the repo, adds the external clocks the doc never mentions, and files nothing until you confirm |
| `/lc:next` | Hands you the next unblocked story this session can actually do, traps read out in full |
| `/lc:start <ID>` | Binds the session to a story: status, branch, `.current-story` |
| `/lc:done` | Verifies the criteria, ships through a PR, merges by policy, records, unblocks dependents |
| `/lc:mine [prefix]` | The work only a human can do: clocks by lead days with projected finish dates, your desk by estimate, and the one item to start today with its arithmetic |
| `/lc:status` | Where every project stands |
| `/lc:groom <what>` | Files something newly discovered, with real acceptance criteria |
| `/lc:reconcile` | Audits the board against the repo; evidence required to close anything |
| `/lc:doctor [repo]` | Checks the config hasn't quietly broken: view keys, road scoping, base branch, duplicate IDs, notices naming finished stories. Exits non-zero on any |

Two hooks do the rest: `SessionStart` tells a session which story it is bound to
and reads out that repo's standing warnings; `Stop` refuses a silent exit while a
story is still claimed — once per story, so it nudges but never traps you.

## If you have hooks of your own

The plugin ships its two hooks in `plugins/lc/hooks/hooks.json`. What happens when
a project's own `.claude/settings.json` *also* has `SessionStart` or `Stop` hooks
is **not settled by Claude Code's documentation**, and Launch Control does not
pretend otherwise:

- The [hooks reference](https://code.claude.com/docs/en/hooks#hook-locations) says
  hook entries *merge across settings levels* — but the levels it names are user,
  project, local and managed settings. It lists a plugin's `hooks/hooks.json` as a
  hook location without saying the merge covers it.
- The same page says an identical handler defined in several settings files runs
  once, while "a plugin's or skill's copy of the same handler stays separate". That
  reads as plugin hooks running *alongside* settings hooks rather than replacing
  them, but it is an inference, not a statement.
- It has not been tested. The one attempt was invalid: the repo it ran in had
  already been migrated, so there were no project-side hooks left to observe.

**On a standard install the question does not arise.** `install.sh --apply` removes
the old copied Launch Control hooks from the target's `.claude/settings.json`
(step 3), because leaving them beside the plugin's would at best fire twice.

**If you keep a `SessionStart` or `Stop` hook of your own, expect this:**

- Step 3 removes only Launch Control's own handlers: a `SessionStart` handler whose
  command runs `.claude/hooks/session-start.sh`, and a `Stop` handler whose command
  runs `.claude/hooks/stop.sh` — the two scripts step 4 moves away. Every other
  handler stays, including one that shares a matcher group with ours; a group or
  event is dropped only once nothing is left in it. The dry run lists each handler
  by command as `would remove` or `keep`, so check that list before `--apply`.
  If `settings.json` is not valid JSON, step 3 says so and changes nothing. Hooks
  in `.claude/settings.local.json` and `~/.claude/settings.json` are not touched.
- Your hook then sits beside the plugin's. The likely outcome is that both run,
  in parallel, in no guaranteed order: two blocks of `SessionStart` context, and
  two `Stop` hooks each able to block an exit. If instead one silences the other,
  that is the unsettled case above — please open an issue saying which won.

## Per-repo policy

The commands and hooks are identical everywhere, and are not meant to be edited
per repo — `install.sh` treats a local edit as drift to be propagated back. The
intended extension point is the `git` block of `.claude/launch-control.json`,
which is where everything that differs between repos lives:

| Key | What it decides |
|---|---|
| `baseBranch` | The branch PRs target |
| `mergeMethod` | `squash`, `merge` or `rebase` |
| `autoMerge` | Whether `/lc:done` may merge at all, or stops at a green PR |
| `mergeIsDeploy` | Whether **merging is deploying**. Where it is, `/lc:done` always stops and leaves the decision to you |
| `ciTimeoutMinutes` | How long to wait for checks before leaving the PR open rather than merging on optimism |
| `extraChecks` | Expensive opt-in checks, each run only when its `when` matches, read literally |
| `notes` | Standing warnings for this repo, read before anything is staged |

`enabled: false` turns shipping off entirely; `/lc:done` then records without
opening a PR. See [`docs/config-reference.md`](docs/config-reference.md).

## Status

v0.1.0, and honest about it: this was extracted from a working setup managing five
projects, and has one real user. The board is provisioned by `/lc:init`; projects on it are provisioned by `/lc:plan`.

What this is *not* is a task engine. Claude Code's native Tasks already persist
work, track which task blocks which, and surface what just became unblocked — use
them for the steps inside a story. Launch Control keeps a thin version of each only
because the board has a reader native Tasks do not: a human looking across every
project, at work that is not an agent's to do. The one thing it offers that nothing
else does is the human-work critical path in `/lc:mine`. See
[`docs/decisions/0001-native-tasks.md`](docs/decisions/0001-native-tasks.md).

MIT.
