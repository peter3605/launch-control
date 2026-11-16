---
name: doctor
description: Check this repo's Launch Control config and board scoping for regressions that fail silently
argument-hint: [repo path, optional]
---

Check that this repo's Launch Control setup still works. Every check here is a failure that actually happened and stayed invisible until someone tripped on it: view keys that vanished from one repo, a `baseBranch` of `main` in a repo whose default is `master`, notices naming finished stories as if they were still in flight, one Story ID on two rows, and a board provisioned by an older plugin whose properties or view filters no longer match `board.json`.

The checks live in `doctor.py`, in this skill's base directory. It sets the exit code, so the verdict is the script's, not yours. It cannot reach Notion, so you query the views and hand it the results.

If the user passed a repo path, check that repo instead of this one: use its `.claude/launch-control.json` and pass `--repo <path>` below. Checking another repo is reading, not working in it. Do not fix anything there without asking.

1. Read `.claude/launch-control.json`. Note which of the ten `views` keys are present — `ready`, `inProgress`, `inReview`, `waitingExternal`, `yourTurn`, `board`, `dependents`, `road`, `next`, `open`.
2. Query each present view in **view mode**, never SQL mode (SQL is billed).
   - For the seven shared views, one page is enough: set `page_size` to 1. Only whether it resolves is checked.
   - Read `next` in full (it is small: this project's Ready stories). Every row must carry this prefix and be Ready.
   - Read `open` in full, every page (this project's stories that are not Done). Every row must carry this prefix, and none may be Done.
   - Page `road` to the end with `start_cursor` until `has_more` is false. The duplicate check needs every row, Done ones included - this is one of the reads that must not move to `open`.
3. Write a JSON file in your scratchpad, keyed by view name, describing the results. Each value is one page or a list of pages, and each page is exactly one of:
   - `{"error": "<the error text>"}` — the query failed.
   - `{"file": "<path>"}` — the tool saved the result to disk because it was large. Use that path.
   - `{"resolved": true}` — a shared view's result came back inline. Its rows are never inspected, so nothing of it is copied. Not accepted for `road`, `next` or `open`.
   - `{"count": <rows on the page>, "rows": [["APP-1", "Done"], ...], "hasMore": <true|false>}` — a `road`, `next` or `open` page came back inline. State how many rows it held, and each row's Story ID and Status (blank IDs as `""`), in order; `count` is checked against `rows`, so a dropped row is a FAIL rather than a hidden duplicate. Nothing else of the row is needed.
4. **Fetch** the Stories database (`stories.database`) and the Projects database (`projects.database`) — one `fetch` each, not a query. If the tool saved a result to disk because it is large, use that path. If it came back inline, write a text file holding **only** its `<data-source-state>…</data-source-state>` block and its `<view …>…</view>` blocks, each copied exactly as returned: those are the only parts the script reads, so the prose, option URLs and SQL table are not copied. The script fails loudly on a block that is cut short or does not parse.
5. Run `python3 <base directory>/doctor.py --views <views file> --stories <stories fetch> --projects <projects fetch>` (add `--repo <path>` if checking another repo). Show its output as it printed.
6. Report the exit status plainly. For each `FAIL`, say what fixes it — and do not fix it unprompted, including on the board: a property or view that does not match `board.json` is reported with the fix the script prints (the `configure` line for a view, from `init.py views`; the property's definition, from `init.py ddl`), and changing the board's schema is the user's call. A missing view key needs the view URL from the board; a missing `next` is a board from before 0.10.0, and a missing `open` or `dependents` one from before 0.14.0; each FAIL names the view to create and its `configure` line. `dependents` is shared, so it is created once per board and its URL goes into every repo config on that board. A notice naming a Done story is either stale ("until that lands", about something that landed), which means rewriting what is now true, or a citation of a fact that still holds, which means stating the fact without the ID; read the passage before deciding which. A duplicate Story ID needs a human to decide which row is real.

`--local-only` skips the board, including the schema comparison, and checks only the config and git. Use it when Notion is unreachable, and say the board was not checked — a partial run is not a clean bill of health.
