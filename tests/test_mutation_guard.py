"""Proof that test_mine.py would notice if the arithmetic broke.

A test suite that passes is not evidence of anything on its own - assertions rot
into tautologies, and a suite can go green against code that computes nonsense.
So: break mine.py on purpose, one edit at a time, and require test_mine to go red
for every break. A mutation that slips through is a failure HERE, which means the
gap shows up as a red build rather than as a number nobody checked.

This is what satisfies LC-B8's "a deliberately broken computation fails the build".

Each mutation is a single-token edit to a real computation. If you change mine.py
and a mutation stops applying, the guard fails loudly rather than skipping - a
mutation that no longer matches is a mutation that is no longer testing anything.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINE = os.path.join("plugins", "lc", "skills", "mine", "mine.py")

# (name, exact source to replace, replacement, what it breaks)
MUTATIONS = [
    (
        "finish_sums_blockers_instead_of_taking_the_latest",
        "blo, bhi, known = max(blo, flo), max(bhi, fhi), known and fknown",
        "blo, bhi, known = blo + flo, bhi + fhi, known and fknown",
        "concurrent waits would be added together, inflating every date",
    ),
    (
        "finish_takes_the_earliest_blocker",
        "self._finish[pid] = (lo + blo, hi + bhi, known)",
        "self._finish[pid] = (lo, hi, known)",
        "blockers would stop contributing to a finish date at all",
    ),
    (
        "chain_stops_following_its_dependents",
        "self._chain[pid] = (lo + best[0], hi + best[1], known and best[2], [pid] + best[3])",
        "self._chain[pid] = (lo, hi, known and best[2], [pid] + best[3])",
        "chain would measure one item, not the run it heads",
    ),
    (
        "chain_follows_the_shortest_run",
        "if (c[1], c[0]) > (best[1], best[0]):",
        "if (c[1], c[0]) < (best[1], best[0]):",
        "the critical path would be the least critical one",
    ),
    (
        "unknown_lead_stops_marking_a_floor",
        "return (0.0, 0.0, False) if lead is None else (lead[0], lead[1], True)",
        "return (0.0, 0.0, True) if lead is None else (lead[0], lead[1], True)",
        "a guessed-at zero would be printed as a known total",
    ),
    (
        "self_serve_is_treated_as_an_unknown_clock",
        "                lead = (0.0, 0.0)\n",
        "                lead = None\n",
        "desk work would poison every total with a false floor marker",
    ),
    (
        "cycle_detection_in_finish_is_disabled",
        "        if pid in stack:\n"
        "            raise ValueError(\" -> \".join(self.items[p][\"id\"] for p in stack + (pid,)))\n"
        "        lo, hi, known = self.lead(pid)\n"
        "        blo = bhi = 0.0\n",
        "        lo, hi, known = self.lead(pid)\n"
        "        blo = bhi = 0.0\n",
        "a dependency cycle would hang or guess instead of refusing to rank",
    ),
]


def build_tree(dest, mutate=None):
    """A runnable copy of the tree: the plugin scripts plus this suite."""
    for sub in ("plugins", "tests"):
        shutil.copytree(
            os.path.join(REPO, sub), os.path.join(dest, sub),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    if mutate:
        old, new = mutate
        path = os.path.join(dest, MINE)
        with open(path) as f:
            src = f.read()
        if src.count(old) != 1:
            raise AssertionError(
                f"mutation target appears {src.count(old)} times in {MINE}, expected exactly 1. "
                "mine.py changed - update the mutation so it keeps testing something."
            )
        with open(path, "w") as f:
            f.write(src.replace(old, new))


def run_suite(cwd):
    """test_mine only - discovery would re-run this guard inside itself."""
    return subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "tests.test_mine"],
        cwd=cwd, capture_output=True, text=True, timeout=120,
    )


class MutationGuard(unittest.TestCase):
    def test_the_unmutated_tree_passes(self):
        """The control. Without it, a broken harness would 'catch' everything."""
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            r = run_suite(tmp)
        self.assertEqual(r.returncode, 0,
                         f"the copied tree must pass before mutations mean anything:\n{r.stderr}")


def _make(name, old, new, why):
    def test(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp, mutate=(old, new))
            r = run_suite(tmp)
        self.assertNotEqual(
            r.returncode, 0,
            f"mutation '{name}' survived: {why}, and the suite still passed.\n"
            f"Add or tighten an assertion in tests/test_mine.py until this breaks it.",
        )
    test.__name__ = f"test_caught_{name}"
    test.__doc__ = f"Breaking it means: {why}."
    return test


for _n, _o, _w, _y in MUTATIONS:
    setattr(MutationGuard, f"test_caught_{_n}", _make(_n, _o, _w, _y))


if __name__ == "__main__":
    unittest.main()
