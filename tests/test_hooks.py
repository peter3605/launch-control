"""The two hooks, and the command list the README promises.

1. THE STOP HOOK NUDGES ONCE PER BOUND STORY, AND NEVER WHEN NOTHING IS BOUND.
   /lc:release (LC-B17) drops a story by emptying .claude/.current-story. The
   hook must read an empty binding as "nothing claimed" and let the session stop,
   or releasing a story would earn a nudge about the story just released.

2. BOTH HOOKS PARSE UNDER STOCK MACOS /bin/bash (3.2), like the other scripts.

3. THE README COMMANDS TABLE LISTS EVERY SKILL. A new skill that is not in the
   table is a command no one reading the README knows exists.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(REPO, "plugins", "lc", "hooks")
SKILLS = os.path.join(REPO, "plugins", "lc", "skills")


class StopHook(unittest.TestCase):
    def setUp(self):
        self.proj = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.proj)
        self.claude = os.path.join(self.proj, ".claude")
        os.mkdir(self.claude)
        with open(os.path.join(self.claude, "launch-control.json"), "w") as f:
            json.dump({"project": "demo", "prefix": "DM"}, f)

    def bind(self, text):
        with open(os.path.join(self.claude, ".current-story"), "w") as f:
            f.write(text)

    def run_hook(self, name="stop.sh"):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.proj)
        r = subprocess.run(["bash", os.path.join(HOOKS, name)], env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_a_bound_story_is_nudged_once_and_names_release(self):
        self.bind("DM-3\n")
        out = json.loads(self.run_hook())
        self.assertEqual(out["decision"], "block")
        self.assertIn("DM-3", out["reason"])
        self.assertIn("/lc:release", out["reason"])
        self.assertEqual(self.run_hook(), "", "the nudge fired twice for one story")

    def test_an_empty_binding_after_release_is_not_nudged(self):
        # What /lc:release leaves behind: both files present and empty.
        self.bind("")
        open(os.path.join(self.claude, ".nudged"), "w").close()
        self.assertEqual(self.run_hook(), "")

    def test_a_whitespace_only_binding_is_not_nudged(self):
        self.bind("  \n\n")
        self.assertEqual(self.run_hook(), "")

    def test_releasing_after_a_nudge_then_claiming_again_nudges_again(self):
        self.bind("DM-3\n")
        self.assertTrue(self.run_hook())
        self.bind("")
        open(os.path.join(self.claude, ".nudged"), "w").close()
        self.assertEqual(self.run_hook(), "")
        self.bind("DM-3\n")
        self.assertTrue(self.run_hook(), "a re-claimed story lost its nudge")

    def test_session_start_reports_an_empty_binding_as_unbound(self):
        self.bind("")
        ctx = json.loads(self.run_hook("session-start.sh"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("No story is bound", ctx)

    def test_session_start_names_release_for_a_bound_story(self):
        self.bind("DM-3\n")
        ctx = json.loads(self.run_hook("session-start.sh"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("bound to story `DM-3`", ctx)
        self.assertIn("/lc:release", ctx)


class HooksParse(unittest.TestCase):
    def test_hooks_parse_under_bin_bash(self):
        bash = "/bin/bash" if os.path.exists("/bin/bash") else shutil.which("bash")
        for name in ("stop.sh", "session-start.sh"):
            r = subprocess.run([bash, "-n", os.path.join(HOOKS, name)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr}")


class ReadmeCommands(unittest.TestCase):
    def test_every_skill_is_in_the_readme_commands_table(self):
        with open(os.path.join(REPO, "README.md")) as f:
            readme = f.read()
        table = readme.split("## Commands", 1)[1].split("\n## ", 1)[0]
        listed = set(re.findall(r"^\| `/lc:([a-z-]+)", table, re.M))
        skills = {d for d in os.listdir(SKILLS)
                  if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md"))}
        self.assertIn("release", skills)
        self.assertEqual(skills - listed, set(), "skills missing from the README Commands table")
        self.assertEqual(listed - skills, set(), "README lists commands with no skill")


if __name__ == "__main__":
    unittest.main()
