# Troubleshooting

Failures with names. Find the symptom, not the cause — the cause is the part you
do not know yet.

Two things to reach for before anything else:

```
/lc:doctor              # in the affected repo: what has silently regressed
claude mcp list         # is the `notion` server configured, and does it connect
```

---

## The Notion connector: three different half-set-up states

This is the single largest category, and the reason is that **connecting Notion is
three steps, and stopping after any one of them leaves a different symptom.** They
look similar and are fixed in completely different places, so the first job is
telling them apart.

| Symptom | Which step is missing | Where the fix is |
|---|---|---|
| Claude Code has no Notion tools at all | 1. Server not configured | Your machine (`claude mcp add`) |
| Notion tools exist; calls fail with an auth or permission error | 2. Not authorised | Your browser (OAuth) |
| Notion tools exist; calls succeed and return **nothing** | 3. Page not shared | The Notion UI |

### 1. Connector not added

**Symptom.** The session has no Notion tools whatsoever. `/lc:init` stops at
pre-flight and says the Notion connector is not installed or not enabled. Nothing
Launch Control does works, because there is no local or offline mode — every
command reads or writes the board through Notion's MCP tools.

**Check.**

```
claude mcp list
```

There is no line whose server name is `notion`.

**Fix.**

```
claude mcp add --transport http notion https://mcp.notion.com/mcp --scope user
```

`--scope user` makes it available in every repo rather than just this one.
`./setup.sh --apply` does this for you.

The commands look the server up **by the name `notion`**. If you already have the
Notion connector under a different name, either rename it or add it again under
this one — `setup.sh` will tell you if it sees a similarly-named server.

### 2. Added but not authorised

**Symptom.** The Notion tools are present, but calls fail. The error is about
authentication, an expired token, or permission — not about an empty result.
`claude mcp list` may show the server as not connected.

Adding the server is **configuration**. It is not access. This step is what grants
access, and it cannot be scripted: it is a browser flow.

**Fix.** Either:

```
claude mcp login notion
```

or run `/mcp` inside Claude Code and complete Notion's OAuth flow in the browser.

If it was working and stopped, the grant has probably expired or been revoked —
the same command re-authorises it.

### 3. Authorised but the page is not shared

**This is the one that wastes an afternoon.** Everything reports healthy. The
connector is connected. Tool calls succeed. They just return nothing, or find
nothing, and `/lc:init` cannot see the page you named.

**Notion connectors see only the pages you explicitly share with them.** A
connected connector with no shared pages is a connector with access to an empty
workspace, and Notion reports that as success, because from Notion's point of view
it is.

**Fix.** In Notion, open the page the board lives (or will live) under:

> `···` menu → **Add connections** → the Notion connector

Access cascades to everything inside that page, so sharing the parent is enough —
you do not need to share each database.

**If the board already exists and commands suddenly return nothing**, check this
first. Revoking a connector's access to a page is done through the same menu, and
it is easy to do by accident while tidying up integrations.

---

## A stale plugin version

**Symptom.** A command behaves like a version you no longer have: a bug you read
was fixed is still there, a flag in the docs is not recognised, `/lc:doctor`
checks something the README says it stopped checking. The `## Launch Control
v0.0.0` banner at the top of a session shows a version older than the one on
GitHub.

**Cause.** **Third-party marketplaces do not auto-update.** Official Anthropic
marketplaces do; this one is not one of them. Unless you turned auto-update on,
the plugin sits at whatever version you installed, indefinitely. This is not
obvious, it is not your fault, and it is the single most common reason this
project's behaviour and its README disagree.

**Fix, in order.**

1. **Update now:**

   ```
   claude plugin update lc@launch-control
   ```

   Or `/plugin` → Marketplaces → `launch-control` → Update.

2. **Reload without restarting** — new plugin code is picked up at session start,
   so an update mid-session does nothing until:

   ```
   /reload-plugins
   ```

   Restarting Claude Code has the same effect.

3. **Turn auto-update on, so this does not happen again:**

   `/plugin` → Marketplaces → `launch-control` → **Enable auto-update**, or set
   `"autoUpdate": true` for this marketplace under `extraKnownMarketplaces` in
   your settings.

**Check what you actually have:**

```
claude plugin list --json
```

Look for the `lc@launch-control` entry and its `version`.

---

## `gh` is not authenticated

**Symptom.** Everything works until `/lc:done`, which fails at the push, the PR, or
reading the check rollup.

`gh` is used by `/lc:done` and by nothing else. The board, `/lc:next`, `/lc:mine`,
`/lc:start` and `/lc:doctor` are all unaffected.

**Check.**

```
gh auth status
```

Read its output rather than just its exit code — it says which host, which account,
and which scopes, and that is usually the whole fix.

**Fix.**

```
gh auth login
```

**If you do not want Launch Control shipping code at all**, that is a supported
configuration and a better answer than half-working `gh`: set `"enabled": false`
in the `git` block of `.claude/launch-control.json`. `/lc:done` then verifies the
story and records it, but makes no commit, no push and no PR, leaving the change in
your working tree. See [config-reference.md](config-reference.md).

---

## `python3` is not on `PATH`

**Symptom, and the reason this one is nasty: the hooks fail *quietly*.** Every
skill shells out to `python3`, and so do both hooks, `setup.sh` and `migrate.sh`.
The hooks are written never to fail a session — any error exits 0 silently — so
without `python3` you get no `SessionStart` banner, no story binding, no `Stop`
nudge, and no error message saying why.

**Check.**

```
python3 -V
```

**Fix.** Install Python 3 and make sure the executable is named `python3` on
`PATH`. A `python` that is Python 3 is not enough; nothing here looks for that
name.

`./setup.sh` stops and names this. `./migrate.sh` stops at step 0 rather than
half-migrating a repo.

**Related symptom:** no `## Launch Control` banner at the top of a session in a
repo you believe is tracked. Two causes, and it is worth ruling out the cheaper one
first — both hooks open with `[ -f launch-control.json ] || exit 0`, so a **missing
or untracked `.claude/launch-control.json`** produces exactly the same silence.
Check that the file exists and, on a fresh clone, that it was committed.

---

## The hooks do nothing

**Symptom.** No `## Launch Control` banner at the start of a session, no story
binding, no `Stop` nudge — and no error. The hooks are written never to fail a
session, so every cause below looks identical. Rule them out in this order.

1. **An unsupported platform — native Windows.** Launch Control supports macOS and
   Linux, including WSL. Both hooks are bash scripts that call `python3`; on native
   Windows the plugin installs and the hooks then do nothing, silently. Claude
   Code's docs say it runs command hooks through Git Bash on Windows, or through
   PowerShell when Git Bash is not installed (checked 2026-11-15, [hooks
   reference](https://code.claude.com/docs/en/hooks)). Whether these hooks work
   under Git Bash is **untested**, and under PowerShell they cannot. Check with
   `uname -s` in the shell you launch Claude Code from: anything other than
   `Darwin` or `Linux` (for example `MINGW64_NT-…`, `MSYS_NT-…`, `CYGWIN_NT-…`) is
   this. `./setup.sh` refuses on those and names the platform. **Fix:** run Claude
   Code inside WSL.
2. **`python3` is not on `PATH`** — see [the section above](#python3-is-not-on-path).
3. **No committed `.claude/launch-control.json`** in this repo. Both hooks open with
   `[ -f launch-control.json ] || exit 0`.

---

## What each `/lc:doctor` failure means

`/lc:doctor` exits non-zero if any check fails. Every check in it was a real
failure that went unnoticed until someone tripped on it, which is why the wording
is blunt.

### Config file

| It says | What it means |
|---|---|
| `.claude/launch-control.json not found` | This repo is not on the board. Run `/lc:init` (first repo) or `/lc:plan` (any repo after). |
| `... is not valid JSON - truncated or half-written?` | An edit left the file broken. The line and column are in the message. |
| `... must be an object, not list` | The file parses but holds the wrong shape — usually a stray `[` at the top. |
| `launch-control.local.json must be an object` | Same, for the private-notice file. Its only expected key is `notice`. |
| `no prefix - every command filters on it` | Without `prefix`, every board query returns other projects' stories. Set it to this project's story-ID prefix. |

### Views

| It says | What it means |
|---|---|
| `missing view keys: ...` | `views` is missing one of the eight the commands read. `/lc:init` writes all eight; a hand-edited config is the usual cause. |
| `views.next is missing - a board provisioned before 0.10.0 ...` | This project has no `next` view, the one `/lc:next` reads (its Ready, agent-doable stories). Until it does, `/lc:next` falls back to reading the whole road. Create a table view on the Stories database with the name and `configure` line the message gives, and add its URL to `views.next`. |
| `views.X points at a database other than stories.database` | A copied-and-pasted URL from a different board. Every view must belong to the Stories database named in the same config. |
| `views.X has no ?v= view id - it opens the database, not a view` | The URL was copied from the database page rather than from a specific view, so it ignores that view's filters. This is how a "scoped" query quietly stops being scoped. |
| `views.X was not queried - a check that did not run is not a pass` | The session skipped a view when gathering results. Re-run `/lc:doctor`. |
| `views.X did not resolve: ...` | The query itself failed. The message is Notion's. Often a deleted view, or the connector losing access to the page — see the three connector states above. |

### The road view — this project's own scoping

| It says | What it means |
|---|---|
| `views.road returned zero rows - a scoping bug reads exactly like a clean board` | The most dangerous result in the whole tool. An empty backlog and a broken filter are indistinguishable from the output, so this is always a failure. Open the road view in Notion and check its filter. |
| `views.road was not read to the last page - duplicates cannot be ruled out` | The result was paginated and only the first page was read, so the duplicate check below could not run honestly. |
| `views.road returned Story IDs outside PREFIX-` | The road view is not filtered to this project. It is meant to show one project alone; a shared browse view must never be substituted for it. |
| `views.next returned Story IDs outside PREFIX-` | The next view is not filtered to this project, so `/lc:next` would hand out another repo's work. Fix its filter with the line `init.py views --next` prints. |
| `views.next returned stories that are not Ready` | The next view lost its Status filter. Same fix. An empty next view is fine: nothing is Ready. |
| `Story ID on more than one row` | Two stories carry the same ID. Every command that looks a story up by ID will now find the wrong one roughly half the time. Fix it on the board. |

### Board schema against board.json

When the plugin's `board.json` changes, a board that is already provisioned does
not change with it. These checks compare the board this repo is on with
`plugins/lc/skills/init/board.json`, with the same code `/lc:init` uses to verify a
board it has just built. The session fetches the Stories and Projects databases
once each for them. Doctor reports these and never changes the board: what to do
about a schema difference is your call.

| It says | What it means |
|---|---|
| `Stories: property 'X' is missing - fix it on the board ...` (or `Projects:`) | The board has no property of that name, or it was renamed. Commands that read or write it will fail or quietly skip it. Add it in Notion with the type and options in `board.json`; the `init.py ddl` command named in the message prints every property's definition. |
| `Stories: 'X' is 'text', not 'select'` | The property exists with a different type. Notion cannot convert every type cleanly, so check the existing values before you change it. |
| `Stories: 'X' is missing options A, B` | A select is missing options that `board.json` (and the commands) use. For `Status` this means `/lc:done` or `/lc:start` would set a value that does not exist. Add the options, or rename the ones that were renamed. |
| `Stories: 'X' relates to '...', not projects` | A relation points at a different data source from the one in the config. Usually a board copied or duplicated in Notion, where the relation still points at the original. |
| `views.X ('Name'): filter is [...], not [...] - fix: configure it as ...` | The view filters on something `board.json` does not, or misses something it does. The best-known case is `yourTurn` still filtering on `Type`, on boards built before that filter was dropped: human work typed anything but Launch Blocker is hidden from `/lc:mine`. Set the view's filter to the `configure` line in the message; `init.py views` prints every view's line. Do not retype stories to suit an old filter. A filter on `board` matters as much: since 0.9.0 `/lc:done`, `/lc:reconcile` and `/lc:plan` read it as the board-wide view (dependents in other projects, whether a prefix is free), so a filter there silently drops rows from those answers. For `board`, which `board.json` gives no filter, the line starts with `CLEAR FILTER`, and the message says to clear any filter the view has: keep it, because a line with no `FILTER` clause leaves an existing filter in place (see [Repairing a view's filter](#repairing-a-views-filter)). |
| `views.X ('Name'): sort is [...], not [...]` / `not grouped by 'Status'` / `type is ...` | Same fix, the same `configure` line. A view out of `Seq` order makes `/lc:next` pick the wrong story. |
| `views.X: ... is not a view of the Stories database` | The view in the config does not appear in the database fetch. It was deleted, or it belongs to another database. |
| `views.road ...: filter is ...` | The road view is not filtered to this project's row (`projectPageId`). The message carries the `init.py views --road` command that prints its `configure` line. |
| `views.next ...: filter is ...` | The same for the next view. `init.py views --next` prints its line. |
| `skip views.road filter - no projectPageId in the config` | There is no `projectPageId` to compare the road's filter with. Not a failure; the road's prefix check above still runs. |
| `stories: ... is data source X, but stories.dataSource is Y` | The fetch is of a different database from the one the config names. Re-run `/lc:doctor`, fetching `stories.database` and `projects.database` from this repo's config. |
| `board schema was not checked - pass --stories and --projects` | The session ran a full check without the two database fetches. Re-run `/lc:doctor`. |

#### Repairing a view's filter

How the Notion MCP's update-view tool treats a `configure` line, checked on a
throwaway board on 2026-11-15 (LC-B14), never on a live one:

- A line with **no** `FILTER` clause leaves the view's existing filter in place. A
  board view filtered on `Type = Launch Blocker`, updated with `GROUP BY "Status";
  SORT BY "Seq" ASC`, kept its Type filter.
- `CLEAR FILTER` removes it. The same update with `CLEAR FILTER;` in front left the
  view unfiltered, and a fetch of the view afterwards confirmed it.
- A `FILTER` clause replaces the whole filter rather than adding to it, and `SORT BY`
  replaces the sorts the same way. So a view `board.json` gives filters is repaired
  by its `configure` line as printed.
- create-view accepts `CLEAR FILTER` on a new view, so `/lc:init` creates `board`
  from the same line.

That is why the `configure` line for a view with no filters (today only `board`)
starts with `CLEAR FILTER`. If you repair such a view in the Notion UI instead,
remove the filter in its filter menu.

### Git

| It says | What it means |
|---|---|
| `git is not on PATH, but git.enabled is not false` | Install git, or set `"enabled": false` in the `git` block if you want the board without the shipping. Distinguished from the next line deliberately — they used to arrive as the same message and sent people to fix the wrong thing. |
| `not a git repository, but git.enabled is not false` | You are in a directory that is not a git repo. Same two fixes. |
| `could not determine the default branch (no reachable origin, no origin/HEAD)` | The remote could not be reached and there is no cached `origin/HEAD`. Usually offline, an SSH key needing a passphrase, or no remote at all. Not fatal to anything but this check. |
| `git.baseBranch is 'master' but the default branch is 'main'` | Your config targets a branch the host no longer treats as default — typically after a rename. `/lc:done` would open PRs against the wrong branch. Update `git.baseBranch`. |

### Standing notices

| It says | What it means |
|---|---|
| `... names Done stories LC-00 - reword it as a standing fact, or drop it` | A `notice` or `git.notes` entry still says "until X lands" about something that landed. Notices are read as current fact at the start of every session, so a stale one actively misinforms. |
| `... names LC-00, which the road view does not have` | The notice refers to a story ID that is not on this project's road — a typo, or a story from another project. |
| `skip ... whether they are Done needs the board` | You ran `--local-only`. Not a failure; that check simply did not run. |

A `skip` line is never a failure. `ok` lines are printed for checks that passed,
and they are worth reading in a bug report — which checks passed narrows a problem
as fast as which failed.

---

## When a Notion result comes back inline

The tool saves a Notion result to disk only when it is over the client's output
limit, and that limit differs between Claude Code versions and hosts. Under it, the
result comes back inline in the conversation, and the scripts cannot read the
conversation. No command asks for an inline result to be re-typed whole into a file,
because a hand copy of 15 KB gets trimmed, and a mistyped value can produce a false
Clean. Instead, each input has a short form that can be stated exactly and is checked
loudly (LC-B15):

| Input | Read by | Inline form |
|---|---|---|
| A page of a view (`board`, `road`) for an ID lookup or dependents | `ids.py` (`/lc:done`, `/lc:reconcile`, `/lc:start`, `/lc:groom`) | `--inline-page COUNT HAS_MORE` plus one `--row ID STATUS URL BLOCKERS` per row. A count that differs from the rows, a URL with no page id or a malformed blocker list is a FAIL. |
| A shared view's page, only checked to resolve | `doctor.py` | `{"resolved": true}`: nothing is copied. |
| A `road` or `next` page | `doctor.py`, `plan.py` | `{"count": N, "rows": [[ID, Status], ...], "hasMore": bool}`. `count` must match. |
| The Stories or Projects database fetch | `doctor.py`, `init.py check` | A text file with only the `<data-source-state>` and `<view>` blocks, copied exactly. A block that is opened but not closed, or does not parse, is a FAIL. |

Do not try to force results onto disk by changing `page_size`. Whether a result is
saved depends on the client, not on the plugin.

## Setup and migration scripts

**`install.sh` prints a message and exits 2.** That is correct and deliberate. It
is a signpost, not a script: `./setup.sh` sets up a machine, `./migrate.sh <repo>`
moves an old repo off the copied-files layout. The migration script was called
`install.sh` until 0.6.0.

**`./migrate.sh --apply` refuses, changing nothing.** It refuses while the target
repo has a story bound in `.claude/.current-story`, or uncommitted changes under
`.claude/` or to `.gitignore`. A live session editing the same files once undid the
ignore lines it had just written and swept a private file into git. Finish or
unbind the story, commit or stash the changes, and re-run.

**`./migrate.sh` reports local edits and refuses.** Commands under `.claude/` were
edited locally after being copied from an older plugin version. They are not
deleted — step 4 moves them to `.claude/_pre-plugin/` so you can diff them at your
leisure. Propagate anything worth keeping back into the plugin before applying.

**A script fails to parse on macOS.** Stock macOS `/bin/bash` is 3.2. Check with
`/bin/bash -n <script>`, not with whatever `bash` is on your `PATH` — on a machine
with Homebrew bash those are different programs. See [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Still stuck

Open an issue with [the bug template](../.github/ISSUE_TEMPLATE/bug.md). It asks
for the plugin version from the `SessionStart` banner, your Claude Code version,
your OS, and the full `/lc:doctor` output. Those four answers are what separate a
stale plugin from a regressed config, which is most of what lands here.

This repository is public — redact real Notion IDs, spend figures and account
state before pasting.
