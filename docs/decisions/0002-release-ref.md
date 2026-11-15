# 0002 — Whether installs should pin to a release ref

**Status:** Accepted, 2026-11-15 · **Story:** LC-22

## Context

`.claude-plugin/marketplace.json` lists the plugin with a relative-path source,
`"source": "./plugins/lc"`. A holistic review on 2026-11-14 read that as "every
merge to `main` is a release to every user", and asked whether installs should be
pinned to a tagged release instead of following the default branch.

What Claude Code actually does was checked against its documentation on
2026-11-15, with Claude Code 2.1.325 installed locally:

- **A relative path resolves inside the marketplace checkout.** "The path resolves
  from the marketplace root", and a marketplace added as `owner/repo` is cloned at
  its `ref`, which "defaults to the repository's default branch".
  ([Marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference.md#relative-path-plugin-source))
- **Installed copies move only when the version changes.** "Users get a new copy
  only when the plugin's computed version differs from the one they have. That
  version comes from `plugin.json` first", and "if you set `"version": "1.0.0"` and
  push new commits without changing it, users don't receive them."
  ([Host and maintain a marketplace — Release a new version](https://code.claude.com/docs/en/plugins/host-marketplace.md#release-a-new-version))
- **Pinning is available two ways.** A plugin entry can name a `ref` (branch or
  tag) and a `sha` on a `github`, `url` or `git-subdir` source. A plugin that is a
  subdirectory of a repository, as this one is, needs `git-subdir`:

  ```json
  { "name": "lc",
    "source": { "source": "git-subdir",
                "url": "peter3605/launch-control",
                "path": "plugins/lc",
                "ref": "v0.9.0",
                "sha": "<the tag's full 40-character commit SHA>" } }
  ```

  Separately, a user can pin the whole marketplace when adding it:
  `/plugin marketplace add peter3605/launch-control#v0.9.0`, or `@v0.9.0`.
  ([Marketplace reference — Plugin sources](https://code.claude.com/docs/en/plugins/marketplace-reference.md#plugin-sources),
  [Marketplace sources](https://code.claude.com/docs/en/plugins/marketplace-reference.md#marketplace-sources))

So the review's premise is half right. A merge with **no version bump** does not
reach an existing install; it reaches only a fresh install, which clones
`main`. A merge **with** a version bump reaches every user who updates, or who has
auto-update on, which Quickstart step 4 recommends. In this repo the bump travels
in the same pull request as the change (CONTRIBUTING's version-bump rule), so a
bad change that bumps the version does ship on merge.

## Decision

**Do not pin the marketplace entry yet. Make the version bump the release, and
make every release a tag and a GitHub release.**

- Every version that reaches `main` gets an annotated tag `v<version>` on the
  last commit carrying it, and a GitHub release whose body is that version's
  `CHANGELOG.md` entry. CONTRIBUTING's "Cutting a release" section is the
  procedure. Versions 0.1.0 to 0.9.0 were backfilled on 2026-11-15.
- `marketplace.json` keeps `"source": "./plugins/lc"`.

Why not pin now:

1. **The gate that matters is already the version.** Existing installs do not
   move until `plugin.json` changes, so the risky event is a version-bumping
   merge, and that is now a deliberate, tagged step with a release note.
2. **Pinning costs a second commit per release, and that commit is itself a
   merge to `main`.** The entry's `ref`/`sha` can only name a commit that already
   exists, so every release becomes "merge, tag, then merge again to move the
   pin". A broken or forgotten pin commit fails in the other direction: users
   silently stay on an old version.
3. **Switching the source type under existing installs is untested.** Every
   current install has a relative-path source. What changing that entry to
   `git-subdir` does to an installed copy, a cached version, or someone's local
   edits has not been tried, and this change would reach every user at once with
   no staging step.

## When to revisit

Pin, using the `git-subdir` entry above, when any one of these becomes true:

- a release ships a regression to users who were not the author;
- the plugin has users outside the author's own machines who keep auto-update on;
- someone asks for a stable channel. The documented way to offer one is a second
  marketplace whose entry points at a `stable` ref
  ([Run release channels](https://code.claude.com/docs/en/plugins/host-marketplace.md#run-release-channels)).

Until then, someone who wants a fixed version can add the marketplace at a tag:
`/plugin marketplace add peter3605/launch-control#v0.9.0`.

The platform facts above are dated 2026-11-15. Re-check them at the source before
relying on them, as decision 0001's amendment learned the hard way.
