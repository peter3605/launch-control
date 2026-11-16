"""Is the version on main released - tagged, annotated, on a commit carrying it?

Decision 0002 makes a version bump the release, and every released version an
annotated v<version> tag plus a GitHub release. 0.9.1 was the first version
after that decision, and it went out untagged: the procedure slipped on its
very first use. This is the check that notices next time.

    python3 tests/check_release_tag.py [--before SHA] [ROOT]

ROOT is a git checkout (default: this repo), and it must have its tags fetched
- actions/checkout fetches none unless asked, which would make this check fail
on every run for a reason that has nothing to do with releases.

Exit 0 when the version in plugin.json has its tag, 1 when it does not, 2 when
the check cannot read what it needs.

WHEN IT RUNS, and why --before exists. The tag is cut AFTER the bump merges, so
the version a push introduces cannot have its tag yet. Requiring one there
would make every bump red by design. With --before (the commit main was at
before this push, github.event.before in CI), a version that differs from the
one at SHA is new in this push and passes with a reminder. A version that was
already on main before the push must be tagged. So an untagged release fails
the next push to main after it, and the daily scheduled run catches one that
nothing merges on top of. Without --before the check is strict.

Two more ways a tag can be present and still wrong, both failures:
  - a lightweight tag: decision 0002 says annotated, and `git describe` and
    `gh release create --verify-tag` both treat the two differently;
  - a tag on a commit whose plugin.json carries some other version, which is
    what a tag cut on the wrong checkout looks like.
"""
import json
import os
import subprocess
import sys

PLUGIN_JSON = "plugins/lc/.claude-plugin/plugin.json"
NULL_SHA = "0" * 40

FIX = (
    "\nTag it, following CONTRIBUTING.md's \"Cutting a release\":\n"
    "  git tag -a v{v} -m v{v} <last commit on main carrying {v}>\n"
    "  git push origin v{v}\n"
    "then create its GitHub release (step 3 there), and re-run this workflow.\n")


class Unreadable(Exception):
    pass


def git(root, *args):
    done = subprocess.run(["git", "-C", root] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return done.returncode, done.stdout.decode("utf-8", "replace").strip()


def version_at(root, rev):
    """plugin.json's version at `rev`, or None when that commit has no plugin.json."""
    code, text = git(root, "show", "%s:%s" % (rev, PLUGIN_JSON))
    if code != 0:
        return None
    try:
        version = json.loads(text)["version"]
    except (ValueError, KeyError, TypeError):
        raise Unreadable("%s at %s has no readable version" % (PLUGIN_JSON, rev))
    if not isinstance(version, str) or not version.strip():
        raise Unreadable("%s at %s: version is not a string" % (PLUGIN_JSON, rev))
    return version.strip()


def main(argv):
    args = argv[1:]
    before = None
    if args[:1] == ["--before"]:
        if len(args) < 2:
            sys.stderr.write("release tag: --before needs a commit\n")
            return 2
        before, args = args[1], args[2:]
    root = args[0] if args else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))

    try:
        version = version_at(root, "HEAD")
        if version is None:
            raise Unreadable("%s not found at HEAD in %s" % (PLUGIN_JSON, root))
        tag = "v" + version

        if before and before != NULL_SHA:
            code, _ = git(root, "cat-file", "-e", before + "^{commit}")
            if code != 0:
                raise Unreadable("--before %s is not a commit in this checkout "
                                 "(shallow clone? use fetch-depth: 0)" % before)
            previous = version_at(root, before + "^{commit}")
            if previous != version:
                sys.stdout.write(
                    "release tag: %s is new in this push (was %s), so it cannot be "
                    "tagged yet.\nTag and release it now that it has merged; the next "
                    "push to main, or the daily run, fails until you do.\n"
                    % (version, previous or "absent"))
                return 0

        code, kind = git(root, "cat-file", "-t", "refs/tags/" + tag)
        if code != 0:
            code, count = git(root, "tag", "-l")
            hint = ("" if count else
                    "\nThis checkout has NO tags at all - was it fetched with "
                    "fetch-depth: 0 or fetch-tags: true?\n")
            sys.stderr.write(
                "UNTAGGED RELEASE: plugin.json on main says %s, and there is no "
                "tag %s.\n%s%s" % (version, tag, hint, FIX.format(v=version)))
            return 1
        if kind != "tag":
            sys.stderr.write(
                "LIGHTWEIGHT TAG: %s exists but is not annotated (it is a %s).\n"
                "Decision 0002 requires an annotated tag. A pushed tag is never "
                "moved, so ask Peter before replacing it.\n" % (tag, kind))
            return 1
        tagged = version_at(root, tag + "^{commit}")
        if tagged != version:
            sys.stderr.write(
                "MISPLACED TAG: %s points at a commit whose plugin.json says %s, "
                "not %s.\nA pushed tag is never moved, so ask Peter before "
                "touching it.\n" % (tag, tagged or "nothing", version))
            return 1
    except Unreadable as exc:
        sys.stderr.write("release tag: cannot check.\n  %s\n" % exc)
        return 2

    code, sha = git(root, "rev-parse", "--short", tag + "^{commit}")
    sys.stdout.write("release tag OK: %s is tagged %s (annotated, on %s)\n"
                     % (version, tag, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
