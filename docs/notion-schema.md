# The board

Two databases in one Notion page. `/lc:init` provisions all of it over the API —
both databases, every property below and every view — and puts the repo it runs in
on the board. Every later repo joins with `/lc:plan --board`, which provisions a
*project* on the existing board: its Projects row, its `road` view and the repo's
config. Neither needs a visit to the Notion UI.

[`plugins/lc/skills/init/board.json`](../plugins/lc/skills/init/board.json) is the
same schema as a contract: `/lc:init` generates the databases and views from it and
then checks what Notion reports back against it. Change the two together.

## Projects

One row per repo: **Name**, **Key**, **Repo**, **Kind** and **State of play**, plus
whatever else you want to see. Its page ID goes in each repo's `projectPageId`.
Stories relate to it. `/lc:plan` fills Key, Repo and Kind when the database has
them.

## Stories

The work. Properties, in rough order of how much they carry:

| Property | Type | Why it exists |
|---|---|---|
| **Name** | Title | Short, imperative |
| **Story ID** | Text | `APP-14`, `APP-B7`. Plain numbers are launch blockers; the `-B` series is backlog. Goes in the branch name and every commit subject, so git history and the board can be joined later |
| **Project** | Relation → Projects | What makes one board readable from many repos |
| **Status** | Select | `Backlog` · `Ready` · `In Progress` · `Blocked` · `In Review` · `Done` |
| **Done when** | Text | Acceptance criteria, checkable by someone who was not in the conversation. Restating the title is not acceptance criteria |
| **Agent can do this** | Checkbox | The honesty flag. Unchecked for anything needing a GUI, a login, a payment, a physical device, or a third party. This single property splits the board into "work" and "your desk" |
| **Gating** | Select | `Self-serve` · `External`. External items are clocks, not tasks |
| **Lead time** | Text | Why the outside world takes as long as it does, and what makes it worse: "each rejection restarts the clock". Read by people, not computed with |
| **Lead days min** | Number | Calendar days the third party takes on a good run. Convert business days (5 business = 7 calendar) |
| **Lead days max** | Number | Calendar days on a bad but ordinary run — the prose's stated upper figure. With min, what lets `/lc:mine` project finish dates and rank by calendar cost. An External story with neither is listed as unranked, never guessed |
| **Blocked by** | Relation → Stories (self) | Real edges. Lets `/lc:done` walk the graph and promote what just became unblocked |
| **Notes and traps** | Text | Where expensive mistakes are recorded so they are paid for once. Commands read this out rather than summarising it |
| **Last session** | Text | Date, what was done, commit SHA, PR number |
| **Seq** | Number | Ordering within a project, so "next" is a decision already made |
| **Type** | Select | Launch Blocker · Backlog · Chore |
| **Epic** | Select | Grouping. Keep the options project-agnostic so they work across repos |
| **Estimate** | Select | XS &lt;1h · S 1–3h · M half a day · L 1–2d · XL 3d+ |

### Two traps in the schema itself

**Notion select options cannot contain commas.** Use dashes.

**Rollups are opaque over the API.** A rollup of the blockers' statuses renders
correctly in the Notion UI but returns `rollupResult://` handles to the API. So
commands treat `Status = Ready` as the primary unblocked signal, and fetch the
linked pages when they need to verify. Do not build logic on a rollup. `/lc:init`
does not create any (see [decision 0001](decisions/0001-native-tasks.md)); add
**Blocked by IDs** or **Blocker status** by hand if you want them in the UI.

## Views

Seven, each answering one question. Every one is referenced by name in
`launch-control.json`.

| Key | Filter | Read by |
|---|---|---|
| `ready` | Status is `Ready` **and** Agent can do this is checked | `/lc:next` |
| `yourTurn` | Agent can do this is **un**checked, not Done. **No Type filter, deliberately** | `/lc:mine` |
| `inProgress` | Status is `In Progress` | `/lc:status` |
| `inReview` | Status is `In Review` | `/lc:status` |
| `waitingExternal` | Gating is `External`, not Done | `/lc:status` |
| `road` | **Project is this one.** One per project | `/lc:reconcile` |
| `board` | Grouped by Status, for reading | — |

### Why `road` is per-project and not one shared view

A shared "everything" view is editable by anyone in the Notion UI. One stray filter
left behind returns another project's rows — or none — and an empty result from a
scoping bug reads exactly like a clean bill of health. `/lc:reconcile` therefore
refuses to run if zero rows come back or if a returned Story ID does not match the
repo's prefix. Keep a free-for-all browse view if you want one, but do not
reference it from any command.

### Why `yourTurn` has no Type filter

It used to filter to `Type = Launch Blocker`, and that quietly broke the one thing
`/lc:mine` exists to do. Type is assigned at groom time, by a model weighing "does
this block shipping?" — a question with nothing to do with whether a human has to do
the work. So anything it typed `Backlog` or `Chore` became invisible to the command
built to surface human work, while `/lc:groom` went on telling people that unchecking
**Agent can do this** was enough to put an item in `/lc:mine`.

It cost something real before it was found: a `/lc:mine` run on 2026-09-15 had to dig
out a leaked GitHub token by hand — the most urgent item on that board — because it
had been typed `Backlog`.

**Agent can do this** is the only question this view should ask, because it is the
only one whose answer decides who can act. Type is in the view's columns, so
`/lc:mine` can still rank or label by it; it just cannot hide anything. If you are
tempted to narrow this filter again, narrow it in `/lc:mine`'s output instead.
