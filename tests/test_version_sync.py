"""The version-sync check, demonstrated in both directions.

LC-B10 asks for a command that exits non-zero while the three version records
disagree and 0 once they agree, shown both ways. Both directions are asserted
here so CI holds the line: the drift this replaces came back within one story
of being fixed by hand, twice.

The mismatch is SYNTHETIC - written into a temp tree, never into the working
tree. Real drift is the thing being prevented, not a fixture to leave lying
around. The one test that does read the working tree reads it, and asserts the
check passes against it as it stands.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join("tests", "check_version_sync.py")

PLUGIN_JSON = os.path.join("plugins", "lc", ".claude-plugin", "plugin.json")
MARKETPLACE_JSON = os.path.join(".claude-plugin", "marketplace.json")
README = "README.md"

# Deliberately nothing like a version this repo has ever carried, so a test
# that accidentally read the real tree would fail rather than pass by luck.
PLUGIN_V, MARKET_V, README_V = "9.9.1", "9.9.2", "9.9.3"


def run(root):
    """The documented command, against `root`. Returns (code, stdout+stderr)."""
    done = subprocess.run(
        [sys.executable, "-B", CHECK, root],
        cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


def write(root, rel, text):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(text)


def tree(root, plugin=PLUGIN_V, market=MARKET_V, readme=README_V):
    """A minimal three-file copy carrying whatever versions it is handed."""
    write(root, PLUGIN_JSON, json.dumps({"name": "lc", "version": plugin}))
    write(root, MARKETPLACE_JSON,
          json.dumps({"name": "launch-control", "metadata": {"version": market}}))
    write(root, README,
          "# Launch Control\n\n## Install\n\nnot here\n\n"
          "## Status\n\nv%s, and honest about it: still pre-1.0.\n\nMIT.\n" % readme)


class VersionSync(unittest.TestCase):

    def test_the_working_tree_agrees(self):
        """The repo as it stands: exit 0, and the version it reports is real."""
        code, out = run(REPO)
        self.assertEqual(code, 0, out)
        with open(os.path.join(REPO, PLUGIN_JSON), encoding="utf-8") as fh:
            live = json.load(fh)["version"]
        self.assertIn(live, out)

    def test_a_synthetic_desync_fails_and_names_all_three(self):
        """Three files disagreeing: non-zero, every value and every file named."""
        with tempfile.TemporaryDirectory() as root:
            tree(root)
            code, out = run(root)
            self.assertNotEqual(code, 0, "drift went unreported:\n" + out)
            for version, where in ((PLUGIN_V, PLUGIN_JSON),
                                   (MARKET_V, MARKETPLACE_JSON),
                                   (README_V, README)):
                self.assertIn(version, out, "value %s not named:\n%s" % (version, out))
                self.assertIn(where, out, "file %s not named:\n%s" % (where, out))

    def test_one_file_lagging_is_enough_to_fail(self):
        """The shape the drift actually took: plugin.json moved, one file did not.

        LC-B6 bumped plugin.json and left marketplace.json and the README
        behind; a check that only noticed all-three-different would have
        passed LC-B9's tree as happily as this one.
        """
        for lag in ("marketplace", "readme"):
            with self.subTest(lag=lag):
                with tempfile.TemporaryDirectory() as root:
                    tree(root,
                         plugin="1.2.3",
                         market="1.2.2" if lag == "marketplace" else "1.2.3",
                         readme="1.2.2" if lag == "readme" else "1.2.3")
                    code, out = run(root)
                    self.assertNotEqual(code, 0, "a lagging file passed:\n" + out)

    def test_the_same_tree_in_sync_passes(self):
        """The fixture is not simply always-red: agree, and it goes green."""
        with tempfile.TemporaryDirectory() as root:
            tree(root, plugin="1.2.3", market="1.2.3", readme="1.2.3")
            code, out = run(root)
            self.assertEqual(code, 0, out)
            self.assertIn("1.2.3", out)

    def test_a_missing_record_is_a_failure_not_a_skip(self):
        """Two files agreeing is not agreement - say so instead of passing."""
        for rel in (PLUGIN_JSON, MARKETPLACE_JSON, README):
            with self.subTest(missing=rel):
                with tempfile.TemporaryDirectory() as root:
                    tree(root, plugin="1.2.3", market="1.2.3", readme="1.2.3")
                    os.remove(os.path.join(root, rel))
                    code, out = run(root)
                    self.assertNotEqual(code, 0, "missing %s passed:\n%s" % (rel, out))
                    self.assertIn(rel, out)

    def test_a_readme_that_hides_the_version_fails_loudly(self):
        """Reformat the Status section and the check complains, not shrugs."""
        with tempfile.TemporaryDirectory() as root:
            tree(root, plugin="1.2.3", market="1.2.3", readme="1.2.3")
            write(root, README,
                  "# Launch Control\n\n## Status\n\nStill pre-1.0, see below.\n")
            code, out = run(root)
            self.assertNotEqual(code, 0, out)
            self.assertIn("## Status", out)


if __name__ == "__main__":
    unittest.main()
