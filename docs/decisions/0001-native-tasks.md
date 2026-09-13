# 0001 — What to cede to Claude Code's native Tasks

**Status:** Accepted, 2026-09-12 · **Story:** LC-01

## Context

Around January 2026 Claude Code shipped native Tasks. They cover three things
Launch Control currently implements over Notion:

- **Persistence.** Tasks outlive a session.
- **A dependency graph.** One task blocks another.
- **Auto-promotion.** When a blocker completes, what it blocked becomes available.

Research on 2026-09-07 confirmed that overlap. It found one differentiator that
nothing else covers: tracking the work an agent *cannot* do, ordered by external
lead time (`/lc:mine`). It also found that spec-kit ships an equivalent of
`/lc:reconcile`.

Native Tasks and the board serve different readers:

- **Native Tasks** live with the agent. They are local to the machine and the
  session's task list, and they describe work an agent picks up.
- **The board** is read by a human, across every project at once. It holds items
  that are not agent work at all, such as a D-U-N-S application, an App Store
  review or a legal filing, each with a lead time.

The question for each of the three capabilities is therefore narrower than "does
the platform do this?" It is: does the board still need it, given that the board
has a reader and a kind of work that native Tasks do not?

## Decision

Two rules apply to all three items:

- **Scope.** Native Tasks own the steps *inside* a story, within a session. The
  board owns stories. Launch Control does not mirror stories into native Tasks, and
  does not file sub-steps as stories.
- **Marketing.** None of the three is advertised as a differentiator. They are
  plumbing the board needs, not the reason to use it.

### Persistence — keep, but stop claiming it

The board stays the system of record for stories.

**Reason:** Persistence is not the point of the board; being readable is. Native
Tasks persist, but a human looking across six projects cannot see them, and they
have no place for work that is not a task for an agent. `/lc:mine` and
`/lc:status` exist to answer "where does everything stand, and what is waiting on
me?" That requires one shared, human-readable store, whether or not the platform
also persists tasks.

### Dependency graph — keep the edges, build nothing more on them

The **Blocked by** relation stays. It is still a single hop: `/lc:next` checks a
candidate's direct blockers, and `/lc:done` finds a finished story's direct
dependents. Launch Control will not add transitive walks, cycle detection, graph
visualisation or critical-path computation over agent stories.

**Reason:** The edges that matter most are the ones native Tasks cannot hold. An
agent story can be blocked by a human item, such as "cannot ship push notifications
until the APNs key exists". `/lc:mine` needs those edges on the same board as the
human work to rank what to start today. Within agent work, the platform's graph is
the better tool, so investing further here would re-implement what is given away.

### Auto-promotion — keep the one step, do not extend it

`/lc:done` (and `/lc:reconcile`, when it closes a story) keeps its single
promotion step: find the dependents, confirm every blocker is Done, and move
`Backlog` to `Ready`. `/lc:next` keeps its guard that demotes a mis-promoted story.
Nothing further is built: no background sync and no promotion on status changes
made in the Notion UI.

**Reason:** `Ready` is what a human scanning the board sees. It is also the filter
on the `ready` view that `/lc:next` reads, and Notion rollups cannot be read over
the API (see [notion-schema.md](../notion-schema.md)), so the stored status is the
only unblocked signal a command can read cheaply. The step is one query per closed
story. Ceding it would leave the board's `Ready` column wrong for its only reader,
and there is nothing in the platform to delegate it to, because native Tasks do not
see the board.

## Consequences

- **README.** Its Status section names the human-work critical path as the
  differentiator. It describes persistence, dependencies, promotion and
  reconciliation as things the board needs, not things only it offers.
- **`lc init`** (not built yet) must provision the **Blocked by** self-relation and
  the `Backlog` and `Ready` status options, because `/lc:done` and `/lc:next`
  depend on them. It need not provision the `Blocked by IDs` and `Blocker status`
  rollups. They help only in the Notion UI, and no command may read them.
- **Revisit** if native Tasks gain a shared, human-readable store that spans
  projects, or a way to represent work that is not an agent's. At that point
  persistence and promotion become candidates to cede for real.
