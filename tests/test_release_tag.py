"""The release-tag check, demonstrated in both directions.

LC-27 asks for a CI check that fails when plugin.json's version has no matching
v<version> tag, and a test proving it fails untagged and passes tagged. Every
case runs against a throwaway git repo built in a temp dir, never this one:
tagging the real repo is a public write, and its tags are not a fixture.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = os.path.join(REPO, "tests", "check_release_tag.py")
PLUGIN_JSON = os.path.join("plugins", "lc", ".claude-plugin", "plugin.json")

ENV = dict(os.environ,
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def git(root, *args):
    done = subprocess.run(["git", "-C", root] + list(args), env=ENV,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if done.returncode:
        raise AssertionError("git %s failed: %s" % (" ".join(args), done.stdout))
    return done.stdout.decode().strip()


def commit_version(root, version):
    """Commit a plugin.json carrying `version`; return the commit's SHA."""
    path = os.path.join(root, PLUGIN_JSON)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"name": "lc", "version": version}, fh)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--allow-empty", "-m", "v" + version)
    return git(root, "rev-parse", "HEAD")


def run(root, *flags):
    done = subprocess.run([sys.executable, "-B", CHECK] + list(flags) + [root],
                          env=ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return done.returncode, done.stdout.decode("utf-8", "replace")


class ReleaseTag(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        git(self.root, "init", "-q")

    def tearDown(self):
        self._tmp.cleanup()

    def test_an_untagged_version_fails_and_says_how_to_fix_it(self):
        commit_version(self.root, "1.2.3")
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("v1.2.3", out)
        self.assertIn("Cutting a release", out)

    def test_the_same_version_tagged_passes(self):
        commit_version(self.root, "1.2.3")
        git(self.root, "tag", "-a", "v1.2.3", "-m", "v1.2.3")
        code, out = run(self.root)
        self.assertEqual(code, 0, out)
        self.assertIn("v1.2.3", out)

    def test_an_older_tag_does_not_cover_a_newer_version(self):
        commit_version(self.root, "1.2.3")
        git(self.root, "tag", "-a", "v1.2.3", "-m", "v1.2.3")
        commit_version(self.root, "1.2.4")
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("v1.2.4", out)

    def test_a_lightweight_tag_fails(self):
        commit_version(self.root, "1.2.3")
        git(self.root, "tag", "v1.2.3")
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("annotated", out)

    def test_a_tag_on_a_commit_carrying_another_version_fails(self):
        commit_version(self.root, "1.2.2")
        git(self.root, "tag", "-a", "v1.2.3", "-m", "cut on the wrong commit")
        commit_version(self.root, "1.2.3")
        code, out = run(self.root)
        self.assertEqual(code, 1, out)
        self.assertIn("MISPLACED", out)

    def test_the_push_that_bumps_the_version_is_not_red_by_design(self):
        """The tag is cut after merge, so the bump's own push must pass."""
        before = commit_version(self.root, "1.2.3")
        git(self.root, "tag", "-a", "v1.2.3", "-m", "v1.2.3")
        commit_version(self.root, "1.2.4")
        code, out = run(self.root, "--before", before)
        self.assertEqual(code, 0, out)
        self.assertIn("new in this push", out)

    def test_the_next_push_after_an_untagged_bump_fails(self):
        """What slipped with 0.9.1: bumped, merged, never tagged, more merged on top."""
        commit_version(self.root, "1.2.3")
        before = commit_version(self.root, "1.2.4")
        commit_version(self.root, "1.2.4")
        code, out = run(self.root, "--before", before)
        self.assertEqual(code, 1, out)
        self.assertIn("v1.2.4", out)

    def test_a_before_the_checkout_does_not_have_is_an_error_not_a_pass(self):
        commit_version(self.root, "1.2.3")
        code, out = run(self.root, "--before", "1" * 40)
        self.assertEqual(code, 2, out)
        self.assertIn("fetch-depth", out)

    def test_a_branch_creation_push_is_checked_strictly(self):
        """GitHub sends 40 zeros as `before` when a ref is created."""
        commit_version(self.root, "1.2.3")
        code, out = run(self.root, "--before", "0" * 40)
        self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main()
