# 0001 — What to cede to Claude Code's native Tasks

**Status:** Accepted, 2026-09-12 · Amended, 2026-09-17 · **Story:** LC-01, LC-15

> **Amendment, 2026-09-17.** The task tools this record cedes scope to are **not
> available by default on current models**, and had already stopped being so a month
> before this record was signed. The Decision below stands; its justification does
> not. Read [the amendment](#amendment-2026-09-17--platform-re-check) before
> inheriting the reasoning in Context.

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

## Amendment, 2026-09-17 — platform re-check

**Platform fact last verified:** 2026-09-17, against Anthropic's own changelog and
documentation.

### What is true today

Claude Code's task-tracking tools — `TaskCreate`, `TaskGet`, `TaskUpdate`,
`TaskList` and `TodoWrite` — are **not available by default on current models**.
They are offered only on Claude 3.x, Opus 4.0–4.7, Sonnet 4.0–4.6 and Haiku 4.5. On
anything newer, Opus 5 and Sonnet 5 included, a session has them only if it sets
`CLAUDE_CODE_ENABLE_TODO_TOOLS=1`.

Two primary sources, both Anthropic's:

- The changelog in [`anthropics/claude-code`](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md):
  - **v2.1.233** — "Todo/task-tracking tools (TaskCreate/Get/Update/List,
    TodoWrite) are no longer available on Opus 4.8, Sonnet 5, Fable 5, Mythos 5, and
    newer models; set `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` to bring them back"
  - **v2.1.268** — "Changed the task-tracking tools (TaskCreate/Get/Update/List,
    TodoWrite) to be offered only on Claude 3.x, Opus 4.0–4.7, Sonnet 4.0–4.6, Haiku
    4.5; set `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` elsewhere"
- The docs, [Track todos → Model availability](https://code.claude.com/docs/en/agent-sdk/todo-tracking#model-availability):
  "available by default only on Claude 3.x models, Opus 4 through 4.7, Sonnet 4
  through 4.6, and Haiku 4.5. On every other model, including model IDs Claude Code
  doesn't recognize, they aren't available unless you opt in." The same page states
  the platform's reasoning: "Newer models track multi-step work without a written
  todo list."

The changelog carries no dates; the release dates below are the npm publish times
for `@anthropic-ai/claude-code`. Corroborated in passing by the session that made
this edit: Claude Code v2.1.274 on Opus 5, no task tools offered, no
`CLAUDE_CODE_ENABLE_TODO_TOOLS` in the environment.

### What this corrects

LC-15 was filed on a third-party report that **v2.1.269, 11 September** made the
change. That report was right about the substance and **wrong about when**. v2.1.269
says nothing about task tools. The gating landed in **v2.1.233, published
2026-08-14**, and was narrowed to the current allowlist in **v2.1.268, published
2026-09-10**.

The correction is worth more than the pedantry suggests. The worry was that this
record had been overtaken by a change four days *after* it was accepted. It had not.
It was **29 days out of date on the day it was signed**. The 2026-09-07 research
this record rests on described a platform that had already moved three weeks
earlier, and nobody noticed for ten days.

### What it changes

The Decision stands unaltered. Its *justification* does not survive intact: every
"the platform gives this away, so don't re-implement it" argument was load-bearing
on tools a user of a current model does not have.

- **Persistence, the dependency graph and auto-promotion** stay on the board, as
  decided — now for the plainer reason that on a current model there is nothing to
  cede them to short of an environment variable the settings docs do not mention.
- **The scope rule is no longer a description of the default environment.** "Native
  Tasks own the steps inside a story" holds only where those tools exist. Launch
  Control must not depend on their being present, and no command may assume it.
- **The marketing rule stands and gets easier.** Still do not advertise the three as
  differentiators. `/lc:mine`'s human-work critical path is the thing nothing else
  covers.

### The standing lesson

This was sound reasoning against a platform fact that had already moved, and nothing
in the record said when that fact was last checked — so the staleness was invisible
to the next reader, who would have inherited it as settled. Every future claim here
about what the platform does by default carries the date it was verified and a
primary source. A third-party changelog mirror is not one.

## Consequences

- **README.** Its Status section names the human-work critical path as the
  differentiator. It describes persistence, dependencies, promotion and
  reconciliation as things the board needs, not things only it offers.
- **`lc init`** (not built yet) must provision the **Blocked by** self-relation and
  the `Backlog` and `Ready` status options, because `/lc:done` and `/lc:next`
  depend on them. It need not provision the `Blocked by IDs` and `Blocker status`
  rollups. They help only in the Notion UI, and no command may read them.
- **Revisit** if native Tasks gain a shared, human-readable store that spans
  projects, or a way to represent work that is not an agent's — *and* are available
  by default on the models users actually run, which as of 2026-09-17 they are not.
  At that point persistence and promotion become candidates to cede for real.
  Re-check that availability at a primary source, and date the answer.
