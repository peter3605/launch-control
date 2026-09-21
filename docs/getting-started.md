# Getting started

Zero to a first story marked **Done**.

The [Quickstart](../README.md#quickstart) is the same path in one screen. This is
the version with the output in it, for when you want to know what each step should
look like before you run it, or when one of them did something else.

**About the output below.** Everything in a `setup.sh` or `doctor` block was
captured from a real run and then anonymised. The blocks showing a conversation
with `/lc:next`, `/lc:start` and `/lc:done` are marked as **shape, not transcript**:
those commands are agent turns, so their exact wording differs every time, and a
"real" transcript would be a fiction dressed as a promise. What is fixed is what
they do and what they write, and that is what those blocks show.

Names here are a fictional project, `my-app`, with the story-ID prefix `APP`.

---

## Before you start

Have these, or [Quickstart step 1](../README.md#quickstart) will tell you which is
missing:

- **Claude Code.**
- **`python3`**, by that name, on `PATH`.
- **`git`**.
- **A Notion account.** The free plan is enough — every command queries views in
  view mode, which is unmetered. Nothing here uses billed SQL mode.
- **`gh`, authenticated** — only if you want `/lc:done` to open pull requests. The
  board works fine without it.
- **A Notion page** to put the board under. An empty one is ideal. Everything
  Launch Control creates goes inside it, and deleting that page later removes all
  of it.

[What you need first](../README.md#what-you-need-first) in the README says what
each of these breaks if it is missing.

---

## 1. Run the setup script

Clone the repo and run it. **It is a dry run by default** — it tells you what it
would do and changes nothing:

```
$ ./setup.sh

Launch Control setup
(dry run - nothing will be changed. Pass --apply to do the automatable steps.)

1. Tools this needs
  ok        claude      2.1.278 (Claude Code)
  ok        python3     Python 3.13.1
  ok        git         git version 2.50.1
  WARN      gh          gh version 2.96.0 is installed but not authenticated:
              You are not logged into any GitHub hosts. To log in, run: gh auth login
  note                  Run: gh auth login      (/lc:done needs this; nothing else does)

2. Notion MCP server
  MISSING   no MCP server named `notion`
  would     claude mcp add --transport http notion https://mcp.notion.com/mcp --scope user
  note      --scope user makes it available in every repo rather than just this one.

3. The plugin
  would     claude plugin marketplace add peter3605/launch-control
  would     claude plugin install lc@launch-control
  note      Third-party marketplaces do NOT auto-update. This one is third-party, so
  note      the plugin will sit at whatever version you installed until you say
  note      otherwise - see step 3 of section 4.

4. What no script can do for you
  ...
```

Read the `would` lines, then:

```
$ ./setup.sh --apply
```

**On a machine that is already set up**, the same run reports everything already in
place and changes nothing — the script is idempotent, so re-running it is a way of
checking state, not only of changing it:

```
1. Tools this needs
  ok        claude      2.1.278 (Claude Code)
  ok        python3     Python 3.13.1
  ok        git         git version 2.50.1
  ok        gh          gh version 2.96.0, authenticated

2. Notion MCP server
  ok        `notion` is configured, and the health check reports it connected

3. The plugin
  ok        marketplace `launch-control` is already added
  ok        plugin `lc@launch-control` is installed (v0.6.0)
```

**If it stops**, it stops at the *first* missing hard requirement and names it,
rather than printing four problems at once:

```
1. Tools this needs
  MISSING   python3 is not on PATH

  STOPPING at the first missing requirement: python3
  Every skill shells out to python3, and so do both hooks, migrate.sh and this
  script. Without it the commands fail quietly rather than loudly, which is
  worse. Install python3 and re-run.

  Nothing has been changed.
```

---

## 2, 3 and 4. The parts no script can do

`setup.sh` finishes by printing these, because it cannot do them and will not
pretend it did. **Do all three.** Stopping after the first two is the usual way to
arrive at step 5 with a connector that reports healthy and returns nothing.

1. **Authorise Notion.** `/mcp` inside Claude Code, or `claude mcp login notion`.
   A browser flow. Step 1 configured the connector; this is what grants it access.

2. **Share the page.** In Notion: your page → `···` → **Add connections** → the
   Notion connector. Connectors see only what you share with them, and access
   cascades to everything inside that page.

3. **Turn on auto-update.** `/plugin` → Marketplaces → `launch-control` → Enable
   auto-update. Third-party marketplaces do not update themselves, and a plugin
   frozen at the version you installed today is the most common reason this
   project's behaviour and its documentation stop agreeing.

Then restart Claude Code, or run `/reload-plugins`, so the session picks the plugin
up. You should see a banner at the top of the next session in a tracked repo:

```
## Launch Control `v0.6.0`

This repo is tracked as project **my-app** (story IDs `APP...`). The backlog is
the source of truth for what to work on and what counts as finished.
```

No banner? The hooks open with `[ -f launch-control.json ] || exit 0`, so either
this repo is not on the board yet (expected — that is step 5) or `python3` is
missing. See [troubleshooting](troubleshooting.md#python3-is-not-on-path).

---

## 5. Build the board

In the repo you want tracked, inside Claude Code:

```
/lc:init https://www.notion.so/<your empty page>
```

It creates **two Notion databases** — Projects and Stories — every property the
commands read, and six shared views, then this repo's Projects row, its own `road`
view, and `.claude/launch-control.json`. It shows you the plan and **writes nothing
to Notion or to the repo until you confirm.**

Then it reads back everything it created and compares it against the schema, so a
property that did not take is a failure now rather than a mystery in three weeks.
Expect a few minutes of agent turns; it is doing a lot of small writes.

[`notion-schema.md`](notion-schema.md) describes what it built.

**For the second repo and every repo after it, do not run `/lc:init` again** — a
second board splits your work in two and each half looks complete. Run, in that
repo:

```
/lc:plan <design doc or repo path> --board <first repo>/.claude/launch-control.json
```

That creates the project, its road view and config on the **existing** board, and
files a backlog from your design doc or from the repo itself.

### Check it

```
/lc:doctor
```

A clean local run looks like this:

```
Launch Control doctor -> /Users/you/repos/my-app

Views in config
  ok    all seven view keys present

Git
  ok    git.baseBranch 'main' matches the default branch (remote)

Board
  ok    views.ready resolves (3 rows)
  ok    views.road resolves, 12 rows, all APP-

Standing notices
  ok    no notice names a finished story

Clean.
```

And a broken one says what broke and where — this is a real run against a config
with two deliberate faults in it:

```
Views in config
  ok    all seven view keys present
  FAIL  views.road has no ?v= view id - it opens the database, not a view

Git
  FAIL  could not determine the default branch (no reachable origin, no origin/HEAD)

Board
  skip  view resolution, road scoping and duplicate IDs - run with --views for a full check

Standing notices
  skip  git.notes names APP-04 - whether they are Done needs the board

2 problem(s).
```

Every line is explained in
[troubleshooting](troubleshooting.md#what-each-lcdoctor-failure-means). `skip` is
never a failure — it means a check did not run, which is different from passing.

---

## 6. Put some work on the board

If `/lc:plan` filed a backlog, you already have some. Otherwise file one thing:

```
/lc:groom the release workflow has no test step
```

Grooming is where the **Done when** gets written, and it is the part worth slowing
down for. The rule: *checkable by someone who was not in the conversation.* A
command that exits 0. A file containing a value. A screen showing a thing. Not
"the workflow is tested".

`/lc:groom` also decides whether this is work an agent can do at all. Anything
needing a human, a login, a card or a legal filing is filed as **your** work with a
lead time, and turns up in `/lc:mine` rather than `/lc:next`. That split is the
reason this project exists — see
[what `/lc:mine` prints](../README.md#what-it-prints-that-nothing-else-does).

---

## 7. Start a story

```
/lc:next
```

> **Shape, not transcript.** This is an agent turn; the wording varies.

It queries the Ready view, keeps only your prefix, takes the lowest `Seq`,
double-checks that the blockers really are closed, and reads the story out —
including **Notes and traps** in full, because that field is where the expensive
mistakes were recorded:

```
APP-04  Add a test step to the release workflow        Estimate: S

Done when
  .github/workflows/release.yml runs the suite before the publish step, and
  `python3 -m unittest discover -s tests -t .` exits 0 in CI on a pull request.

Notes and traps
  The publish step uses a token with write scope. Do not move it above the
  tests - a failing build would publish before the failure was known.

Start this? (/lc:start APP-04)
```

Confirm, and it binds the session:

```
/lc:start APP-04
```

Which sets the story to **In Progress** on the board, writes `APP-04` into
`.claude/.current-story`, and cuts a branch named `app-04-<short-slug>` from your
base branch. From here every commit should carry `APP-04` in its subject line.

Then do the work — that part is an ordinary Claude Code session.

---

## 8. Finish it

```
/lc:done
```

> **Shape, not transcript.**

`/lc:done` **checks the Done-when criteria before it ticks anything off.** This is
the whole point of the tool, and the step that makes the board worth trusting:

```
APP-04  Add a test step to the release workflow

Checking Done when:
  1. release.yml runs the suite before publish   ok   (line 22, publish at 31)
  2. unittest exits 0 in CI on a PR              ok   (run 1841, conclusion success)

Staging 2 files, committing, pushing, opening the PR...
  PR #12  https://github.com/you/my-app/pull/12
  checks: 1 passed
```

Then, by your repo's policy in the `git` block of `.claude/launch-control.json`:

- **`autoMerge: false`** — the default in a new repo — stops at a green PR, sets
  the story **In Review**, and leaves the merge to you.
- **`autoMerge: true`** merges and deletes the branch, sets the story **Done**, and
  promotes anything that was blocked on it from Backlog to Ready.
- **`enabled: false`** makes no commit, no push and no PR at all: it verifies and
  records, and leaves the change in your working tree.

If a criterion fails, **it does not mark the story Done.** It says which one
failed and what it found, and writes that into the story's **Last session** field.
Marking something Done that is not removes the only check that would have caught
the gap.

Out of the box you will land on **In Review**, so merge the PR yourself and the
story closes. That is your first story Done.

See [config-reference.md](config-reference.md) for the whole `git` block.

---

## Then what

```
/lc:mine       the work only a human can do, longest lead time first
/lc:status     where every project stands
/lc:reconcile  re-audit the board against the repo; evidence required to close anything
/lc:doctor     check the config has not silently regressed
```

`/lc:mine` is the one to look at next, and the one nothing else does. It splits
your non-agent work into *clocks* — external waits you cannot compress — and *your
desk*, projects a finish date for each, and names the single item that buys back
the most calendar time if you start it today, with the arithmetic shown rather than
asserted. [The README has a real run of it.](../README.md#what-it-prints-that-nothing-else-does)

Run it before you run `/lc:next`. The story an agent can do will still be there in
an hour; a six-week D-U-N-S application will not have started itself.
