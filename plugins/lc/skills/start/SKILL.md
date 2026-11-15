---
name: start
description: Claim a Launch Control story and bind this session to it
argument-hint: <STORY-ID>
---

Bind this session to story **$ARGUMENTS**.

1. Read `.claude/launch-control.json` for the board URLs.
2. Find the story by its Story ID. Query **`views.road`** in view mode, every page until `has_more` is false (or `views.board` if the ID has another project's prefix and the user named that project), keeping each page's result file, then run `python3 <base directory>/../doctor/ids.py find <page files...> --id <ID>`. It prints the page URL; `fetch` that page for the full story. Exit 1 means it does not exist - say so and stop, do not invent one. Exit 2 means the ID is on two rows - say so and stop. Do not use a rows-mode or SQL query to look it up: Notion's free plan meters both from one workspace allowance, and view mode is unmetered.
3. Check its **Blocked by** relation. If any blocker is not Done, warn clearly and ask whether to proceed anyway before doing anything else.
4. Set the story's **Status** to `In Progress`.
5. Write the story ID to `.claude/.current-story` (one line, just the ID) and empty `.claude/.nudged` if present.
6. Create a working branch named `<lowercase story id>-<short kebab slug>` — the same pattern `/lc:done` expects. Never branch off anything but `git.baseBranch`.
7. Read out the story's **Done when** and **Notes and traps** verbatim, then state your plan for satisfying the Done-when criteria.

Every commit in this session should carry the story ID in its subject line.
