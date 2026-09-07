# `.claude/launch-control.json`

One file per repo. The commands are identical everywhere; this is where the
differences live.

## Identity

| Key | Meaning |
|---|---|
| `project` | Project key, matching the row in the Projects database |
| `prefix` | Story-ID prefix, e.g. `APP` — every command filters on it |
| `projectPageId` | The Projects-database row for this repo, used by `/lc:groom` |

## Board

`stories` and `projects` each carry a `database` URL and a `dataSource`
(`collection://...`). `views` carries seven named view URLs — see
[notion-schema.md](notion-schema.md) for what each view must filter on.

Query views in **view mode**, not SQL mode: view mode is unmetered on Notion's
free plan and SQL mode is billed. This is why the views are durable named objects
rather than filters composed at call time.

## `git`

| Key | Meaning |
|---|---|
| `enabled` | If false, `/lc:done` records but never ships |
| `baseBranch` | PR target. Check it — a repo whose default is `master` will silently fail against `main` |
| `mergeMethod` | `squash`, `merge` or `rebase` |
| `autoMerge` | If false, `/lc:done` stops at a green PR and sets the story `In Review` |
| `mergeIsDeploy` | If true, merging ships to production. `/lc:done` always stops, green or not |
| `ciTimeoutMinutes` | After this, leave the PR open rather than merge on optimism |
| `extraChecks` | Expensive opt-in checks, each with a `when` that is read **literally** |
| `notes` | Standing per-repo warnings. Read before staging anything |

## `notice` and `launch-control.local.json`

`notice` is injected at the top of every session, under "Read this before you
start". It is for facts that stay true — how to recognise a billing rejection,
which runners are expensive, a known-broken assumption. Anything about the
current working tree goes stale within the session and belongs in a story's
**Last session** field instead.

**`launch-control.local.json` is gitignored** and merged over the shared file at
read time. Its keys override; its `notice` is *appended* rather than replacing.
Put anything private there — measured spend, account or billing state, private
infrastructure detail. This matters most in a public repo, where the shared file
is world-readable.
