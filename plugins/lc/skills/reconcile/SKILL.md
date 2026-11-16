---
name: reconcile
description: Re-check this project's open stories against the actual repo and correct the board
argument-hint: [epic or story-id range, optional]
---

Verify the backlog against reality. Stories drift as the code moves, and some may have been true the day they were written.

1. Read `.claude/launch-control.json` and query **`views.road`** in **view mode**. Every project has its own road view, scoped to that project. Never substitute a shared browse view — its filters are editable in the board UI and a stray filter silently returns another project's rows, or none.
2. **Sanity-check what came back before doing anything with it.** If any returned **Story ID** does not start with this repo's prefix, or if zero rows came back at all, the view is misconfigured — say so and stop. Do not report "nothing to reconcile": an empty result from a scoping bug reads exactly like a clean bill of health, and that is the failure this command exists to catch.
3. Take every story that is **not** Done and whose **Agent can do this** is checked. If the user gave an argument, narrow to it. Cap the run at about 15 stories and say which you covered — a partial honest pass beats a rushed complete one.
4. For each, read its **Done when** and go and check it **in the repo**. Actually run the command, read the file, check the setting. Do not infer from a doc, and do not infer from the story's own Notes field — that is what is being audited.
5. Classify each:
   - **Already true** — set Status to `Done` and write into **Last session**: today's date, "reconciled", and the specific evidence (the command you ran and its output, or the file and line). Evidence is required; a bare "already done" is not acceptable.
   - **Still open, unchanged** — leave it.
   - **Drifted** — the criteria are now wrong, or the trap it warns about no longer exists, or it needs different steps. Update **Done when** and **Notes and traps**, and say what changed and why.
   - **Obsolete** — the work no longer makes sense. Do NOT delete it. Set Status to `Done` and record in **Last session** why it is moot.
6. If anything flipped to Done, check whether it unblocks others: **read the shared `board` view (`views.board`) in view mode** - it is board-wide, because a dependent can live in another project (a clock blocks stories across projects), so the project's road view would miss it. Page it to the end with `start_cursor` until `has_more` is false, then `python3 <base directory>/../doctor/ids.py dependents <page files...> --url <that story's page URL>` lists the dependents. Each page the tool saved to a file is passed by its path. A page that came back inline - the last one usually does - is **not** written to a file: give it on the command line as `--inline-page <rows on that page> <its has_more, true or false> --row <Story ID> <Status> <page url> <Blocked by URLs comma-separated, or ->` with one `--row` per row, in order (`-` for a blank Story ID). Those are short values you can state exactly; the script checks the count and every URL, and refuses rather than answers when one is off. Never read the rows by eye, and never use a rows-mode or SQL query here: Notion's free plan meters both from one allowance, and this runs for every story that flipped. If `/lc:doctor` reports the `board` view filtered, fix that first - a filtered board view silently drops dependents. For each dependent, fetch its blockers; if all are now Done and it is in `Backlog`, promote it to `Ready`.
7. Report a short table: story ID, verdict, evidence. Then state how many launch blockers this project actually has left.

Be sceptical in both directions. Marking something Done that is not is worse than leaving it open — it removes the only thing that would have caught the gap before submission.
