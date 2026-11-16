---
name: release
description: Drop the story bound to this session without shipping it - back to Ready or Backlog, branch kept
argument-hint: <reason>
---

Release the story bound to this session **without shipping it**. The reason given: **$ARGUMENTS**

`/lc:done` is the exit for finished work. This is the exit for work that is not going to be finished in this session: the wrong story was claimed, it turned out bigger than its estimate, it needs a decision first, or the session is out of time. It puts the story back on the board for someone else to pick up and unbinds the session. It ships nothing and deletes nothing.

1. Read `.claude/.current-story`. **If it is missing or empty, say that no story is bound to this session and stop.** Change nothing: no Notion write, no file write, no git command.
2. If no reason was given above, ask for one line on why the story is being dropped, and wait. The reason goes on the board, where the next person to claim the story will read it; do not make one up.
3. Read `.claude/launch-control.json` for the board URLs, and find the story the way `/lc:start` does: query **`views.open`** in view mode, every page until `has_more` is false (on a board with no `views.open`, read `views.road` and say that `/lc:doctor` names the view to create), then run `python3 <base directory>/../doctor/ids.py find <page files...> --id <ID>`. Each page the tool saved to a file is passed by its path. A page that came back inline - the last one usually does - is **not** written to a file: give it on the command line as `--inline-page <rows on that page> <its has_more, true or false> --row <Story ID> <Status> <page url> <Blocked by URLs comma-separated, or ->` with one `--row` per row, in order (`-` for a blank Story ID). Do not use a rows-mode or SQL query: Notion's free plan meters both, and view mode is unmetered. `fetch` the page it prints.
   - **Exit 1** means no open story carries that ID - it is already Done, or the binding names a story that does not exist. Change nothing on the board. Say so, then empty `.claude/.current-story` and `.claude/.nudged`, because the binding points at nothing that can be released.
   - **Exit 2** means the ID is on two rows. Say so and stop, changing nothing.
4. If the story's **Status** is `In Review`, a pull request for it is open. Say so, and ask whether to release it anyway before going on: releasing it does not close the PR, and a merge after the release would ship work the board no longer calls in flight.
5. **Work out where it goes back to. Do not assume `Ready`.** Read the story's **Blocked by** relation and `fetch` every page it links. (The `Blocked by IDs` and `Blocker status` rollups come back as opaque handles - they cannot answer this.) If it has no blockers, or every blocker's Status is `Done`, the new Status is `Ready`. If any blocker is not `Done`, it is `Backlog`, and say which blocker holds it there.
6. **Leave the branch and its commits exactly where they are.** Someone may want that work. Do not delete the branch, switch branches, reset, stash, commit, push, or close a PR. Gather and report the facts instead: the current branch (`git branch --show-current`), how many commits it is ahead of `git.baseBranch` (`git rev-list --count <baseBranch>..HEAD`), whether it is on the remote (`git ls-remote --heads origin <branch>`), and whether the working tree has uncommitted changes (`git status --porcelain`). If `git.enabled` is false, skip the remote check - that key means never touch the remote - and report the rest. If this is not a git repo, say there is no branch to keep and leave the branch part out of the Last session line.
7. Update the story in one write:
   - **Status** to the value from step 5.
   - **Last session**: keep everything already in it, and append one new line, `<today as YYYY-MM-DD>: Released without shipping - <the reason>. Branch <branch name> kept, <N> commits ahead of <git.baseBranch>.` Use the git facts from step 6. Do not rewrite or trim earlier lines.
   - Leave **Started** alone. An External story's clock began the day it was first claimed and has not stopped; `/lc:mine` counts from it, and `/lc:start` never overwrites it when the story is claimed again.
8. Empty `.claude/.current-story` and `.claude/.nudged` (write them empty rather than deleting them - some filesystems forbid the delete, and an empty file reads as unbound). With the binding empty, the Stop hook has nothing to nudge about.

Report: the story ID, the Status it went back to and why (naming any blocker that is not Done), the line added to Last session, and that the branch, its commits and any uncommitted changes were left in place - by name, with the counts from step 6. The session is now unbound; `/lc:next` finds the next story.
