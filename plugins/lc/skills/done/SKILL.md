---
name: done
description: Verify the story, ship the code through a PR, and tick it off on the board
---

Close out the story bound to this session.

## 1. Verify

1. Read `.claude/.current-story`. If missing or empty, ask which story this work belongs to — or `/lc:groom` it if it was never on the backlog.
2. Fetch the story and re-read its **Done when**.
3. **Check the acceptance criteria honestly, one clause at a time.** Run the thing that verifies it — the tests, the script, the command the criteria name. Do not mark something Done because the code was written; mark it Done because you checked and the criteria hold.
4. If any clause is unmet: say which and why, set **Status** to `Blocked` if something external is in the way (otherwise leave it `In Progress`), write what happened into **Last session**, and stop. Do not ship it and do not tick it off.

## 2. Ship it

Read the `git` block in `.claude/launch-control.json` and follow it — the policy differs per repo and the differences are not cosmetic. `git.notes` carries this repo's standing warnings; read them before staging anything.

**Does this story involve a repo change?** Run `git status --porcelain`. If the tree is clean, there is nothing to ship — skip to step 3. (Plenty of stories are like this: a GUI build, a dashboard setting, a filing.) Do not invent a commit to have something to push.

Otherwise:

5. **Branch.** `<lowercase story id>-<short kebab slug>`. If you are already on such a branch, stay on it. Never commit to `git.baseBranch` directly.
6. **Commit.** The story ID leads the subject. Body says what changed and why, not what the files are. Follow this session's own commit-attribution convention for trailers.
   - Review `git status` before staging. **Stage deliberately — never `git add -A`.** Some repos hold live credentials or worker state in working files; `git.notes` says which and where.
7. **Push and open a PR** against `baseBranch`. The PR body should carry the story ID, its **Done when** verbatim, and what you did to satisfy it — so the PR is reviewable by someone who has not read the story.
8. **Run any `extraChecks` whose `when` matches** — and read the `when` literally. These are deliberately narrow because they are expensive. If a check's `when` says *before the release build*, that does not mean *on every PR*. Do not widen it to be thorough.
   - **Minutes are a budget.** Before triggering anything on an expensive runner, or re-running a failed job more than once, say what it will cost and why it is worth it. If a run can wait, let it.
9. **Wait for CI**, up to `ciTimeoutMinutes`.

## 3. Merge — deliberately, not with `--auto`

**Do not use `gh pr merge --auto`.** It delegates the decision to branch protection, and a repo without branch protection will merge immediately regardless of what the checks say. Branch protection on private repos requires a paid GitHub plan, so assume it is absent unless you have confirmed otherwise. Evaluate the rollup yourself:

10. Read the actual conclusions (`gh pr view <n> --json statusCheckRollup`, or `gh pr checks <n>`). Merge only if **every** check concluded successfully.
    - **If zero checks ran, refuse to merge.** An empty rollup is not a pass. The one exception is a workflow whose `paths-ignore` excludes everything in the diff *by design* — confirm that with `git diff --name-only <baseBranch>...HEAD` and say that is what you did. If a single covered file is in the diff and the rollup is still empty, that is the accident case: refuse.
    - **Say which workflows ran, and whether they cover this diff.** Path-filtered workflows mean a green rollup can mean "the checks that test this change never ran." A PR touching only scripts or config can pass on a secret-scan job alone; that is not validation of an application change. Name what ran before you merge on it.
    - A `skipped` required check is not a pass either. Say which check was skipped and why you think it is safe, or stop.
    - **A red rollup is not always a failing test.** When a GitHub Actions allowance is exhausted or billing is misconfigured, jobs are rejected before their first step: the run ends in a couple of seconds, conclusion `failure`, with **zero steps** and no log. Check with `gh api repos/:owner/:repo/actions/runs/<id>/jobs -q '.jobs[].steps|length'` — if it is `0`, that is a billing state, not a broken diff. Do not debug it and do not re-run it.
    - **Zero steps with conclusion `skipped` is the opposite case** — that is a workflow `if:` condition doing its job. Do not confuse the two: same step count, opposite meaning.
    - Never merge with `--admin` and never bypass a failing check. If CI is red, fix it or leave the PR open — those are the only two options.
11. **If `autoMerge` is false, or `mergeIsDeploy` is true, stop here even when everything is green.** Where merging ships to production, that is the owner's call and their timing, not a session's. Set the story to `In Review`, record the PR URL in **Last session**, and say it is green and waiting.
12. Otherwise merge with `mergeMethod` and delete the branch.
13. If CI is still running when `ciTimeoutMinutes` elapses: do not wait longer and do not merge on optimism. Leave the PR open, set the story to `In Review`, record the PR URL, and say so.

## 4. Record

14. Set **Status** to `Done` — or leave it `In Review` if the PR is open per step 11 or 13. A story is not Done while its code is unmerged.
15. Write into **Last session**: today's date, one or two sentences on what was actually done, and the commit SHA and PR number.
16. If the work made a *different* story wrong — a trap discovered, a dependency that was mistaken, a step no longer needed — update that story too. A stale tracker is the problem this replaced.
17. Empty `.claude/.current-story` and `.claude/.nudged` (some filesystems forbid deleting them; an empty file reads as unbound).
18. **Only if the story reached `Done`**, find what it unblocks: query the Stories data source filtered on **Blocked by** `relation_contains` this story's page URL. For each dependent, fetch its blockers; if every one is now Done and the dependent is in `Backlog`, promote it to `Ready`. Say which opened up. A story sitting in `In Review` unblocks nothing — its code is not on the base branch yet.

## 5. Report

What was done, the PR and its state, what it unblocked, and what the next story would be.
