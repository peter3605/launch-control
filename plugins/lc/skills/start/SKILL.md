---
name: start
description: Claim a Launch Control story and bind this session to it
argument-hint: <STORY-ID>
---

Bind this session to story **$ARGUMENTS**.

1. Read `.claude/launch-control.json` for the board URLs.
2. Find the story by its Story ID. Query **`views.open`** in view mode - this project's stories that are not Done - every page until `has_more` is false, then run `python3 <base directory>/../doctor/ids.py find <page files...> --id <ID>`. Do not read `views.road` for this: it keeps every Done row forever, so it grows with the project's history, and a story to start is never Done. If the config has **no `views.open`** (a board provisioned before 0.14.0), say that `/lc:doctor` names the view to create, and read `views.road` instead for now. If the ID has another project's prefix and the user named that project, read `views.board` instead. Each page the tool saved to a file is passed by its path. A page that came back inline - the last one usually does - is **not** written to a file: give it on the command line as `--inline-page <rows on that page> <its has_more, true or false> --row <Story ID> <Status> <page url> <Blocked by URLs comma-separated, or ->` with one `--row` per row, in order (`-` for a blank Story ID). Those are short values you can state exactly; the script checks the count and every URL, and refuses rather than answers when one is off. It prints the page URL; `fetch` that page for the full story. Exit 1 on the open view means no open story carries that ID: it does not exist, or it is already Done - say so and stop, do not invent one. (If the user says it exists, `fetch` its page by URL to see its Status rather than reading the road.) Exit 2 means the ID is on two rows - say so and stop. Do not use a rows-mode or SQL query to look it up: Notion's free plan meters both from one workspace allowance, and view mode is unmetered.
3. Check its **Blocked by** relation. If any blocker is not Done, warn clearly and ask whether to proceed anyway before doing anything else.
4. Set the story's **Status** to `In Progress`.
   If its **Gating** is `External` and its **Started** date is empty, set Started to today in the same update (`date:Started:start` = today as `YYYY-MM-DD`, `date:Started:is_datetime` = 0). That is the day its clock began, and `/lc:mine` counts the remaining lead from it. **Never overwrite a Started that is already set** - a story re-claimed after a pause did not restart its clock. A Self-serve story gets no Started. If the board has no Started property, set the Status alone and say that `/lc:doctor` names the column to add.
5. Write the story ID to `.claude/.current-story` (one line, just the ID) and empty `.claude/.nudged` if present.
6. Create a working branch named `<lowercase story id>-<short kebab slug>` — the same pattern `/lc:done` expects. Never branch off anything but `git.baseBranch`.
7. Read out the story's **Done when** and **Notes and traps** verbatim, then state your plan for satisfying the Done-when criteria.

Every commit in this session should carry the story ID in its subject line.
