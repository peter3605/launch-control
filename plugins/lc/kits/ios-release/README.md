# iOS release kit

Scripts that make an App Store release one checked command, and template
stories for everything around it that a script cannot do. Taken from an iOS app
that shipped 1.0 through a by-hand checklist and then turned each step that went
wrong into a check.

The kit is two halves, split by what they need:

| | Needs | Who runs it |
|---|---|---|
| `check-release-ready.sh` | nothing but the repo | a session, CI on a Mac runner, you |
| `archive.sh` | your signing identity and App Store profiles | you, on the release machine |

Launch Control's split, applied to a release: a session can take the first half
all the way to green, and the second half is a human step on `/lc:mine`.

## Install

```sh
plugins/lc/kits/ios-release/install.sh ~/Repos/myapp           # dry run
plugins/lc/kits/ios-release/install.sh ~/Repos/myapp --apply
```

From an installed plugin the kit is under the plugin cache, at
`~/.claude/plugins/cache/launch-control/lc/<version>/kits/ios-release/`.

It writes `scripts/release/` (use `--dest` for somewhere else) and, if absent,
`docs/store-copy.md`. The scripts are the kit's and are replaced on every
re-install. `release.conf`, `ExportOptions.plist` and `docs/store-copy.md` are
yours and are never overwritten. Everything app-specific lives in those three
files, so a fix to a script reaches every app by re-installing.

Then fill in `release.conf` and the team ID in `ExportOptions.plist`, and run
`scripts/release/check-release-ready.sh`.

## The scripts

| Script | Checks | Signing |
|---|---|---|
| `archive.sh` | Runs the preflight, bumps the build number, archives Release, exports, then checks the **export's** build number, entitlements and build tree. Puts the build number back on any failure. | needed |
| `check-release-ready.sh` | All the checks below that need no signing, plus the version file, `ExportOptions.plist`, `ITSAppUsesNonExemptEncryption` in Info.plist and the privacy manifest. Reports every failure, not just the first. | none |
| `verify-entitlements.sh` | With `--app <path>`: a built app's signature carries `REQUIRED_ENTITLEMENTS`, bundle by bundle. With no argument: a signed device build. With `--source`: the `.entitlements` files ask for them. | `--source` needs none |
| `check-build-secrets.sh` | No secret from the launching shell was written into the build tree. | none |
| `check-store-copy.sh` | Every listing field fits Apple's character limit, has no placeholder, and has no Markdown where it will not render. | none |
| `check-log-privacy.sh` | No `privacy: .public` log interpolation outside an allowlist with reasons. | none |

The parsing lives in `scripts/lib/release_kit.py` (stdlib Python 3.9, the
version the Xcode command-line tools ship), and is tested in this repo's
`tests/test_ios_release_kit.py` without a Mac.

## Traps the scripts encode

- **The archive is not what ships.** Under automatic signing the archive is
  development-signed and Xcode re-signs it on export. An entitlement check on
  the archive, or on a Debug build, says nothing about the `.ipa`. `archive.sh`
  checks the export.
- **Upload with Transporter.** Organizer re-signs the archive itself, so what it
  uploads is not the file the checks read.
- **Every upload needs a new build number**, a re-upload of the same release
  included. `archive.sh` bumps it, and puts it back when a run fails so a failed
  attempt does not use one up. Commit it after the upload.
- **`manageAppVersionAndBuildNumber` is false.** Left on, the export rewrites
  the build number and the app ships one nothing in the repo records.
- **Build once from Xcode on a fresh machine.** Only Xcode.app can create the
  managed provisioning profiles without an App Store Connect API key;
  `xcodebuild -allowProvisioningUpdates` fails with *No Accounts*. Without them a
  device build falls back to the wildcard profile and fails with *"doesn't
  include the ... capability"*, which looks like a team problem and is not.
- **A simulator build has no entitlements.** It consults no profile, so an
  entitlement check on one fails a correctly configured project. There is no
  simulator mode.
- **`aps-environment` is rewritten on export.** It says `development` in source
  and `production` in an App Store export, so `--source` compares only array
  values (app groups, associated domains) and leaves strings to the signed check.
- **What's New does not exist on a 1.0.** Leave `whats_new` out of
  `STORE_COPY_FIELDS` until the second release.

### Secrets in the build environment

`xcodebuild` serialises the environment of every build task into
`<derivedData>/Build/Intermediates.noindex/XCBuildData/*.xcbuilddata/attachments/*`.
Any secret exported by the shell that launched the build is written to disk
there, on every build. The kit strips secret-shaped variable names before
calling `xcodebuild` (`lib/build-env.sh`) and scans the tree afterwards
(`check-build-secrets.sh`), but the real fix is on the machine: stop exporting
secrets from your shell profile, and hand each one only to the tool that needs
it, for example from the login keychain through a wrapper function.

## Template stories

`templates/stories.json` holds the launch stories around a release, in
`/lc:plan`'s proposal format, and passes `plan.py lint`. They are the
self-serve steps. The waits a third party sets (enrollment, export compliance,
Beta App Review, App Review) are external clocks that `/lc:plan` already files
from `clocks.json`, so they are not repeated here.

Each story has `appliesWhen`: `always`, `accounts` (the app has sign-in),
`push`, or `update` (from the second release on). File the ones that apply with
`/lc:plan` or `/lc:groom`.

## What it does not do

- Upload. That is Transporter, by hand, on the checked file.
- Set `MARKETING_VERSION`. A release is named by a person.
- Submit for review, answer App Privacy, or upload screenshots. Those are
  stories, because they need App Store Connect.
- Support a project whose build number is not in a `project.yml` or an
  `.xcconfig`, such as one set only in the `.pbxproj`. Move it to an
  `.xcconfig` first.
