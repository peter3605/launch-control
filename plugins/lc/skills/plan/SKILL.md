---
name: plan
description: Turn a design document or an existing repo into a Launch Control project and its whole backlog
argument-hint: <design doc path | Notion or doc URL | repo path> [--repo <target repo>] [--board <a launch-control.json on the same board>]
---

Plan **$ARGUMENTS** onto the Launch Control board: provision the project, propose its whole backlog for review, and file it on confirmation.

This is the front door. Every other command starts from an existing story; this one starts from a document or a repo that the board has never seen. It provisions a **project inside an existing board** - the Projects row, its road view, the repo's config. It does not create the board itself (databases, properties, the shared views); if there is no board, say so, point at `/lc:init`, which creates one, and stop.

The deterministic parts live in `plan.py` in this skill's base directory, and its exit code is the verdict, as with `doctor.py`. It cannot reach Notion: you query the board and hand it the results, in doctor's page format (`{"file": <saved result path>}` or `{"rows": [["APP-1", "Ready"], ...], "hasMore": false}`, or a list of pages).

Four things decide whether the output is a launch plan or fiction. Each one has a check in `plan.py` - do not route around it:

- **The document lies.** Design docs, READMEs and action-item lists go stale the day they are written. A README once said "the code does not exist" about a milestone with 43 test files; an action list called infrastructure work undone while Terraform already pointed at a live backend. Every claim is checked against the repo before it becomes - or fails to become - a story.
- **`Agent can do this` feeds `/lc:mine`**, the one report nothing else produces. Marking everything agent-doable quietly deletes it. Anything needing a GUI, a login, a payment, a physical device or a third party is unchecked.
- **`Done when` is checkable by someone who was not in this conversation** - a command that exits 0, a file containing a value, a screen showing a thing. A restated title is worse than an empty field, because it looks finished.
- **IDs are allocated one story at a time**, by re-read-and-retry, never once for the batch.

## 0. Pre-flight - reads only

Stop at the first failure and say which check failed. Nothing has been written yet, so there is nothing to undo.

1. **Resolve the source.** A file path: read it all. A URL: fetch it (a Notion page through the Notion fetch tool). Text pasted into the conversation: save it verbatim to a file in your scratchpad, because `plan.py` reads the source from disk. A directory: the repo is the source, and its README and docs are the documents.
2. **Resolve the target repo** - where the config will be written. `--repo` if given; else the source itself if it is a directory; else this session's project directory. If the target is not this session's project, say so plainly in the proposal: writing another repo's config is crossing into that project, and the confirmation in step 12 must cover it.
3. **The target must not be on the board already.** If `<target>/.claude/launch-control.json` exists, stop: this repo already has a project. Use `/lc:groom` for new items or `/lc:reconcile` to re-audit. The one exception is a resumed run - `<target>/.claude/lc-plan/state.json` exists - see **Resuming** below.
4. **Find the board.** `--board` if given. Otherwise read `launch-control.json` from this session's project and from every sibling of the target (`<target>/../*/.claude/launch-control.json`), and group them by `stories.dataSource`. Exactly one board: use it, and name the file you took it from. More than one: ask which. None: stop - there is no board to plan onto; `/lc:init` creates one.
5. **Check the board can take a project.** Fetch the Stories database and the Projects database.
   - Stories must have: Name, Story ID, Project (relation), Status with `Ready` and `Backlog` options, Done when, Agent can do this, Gating with `Self-serve` and `External`, Lead time, Lead days min and Lead days max (numbers), Blocked by (relation), Notes and traps, Seq, Type, Epic, Estimate. Note the Epic options - they go to `lint --epics`.
   - The chosen config must carry all six shared views (`ready`, `inProgress`, `inReview`, `waitingExternal`, `yourTurn`, `board`) - `plan.py config` copies them.
   - Note the Projects title property and whether `Key`, `Repo` and `Kind` exist, and Kind's options.
   - **Fetch the `yourTurn` view** and note its filter. It should filter on `Agent can do this` and `Status` only. If it also filters on `Type`, this is a board built before that filter was dropped, and human work typed anything but `Launch Blocker` is invisible to `/lc:mine` - say so and offer to update the view to the `configure` line from `init.py views`. Do not work around it by retyping stories: Type answers "does this block shipping", not "who can do this", and bending it to satisfy a view corrupts both.
6. **Pick the key and prefix, and prove they are free.** Key: the repo directory name, lowercased. Prefix: 2-6 capitals. Query the Stories data source in **rows mode** filtered on `Story ID` `string_starts_with` `<PREFIX>-`, limit 1, and the Projects data source filtered on `Key` `string_is` the key (or the title, if there is no Key property). Either returning a row means taken - pick another and re-check. Do not use SQL mode; it is billed.

## 1. Propose - writes nothing

7. **Inventory the repo before believing the document.** Top-level tree, `git log --oneline | head -50` and the commit count, manifests (`package.json`, `pyproject.toml`, `Package.swift`, `*.xcodeproj`, `build.gradle`, `go.mod`, `Cargo.toml`), test directories and how many tests exist, CI workflows, infrastructure (`*.tf`, `Dockerfile`, deploy configs), and env examples. An empty repo is an answer too - then the document is all there is, and its claims are `unverifiable`, not `holds`.
8. **Extract every claim the source makes about the state of things** - built, not built, deployed, decided, pending - and check each against the inventory. Record each as `holds`, `false`, `partial` or `unverifiable`, with the evidence (a path, a command and its output, a commit). Work that is already done does not become a story; a claim marked `false` usually changes one.
9. **Run `python3 <base directory>/plan.py clocks --repo <target> --source <source file>`.** These are the external clocks this launch has - store reviews, account verifications, sandbox exits - with lead times the outside world sets. File every one it prints as its own story (`gating: External`, `agent: false`, `clock: <key>`, `leadTime`, `leadDays`, `doneWhen` and `notes` from the clock, adjusted to this project, with each `Source` URL carried into `notes`), keeping the clock's own `blockedBy` edges between clocks. A clock whose reason reads `blocks <key>` was pulled in because a triggered clock waits on it; decline it only together with that clock, or by saying why the edge does not apply here. Decline one only with a concrete reason in `clocksDeclined` ("enrolling as an individual, so no D-U-N-S"). Then think past the list: if this launch has a clock it does not know - a regulator, a partner's API approval, a hardware certification - file that too. The document will almost never mention these, and they are the reason this command exists.
10. **Draft the stories.** Split the remaining work into stories a single session can finish: XS under an hour, S 1-3 hours, M half a day, L 1-2 days, XL 3+ days - split anything bigger than L. For each:
    - `type`: Launch Blocker if users cannot be served without it, Backlog if it is a better product, Chore otherwise. Launch Blockers take plain IDs (`APP-07`), everything else the `-B` series.
    - `agent`: false for anything needing a human at a GUI, a login, a payment, a device, legal judgement or a third party. Code that *implements* a login is agent work; *logging in to* a console is not. If the wording trips `lint` but an agent really can do it, give `agentOverride` a reason.
    - `doneWhen`: the check, not the goal.
    - `blockedBy`: real dependencies only, as draft IDs. An edge that is merely "nicer to do first" is ordering, not blocking - express it by position instead.
    - `notes`: traps from the claims check, the clock notes, anything the next session would otherwise pay to rediscover.
    - Put every file name and path in backticks, in every field. Notion stores a bare `DESIGN.md` or `cli.py` as a link to `http://DESIGN.md`, and that is what every later session reads out. `lint` fails on it.
    List stories in the order they should run; Seq follows that order, moved only as far as needed to put blockers first.
11. **Write the proposal** to `<scratchpad>/lc-plan/proposal.json` in the format in `plan.py`'s docstring, and run `python3 <base directory>/plan.py lint <proposal> --repo <target> --source <source file> --epics "<the board's Epic options, comma-separated>"`. Fix every FAIL and re-run until it exits 0. Read the warnings; each one is a question you should be able to answer.
12. **Present it for review** - in this order:
    - What will be provisioned: the Projects row (name, key), the road view name, the config path, and the board it goes on.
    - **Claims checked**: claim, verdict, evidence. This table is how the user sees the document was not taken on trust.
    - **The backlog**, one table: draft ID, proposed Story ID series (`TP-nn` or `TP-Bn` - say the real numbers are assigned at filing), Name, Type, Estimate, Gating, Agent can do this, Lead time, Lead days, Blocked by, Done when. Do not abbreviate Done when.
    - External clocks filed and declined, with the reasons.
    - What `/lc:next` would hand out first and what `/lc:mine` would lead with, once filed.

    **Ask for confirmation, and write nothing - to Notion or to disk outside the scratchpad - until the user gives it.** Edits go back through step 11: change the proposal, re-lint, re-present what changed.

## 2. Provision - on confirmation

Do these in order. If a step fails, stop: say exactly what now exists (with URLs) and what does not, and that re-running `/lc:plan` with the same source resumes from there. Never skip ahead to filing stories on a half-provisioned project.

13. Copy the proposal to `<target>/.claude/lc-plan/proposal.json`, and create `<target>/.claude/lc-plan/state.json` holding `{}`. Everything below records into the state file as it goes, which is what makes a failed run resumable.
14. **Create the Projects row** in the Projects data source: the title, `Key`, `Repo` (the target's absolute path) and `Kind` if one of its options fits - leave the rest for the owner. Fetch it back, and record it: `plan.py record --state <state> --draft _project --url <its URL>`.
15. **Create the road view** on the Stories database (`database_id` = the Stories database, `data_source_id` = its data source), type `table`, named `Road — <key>`, configured:
    `FILTER "Project" = "<project page URL>"; SORT BY "Seq" ASC; SHOW "Name", "Story ID", "Status", "Type", "Seq", "Estimate", "Gating", "Agent can do this", "Done when"`.
    Build its URL as `https://www.notion.so/<stories database id, no dashes>?v=<view id, no dashes>`. Fetch the view and confirm its filter is `relation_contains` on Project with this project's page, then query it in view mode: it must resolve and return **zero** rows. A row here means the filter is wrong - stop. Record it: `plan.py record --state <state> --draft _road --url <road URL>`.
16. **Write the config**: `python3 <base directory>/plan.py config --repo <target> --from <the board's launch-control.json> --project <key> --prefix <PREFIX> --project-page <project URL> --road <road URL>`. It refuses to overwrite another project's config, copies the shared views, sets `autoMerge` false until the owner decides otherwise, and adds the local files to `.gitignore`.
17. Run `python3 <base directory>/../doctor/doctor.py --repo <target> --local-only`. The one failure to expect is a repo with no reachable `origin`: say so, and that `git.baseBranch` needs checking before the first `/lc:done`. Anything else, stop and report it.

## 3. File - one story at a time

18. Get the filing order: `python3 <base directory>/plan.py order <target>/.claude/lc-plan/proposal.json --state <state>`. It lists unfiled drafts, blockers first.
19. For **each** draft, in that order - this loop is groom's re-read-and-retry, run per story:
    1. **Re-read the road view** in view mode, every page, and write the pages to a board file in your scratchpad. This is the last thing before the create, and it is also the read-back of the previous one.
    2. `plan.py next-id <proposal> --state <state> --draft <D> --board <board file> --prefix <PREFIX>` prints the candidate. It counts this run's own ledger as well as the board, so a row not yet visible in the view cannot be handed out twice.
       - Exit 2 means an ID this run filed is now on two rows: another session lost or won the same race. Allocate a fresh ID for **the row this run created** (never the other one - its session is using it), set its `Story ID` with the page update tool, `plan.py record --replace`, and go back to 1. Five renumbers in a row: stop and say so.
    3. `plan.py payload <proposal> --state <state> --draft <D> --id <candidate> --project-url <project URL>` prints the page properties: Blocked by as the filed blockers' page URLs, Seq, and Status - `Ready` with no blockers, `Backlog` otherwise (every blocker in a new plan is a story this run just filed, so none is Done).
    4. Create the page in the Stories data source with exactly those properties, synchronously (`allow_async: false`).
    5. `plan.py record --state <state> --draft <D> --id <candidate> --url <new page URL>`.
    If a create fails, stop: the state file holds everything filed so far.
20. **Verify the board.** Re-read the road view to the last page and run `plan.py verify --state <state> --board <board file> --prefix <PREFIX>`. A missing ID is usually view lag - re-read once or twice before calling it lost. A duplicate is handled as in 19.2.
21. Run `/lc:doctor` for the target in full: with stories on the road view it should now be clean.

## 4. Report

- The Projects row, the road view, and the config path.
- Every story filed: Story ID, name, Status, Agent can do this, Gating, Lead time, Lead days.
- Claims that turned out false, in one line each - that is where the document was wrong.
- **The first story `/lc:next` returns** in that repo (lowest Seq, Ready, agent-doable) and **what `/lc:mine` leads with** (the item `/lc:mine` names under Start today, now that the rows are filed). Name the clock to start today.
- Whether to commit `.claude/launch-control.json`: yes for a private repo, so a fresh clone works (the hooks silently do nothing without it); no for a public one, where the board's IDs should stay out of history.
- `.claude/lc-plan/` can be deleted once `/lc:doctor` is clean; it is gitignored until then.

## Resuming

If `<target>/.claude/lc-plan/state.json` exists, an earlier run stopped part way. Do not start over - that is how a project ends up with two Projects rows and two road views.

- Read the proposal and state from `<target>/.claude/lc-plan/`, and tell the user what the earlier run got through.
- Skip step 6: the key and prefix are taken by this run's own Projects row and stories, which is expected. Do re-run the rest of pre-flight.
- `_project` present: fetch it; it must still exist. Otherwise continue from step 14.
- `_road` present: query it; it must resolve and hold only this prefix. Otherwise continue from step 15.
- Config present and `plan.py config` reports it already written: continue. Otherwise step 16.
- Then step 18 onward: `order` skips every draft already filed.

The proposal was confirmed when the earlier run began. If the user wants to change it now, re-run step 11's lint on the edited proposal and confirm again before filing anything further.
