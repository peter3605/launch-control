#!/usr/bin/env bash
#
# Install the iOS release kit into an app repo.
#
#   install.sh <repo>                    dry run: say what would change
#   install.sh <repo> --apply            do it
#   install.sh <repo> --dest DIR --apply install somewhere other than scripts/release
#
# Two kinds of file, treated differently:
#
#   KIT-OWNED   the scripts and scripts/lib. Copied every time; a re-install is
#               how an app picks up a fixed script. Nothing app-specific belongs
#               in them - that is what release.conf is for - so overwriting them
#               loses nothing that should have been there.
#   APP-OWNED   release.conf, ExportOptions.plist and docs/store-copy.md. Written
#               only when absent, from the kit's templates. Never overwritten.
#
# Dry run by default, like the rest of Launch Control's scripts.
set -euo pipefail

KIT="$(cd "$(dirname "$0")" && pwd)"
REPO=""
DEST="scripts/release"
APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --dest) DEST="${2:?--dest needs a directory}"; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) [[ -z "$REPO" ]] || { echo "one repo at a time" >&2; exit 2; }; REPO="$1" ;;
  esac
  shift
done
[[ -n "$REPO" ]] || { sed -n '2,7p' "$0" >&2; exit 2; }
REPO="$(cd "$REPO" && pwd)"
if ! git -C "$REPO" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "!! $REPO is not a git repository" >&2
  exit 1
fi
[[ "$DEST" == /* || "$DEST" == *..* ]] && { echo "!! --dest must be a path inside the repo" >&2; exit 2; }

TARGET="$REPO/$DEST"
VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
  "$KIT/../../.claude-plugin/plugin.json" 2>/dev/null || echo unknown)"

changes=0
plan() {  # plan <src> <dst> <owned-by>
  local src="$1" dst="$2" owner="$3" rel="${2#"$REPO"/}"
  if [[ ! -e "$dst" ]]; then
    echo "  create  $rel"
  elif [[ "$owner" == app ]]; then
    echo "  keep    $rel (yours; never overwritten)"
    return
  elif cmp -s "$src" "$dst"; then
    echo "  same    $rel"
    return
  else
    echo "  update  $rel"
  fi
  changes=$((changes + 1))
  if [[ $APPLY -eq 1 ]]; then
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    [[ -x "$src" ]] && chmod +x "$dst"
  fi
  return 0
}

echo "iOS release kit $VERSION -> $REPO"
echo
for f in "$KIT"/scripts/*.sh; do
  plan "$f" "$TARGET/$(basename "$f")" kit
done
for f in "$KIT"/scripts/lib/*; do
  plan "$f" "$TARGET/lib/$(basename "$f")" kit
done
plan "$KIT/release.conf.example" "$TARGET/release.conf.example" kit
plan "$KIT/release.conf.example" "$TARGET/release.conf" app
plan "$KIT/ExportOptions.plist" "$TARGET/ExportOptions.plist" app
plan "$KIT/templates/store-copy.md" "$REPO/docs/store-copy.md" app

# The version the scripts came from, so a later reader can tell a stale copy
# from a locally edited one.
stamp="$TARGET/.kit-version"
if [[ "$(cat "$stamp" 2>/dev/null || true)" != "$VERSION" ]]; then
  echo "  stamp   ${stamp#"$REPO"/} = $VERSION"
  changes=$((changes + 1))
  [[ $APPLY -eq 1 ]] && { mkdir -p "$TARGET"; echo "$VERSION" >"$stamp"; }
fi

echo
if [[ $changes -eq 0 ]]; then
  echo "Nothing to do: already installed at $VERSION."
  exit 0
fi
if [[ $APPLY -eq 0 ]]; then
  echo "Dry run: $changes change(s). Re-run with --apply to make them."
  exit 0
fi
cat <<EOF
Installed. Next:
  1. Fill in $DEST/release.conf - every REPLACE_ME.
  2. Put your team ID in $DEST/ExportOptions.plist.
  3. Gitignore the build directory (PROJECT_DIR/build by default).
  4. Run $DEST/check-release-ready.sh. Everything it checks needs no signing.
  5. File the stories in the kit's templates/stories.json that apply to this app.
EOF
