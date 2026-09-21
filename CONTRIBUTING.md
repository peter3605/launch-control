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
| `tests/test_mutation_guard.py` | That `test_mine.py` would actually go red if that arithmetic broke. A mutation that slips through fails here |
| `tests/test_version_sync.py` | The version check, demonstrated failing and passing |
| `tests/test_setup.py` | `setup.sh` parses under bash 3.2, and its dry run writes nothing |

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

**Bump the version whenever command or hook behaviour changes.** Documentation-only
changes do not need one. The full argument is in `tests/check_version_sync.py`'s
own docstring.

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
