# Changelog

Every released version, newest first.

Versions 0.1.0 to 0.5.9 were **reconstructed from git history** after the fact —
this file did not exist while they were being made. Each entry is derived from the
commits whose `plugins/lc/.claude-plugin/plugin.json` carried that version, so the
grouping is exactly what shipped under that number, not a later tidy-up. The date
is that version's last commit. Where a change came from a story on this project's
own board, the story ID is given, because the acceptance criteria for it are on the
board and this file is not the place to restate them.

The three version records — `plugins/lc/.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json` and the README's `## Status` line — always carry
the same version and move in the same commit. `python3 tests/check_version_sync.py`
enforces it; see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 0.15.0 — 2026-11-15

**A session can drop a bound story without shipping it.** (LC-B17)

- **Why.** `/lc:done` was the only exit from a bound story, and it is built to ship.
  Dropping one meant editing Notion by hand and deleting `.claude/.current-story`,
  and the Stop hook still nudged once about a story nobody was working on.
- **New skill `/lc:release <reason>`.** On a bound story it fetches every
  **Blocked by** page and sets Status back to `Ready`, or to `Backlog` when any
  blocker is not Done; appends a dated **Last session** line with the reason; and
  empties `.claude/.current-story` and `.claude/.nudged`. The branch, its commits
  and any uncommitted changes are left in place and reported by name. With no story
  bound it says so and changes nothing. A story `In Review` (an open PR) asks before
  it is released. **Started** is never touched, so an External clock keeps counting.
- **A skill, not a `/lc:start --abandon` flag.** Skills receive their arguments as
  free text and parse no flags; `/lc:start`'s argument is a story ID and this one's
  is a reason. A separate command is listed in the slash menu and the README table,
  and the Stop hook and SessionStart banner can name it.
- The Stop hook's nudge and the SessionStart banner for a bound session now mention
  `/lc:release` for work being dropped rather than paused. Neither hook nudges once
  the binding is empty; `tests/test_hooks.py` pins that, and that the README
  Commands table lists every skill.

---

## 0.14.0 — 2026-11-15

**Board reads stop growing with the project's Done history.** (LC-30)

- **Why.** The road view filters only on Project, so every Done story stays in it
  forever. On this project's board one read of it was 193,380 characters for 47
  rows, 44 of them Done, and `/lc:done`'s unblock step paged the whole board view -
  six pages, over two million characters - to find the few rows naming a blocker.
  Both grew with every story closed.
- **New per-project view `open`** (Project is this one, Status is not Done), in
  `board.json`, provisioned by `/lc:init` and `/lc:plan` (`plan.py config` now takes
  `--open`), printed by `init.py views --open`. `/lc:start` finds its story there
  and `/lc:reconcile` audits from it. Measured: about 8,000 characters, one page.
- **New shared view `dependents`** (Status is not Done, Blocked by is not empty,
  every project). `/lc:done` and `/lc:reconcile` read it to find what a closed story
  unblocks: 172,178 characters in one page. Closing a story shrinks both views.
  `board.json` filters gain `is_not_empty`, which `boardcheck.py` writes as
  `IS NOT EMPTY` and reads back from Notion's value-less leaf.
- **Unchanged on purpose:** `/lc:groom`'s ID allocation and duplicate check, and
  `/lc:doctor`'s duplicate-ID check, still read the road. They must see every ID
  ever issued, Done ones included, or an ID gets issued twice. `/lc:plan`'s
  prefix check still reads the unfiltered `board`.
- **Older boards.** `/lc:doctor` fails a config without `views.open` or
  `views.dependents` and names the view to create, with its exact `configure`
  line; `dependents` is created once per board and its URL added to every repo
  config on it. Until then each command says so and falls back to the old read.
  Doctor also reads `open` in full and fails a row from another project or a Done
  row.

---

## 0.13.0 — 2026-11-15

**`/lc:mine` projects an in-flight clock from the day it started, not from today.** (LC-29)

- **Why.** An In Progress clock was projected as if it started today, so a
  registration filed four weeks ago still showed its whole lead ahead of it, and
  the dates were late by exactly the time already waited.
- **New Stories property `Started`** (date) in `board.json`, so `/lc:init`
  provisions it. On an existing board `/lc:doctor` fails until it is added, and
  names the exact statement: `ADD COLUMN "Started" DATE COMMENT '...'` on
  `stories.dataSource` through update-data-source. The `yourTurn` view shows it.
  The DDL generation moved from `init.py` into `boardcheck.py` so doctor can print it.
- **`/lc:start`** sets Started to today on an External story whose Started is
  empty, and never overwrites one already there.
- **`mine.py`** reads Started from a view file (`Started` or `date:Started:start`)
  and from `--inline`, where it is a new allowed key; a malformed date exits 1. An
  In Progress clock with Started set runs each lead bound as
  `max(0, bound - days since Started)` through the blocker chain, and its row shows
  the start date and the days it has run. Past its lead max it prints
  `earliest finish overdue`, never a past date or a negative number. With Started
  blank it projects from today and says so, as before.
- The sample board has a started clock, and the mutation guard covers the
  elapsed-days subtraction.

---

## 0.12.0 — 2026-11-15

**`/lc:mine` no longer asks for an inline view page to be re-typed.** (LC-B16)

- **`mine.py --inline FILE`** takes a page of `yourTurn` that came back inline as
  `{"count", "hasMore", "rows"}`, where each row has only the ten fields `mine.py`
  reads. The count is checked, and an unexpected key, a URL with no page id, an
  unknown Status or Gating, a non-numeric lead day or a malformed `Blocked by` exits
  1 instead of ranking. `--view` is no longer required when the whole read was inline.
- This was the last command still saying to write an inline result "verbatim", left
  over from 0.11.0 (LC-B15).

## 0.11.0 — 2026-11-15

**No command asks for an inline Notion result to be re-typed into a file.** (LC-B15)

- **Why.** The tool saves a result to disk only when it is over the client's output
  limit. Under it, the result comes back inline, and `/lc:doctor` and `/lc:done` told
  the model to write it out "verbatim". In practice a 15 KB database fetch got
  trimmed, and the last page of a board read had to be hand-copied for `ids.py`. A
  mistyped value there can mean a false Clean or a missed promotion.
- **`ids.py` takes an inline page on the command line**:
  `--inline-page COUNT HAS_MORE` plus one `--row ID STATUS URL BLOCKERS` per row.
  These are short values that can be stated exactly. A count mismatch, a URL with no
  page id, a malformed blocker list, an unknown status or a bad `HAS_MORE` is a FAIL.
  `/lc:done`, `/lc:reconcile`, `/lc:start` and `/lc:groom` use it.
- **`doctor.py` views file**: `{"resolved": true}` for a shared view that is only
  checked to resolve, so nothing of it is copied. An inline `road` or `next` page must
  carry `count`, which is checked against its rows, and an explicit `hasMore`. The
  old count-less `rows` form is refused. `plan.py`'s board file uses the same form.
- **Database fetches**: an inline fetch is given as a text file with only its
  `<data-source-state>` and `<view>` blocks, the only parts read. The parser now
  fails on a view block that is opened but not closed, a block that does not parse,
  or a data-source state with no `schema` or `url`, where before a truncated copy
  could read as a board with one view fewer.
- `docs/troubleshooting.md` has a table of every input and its inline form.

## 0.10.0 — 2026-11-15

**`/lc:next` reads only this project's Ready stories.** (LC-28)

- **Every project gets a second view of its own, `next`**: Project is this one,
  Status is `Ready`, Agent can do this is checked, sorted by `Seq`. `/lc:next` reads
  it in view mode instead of the shared `ready` view, which holds every project's
  Ready rows. On a board with six projects one read of `ready` was 30 rows and about
  120 KB, past the tool's output limit.
- **`/lc:init` and `/lc:plan` create it beside the road view**, `init.py views --next`
  prints its `configure` line, `init.py check` verifies it, and `plan.py config`
  requires `--next` and never copies a sibling project's.
- **New config key `views.next`.** `/lc:doctor` FAILs a config without it, naming the
  view to create and its `configure` line, and FAILs a `next` view holding another
  project's stories or stories that are not Ready. An empty one is fine. Until a
  board from before 0.10.0 has it, `/lc:next` falls back to reading the road.
- `/lc:mine` still reads `yourTurn` across every project, on purpose: a clock in one
  project can block another. See `docs/notion-schema.md`.

## 0.9.1 — 2026-11-15

**A view's repair line now removes a filter the view should not have.** (LC-B14)

- **The `configure` line for a view with no filters starts with `CLEAR FILTER`.**
  Through the Notion MCP's update-view tool, a line with no `FILTER` clause leaves an
  existing filter in place. So the fix `/lc:doctor` named for the shared `board` view
  filtering on `Type`, the case that turned up on a live board, changed nothing.
  Checked on a throwaway board; the details are in `docs/troubleshooting.md`.
- **The FAIL says so too.** For such a view, `/lc:doctor` and `init.py check` both
  say to clear any filter it has. `init.py check`'s view FAILs now name the fix too,
  as `/lc:doctor`'s already did.

## 0.9.0 — 2026-11-15

**No command spends the free plan's metered query allowance.** (LC-25)

- **Every board read is now a saved view in view mode, or a `fetch` of one page.**
  On Notion's free plan, SQL and rows-mode queries share one metered workspace
  allowance and view mode has no quota ([Notion's MCP database tools
  reference](https://developers.notion.com/guides/mcp/tools-databases-reference),
  checked 2026-11-15). The old README claim that nothing here was metered was true
  of SQL and false of rows mode: five steps used it, and one ran on every story
  close. A grooming session hit `usage_limit_reached` on 2026-11-14.
- **New `ids.py`** (beside `doctor.py`) does the filtering those queries did, over
  saved view pages: `find` a story by ID, the `next` free ID in a sequence, the
  `dependents` of a page, and whether a prefix is free. It refuses to answer from a
  view that was not read to the last page, and matches page URLs by id, so an
  `app.notion.com/p/...` link and a `notion.so/...-Title-<id>` link compare equal.
- **Rewritten:** `/lc:start` step 2 and `/lc:groom` step 4 read `views.road`;
  `/lc:done` step 18 and `/lc:reconcile` step 6 read `views.board`, because a
  dependent can live in another project; `/lc:plan` step 6 reads `views.board` for
  the prefix and `notion-search` plus `fetch` for the key.
- **`views.board` must stay unfiltered** now that it answers board-wide questions.
  `/lc:doctor` already fails it if it is filtered.

---

## 0.8.0 — 2026-11-15

**`/lc:doctor` catches a board whose schema predates the plugin.** (LC-B12)

- **A full `/lc:doctor` run now compares the board with `board.json`**: every
  Stories and Projects property (present, right type, every select option, each
  relation pointing at the configured data source) and every view in the config
  (filter, sort, grouping, type; the road view against `projectPageId`). When
  `board.json` changes, existing boards do not, and until now that surfaced as a
  command misbehaving rather than as a named failure. The best-known case is a
  `yourTurn` view still filtering on `Type`.
- **Each failure carries its fix**: the view's `configure` line (what
  `init.py views` prints), or the `init.py ddl` command that prints a property's
  definition. Doctor reports; it does not change the board.
- **The session fetches the Stories and Projects databases once each** and passes
  them to `doctor.py` as `--stories` and `--projects`. A full run without them is a
  FAIL, not a pass. `--local-only` skips the comparison.
- **One comparison, two callers.** `init.py check`'s comparison moved into
  `plugins/lc/skills/doctor/boardcheck.py`, which both scripts import and which
  imports neither, so there is no import cycle. `unwrap_saved` moved with it.
- Added `tests/test_doctor.py` on `test_init.py`'s fixtures. The mutation guard's
  board mutations now target `boardcheck.py` and must be caught by both
  `test_init` and `test_doctor`, plus one mutation that skips doctor's comparison.

---

## 0.7.0 — 2026-11-14

**An iOS release kit: the release as one checked command.** (LC-20)

- **Added `plugins/lc/kits/ios-release/`**, generalised from the scripts one iOS
  app shipped 1.0 with and then hardened after. `archive.sh` bumps the build
  number, archives Release, exports, and checks the exported `.ipa` (build number
  in every bundle, required entitlements per bundle, secrets in the build tree),
  restoring the build number on any failure. `check-release-ready.sh` runs every
  check that needs no signing identity and reports all failures, not the first:
  the version file, `ExportOptions.plist`, `ITSAppUsesNonExemptEncryption`, the
  privacy manifest, the entitlements the project asks for, store copy against
  App Store Connect's limits, un-redacted log lines, and the build tree.
- **Everything app-specific is in `release.conf`.** Project directory and
  generate step (XcodeGen), scheme, bundles, required entitlements, log source
  directories and their allowlist, store copy fields. `install.sh` copies the
  scripts on every run and writes `release.conf`, `ExportOptions.plist` and
  `docs/store-copy.md` only when absent. Dry run by default.
- **Added `templates/stories.json`**: ten release stories in `/lc:plan`'s
  proposal format, each with `appliesWhen`, carrying the traps that cost real
  time - Transporter rather than Organizer, a new build number per upload, What's
  New absent at 1.0, the screenshot sizes, App Review sign-in for apps with
  accounts, Sign in with Apple under 4.8, a Sandbox-only APNs key, phased release
  for migrations. They pass `plan.py lint`.
- **Plists with `--` inside a comment are read the way Xcode reads them.** Found
  on the first real install: Apple's parser accepts it, Python's does not.
- Tested without a Mac in `tests/test_ios_release_kit.py`, including the shell
  scripts against a synthetic app repo.

## 0.6.0 — 2026-09-21

**A front door for someone who has never seen this repo.** (LC-17)

- **Added `setup.sh`**, the installer for a new machine. Checks `claude`,
  `python3`, `git`, `gh` and `gh auth status`; adds the Notion MCP server; adds
  the marketplace and installs the plugin through the `claude plugin` CLI when
  that CLI supports it, falling back to printing the two slash commands when it
  does not. Dry run by default; `--apply` does the automatable parts. Idempotent —
  a second `--apply` reports everything already done and changes nothing. It then
  prints the three steps no script can do (Notion's OAuth flow, sharing the Notion
  page with the connector, enabling auto-update) as work still outstanding, rather
  than claiming them.
- **Renamed `install.sh` to `migrate.sh`.** It was never the installer: it moves a
  repo off the older copied-files layout. `install.sh` is now a shim that explains
  the two scripts and exits non-zero, so the old name cannot be mistaken for a
  successful install.
- **Added a `## Quickstart` section to the README**, above the rationale rather
  than 270 lines below it. The existing depth sections are unchanged and now sit
  under it.
- **Added `docs/getting-started.md`, `docs/troubleshooting.md`,
  `CONTRIBUTING.md`, this changelog, and a bug-report issue template.**
  Troubleshooting names the three different ways a Notion connector can be
  half-set-up, and what every `/lc:doctor` failure means.
- **Said out loud that third-party marketplaces do not auto-update**, in the
  Quickstart and not only in troubleshooting. Official Anthropic marketplaces
  update themselves; this one does not, and every new user hits it.
- Tests: `setup.sh` parses under stock macOS `/bin/bash` 3.2, and a dry run
  against a throwaway `HOME` writes nothing to it.

## 0.5.9 — 2026-09-20

- **`git.enabled: false` now actually stops `/lc:done` shipping** rather than
  being documented as if it did. (LC-B9)
- **Version drift fails the build** instead of misleading a later reader:
  `tests/check_version_sync.py`, run as its own CI step. (LC-B10)
- `.claude/_pre-plugin/` is gitignored, as the migration script already assumed.

## 0.5.8 — 2026-09-20

- **`/lc:mine` prints the arithmetic** behind "start today" — the chain, the
  bounds and the slack subtraction — instead of a retelling of a number the reader
  cannot check. (LC-16)
- The README shows what `/lc:mine` actually prints, from a real run. (LC-12)

## 0.5.7 — 2026-09-20

- **Helper scripts fail as failures, not tracebacks.** An anticipated error is a
  `FAIL` line naming what to fix. (LC-B6)
- **Answered the questions a stranger asks before installing**: what leaves your
  machine, what it can do to your repo, how to remove it, what happens to the
  board. (LC-B7)
- **Tested the arithmetic the product is sold on**, including a mutation guard that
  fails the build if those tests stop catching a broken computation. (LC-B8)

## 0.5.6 — 2026-09-17

- Fixed the three places the repo contradicted itself. (LC-B5)

## 0.5.5 — 2026-09-17

- A filed clock is held to the clock it came from. (LC-14)
- The native-Tasks decision is dated to a primary source. (LC-15)

## 0.5.4 — 2026-09-16

- `clocks.json` widened past the Apple chain, so `/lc:mine` recognises external
  waits outside iOS releases. (LC-13)

## 0.5.3 — 2026-09-16

- `/lc:groom` no longer files human work where `/lc:mine` cannot see it. (LC-11)

## 0.5.2 — 2026-09-16

- Said what this costs before someone installs it — the prerequisites table, and
  what each missing piece breaks. (LC-10)

## 0.5.1 — 2026-09-15

- `/lc:mine` no longer crashes on saved list-form results. (LC-07)
- The drift check stopped refusing every repo it was meant to migrate. (LC-08)
- The installer fails cleanly instead of leaving a repo half-migrated: every
  dependency is validated before the first write. (LC-09)

## 0.5.0 — 2026-09-14

- **Added `/lc:init`**, which provisions the whole board — both databases, every
  property, all seven views — from one command, then checks what it built against
  the schema. (LC-02)
- The installer refuses to run in a repo something else is working in. (LC-B1)
- The installer parses on stock macOS `/bin/bash` 3.2. (LC-06)
- Documented the hook-merge ambiguity and the policy model rather than guessing at
  it. (LC-B2)
- The installer stops deleting hooks it did not install. (LC-B3)
- Said which readers actually merge `launch-control.local.json`. (LC-B4)

## 0.4.0 — 2026-09-13

- **`/lc:mine` ranks by computed lead days** — projected finish dates and slack —
  instead of by eye. This is the feature the project exists for. (LC-04)
- Decided what to cede to Claude Code's native Tasks, recorded in
  [`docs/decisions/0001-native-tasks.md`](docs/decisions/0001-native-tasks.md).
  (LC-01)

## 0.3.0 — 2026-09-13

- **Added `/lc:plan`**, which turns a design doc or an existing repo into a project
  and its whole backlog, checks every claim against the repo, adds the external
  clocks the doc never mentions, and files nothing until you confirm. (LC-05)

## 0.2.0 — 2026-09-12

- **Added `/lc:doctor`**, which catches a config that has silently regressed: view
  keys, road scoping, base branch, duplicate story IDs, notices naming finished
  stories. Exits non-zero on any. (LC-03)

## 0.1.0 — 2026-09-08

- **Extracted Launch Control from a working setup into a distributable Claude Code
  plugin**: the `lc` plugin, its marketplace manifest, and a migration script for
  repos still carrying copied command and hook files.
- The drift check is based on a recorded baseline rather than on `HEAD`, so "you
  edited this locally" is distinguishable from "the plugin moved on".
- The migration script stopped clobbering other tools' commands, and two silent
  gaps were closed.
- Launch Control started tracking itself on its own board.
