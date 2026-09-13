---
name: doctor
description: Check this repo's Launch Control config and board scoping for regressions that fail silently
argument-hint: [repo path, optional]
---

Check that this repo's Launch Control setup still works. Every check here is a failure that actually happened and stayed invisible until someone tripped on it: view keys that vanished from one repo, a `baseBranch` of `main` in a repo whose default is `master`, notices naming finished stories as if they were still in flight, and one Story ID on two rows.

The checks live in `doctor.py`, in this skill's base directory. It sets the exit code, so the verdict is the script's, not yours. It cannot reach Notion, so you query the views and hand it the results.

If the user passed a repo path, check that repo instead of this one: use its `.claude/launch-control.json` and pass `--repo <path>` below. Checking another repo is reading, not working in it. Do not fix anything there without asking.

1. Read `.claude/launch-control.json`. Note which of the seven `views` keys are present — `ready`, `inProgress`, `inReview`, `waitingExternal`, `yourTurn`, `board`, `road`.
2. Query each present view in **view mode**, never SQL mode (SQL is billed).
   - For all but `road`, one page is enough: set `page_size` to 1. Only whether it resolves is checked.
   - Page `road` to the end with `start_cursor` until `has_more` is false. The duplicate check needs every row.
3. Write the results to a JSON file in your scratchpad, keyed by view name. Each value is one page or a list of pages, and each page is exactly one of:
   - `{"error": "<the error text>"}` — the query failed.
   - `{"file": "<path>"}` — the tool result was saved to disk because it was large. Use that path; do not transcribe it.
   - `{"rows": [["APP-1", "Done"], ...], "hasMore": false}` — the result came back inline. Copy **every** row's Story ID and Status exactly, blank IDs as `""`, in order. A dropped or merged row hides exactly the duplicate this is looking for. For views other than `road` the rows are not inspected, so one is enough.
4. Run `python3 <base directory>/doctor.py --views <that file>` (add `--repo <path>` if checking another repo). Show its output as it printed.
5. Report the exit status plainly. For each `FAIL`, say what fixes it — and do not fix it unprompted. A missing view key needs the view URL from the board. A notice naming a Done story is either stale ("until that lands", about something that landed), which means rewriting what is now true, or a citation of a fact that still holds, which means stating the fact without the ID; read the passage before deciding which. A duplicate Story ID needs a human to decide which row is real.

`--local-only` skips the board and checks only the config and git. Use it when Notion is unreachable, and say the board was not checked — a partial run is not a clean bill of health.
