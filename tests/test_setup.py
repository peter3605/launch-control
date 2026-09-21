"""setup.sh: it parses where it has to run, and a dry run really is dry.

Two properties, both of which have been broken before in this repo's shell
scripts and both of which fail silently rather than loudly:

1. IT PARSES UNDER BASH 3.2. Stock macOS /bin/bash is 3.2 (2007). LC-06 was a
   whole story about install.sh failing to parse there - and the failure mode is
   the bad one, because bash parses a compound statement as a unit: a syntax
   error inside an if-block at the bottom of the file is only discovered once
   execution reaches it, by which time the steps above it have already run and
   written. `bash -n` is what catches that before a user does.

2. A DRY RUN WRITES NOTHING. Dry run is the default, so this is the mode almost
   every first run is in. "Writes nothing" is asserted against a throwaway HOME
   that starts empty and must stay empty - which also caught a real one: Apple's
   python3 was depositing bytecode caches under ~/Library/Caches on every run,
   so setup.sh now invokes python3 with -B.

The external commands are STUBBED on PATH. That is the point rather than a
compromise: it lets the dry run walk every section on a machine that has none of
them (CI has no `claude` and no `gh`), and it makes the run deterministic on a
machine that has all of them. python3, git and the coreutils stay real, because
the script genuinely uses them.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPTS = ("setup.sh", "migrate.sh", "install.sh")

# A `claude` that reports a machine with nothing set up: no notion server, this
# marketplace absent, the plugin not installed. The JSON shapes are the ones
# `claude plugin ... --json` actually returns, trimmed to the keys setup.sh reads.
STUB_CLAUDE_EMPTY = r"""#!/bin/sh
case "$1 $2" in
  "--version ") echo "9.9.9 (Claude Code)"; exit 0;;
  "mcp list") echo "Checking MCP server health…"; echo ""
              echo "some-other: https://example.invalid/mcp (HTTP) - ✔ Connected"; exit 0;;
  "plugin --help") echo "Commands:"; echo "  install|i [options] <plugin>"
                   echo "  marketplace   Manage Claude Code marketplaces"; exit 0;;
esac
case "$*" in
  "plugin marketplace list --json") echo '[{"name":"claude-plugins-official"}]'; exit 0;;
  "plugin list --json") echo '[{"id":"other@claude-plugins-official","version":"1.0.0"}]'; exit 0;;
esac
echo "stub claude: unhandled: $*" >&2; exit 1
"""

# The same machine after a successful --apply: everything already in place.
STUB_CLAUDE_READY = r"""#!/bin/sh
case "$1 $2" in
  "--version ") echo "9.9.9 (Claude Code)"; exit 0;;
  "mcp list") echo "Checking MCP server health…"; echo ""
              echo "notion: https://mcp.notion.com/mcp (HTTP) - ✔ Connected"; exit 0;;
  "plugin --help") echo "Commands:"; echo "  install|i [options] <plugin>"
                   echo "  marketplace   Manage Claude Code marketplaces"; exit 0;;
esac
case "$*" in
  "plugin marketplace list --json") echo '[{"name":"launch-control"}]'; exit 0;;
  "plugin list --json") echo '[{"id":"lc@launch-control","version":"9.9.9"}]'; exit 0;;
esac
echo "stub claude: unhandled: $*" >&2; exit 1
"""

# A Claude Code old enough to predate `claude plugin`. The subcommands are newer
# than the slash commands they mirror, so setup.sh must check rather than assume -
# running a subcommand that does not exist would fail the script on a machine
# whose only real problem is being a few versions behind.
STUB_CLAUDE_NO_PLUGIN_CLI = r"""#!/bin/sh
case "$1 $2" in
  "--version ") echo "1.0.0 (Claude Code)"; exit 0;;
  "mcp list") echo "notion: https://mcp.notion.com/mcp (HTTP) - ✔ Connected"; exit 0;;
  "plugin --help") echo "error: unknown command 'plugin'" >&2; exit 1;;
esac
echo "stub claude: unhandled: $*" >&2; exit 1
"""

STUB_GH = r"""#!/bin/sh
[ "$1" = "--version" ] && { echo "gh version 9.9.9 (2026-01-01)"; exit 0; }
[ "$1 $2" = "auth status" ] && { echo "Logged in to github.com account stub"; exit 0; }
exit 0
"""


def bashes():
    """The bash binaries worth checking, without duplicates.

    /bin/bash first and always: on macOS that is 3.2 and is what a user runs,
    while `bash` on PATH may be a Homebrew 5.x that accepts things 3.2 rejects.
    Checking only the one on PATH is how this class of bug reaches a user.
    """
    found = []
    for candidate in ("/bin/bash", shutil.which("bash")):
        if candidate and os.path.exists(candidate) and candidate not in found:
            found.append(candidate)
    return found


def write_exe(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, 0o755)


def snapshot(root):
    """Every path under `root`, relative. Order-independent."""
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root):
        for name in list(dirnames) + list(filenames):
            seen.add(os.path.relpath(os.path.join(dirpath, name), root))
    return seen


class Parses(unittest.TestCase):
    """bash -n, on every bash a user might plausibly reach for."""

    def test_the_shell_scripts_parse(self):
        found = bashes()
        self.assertTrue(found, "no bash found to check with")
        for shell in found:
            for script in SCRIPTS:
                done = subprocess.run(
                    [shell, "-n", script], cwd=REPO,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(
                    0, done.returncode,
                    "%s failed to parse under %s:\n%s"
                    % (script, shell, done.stdout.decode("utf-8", "replace")))

    def test_bin_bash_is_covered(self):
        """The check above is worthless if it silently skipped /bin/bash."""
        if not os.path.exists("/bin/bash"):
            self.skipTest("/bin/bash does not exist on this platform")
        self.assertIn("/bin/bash", bashes())


class DryRun(unittest.TestCase):
    """The default mode, against a throwaway HOME that must stay empty."""

    def run_setup(self, stub_claude, args=()):
        """setup.sh with stubbed `claude`/`gh` and an empty HOME.

        Returns (returncode, output, paths written into HOME).
        """
        work = tempfile.mkdtemp(prefix="lc-setup-")
        self.addCleanup(shutil.rmtree, work, True)
        home = os.path.join(work, "home")
        binned = os.path.join(work, "bin")
        os.makedirs(home)
        os.makedirs(binned)
        write_exe(os.path.join(binned, "claude"), stub_claude)
        write_exe(os.path.join(binned, "gh"), STUB_GH)

        self.assertEqual(set(), snapshot(home), "the throwaway HOME did not start empty")

        env = dict(os.environ)
        env["HOME"] = home
        env["PATH"] = binned + os.pathsep + env.get("PATH", "")
        # Left unset on purpose. Setting it would make "writes nothing" true by
        # configuration rather than because the script behaves; setup.sh passes
        # -B to python3 itself, and that is the thing under test.
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        for var in ("XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
            env.pop(var, None)

        shell = bashes()[0]
        done = subprocess.run(
            [shell, "./setup.sh"] + list(args), cwd=REPO, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return (done.returncode,
                done.stdout.decode("utf-8", "replace"),
                snapshot(home))

    def test_a_dry_run_writes_nothing_to_home(self):
        code, out, written = self.run_setup(STUB_CLAUDE_EMPTY)
        self.assertEqual(0, code, out)
        self.assertEqual(
            set(), written,
            "a dry run wrote into HOME:\n  %s\n\nfull output:\n%s"
            % ("\n  ".join(sorted(written)), out))

    def test_every_python3_call_in_setup_passes_dash_B(self):
        """The mechanism behind "writes nothing", guarded directly.

        The black-box test above is the property that matters, but it is only
        SENSITIVE to this regression on an interpreter that caches bytecode
        under HOME - Apple's framework python3 does, a Homebrew or Linux one
        does not. So on most machines it would go on passing with -B removed,
        which is a test that has quietly stopped testing. Assert the flag too,
        where the check costs nothing and holds everywhere.
        """
        with open(os.path.join(REPO, "setup.sh"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()

        # An INVOCATION is `python3` followed by a flag or a heredoc. That
        # deliberately excludes `command -v python3` (a lookup, not a run),
        # `python3 -V` (writes no bytecode), and the word appearing in a comment
        # or in a message printed to the user.
        invocation = re.compile(r"python3\s+(?:-\w|<<)")
        exempt = re.compile(r"command\s+-v\s+python3|python3\s+-V\b")
        offenders = []
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("#"):
                continue
            stripped = exempt.sub("", line)
            if invocation.search(stripped) and not re.search(r"python3\s+-B\b", stripped):
                offenders.append("%d: %s" % (n, line.strip()))
        self.assertEqual(
            [], offenders,
            "setup.sh invokes python3 without -B, so a run can leave bytecode "
            "caches in the user's HOME:\n  %s" % "\n  ".join(offenders))

    def test_the_dry_run_that_wrote_nothing_actually_ran(self):
        """A run that bailed at step 0 would also write nothing.

        So require the evidence that it walked the whole script: a `would` line
        from each of the two sections that change anything, and the closing
        paragraph. Without this, the test above passes on a script that is
        broken from its second line onwards.
        """
        code, out, _ = self.run_setup(STUB_CLAUDE_EMPTY)
        self.assertEqual(0, code, out)
        for expected in (
                "would     claude mcp add --transport http notion",
                "would     claude plugin marketplace add",
                "would     claude plugin install lc@launch-control",
                "4. What no script can do for you",
                "This was a dry run and changed nothing.",
        ):
            self.assertIn(expected, out, "missing from the dry run:\n%s" % out)

    def test_a_dry_run_on_a_ready_machine_proposes_nothing(self):
        """Idempotency, which is a claim setup.sh makes in its own output.

        With everything already in place there is nothing left to do, so no
        `would` line may appear - in either mode, since what --apply does is
        exactly the set of `would` lines.
        """
        code, out, written = self.run_setup(STUB_CLAUDE_READY)
        self.assertEqual(0, code, out)
        self.assertEqual(set(), written)
        self.assertNotIn("would ", out,
                         "proposed work on an already-set-up machine:\n%s" % out)
        for expected in (
                "`notion` is configured",
                "marketplace `launch-control` is already added",
                "plugin `lc@launch-control` is installed",
        ):
            self.assertIn(expected, out, out)

    def test_it_prints_the_slash_commands_when_the_plugin_cli_is_missing(self):
        """No `claude plugin` subcommands: print the two slash commands instead.

        And do not fail the run over it. The machine is a few versions behind,
        which is a thing to say, not a thing to die on.
        """
        code, out, written = self.run_setup(STUB_CLAUDE_NO_PLUGIN_CLI)
        self.assertEqual(0, code, out)
        self.assertEqual(set(), written)
        self.assertIn("/plugin marketplace add peter3605/launch-control", out)
        self.assertIn("/plugin install lc@launch-control", out)
        # It must not claim it would run a subcommand this Claude Code lacks.
        self.assertNotIn("would     claude plugin", out, out)

    def test_an_unknown_option_is_refused(self):
        code, out, written = self.run_setup(STUB_CLAUDE_READY, args=("--wat",))
        self.assertEqual(2, code, out)
        self.assertIn("unknown option --wat", out)
        self.assertEqual(set(), written)


class NoWrongDoor(unittest.TestCase):
    """install.sh must not look like a working installer. (LC-17 criterion 4)"""

    def test_install_sh_is_a_signpost_and_says_so_loudly(self):
        shell = bashes()[0]
        done = subprocess.run(
            [shell, "./install.sh"], cwd=REPO,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = done.stdout.decode("utf-8", "replace")
        # Non-zero matters as much as the text: a script that prints advice and
        # exits 0 reads as success to a person and to anything scripting it.
        self.assertNotEqual(0, done.returncode, out)
        self.assertIn("./setup.sh", out)
        self.assertIn("./migrate.sh", out)

    def test_the_two_real_scripts_exist_and_are_executable(self):
        for script in ("setup.sh", "migrate.sh"):
            path = os.path.join(REPO, script)
            self.assertTrue(os.path.exists(path), "%s is missing" % script)
            self.assertTrue(os.access(path, os.X_OK), "%s is not executable" % script)


if __name__ == "__main__":
    unittest.main()
