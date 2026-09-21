"""Are the three version records in this repo telling the same story?

Three files carry this project's version, and they have drifted apart twice.
LC-B5 re-synced them by hand; LC-B6 broke them again one story later; LC-B9
re-synced them by hand a second time. This is the check that makes a third
manual correction unnecessary.

    python3 tests/check_version_sync.py [ROOT]

Exit 0 when all three agree, 1 when they disagree, 2 when a record cannot be
read at all. ROOT defaults to this repo, and exists so the suite can point the
check at a synthetic desynced copy without touching the working tree.

Nothing here hard-codes a version. All three are read at run time, so this
check cannot itself rot into the next stale record - which is exactly how the
previous notes about the version went out of date.

THE RULE, settled deliberately: all three carry the SAME version, and move in
the same commit. The three could in principle be allowed to move for different
reasons - plugin.json moves whenever command or hook behaviour changes,
marketplace.json is the marketplace's own catalogue metadata, and the README
Status line is prose about maturity. They are not allowed to here. This
marketplace ships exactly one plugin and exists only to ship it, so a
marketplace version sitting behind the plugin's tells a browsing stranger
something untrue; and the README Status line is the first version a stranger
reads about how mature this is. plugin.json is the one that moves first,
because migrate.sh stamps it into each installed repo as that repo's drift
baseline - the other two follow it in the same commit.
"""
import json
import os
import re
import sys

PLUGIN_JSON = os.path.join("plugins", "lc", ".claude-plugin", "plugin.json")
MARKETPLACE_JSON = os.path.join(".claude-plugin", "marketplace.json")
README = "README.md"

STATUS_HEADING = re.compile(r"^##\s+Status\s*$")
LEADING_VERSION = re.compile(r"^v(\d+(?:\.\d+)*)\b")


class Unreadable(Exception):
    """A version record that could not be found.

    Always a failure, never a skip: a check that silently drops one of the
    three records is a check that reports agreement between two files.
    """


def _from_json(root, rel, path):
    """The string at `path` inside the JSON file `rel`, with where it came from."""
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            node = json.load(fh)
    except OSError as exc:
        raise Unreadable("%s: %s" % (rel, exc.strerror or exc))
    except ValueError as exc:
        raise Unreadable("%s: not valid JSON (%s)" % (rel, exc))
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise Unreadable("%s: has no %s" % (rel, ".".join(path)))
        node = node[key]
    if not isinstance(node, str) or not node.strip():
        raise Unreadable("%s: %s is not a version string" % (rel, ".".join(path)))
    return node.strip(), rel, ".".join(path)


def _from_readme(root):
    """The version the README's Status section opens with, and its line number.

    The contract is narrow on purpose: the first non-blank line under
    "## Status" starts with a vX.Y token. A reformat that buries the version
    somewhere else fails loudly here rather than quietly stopping the check.
    """
    try:
        with open(os.path.join(root, README), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise Unreadable("%s: %s" % (README, exc.strerror or exc))
    for i, line in enumerate(lines):
        if not STATUS_HEADING.match(line):
            continue
        for j in range(i + 1, len(lines)):
            body = lines[j].strip()
            if not body:
                continue
            found = LEADING_VERSION.match(body)
            if not found:
                raise Unreadable(
                    '%s:%d: the first line under "## Status" does not start with '
                    'a version like "v1.2.3": %r' % (README, j + 1, body))
            return found.group(1), "%s:%d" % (README, j + 1), '"## Status" line'
        raise Unreadable('%s: nothing under "## Status"' % README)
    raise Unreadable('%s: no "## Status" heading' % README)


def read_versions(root):
    """All three records as (version, where it came from, which field)."""
    return [
        _from_json(root, PLUGIN_JSON, ("version",)),
        _from_json(root, MARKETPLACE_JSON, ("metadata", "version")),
        _from_readme(root),
    ]


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    try:
        found = read_versions(root)
    except Unreadable as exc:
        sys.stderr.write("version sync: cannot read a version record.\n  %s\n" % exc)
        return 2

    width = max(len(version) for version, _, _ in found)
    table = "\n".join(
        "  %-*s  %s  (%s)" % (width, version, where, field)
        for version, where, field in found)

    if len({version for version, _, _ in found}) == 1:
        sys.stdout.write("version sync OK: all three records read %s\n%s\n"
                         % (found[0][0], table))
        return 0

    sys.stderr.write(
        "VERSION DRIFT: the three version records disagree.\n"
        "%s\n"
        "\nAll three must carry the same version and move in the same commit.\n"
        "migrate.sh stamps plugin.json's version into each installed repo as\n"
        "that repo's drift baseline, so a stale record makes the drift check\n"
        "there report agreement it has not checked.\n" % table)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
