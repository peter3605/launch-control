---
name: init
description: Provision a new Launch Control board in Notion - both databases, every property and view - and put this repo on it
argument-hint: [empty Notion page URL] [--key <project key>] [--prefix <PREFIX>] [--new-board]
---

Provision a Launch Control board from nothing, and put this repo on it as the first project.

This creates the **board**: the Projects and Stories databases, every property in `docs/notion-schema.md`, and the six shared views. Then, as `/lc:plan` does for every later repo, it creates this repo's Projects row, its `road` view and `.claude/launch-control.json`. When it finishes, `/lc:groom` and `/lc:next` work with no visit to the Notion UI. A second repo joins the same board with `/lc:plan <doc or repo> --board <this repo>/.claude/launch-control.json`, not by running init again.

The deterministic parts live in `init.py` in this skill's base directory, and its exit code is the verdict, as with `doctor.py`. `board.json` beside it is the board: the DDL and view configs are generated from it, and `init.py check` compares what Notion reports back against the same file. Never hand-write DDL or a view filter - take them from `init.py` verbatim, so what is checked is what was asked for.

Three things make this go wrong quietly:

- **A second board.** Two boards split one person's work in two, and each looks complete. Preflight refuses if a sibling repo is already on a board.
- **A half-built board that looks finished.** A view with the wrong filter still resolves. That is why every object is read back and checked, not assumed from a successful create.
- **Notion IDs in a public repo.** The run's ledger lives in `.claude/lc-init/`, which ignores itself. Say what the config holds before anyone commits it.

## 0. Pre-flight - reads only

Stop at the first failure and say which check failed.

0. **Is Notion actually reachable?** Do this before anything else, including the repo
   checks - it is the one prerequisite that cannot be fixed from inside this repo, and
   the failure it produces later is an opaque tool error rather than a diagnosis. Fetch
   the connected workspace (`fetch` with id `self`). If that call is unavailable or
   errors, **stop and write nothing** - no Notion objects, no `.claude/lc-init/`, no
   config. Say which of the two it was, because the fix differs:
   - **No Notion tool in this session at all.** The connector is not installed or not
     enabled. Say so in those words - name the Notion connector, do not relay a raw
     "tool not found". Tell them to check with `claude mcp list` and point at the
     prerequisites section of the README.
   - **The tool is there but the call fails or returns nothing.** The connector is
     installed but not authorised, or it has been given no access to any page. Say
     which is likelier from the error, and that the fix is in Notion (`···` >
     Add connections on the parent page) or the OAuth flow in `/mcp` - not in this repo.

   There is no way for a skill to ask Claude Code whether an MCP server is connected,
   so this call *is* the check. Do not skip it on the grounds that a later step would
   fail anyway: a later failure happens after the run has started writing.

   Repeat this fetch if the user fixes something and asks to continue; do not carry a
   stale pass forward from earlier in the session.
1. **Target repo** is this session's project directory. Run `python3 <base directory>/init.py preflight --repo <target>` (add `--new-board` only if the user passed it). A FAIL means stop; relay its line. If it reports an earlier run, go to **Resuming**.
2. **The parent page.** If the user passed a page URL, fetch it. It must resolve, and it must hold no database - a page that already has a Stories or Projects database is a board, and init does not build a second one on top of it. With no URL, propose creating a private workspace-level page titled `Launch Control` (draft mode) and say it can be moved later.
3. **Key and prefix.** Key: `--key`, or the repo directory name, lowercased. Prefix: `--prefix`, or 2-6 capitals drawn from the key. On a brand-new board nothing can collide, so there is nothing to query.
4. **Present the plan and ask for confirmation.** Name the parent page, the two databases, the six shared views by name (from `init.py views`), the Projects row and `Road — <key>` view, and the config path. **Write nothing to Notion or to the repo until the user confirms.**

## 1. The board

`STATE` is `<target>/.claude/lc-init/state.json`. Record each object the moment it exists, before creating the next - that record is what lets a failed run resume instead of leaving an orphan board behind. If any step fails, stop and say exactly what now exists (with URLs) and that re-running `/lc:init` resumes.

5. **The hub page.** If step 2 proposed creating one, create it now. Either way, record it: `init.py record --state STATE --key hub --url <page URL>`.
6. **Projects database.** Create it under the hub page, title `Projects`, with `schema` set to the output of `init.py ddl projects`. Record: `init.py record --state STATE --key projects --url <database URL> --data-source <its collection:// URL>`.
7. **Stories database.** Create it under the hub page, title `Stories`, with `schema` from `init.py ddl stories --projects-ds <Projects data source>`. Record it as `stories` the same way.
8. **Blocked by.** A self-relation needs the Stories data source to exist, so it is added second: update the Stories data source with `statements` from `init.py ddl blocked-by --stories-ds <Stories data source>`. Record: `init.py record --state STATE --key blockedBy --url <Stories data source>`.
9. **The six shared views.** For each entry `init.py views` prints, create a view with `database_id` = the Stories database, `data_source_id` = its data source, and `name`, `type` and `configure` exactly as printed. Record each: `init.py record --state STATE --key views.<key> --url <view URL or view:// URI>`. If the create result names no view id, fetch the Stories database and take the id of the view with that name.
10. **Check the board.** Fetch the Stories database and the Projects database. Each result must reach the script as the tool returned it: a large one is already saved to disk, so use that path; a small one came back inline, so write it verbatim to a file in your scratchpad. Run `init.py check --state STATE --stories <file> --projects <file>`.
    - A view FAIL: update that view with the `configure` from `init.py views` (prefix `CLEAR FILTER; CLEAR SORT;` so nothing stale survives), fetch that one view, and re-run the check with `--view <that fetch>` added. Twice without a clean result: stop and report the line.
    - A property FAIL: stop and report it. Do not patch a property by hand; the DDL is the fix, and a mismatch means the DDL and Notion disagree about something `board.json` needs to learn.

## 2. This repo's project

11. **Projects row.** Create a page in the Projects data source: `Name` and `Key` = the key, `Repo` = the target's absolute path. Record: `init.py record --state STATE --key project --url <page URL>`.
12. **Road view.** `init.py views --road --key <key> --project-url <project page URL>` prints one view; create it as in step 9 and record it with `--key road`. Query it in **view mode** (never SQL mode - SQL is billed): it must resolve and return **zero** rows. A row means the filter is wrong - stop.
13. **Re-check the road.** Fetch the road view (`view://<id>`), save it as in step 10, and re-run `init.py check` with the same two database files plus `--view <road fetch>`. A database fetch taken before the road existed does not list it; the `--view` file fills that in, and the check now covers the road filter too.
14. **Write the config.** `init.py board --state STATE --out <scratchpad>/lc-init-board.json`, then `python3 <base directory>/../plan/plan.py config --repo <target> --from <scratchpad>/lc-init-board.json --project <key> --prefix <PREFIX> --project-page <project page URL> --road <road URL>`. It writes every view key, stamps `installedVersion`, reads `baseBranch` from the remote, sets `autoMerge` false until the owner decides otherwise, and gitignores the local files.
15. Run `python3 <base directory>/../doctor/doctor.py --repo <target> --local-only`. The one failure to expect is a repo with no reachable `origin`: say so, and that `git.baseBranch` needs checking before the first `/lc:done`. A full `/lc:doctor` fails on an empty road by design until the first story is filed.

## 3. Report

- The hub page, both databases and all seven views, as links.
- `init.py check`'s last line, as printed.
- The config path, and whether to commit it: yes for a private repo, so a fresh clone works (the hooks silently do nothing without it); no for a public one, where the board's IDs should stay out of history.
- What comes next: `/lc:plan <design doc or this repo>` to file the whole backlog, or `/lc:groom <item>` for one story. Another repo joins this board with `/lc:plan <doc or repo> --board <target>/.claude/launch-control.json`.
- `.claude/lc-init/` can be deleted once `/lc:doctor` is clean.

## Resuming

If `STATE` exists, an earlier run stopped part way. Do not start over - that is how a workspace ends up with two boards.

- Read `STATE` and tell the user what the earlier run got through.
- For every key present, fetch the object and confirm it still exists (a database or page that was deleted in the UI means asking the user, not recreating silently). Skip creating it.
- Continue from the first step whose key is missing: `hub` 5, `projects` 6, `stories` 7, `blockedBy` 8, any missing `views.*` 9, then the check in 10; `project` 11, `road` 12; a config already written for this project is reported as such by `plan.py config`.
