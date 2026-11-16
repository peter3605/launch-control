---
name: next
description: Pull the next story to work on from the Launch Control backlog
---

Pick up the next piece of work for this project.

1. Read `.claude/launch-control.json` for the project key, the story-ID prefix, and the board URLs.
2. If `.claude/.current-story` exists and is non-empty, a story is already bound. Say which, and stop — offer `/lc:done` or an explicit `/lc:start <other-id>` rather than silently switching.
3. Query this project's **next** view (`views.next`) in **view mode**. It holds this project's Ready, agent-doable stories and nothing else, so its rows need no filtering. View mode is unmetered on the free Notion plan; SQL mode is billed, so do not reach for it. Do not read the shared `ready` view instead: it holds every project's Ready rows, and on a board with several projects one read of it overflows the tool's output limit.
   - **No `views.next` in the config** (a board provisioned before 0.10.0): say so, and that `/lc:doctor` prints the view to create. For now read **`views.road`** in view mode, every page until `has_more` is false, and keep the rows with Status `Ready` and **Agent can do this** checked.
   - **The user named another project**: read the shared `ready` view and keep that project's prefix.
4. Every row should carry this repo's prefix. One that does not means the view's filter is wrong: say so, point at `/lc:doctor`, and do not hand that row out.
5. Take the first row by **Seq**. `Status = Ready` already means unblocked — `/lc:done` promotes dependents from Backlog to Ready as their blockers close — but verify before starting: if the row's **Blocked by** relation is non-empty, fetch each linked page and confirm every one is Done. If any is not, that is a bug in the board: fix the story's Status to Backlog, say so, and move to the next candidate.
6. Present the story: Story ID, name, Estimate, **Done when**, and **Notes and traps** in full. Read the traps out — that field is where the expensive mistakes are recorded, not decoration.
7. Ask before starting. On confirmation, run the `/lc:start` flow for that story.

An argument narrows the candidates first — a project key, an epic, or an estimate (`XS`).

This command only ever returns work a session can actually do. For the tasks that need a human — a GUI build, a login, a legal filing — run `/lc:mine`.
