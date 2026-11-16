"""Proof that the suite would notice if the computations it pins broke.

A test suite that passes is not evidence of anything on its own - assertions rot
into tautologies, and a suite can go green against code that computes nonsense.
So: break mine.py on purpose, one edit at a time, and require test_mine to go red
for every break. A mutation that slips through is a failure HERE, which means the
gap shows up as a red build rather than as a number nobody checked.

This is what satisfies LC-B8's "a deliberately broken computation fails the build".
LC-23 extended it past mine.py: init.py check's comparison with board.json and
plan.py next-id's ledger lookup are guarded the same way, by test_init and test_plan.
LC-B12 moved that comparison into boardcheck.py, shared with doctor.py, so its
mutations now target boardcheck.py and must be caught by BOTH callers' suites.
LC-25 added ids.py, which now does the filtering metered queries used to, so its
dependents match, its next-ID arithmetic and its has_more refusal are guarded too.

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
BOARDCHECK = os.path.join("plugins", "lc", "skills", "doctor", "boardcheck.py")
DOCTOR = os.path.join("plugins", "lc", "skills", "doctor", "doctor.py")
PLAN = os.path.join("plugins", "lc", "skills", "plan", "plan.py")
IDS = os.path.join("plugins", "lc", "skills", "doctor", "ids.py")

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
        "            return (0.0, 0.0, False)\n",
        "            return (0.0, 0.0, True)\n",
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
    (
        "started_clock_counts_elapsed_days_backwards",
        "return max(0, (self.today - it[\"started\"]).days)",
        "return max(0, (it[\"started\"] - self.today).days)",
        "a clock started weeks ago would be projected as if started today (LC-29)",
    ),
    (
        "started_clock_adds_elapsed_days_instead_of_subtracting",
        "return (max(0.0, lead[0] - ran), max(0.0, lead[1] - ran), True)",
        "return (max(0.0, lead[0] + ran), max(0.0, lead[1] + ran), True)",
        "a running clock would grow later the longer it ran (LC-29)",
    ),
]


# (name, file, exact source to replace, replacement, what it breaks, suite that must catch it)
BOARD_MUTATIONS = [
    (
        "init_check_compares_only_the_number_of_view_filters",
        BOARDCHECK,
        "if have != [tuple(e) for e in expect]:",
        "if len(have) != len(expect):",
        "a view filtered on the wrong value would pass as provisioned",
        "tests.test_init",
    ),
    (
        "init_check_ignores_missing_select_options",
        BOARDCHECK,
        'lost = [n for n, _ in p["options"] if n not in names]',
        "lost = []",
        "a Status select without In Review would pass, and /lc:done would set an option that does not exist",
        "tests.test_init",
    ),
    (
        "init_check_ignores_view_sorts",
        BOARDCHECK,
        "if sorts != want_sorts:",
        "if False:",
        "a view sorted wrongly would pass, and /lc:next would pick out of Seq order",
        "tests.test_init",
    ),
    (
        "doctor_never_compares_the_schema",
        DOCTOR,
        "        check_schema(cfg, args.stories, args.projects)\n",
        "        pass\n",
        "a board that predates the plugin would get a clean bill of health from /lc:doctor",
        "tests.test_doctor",
    ),
    (
        "boardcheck_ignores_emptiness_filters",
        BOARDCHECK,
        "    if op in EMPTINESS:\n        # Notion stores",
        "    if False:\n        # Notion stores",
        "the dependents view's Blocked by IS NOT EMPTY filter could never be confirmed, so a correct board would fail",
        "tests.test_init",
    ),
    (
        "doctor_open_view_accepts_done_rows",
        DOCTOR,
        'done = sorted({i for i, st in rows if st == "Done"})',
        "done = []",
        "an open view that lost its Status filter would pass, and /lc:start would read Done history again",
        "tests.test_doctor",
    ),
    (
        "plan_next_id_ignores_the_ledger",
        PLAN,
        'taken = ids + [v["id"] for v in state.values()]',
        "taken = ids",
        "a story filed a second ago and not yet in the view would have its ID handed out again",
        "tests.test_plan",
    ),
    (
        "plan_next_id_misses_a_duplicate_it_filed",
        PLAN,
        'dupes = [(d, v["id"]) for d, v in state.items() if ids.count(v["id"]) > 1]',
        'dupes = [(d, v["id"]) for d, v in state.items() if ids.count(v["id"]) > 2]',
        "an ID this run filed that lost a race would stay on two rows",
        "tests.test_plan",
    ),
    (
        "plan_payload_files_blocked_stories_as_ready",
        PLAN,
        '"Status": "Backlog" if blockers else "Ready",',
        '"Status": "Ready",',
        "a blocked story would be offered by /lc:next before its blocker is done",
        "tests.test_plan",
    ),
    (
        "ids_dependents_stops_matching_page_ids",
        IDS,
        "if target in {page_id(u) for u in r[\"blockedBy\"]}:",
        "if args.url in r[\"blockedBy\"]:",
        "a dependent linked by another URL form would never be promoted to Ready",
        "tests.test_ids",
    ),
    (
        "ids_next_ignores_the_highest_number",
        IDS,
        "n = max(nums, default=0) + 1",
        "n = len(nums) + 1",
        "a gap in the sequence would hand out an ID that is already taken",
        "tests.test_ids",
    ),
    (
        "ids_answers_from_an_incomplete_read",
        IDS,
        "        complete = not data.get(\"has_more\")\n",
        "        complete = True\n",
        "an ID on an unread page would be handed out again, and its dependents missed",
        "tests.test_ids",
    ),
]


def build_tree(dest, mutate=None, target=MINE):
    """A runnable copy of the tree: the plugin scripts, this suite, and the
    examples test_mine runs against (LC-B11's sample board)."""
    for sub in ("plugins", "tests", "examples"):
        shutil.copytree(
            os.path.join(REPO, sub), os.path.join(dest, sub),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    if mutate:
        old, new = mutate
        path = os.path.join(dest, target)
        with open(path) as f:
            src = f.read()
        if src.count(old) != 1:
            raise AssertionError(
                f"mutation target appears {src.count(old)} times in {target}, expected exactly 1. "
                f"{os.path.basename(target)} changed - update the mutation so it keeps testing something."
            )
        with open(path, "w") as f:
            f.write(src.replace(old, new))


def run_suite(cwd, module="tests.test_mine"):
    """One suite only - discovery would re-run this guard inside itself."""
    return subprocess.run(
        [sys.executable, "-B", "-m", "unittest", module],
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

    def test_the_unmutated_tree_passes_init_plan_and_doctor(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp)
            for module in ("tests.test_init", "tests.test_plan", "tests.test_doctor", "tests.test_ids"):
                r = run_suite(tmp, module)
                self.assertEqual(r.returncode, 0,
                                 f"{module} must pass on the copied tree before mutations mean anything:\n{r.stderr}")


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


def _make_board(name, target, old, new, why, module):
    def test(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_tree(tmp, mutate=(old, new), target=target)
            r = run_suite(tmp, module)
        self.assertNotEqual(
            r.returncode, 0,
            f"mutation '{name}' survived: {why}, and {module} still passed.\n"
            f"Add or tighten an assertion in {module.replace('.', '/')}.py until this breaks it.",
        )
    test.__name__ = f"test_caught_{name}"
    test.__doc__ = f"Breaking it means: {why}."
    return test


for _n, _o, _w, _y in MUTATIONS:
    setattr(MutationGuard, f"test_caught_{_n}", _make(_n, _o, _w, _y))
for _n, _t, _o, _w, _y, _m in BOARD_MUTATIONS:
    setattr(MutationGuard, f"test_caught_{_n}", _make_board(_n, _t, _o, _w, _y, _m))
    if _t == BOARDCHECK:
        # The comparison is shared, so each caller's suite must notice it break.
        setattr(MutationGuard, f"test_caught_{_n}_by_doctor",
                _make_board(f"{_n}_by_doctor", _t, _o, _w, _y, "tests.test_doctor"))


if __name__ == "__main__":
    unittest.main()
