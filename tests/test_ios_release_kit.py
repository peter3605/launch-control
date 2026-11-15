"""The iOS release kit (plugins/lc/kits/ios-release), tested without a Mac.

Everything that decides whether a release is right is either in release_kit.py,
tested here directly, or in a shell script that needs no signing, run here
against a synthetic app repo. What is left untested is the part that needs
Xcode and a signing identity - archive.sh's xcodebuild calls - and that part is
a human story, on purpose.

Stdlib only, like the rest of the suite.
"""
import contextlib
import io
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.join(REPO, "plugins", "lc", "kits", "ios-release")
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(KIT, "scripts", "lib"))

import release_kit as rk  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def plist(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(data, f)


class Versions(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def file(self, text, name="project.yml"):
        p = os.path.join(self.dir, name)
        write(p, text)
        return p

    def test_xcodegen_unquoted_build_quoted_version(self):
        p = self.file('targets:\n  App:\n    settings:\n      base:\n'
                      '        CURRENT_PROJECT_VERSION: 1\n        MARKETING_VERSION: "1.0.0"\n')
        self.assertEqual(rk.read_versions(p), ("1.0.0", 1))

    def test_set_build_keeps_quoting_and_every_copy(self):
        p = self.file('a:\n  CURRENT_PROJECT_VERSION: "7"  # app\nb:\n  CURRENT_PROJECT_VERSION: "7"\n'
                      'MARKETING_VERSION: "2.1"\n')
        rk.set_build(p, 8)
        with open(p) as f:
            text = f.read()
        self.assertEqual(text.count('CURRENT_PROJECT_VERSION: "8"'), 2)
        self.assertIn("# app", text)
        self.assertEqual(rk.read_versions(p), ("2.1", 8))

    def test_xcconfig(self):
        p = self.file("CURRENT_PROJECT_VERSION = 41\nMARKETING_VERSION = 3.0 // shipped\n", "Base.xcconfig")
        self.assertEqual(rk.read_versions(p), ("3.0", 41))
        rk.set_build(p, 42)
        self.assertEqual(rk.read_versions(p), ("3.0", 42))

    def test_copies_that_disagree_are_refused(self):
        # Bumping "the" number here would be a guess about which one the build reads.
        p = self.file("CURRENT_PROJECT_VERSION: 3\nCURRENT_PROJECT_VERSION: 4\nMARKETING_VERSION: 1\n")
        with self.assertRaisesRegex(ValueError, "disagrees"):
            rk.read_versions(p)

    def test_missing_and_non_numeric(self):
        with self.assertRaisesRegex(ValueError, "no CURRENT_PROJECT_VERSION"):
            rk.read_versions(self.file("MARKETING_VERSION: 1\n"))
        with self.assertRaisesRegex(ValueError, "not a whole number"):
            rk.read_versions(self.file("CURRENT_PROJECT_VERSION: $(BUILD)\nMARKETING_VERSION: 1\n"))

    def test_the_cli_exits_nonzero_rather_than_printing_nothing(self):
        # archive.sh computes BUILD from this output; an empty success would make it build 1.
        p = self.file("MARKETING_VERSION: 1\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rk.main(["version", p]), 1)
        self.assertIn("no CURRENT_PROJECT_VERSION", out.getvalue())


class Entitlements(unittest.TestCase):
    SIGNED = {
        "aps-environment": "production",
        "com.apple.developer.associated-domains": ["applinks:example.com", "webcredentials:example.com"],
        "get-task-allow": False,
    }

    def check(self, ents, *specs, source=False):
        return [ok for ok, _ in rk.check_entitlements(ents, list(specs), source=source)]

    def test_string_array_and_bool(self):
        self.assertEqual(self.check(self.SIGNED,
                                    ".|aps-environment=production",
                                    ".|com.apple.developer.associated-domains=applinks:example.com",
                                    ".|get-task-allow=false"), [True, True, True])

    def test_wrong_and_missing(self):
        self.assertEqual(self.check(self.SIGNED,
                                    ".|aps-environment=development",
                                    ".|com.apple.developer.associated-domains=applinks:other.com",
                                    ".|com.apple.security.application-groups"), [False, False, False])

    def test_source_mode_ignores_strings_signing_rewrites(self):
        source = {"aps-environment": "development",
                  "com.apple.developer.associated-domains": ["applinks:example.com"]}
        self.assertEqual(self.check(source, ".|aps-environment=production", source=True), [True])
        # An array member is not rewritten by signing, so it is still compared.
        self.assertEqual(self.check(source, ".|com.apple.developer.associated-domains=applinks:x.com",
                                    source=True), [False])

    def test_codesign_blob_header_is_skipped(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        p = os.path.join(d, "e.plist")
        with open(p, "wb") as f:
            f.write(b"\xfa\xde\x71\x71\x00\x00\x01\x00" + plistlib.dumps({"a": True}))
        self.assertEqual(rk.load_plist(p), {"a": True})

    def test_double_hyphen_in_a_comment_is_read_as_xcode_reads_it(self):
        # Valid to plutil and Xcode, invalid XML to expat. Found in a real
        # Info.plist on the first install.
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        p = os.path.join(d, "Info.plist")
        with open(p, "wb") as f:
            f.write(plistlib.dumps({"ITSAppUsesNonExemptEncryption": False}).replace(
                b"<dict>", b"<dict>\n<!-- two keys -- not one -->", 1))
        self.assertEqual(rk.load_plist(p), {"ITSAppUsesNonExemptEncryption": False})

    def test_an_unparseable_plist_fails_without_a_traceback(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        p = os.path.join(d, "Info.plist")
        write(p, "<?xml version='1.0'?><plist><dict><key>a</dict></plist>")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rk.main(["info-plist", p]), 1)
        self.assertTrue(out.getvalue().startswith("!! "))

    def test_bad_spec(self):
        with self.assertRaises(ValueError):
            rk.parse_spec("aps-environment")


STORE = """
<!-- field: name limit: 30 -->
```
Mealwise
```
<!-- field: subtitle limit: 30 -->
```
Plan meals around what\u2019s left.
```
<!-- field: keywords limit: 100 -->
```
meal,planner,leftovers,recipes
```
<!-- field: promotional_text limit: 170 -->
```
Use what you have.
```
<!-- field: description limit: 4000 -->
```
A plain description.
```
<!-- field: whats_new limit: 4000 -->
```
REPLACE_ME
```
"""
REQUIRED = ["name", "subtitle", "keywords", "promotional_text", "description"]


class StoreCopy(unittest.TestCase):
    def test_a_1_0_passes_with_whats_new_unwritten(self):
        ok, lines = rk.check_store_copy(STORE, REQUIRED)
        self.assertTrue(ok, "\n".join(lines))
        self.assertTrue(any("whats_new" in l and "not required" in l for l in lines))

    def test_whats_new_is_held_to_it_once_required(self):
        ok, _ = rk.check_store_copy(STORE, REQUIRED + ["whats_new"])
        self.assertFalse(ok)

    def test_characters_not_bytes(self):
        # 30 characters, 32 bytes in UTF-8: Apple accepts it, `wc -c` would not.
        subtitle = "Plan meals around what\u2019s left."
        self.assertEqual(len(subtitle), 30)
        self.assertGreater(len(subtitle.encode()), 30)
        self.assertTrue(rk.check_store_copy(STORE, REQUIRED)[0])
        over = STORE.replace(subtitle, subtitle + "!")
        self.assertFalse(rk.check_store_copy(over, REQUIRED)[0])

    def test_markdown_in_plain_text_fields(self):
        self.assertFalse(rk.check_store_copy(STORE.replace("A plain description.", "A **bold** one."), REQUIRED)[0])

    def test_keyword_waste(self):
        for bad in ("meal, planner", "meal,,planner", "meal,meal"):
            self.assertFalse(rk.check_store_copy(STORE.replace("meal,planner,leftovers,recipes", bad),
                                                 REQUIRED)[0], bad)
        # A multi-word keyword is legitimate.
        self.assertTrue(rk.check_store_copy(STORE.replace("meal,planner", "meal plan,planner"), REQUIRED)[0])

    def test_placeholder_in_required_field_and_missing_field(self):
        self.assertFalse(rk.check_store_copy(STORE.replace("Mealwise", "REPLACE_ME"), REQUIRED)[0])
        self.assertFalse(rk.check_store_copy(STORE, REQUIRED + ["support_url"])[0])
        self.assertFalse(rk.check_store_copy("no markers", REQUIRED)[0])

    def test_lowercase_todo_is_a_word_not_a_placeholder(self):
        self.assertTrue(rk.check_store_copy(STORE.replace("A plain description.", "A todo list."), REQUIRED)[0])

    def test_the_kit_template_fails_until_written(self):
        with open(os.path.join(KIT, "templates", "store-copy.md"), encoding="utf-8") as f:
            text = f.read()
        ok, lines = rk.check_store_copy(text, REQUIRED)
        self.assertFalse(ok)
        self.assertEqual(sum("placeholder" in l for l in lines), len(REQUIRED))


class LogPrivacy(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root)
        write(os.path.join(self.root, "App", "Store.swift"),
              'log.error("failed: \\(error.localizedDescription, privacy: .public)")\n'
              '// log.info("\\(name, privacy: .public)") is how NOT to do it\n'
              'log.info("saved \\(place.name, privacy: .public)")\n')

    def test_hit_comment_and_allowlist(self):
        hits = rk.scan_log_privacy(self.root, ["App"], ["App/Store.swift:error.localizedDescription"])
        self.assertEqual([(f, n) for f, n, _ in hits], [("App/Store.swift", 3)])

    def test_allowlist_is_per_file(self):
        hits = rk.scan_log_privacy(self.root, ["App"], ["Other.swift:place.name"])
        self.assertEqual(len(hits), 2)

    def test_missing_directory_is_an_error_not_a_pass(self):
        with self.assertRaises(ValueError):
            rk.scan_log_privacy(self.root, ["Nope"], [])


class PlistChecks(unittest.TestCase):
    def test_export_options(self):
        good = {"method": "app-store-connect", "teamID": "ABCDE12345", "manageAppVersionAndBuildNumber": False}
        self.assertEqual(rk.check_export_options(good), [])
        self.assertEqual(len(rk.check_export_options({**good, "teamID": "REPLACE_ME"})), 1)
        self.assertEqual(len(rk.check_export_options({k: v for k, v in good.items()
                                                      if k != "manageAppVersionAndBuildNumber"})), 1)

    def test_the_kit_export_options_ship_unfilled_and_otherwise_right(self):
        with open(os.path.join(KIT, "ExportOptions.plist"), "rb") as f:
            problems = rk.check_export_options(plistlib.load(f))
        self.assertEqual(len(problems), 1)
        self.assertIn("teamID", problems[0])

    def test_info_plist(self):
        self.assertEqual(rk.check_info_plist({"ITSAppUsesNonExemptEncryption": False}), [])
        self.assertEqual(len(rk.check_info_plist({})), 1)

    def test_privacy_manifest(self):
        good = {"NSPrivacyTracking": False, "NSPrivacyAccessedAPITypes": [
            {"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults",
             "NSPrivacyAccessedAPITypeReasons": ["CA92.1"]}]}
        self.assertEqual(rk.check_privacy_manifest(good), [])
        bad = {"NSPrivacyTracking": False,
               "NSPrivacyAccessedAPITypes": [{"NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults"}]}
        self.assertEqual(len(rk.check_privacy_manifest(bad)), 1)
        self.assertEqual(len(rk.check_privacy_manifest({})), 2)


# ------------------------------------------------------------------ the shell half

def run(cmd, cwd=None, env=None):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


CONF = """
APP_NAME="Mealwise"
PROJECT_DIR="ios"
PROJECT="Mealwise.xcodeproj"
SCHEME="Mealwise"
GENERATE_CMD=""
VERSION_FILE="project.yml"
INFO_PLIST="Mealwise/Info.plist"
PRIVACY_MANIFEST="Mealwise/PrivacyInfo.xcprivacy"
BUNDLES=(".|Mealwise/Mealwise.entitlements")
REQUIRED_ENTITLEMENTS=(
  ".|aps-environment=production"
  ".|com.apple.developer.associated-domains=applinks:example.com"
)
LOG_SOURCE_DIRS=("ios/Mealwise")
LOG_PRIVACY_ALLOWED=()
"""


@unittest.skipUnless(shutil.which("bash") and shutil.which("git"), "needs bash and git")
class InstalledKit(unittest.TestCase):
    """Install into a synthetic app repo and run the signing-free half."""

    def setUp(self):
        self.app = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.app)
        run(["git", "init", "-q", self.app])
        self.kit = os.path.join(self.app, "scripts", "release")

    def install(self, *extra):
        return run(["bash", os.path.join(KIT, "install.sh"), self.app, *extra])

    def make_app(self):
        ios = os.path.join(self.app, "ios")
        write(os.path.join(ios, "project.yml"), 'CURRENT_PROJECT_VERSION: 4\nMARKETING_VERSION: "1.0.0"\n')
        plist(os.path.join(ios, "Mealwise", "Info.plist"), {"ITSAppUsesNonExemptEncryption": False})
        plist(os.path.join(ios, "Mealwise", "PrivacyInfo.xcprivacy"),
              {"NSPrivacyTracking": False, "NSPrivacyAccessedAPITypes": []})
        plist(os.path.join(ios, "Mealwise", "Mealwise.entitlements"),
              {"aps-environment": "development",
               "com.apple.developer.associated-domains": ["applinks:example.com"]})
        write(os.path.join(ios, "Mealwise", "App.swift"), 'log.info("\\(id, privacy: .private)")\n')
        write(os.path.join(self.kit, "release.conf"), CONF)
        with open(os.path.join(self.kit, "ExportOptions.plist"), "rb") as f:
            opts = plistlib.load(f)
        opts["teamID"] = "ABCDE12345"
        plist(os.path.join(self.kit, "ExportOptions.plist"), opts)
        write(os.path.join(self.app, "docs", "store-copy.md"), STORE)

    def test_dry_run_writes_nothing(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("Dry run", r.stdout)
        self.assertFalse(os.path.exists(self.kit))

    def test_apply_then_reinstall_keeps_what_is_yours(self):
        self.assertEqual(self.install("--apply").returncode, 0)
        self.assertTrue(os.access(os.path.join(self.kit, "archive.sh"), os.X_OK))
        write(os.path.join(self.kit, "release.conf"), "# mine\n")
        write(os.path.join(self.kit, "archive.sh"), "# stale\n")
        r = self.install("--apply")
        self.assertIn("keep    scripts/release/release.conf", r.stdout)
        self.assertIn("update  scripts/release/archive.sh", r.stdout)
        with open(os.path.join(self.kit, "release.conf")) as f:
            self.assertEqual(f.read(), "# mine\n")
        with open(os.path.join(self.kit, "archive.sh")) as f:
            self.assertNotEqual(f.read(), "# stale\n")
        self.assertIn("Nothing to do", self.install().stdout)

    def test_an_unfilled_conf_fails_by_name(self):
        self.install("--apply")
        r = run(["bash", os.path.join(self.kit, "check-release-ready.sh")])
        self.assertEqual(r.returncode, 2, r.stdout)
        for name in ("APP_NAME", "PROJECT", "SCHEME"):
            self.assertIn(f"{name} is not set", r.stdout)

    def test_a_filled_in_app_is_ready(self):
        self.install("--apply")
        self.make_app()
        r = run(["bash", os.path.join(self.kit, "check-release-ready.sh")])
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("version 1.0.0, build 4", r.stdout)

    def test_every_failure_is_reported_not_just_the_first(self):
        self.install("--apply")
        self.make_app()
        plist(os.path.join(self.app, "ios", "Mealwise", "Info.plist"), {})
        write(os.path.join(self.app, "ios", "Mealwise", "Leak.swift"), 'log.info("\\(email, privacy: .public)")\n')
        plist(os.path.join(self.app, "ios", "Mealwise", "Mealwise.entitlements"), {"aps-environment": "development"})
        r = run(["bash", os.path.join(self.kit, "check-release-ready.sh")])
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("failed: Info.plist, entitlements (source), log privacy", r.stdout)

    def test_a_secret_from_the_shell_is_found_in_the_build_tree(self):
        self.install("--apply")
        self.make_app()
        secret = "s3cr3t-value-with-no-known-shape-0123"
        write(os.path.join(self.app, "ios", "build", "XCBuildData", "attachments", "a1"), f"X={secret}\n")
        r = run(["bash", os.path.join(self.kit, "check-build-secrets.sh")], env={"MY_SERVICE_TOKEN": secret})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("$MY_SERVICE_TOKEN's value was written into", r.stdout)
        self.assertNotIn(secret, r.stdout)
        r = run(["bash", os.path.join(self.kit, "check-build-secrets.sh")], env={"MY_SERVICE_TOKEN": "x" * 20})
        self.assertEqual(r.returncode, 0, r.stdout)


class KitIsGeneric(unittest.TestCase):
    """This repo is public, and the kit installs into every app: nothing in it may
    name a real team, bundle ID or app."""

    TEAM_ID = re.compile(r"<key>teamID</key>\s*<string>(?!REPLACE_ME)[^<]*</string>")
    BUNDLE_ID = re.compile(r"\b(?:group\.)?com\.(?!apple\b|example\b)[a-z0-9-]+\.[a-z0-9.-]+", re.I)

    def files(self):
        for base, _, names in os.walk(KIT):
            for n in names:
                if n.endswith((".pyc",)):
                    continue
                with open(os.path.join(base, n), encoding="utf-8") as f:
                    yield os.path.relpath(f.name, KIT), f.read()

    def test_no_team_or_bundle_ids(self):
        for rel, text in self.files():
            self.assertIsNone(self.TEAM_ID.search(text), rel)
            self.assertEqual(self.BUNDLE_ID.findall(text), [], rel)

    def test_no_app_names_left_from_the_source_app(self):
        for rel, text in self.files():
            self.assertNotRegex(text.lower(), r"muncheez|concertfinder|budgetr", rel)


if __name__ == "__main__":
    unittest.main()
