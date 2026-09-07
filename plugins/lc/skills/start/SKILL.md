---
name: start
description: Claim a Launch Control story and bind this session to it
argument-hint: <STORY-ID>
---

Bind this session to story **$ARGUMENTS**.

1. Read `.claude/launch-control.json` for the board URLs.
2. Fetch the story by its Story ID (search the Stories database, or query the data source filtered on `Story ID`). If it does not exist, say so and stop — do not invent one.
3. Check its **Blocked by** relation. If any blocker is not Done, warn clearly and ask whether to proceed anyway before doing anything else.
4. Set the story's **Status** to `In Progress`.
5. Write the story ID to `.claude/.current-story` (one line, just the ID) and empty `.claude/.nudged` if present.
6. Create a working branch named with the story ID, per `git.branchPattern` in the config — by default `<lowercase story id>-<short kebab slug>`.
7. Read out the story's **Done when** and **Notes and traps** verbatim, then state your plan for satisfying the Done-when criteria.

Every commit in this session should carry the story ID in its subject line.
