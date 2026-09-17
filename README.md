# Launch Control

A backlog for people shipping real software with coding agents.

Most agent task tools help an agent decide what to write next. This one is built
around a different observation: **when a solo developer is late, it is usually not
because code is unwritten.** It is because a D-U-N-S number can take six weeks
when Dun & Bradstreet has never heard of the company, an SES production request
is still in sandbox, an App Store review now runs one to four weeks, and nobody
started any of them.

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

## What you need first

Launch Control is a thin layer over two things it does not ship: Claude Code, and a
Notion board reached through Notion's MCP connector. If the connector is missing, the
first thing you run after installing fails on its first tool call. Check this list
before the install commands below, not after.

| You need | Why | What happens without it |
|---|---|---|
| **Claude Code** | The commands are Claude Code skills; the two hooks are Claude Code hooks | Nothing to install into |
| **A Notion account** | The board *is* a Notion database. The free plan is enough — every command queries views in view mode, which is unmetered; nothing here uses billed SQL mode | No board |
| **Notion connected as an MCP connector in Claude Code** | Every single command reads or writes the board through Notion's MCP tools. There is no local or offline mode | `/lc:init` stops at pre-flight and names this |
| **That connector authorised on the page the board lives under** | Notion connectors see only the pages you share with them. Connected-but-unshared fails the same way as not connected | `/lc:init` stops at pre-flight and names this |
| **`python3` on `PATH`** | Every skill shells out to it; so do both hooks and `install.sh` | `install.sh` stops at step 0. Hooks fail quietly |
| **`git`** | `/lc:start` cuts the branch, `/lc:done` commits | `/lc:start` and `/lc:done` |
| **`gh`, authenticated** | `/lc:done` only — it pushes, opens the PR, and reads the check rollup | `/lc:done` only. Everything else works |

Connecting Notion is three steps, and it is worth knowing they are three, because
stopping after the first is the common way to arrive at `/lc:init` with a connector
that does not work:

1. **Configure the server.**

   ```
   claude mcp add --transport http notion https://mcp.notion.com/mcp
   ```

   Add `--scope user` to have it available in every repo rather than just this one.
2. **Authorise it.** Run `/mcp` inside Claude Code (or `claude mcp login notion`) and
   complete Notion's OAuth flow in the browser. Adding the server is configuration, not
   access — this step is what actually grants it.
3. **Share the page.** In Notion, open the page you want the board to live under, and
   use its `···` menu → **Add connections** to add the integration. Notion connectors
   see only what you share with them, and access cascades to everything inside that
   page. Skipping this is the failure that looks like a working connector returning
   nothing.

Confirm it before you run anything: `claude mcp list` should show `notion` as
connected. Notion's own setup guide is at
[developers.notion.com/guides/mcp/get-started-with-mcp](https://developers.notion.com/guides/mcp/get-started-with-mcp),
and that page, not this one, is the current truth about the endpoint and the auth flow.

**How long to a first working command.** If Notion is already connected: about five
minutes — install the plugin, run `/lc:init`, watch it provision. From nothing,
budget half an hour, and note that most of it is Notion-side account and connector
setup that has nothing to do with this plugin. `/lc:init` itself is a few minutes of
agent turns, because it creates two databases and seven views and then reads every one
of them back to check it. Filing an actual backlog with `/lc:plan` is a separate
session again, and a longer one — it reads your design doc or repo before it proposes
anything.

## Before you install

Four questions worth answering before you run anything. The answers are all in the
source, but you should not have to read it to decide.

### What leaves your machine

**Everything Launch Control stores goes to your own Notion workspace**, and it gets
there through *your* Notion MCP connector under your own OAuth grant. The plugin ships
no credentials and contains no network code of its own — no HTTP client, no endpoint, no
telemetry, no analytics, no version ping. It cannot reach Notion by itself; the session
does the writing.

What lands on the board:

- **Story text** — the title, the **Done when** criteria, the **Notes and traps**,
  estimate, epic, status, sequence, story ID, lead times, and the blocker links between
  stories. `Done when` and `Notes and traps` are *meant* to name real commands and real
  file paths — that is what makes a criterion checkable — so **file names, paths and
  commands from your repo are on the board by design.**
- **Your repo's absolute path.** The Projects row stores it verbatim, so on a typical
  macOS or Linux machine your OS username is in Notion — `/Users/<you>/Repos/<project>`.
- **Per-session records.** `/lc:done` writes into **Last session**: the date, one or two
  sentences on what the session did, the commit SHA and the PR number or URL. When a
  criterion fails it writes what went wrong, which in practice can be an error message
  or a test failure.
- **Command output, in one place by instruction.** `/lc:reconcile` requires evidence to
  close a story and is explicit that this means the command you ran *and its output*, or
  the file and line. A bare "already done" is rejected. Short excerpts of real tool
  output therefore reach Notion.
- **Whatever `/lc:plan` turns into a backlog.** It reads your design doc or repo to
  propose stories, so prose derived from that document ends up in story fields. It files
  nothing until you confirm, and the evidence it gathers while checking claims stays in
  a local file rather than on the board.

**What does not go to Notion:** source code, diffs and patches. Nothing writes file
contents to the board, and every row is properties-only — no page bodies, no comments,
no attachments. Be aware of the honest limit on that promise: these fields are free text
written by an agent, not a constrained payload, so nothing *mechanically* stops a snippet
or a log excerpt landing in one. No instruction asks for it; no check forbids it.

**Other things that touch the network**, all ordinary developer tooling under your own
credentials: `/lc:done` runs `git push` and uses `gh` to open the PR, read the check
rollup and merge — and the PR body it writes carries the story ID and the **Done when**
verbatim, so that much story text also lands on your git host. `/lc:doctor`, `/lc:plan`
and `/lc:init` run `git ls-remote` to confirm your base branch, which contacts the remote
for a ref listing and nothing more. The two hooks are local shell and make no network
calls at all.

One thing this does *not* claim: Launch Control is a layer over Claude Code, so your code
is already being read by an agent and sent to its model provider. That is true before you
install this and has nothing to do with the board.

**Say the rest out loud before you commit to it:** your story titles, acceptance
criteria, trap notes and per-session records live in a third-party SaaS, on their
servers, under their terms. For an unreleased product that is a real disclosure
decision, and this repo would rather you made it now than discover it later. There is
no self-hosted backend and no export command yet.

### What it can do to your repo

| It can | When | Governed by |
|---|---|---|
| Create a branch, write `.claude/.current-story` | `/lc:start` | — |
| Commit and push a branch | `/lc:done` | — |
| **Open a pull request against your base branch** | `/lc:done` | `git.baseBranch` picks the target |
| **Merge that pull request and delete the branch** | `/lc:done` | `git.autoMerge` — **`false` unless you change it** |
| Block a session from exiting silently | `Stop` hook, once per story | fires once per story, then never again |

**Merging is off by default.** Both `/lc:init` and `/lc:plan` write `autoMerge: false`
into a new repo's config, so out of the box `/lc:done` stops at a green PR, sets the
story `In Review`, and leaves the merge to you. Setting `mergeIsDeploy: true` makes it
stop that way permanently, green or not. It stages deliberately and never runs
`git add -A`, and it never merges with `--admin` or past a failing check.

These live in the `git` block of `.claude/launch-control.json`; the full set, including
`enabled`, is in [`docs/config-reference.md`](docs/config-reference.md).

Outside `.claude/`, the only file any of this touches is `.gitignore`, to which
`/lc:init` and `/lc:plan` append the four lines listed below. The one exception is
`install.sh --apply`, used only for the copied-files migration: on top of its own
`.gitignore` lines it rewrites bare `/next`-style command references in `CLAUDE.md` to
the `/lc:` namespace, and moves the old copied commands and hooks into
`.claude/_pre-plugin/` rather than deleting them. Its dry run is the default and prints
all of it first.

### How to remove it

```
/plugin uninstall lc@launch-control
/plugin marketplace remove launch-control
```

Then delete these, none of which anything else reads. Apart from the `.gitignore` lines
below, every file Launch Control creates in a repo is under `.claude/`:

```
.claude/launch-control.json           # the per-repo config
.claude/launch-control.local.json     # private notice, if you made one
.claude/.current-story                # the bound-story marker
.claude/.nudged                       # the Stop hook's once-per-story guard
.claude/lc-plan/                      # /lc:plan's proposal and resume state
.claude/lc-init/                      # /lc:init's ledger; ignores itself, so gitignore has no line for it
.claude/_pre-plugin/                  # only if you migrated with install.sh
```

And remove the four lines appended to `.gitignore`. `/lc:init` and `/lc:plan` add:

```
.claude/launch-control.local.json
.claude/.current-story
.claude/.nudged
.claude/lc-plan/
```

`install.sh` adds the same first three plus `.claude/_pre-plugin/`, so a repo that was
migrated may have five lines rather than four.

Two leftovers to know about. `install.sh` rewrote `CLAUDE.md` command references to
`/lc:next` and friends; that is not reverted for you, so fix them by hand if you care.
And removing `.claude/launch-control.json` alone is enough to silence Launch Control
even with the plugin still installed — both hooks open with
`[ -f launch-control.json ] || exit 0` and exit quietly without it.

### What happens to the board

**Nothing, unless you delete it.** The board is two ordinary Notion databases in your
own workspace, made of ordinary Notion properties and views. Nothing is encoded,
nothing is proprietary, and this project holds no copy of it. Uninstalling the plugin
does not touch it — it just stops anything reading or writing it.

To end it, delete the Launch Control page in Notion; everything inside goes with it.
To keep the data, Notion's own export gets it out as CSV or Markdown, though nothing
here re-imports it. Revoking the connector's access to that page (the same `···` →
**Add connections** menu that granted it) cuts the plugin off while leaving the board
intact.

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

v0.5.6, and honest about it: still pre-1.0, extracted from a working setup managing
five projects, and has one real user. The board is provisioned by `/lc:init`; projects on it are provisioned by `/lc:plan`.

What this is *not* is a tracker for the steps inside a story. Keep those wherever
your agent already keeps them. Launch Control tracks **stories**, and the one thing
it offers that nothing else does is the human-work critical path in `/lc:mine`: the
launch blockers no agent can do, ordered by how long the outside world takes to
answer. Persistence, a dependency graph and auto-promotion are plumbing in service
of that, not the reason to use it.

If you are wondering why this doesn't just defer to Claude Code's native Tasks: as
of **2026-09-17** those tools are not available by default on current models.
`TaskCreate`, `TaskList`, `TodoWrite` and the rest ship only on Claude 3.x, Opus
4.0–4.7, Sonnet 4.0–4.6 and Haiku 4.5, and need `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`
anywhere else. Don't plan around their being there. Sources, and the date that was
last checked, are in
[`docs/decisions/0001-native-tasks.md`](docs/decisions/0001-native-tasks.md).

MIT.
