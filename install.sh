#!/usr/bin/env bash
# Launch Control - migrate a repo from the copied-files layout to the `lc` plugin.
#
#   ./install.sh <repo-path>            dry run: report what WOULD change
#   ./install.sh <repo-path> --apply    actually change it
#
# Dry run is the default on purpose. The one thing this must never do is silently
# delete a local edit that was never propagated back - that is the failure it exists
# to catch.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$HERE/plugins/lc"
TARGET="${1:-}"
APPLY="${2:-}"

if [ -z "$TARGET" ] || [ ! -d "$TARGET" ]; then
  echo "usage: ./install.sh <repo-path> [--apply]" >&2
  exit 2
fi
TARGET="$(cd "$TARGET" && pwd)"
CLAUDE="$TARGET/.claude"
DRY=1
[ "$APPLY" = "--apply" ] && DRY=0

say() { printf '%s\n' "$*"; }
act() { if [ "$DRY" -eq 1 ]; then say "  would $*"; else say "  $*"; fi; }

say "Launch Control -> $TARGET"
[ "$DRY" -eq 1 ] && say "(dry run - pass --apply to make these changes)"
say ""

if [ ! -f "$CLAUDE/launch-control.json" ]; then
  say "!! $CLAUDE/launch-control.json not found."
  say "   Copy examples/launch-control.example.json there and fill it in first."
  exit 1
fi

# ---------------------------------------------------------------- 1. drift check
say "1. Local edits that would be lost"
LOST=0
for f in next start mine status done groom reconcile; do
  old="$CLAUDE/commands/$f.md"
  new="$PLUGIN/skills/$f/SKILL.md"
  [ -f "$old" ] || continue
  # Compare bodies only - frontmatter legitimately differs between the two formats.
  a="$(sed '1{/^---$/!q};1,/^---$/d' "$old" 2>/dev/null || true)"
  b="$(sed '1{/^---$/!q};1,/^---$/d' "$new" 2>/dev/null || true)"
  if [ "$a" != "$b" ]; then
    n=$(diff <(printf '%s' "$a") <(printf '%s' "$b") | grep -c '^[<>]' || true)
    say "  DIFFERS  commands/$f.md  ($n lines)"
    LOST=1
  fi
done
for h in session-start stop; do
  [ -f "$CLAUDE/hooks/$h.sh" ] || continue
  if ! cmp -s "$CLAUDE/hooks/$h.sh" "$PLUGIN/hooks/$h.sh"; then
    say "  DIFFERS  hooks/$h.sh"
    LOST=1
  fi
done
if [ "$LOST" -eq 1 ]; then
  say ""
  say "  ^ These local copies differ from the plugin. Review them before applying;"
  say "    an improvement made here and never propagated is exactly what gets lost."
  say "    Diff with:  diff $CLAUDE/commands/<n>.md $PLUGIN/skills/<n>/SKILL.md"
  if [ "$DRY" -eq 0 ]; then
    say ""
    say "  REFUSING to apply while local copies differ. Reconcile them first, or"
    say "  delete the ones you have already propagated, then re-run --apply."
    exit 3
  fi
else
  say "  none - local copies match the plugin"
fi
say ""

# ------------------------------------------------- 2. split private notice out
say "2. Private notice split"
if python3 - "$CLAUDE" "$DRY" <<'PY'
import json, os, sys
d, dry = sys.argv[1], sys.argv[2] == "1"
main = os.path.join(d, "launch-control.json")
loc  = os.path.join(d, "launch-control.local.json")
cfg = json.load(open(main))
notice = (cfg.get("notice") or "").strip()
if not notice:
    print("  no notice field - nothing to split"); sys.exit(1)
if os.path.exists(loc):
    print("  launch-control.local.json already exists - leaving both alone"); sys.exit(1)
print("  move `notice` -> launch-control.local.json (gitignored)")
print("  %d characters, which may include spend figures or account state" % len(notice))
if not dry:
    json.dump({"notice": notice}, open(loc, "w"), indent=2)
    cfg.pop("notice", None)
    json.dump(cfg, open(main, "w"), indent=2)
    print("  done")
sys.exit(0)
PY
then :; fi
say ""

# ------------------------------------------------ 3. unwire the old local hooks
say "3. Old per-repo hook wiring in settings.json"
if [ -f "$CLAUDE/settings.json" ]; then
  if grep -q 'SessionStart\|Stop' "$CLAUDE/settings.json" 2>/dev/null; then
    act "remove SessionStart/Stop entries (the plugin provides them; leaving both risks double-firing)"
    if [ "$DRY" -eq 0 ]; then
      python3 - "$CLAUDE/settings.json" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
h = s.get("hooks", {})
for k in ("SessionStart", "Stop"):
    h.pop(k, None)
if h: s["hooks"] = h
else: s.pop("hooks", None)
json.dump(s, open(p, "w"), indent=2)
PY
    fi
  else
    say "  none found"
  fi
else
  say "  no settings.json"
fi
say ""

# ------------------------------------------------------- 4. retire the copies
say "4. Retire the copied command and hook files"
if [ -d "$CLAUDE/commands" ] || [ -d "$CLAUDE/hooks" ]; then
  act "move .claude/commands and .claude/hooks to .claude/_pre-plugin/ (kept, not deleted)"
  if [ "$DRY" -eq 0 ]; then
    mkdir -p "$CLAUDE/_pre-plugin"
    for d in commands hooks; do
      [ -d "$CLAUDE/$d" ] && mv "$CLAUDE/$d" "$CLAUDE/_pre-plugin/$d" || true
    done
  fi
else
  say "  already gone"
fi
say ""

# ------------------------------------------------------------- 5. gitignore
say "5. .gitignore"
GI="$TARGET/.gitignore"
for line in ".claude/launch-control.local.json" ".claude/.current-story" ".claude/.nudged" ".claude/_pre-plugin/"; do
  if [ -f "$GI" ] && grep -qxF "$line" "$GI"; then
    say "  present  $line"
  else
    act "add      $line"
    [ "$DRY" -eq 0 ] && printf '%s\n' "$line" >> "$GI"
  fi
done
say ""

say "Next:"
say "  /plugin marketplace add peter3605/launch-control"
say "  /plugin install lc@launch-control"
say "  then start a session here and check that /lc:next resolves."
