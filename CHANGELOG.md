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
