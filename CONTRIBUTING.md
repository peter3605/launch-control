# Contributing

This is a small, pre-1.0 project with one real user. Issues and pull requests are
welcome. What follows is what a PR needs to be mergeable, and the two rules that
are enforced mechanically rather than by review.

## The one thing to understand first

**Everything under `plugins/lc/` takes effect in every repo that has the plugin
installed, on that repo's next session.** There is no staging step and no rollback
but git. A change to a command or a hook is a change to a shared library, not to a
local script — write it that way.

## Running the suite

Stdlib only. No virtualenv, no `pip install`, no requirements file.

```
python3 -B tests/check_version_sync.py          # the version records agree
python3 -B -m unittest discover -s tests -t . -v # everything else
```

Both run on every pull request via [`.github/workflows/test.yml`](.github/workflows/test.yml),
against the runner's own `python3` — deliberately, because that is the closest
thing to the interpreter a user will actually run it under.

`-B` keeps the run from leaving `__pycache__` behind. It is what CI uses.

What the suite covers today:

| File | What it holds the line on |
|---|---|
| `tests/test_mine.py` | `/lc:mine`'s lead-time arithmetic — the computation this product is sold on |
| `tests/test_init.py` | `init.py`: the DDL and views generated from `board.json`, `preflight`'s refusal to build a second board, and `check` failing on a missing property, a lost select option or a wrongly filtered view - against fetch results in both the inline and saved-to-file shapes |
| `tests/test_plan.py` | `plan.py`: `lint`'s refusals, `next-id`'s use of the run's ledger and its exit 2 on a lost ID race, `payload`'s Ready/Backlog, `order`, `verify`, and `config` refusing to overwrite another project |
| `tests/test_doctor.py` | `doctor.py`'s comparison of an existing board with `board.json`: a `yourTurn` view still filtering on Type, a missing property, a lost option, a wrong sort and a mis-scoped road each fail with their fix, and a matching board passes - on `test_init.py`'s fixtures |
| `tests/test_ids.py` | `ids.py`, the board reads that replaced metered queries: `find`, `next` per sequence, `dependents` across projects and URL forms, `prefix-free`, and the refusal to answer from a view not read to its last page |
| `tests/test_mutation_guard.py` | That `test_mine.py`, `test_init.py`, `test_plan.py`, `test_doctor.py` and `test_ids.py` would actually go red if what they pin broke. A mutation that slips through fails here |
| `tests/test_version_sync.py` | The version check, demonstrated failing and passing |
| `tests/test_setup.py` | `setup.sh` parses under bash 3.2, and its dry run writes nothing |
| `tests/test_hooks.py` | The Stop hook nudges once per bound story and never on an empty binding (what `/lc:release` leaves), both hooks parse under `/bin/bash`, and the README Commands table lists every skill |

Tests live at the repo root, never under `plugins/lc/`. The plugin directory is
copied wholesale into every installed repo and its users do not want this suite.

## The version-bump rule

Three files carry this project's version:

- `plugins/lc/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- the README's `## Status` line

**All three carry the same version and move in the same commit.**
`python3 tests/check_version_sync.py` exits non-zero while they disagree, naming
each value and the file it came from. CI runs it as a step of its own.

Bump `plugin.json` first and bring the other two along, because `migrate.sh` stamps
`plugin.json`'s version into each installed repo as that repo's **drift baseline**.
A stale baseline makes the drift check in those repos report agreement it never
checked — which is worse than a wrong number, because it is a check that has
quietly stopped checking.

The landing page in `site/index.html` shows the version too, in its `id="version"`
chip. It is not one of the three records, but `tests/test_site.py` fails until it
matches `plugin.json`, so update it in the same commit. The same test holds the
page's command list to `plugins/lc/skills/`, its `/lc:mine` report to the README's
copy, and its chart to `examples/sample-board.json`; a merge to `main` that touches
`site/` republishes it through `.github/workflows/pages.yml`.

**Bump the version whenever command or hook behaviour changes.** Documentation-only
changes do not need one. The full argument is in `tests/check_version_sync.py`'s
own docstring.

## Cutting a release

A version bump **is** a release: installed copies update only when `plugin.json`'s
version changes ([decision 0002](docs/decisions/0002-release-ref.md)). So every
version that reaches `main` is tagged and released, in this order:

1. **Merge** the pull request that bumps the version, with its `CHANGELOG.md`
   entry, once CI is green.
2. **Tag** the merge commit on `main`, annotated, as `v<version>`, and push the
   tag:

   ```sh
   git checkout main && git pull
   V=$(python3 -c 'import json; print(json.load(open("plugins/lc/.claude-plugin/plugin.json"))["version"])')
   git tag -a "v$V" -m "v$V"
   git push origin "v$V"
   ```

   If more commits land under the same version before anything is tagged, tag the
   last one that still carries it. Never move a tag once pushed.
3. **Release** it, with that version's `CHANGELOG.md` entry as the body:

   ```sh
   python3 - "$V" > /tmp/notes.md <<'PY'
   import re, sys
   text = open("CHANGELOG.md").read()
   m = re.search(r"^## " + re.escape(sys.argv[1]) + r" .*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
   print(m.group(1).strip().rstrip("-").strip())
   PY
   gh release create "v$V" --title "v$V" --notes-file /tmp/notes.md --verify-tag
   ```

4. **Check:** `git ls-remote --tags origin "v$V"` prints a line, and
   `gh release view "v$V"` exits 0.

**CI checks that it happened.** The `release-tag` job in
`.github/workflows/test.yml` runs `python3 tests/check_release_tag.py` on every push
to `main`, daily at 14:00 UTC, and on demand (`workflow_dispatch`). It fails when
the version in `plugin.json` has no `v<version>` tag, when that tag is lightweight
rather than annotated, or when it points at a commit carrying another version. It
never runs on a pull request, because the bump PR cannot have its tag yet. On the
push that merges a bump, the new version passes with a reminder. The next push to
`main`, or the next daily run, fails until it is tagged.

When it fails, do steps 2 and 3 above for the version it names, then re-run the
failed job. `UNTAGGED RELEASE` means cut the tag. If it says the checkout has no
tags at all, the workflow's `fetch-depth: 0` was lost. For `LIGHTWEIGHT TAG` or
`MISPLACED TAG`, a tag was already pushed, so ask Peter before replacing it.

**Who:** Peter, or a session he has told to. The tag and the release are public,
so a session confirms with him before pushing either. Versions 0.1.0 to 0.9.0 were
backfilled on 2026-11-15, each tag on the last `main` commit carrying that version.

## Shell scripts

`setup.sh`, `migrate.sh` and the two hooks must parse and run under **stock macOS
`/bin/bash`, which is 3.2** (2007). That means:

- no associative arrays (`declare -A`)
- no `${var,,}` / `${var^^}`
- no `mapfile` / `readarray`
- no `|&`

Check any edit with `/bin/bash -n <script>`, **not** with whatever `bash` is on
your `PATH` — on a machine with Homebrew bash those are different programs and the
one that matters is `/bin/bash`. `tests/test_setup.py` runs that check in CI.

Two more rules, both paid for by real incidents:

- **Use `python3` for anything beyond trivial text handling.** BSD `sed` — the
  `sed` on every macOS — rejects GNU idioms. A `sed` one-liner in the drift check
  failed on macOS, its error went to `/dev/null`, both sides of the comparison came
  back empty, and every file looked identical. The check silently passed on exactly
  the edits it existed to catch.
- **Never send a failing command's stderr to `/dev/null`.** That message is usually
  the whole fix. `gh auth status` is the clearest example: its stderr tells you what
  to do about it.

## What a pull request needs

1. **A green build.** Both CI steps. An empty check rollup is not a pass in this
   repo — that carve-out was removed deliberately.
2. **The version bumped**, if command or hook behaviour changed, with all three
   records moved together.
3. **A `CHANGELOG.md` entry** under the new version.
4. **Tests for a behaviour change**, where the behaviour is testable without a
   Notion connection. Most of this repo's logic is; the parts that are not are the
   skill prompts.
5. **A story ID in the subject line**, if the work came from the board — e.g.
   `LC-17: Give a stranger a front door`. Work that is not on the board is how the
   last tracker went stale.

## Reporting a bug

Use [the bug template](.github/ISSUE_TEMPLATE/bug.md). It asks for four things,
and all four are load-bearing: the plugin version from the `SessionStart` banner,
your Claude Code version, your OS, and the output of `/lc:doctor`. Most reports
here turn out to be a config that has silently regressed or a plugin version
that stopped updating, and those four answers separate the two immediately.

## The repository is public

No spend figures, no account state, no real Notion IDs in tracked files. This
repo's own `.claude/launch-control.json` is gitignored for that reason — unlike the
product repos, where it is tracked so that a fresh clone works.
[`examples/launch-control.example.json`](examples/launch-control.example.json) is
the version the world sees. Sample output in docs stays anonymised, the way the
README's `/lc:mine` sample is.

## Licence

MIT. By contributing you agree your contribution is licensed under it.
