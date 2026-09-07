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
# A true drift check needs a BASELINE: the plugin version this repo was last
# installed from. Without one we cannot tell "you edited this locally" from
# "the plugin moved on since you copied it" - and reporting the second as the
# first is crying wolf on every single install.
PLUGIN_VERSION="$(python3 -c "import json;print(json.load(open('$PLUGIN/.claude-plugin/plugin.json')).get('version',''))" 2>/dev/null || true)"
BASELINE="$(python3 -c "import json;print(json.load(open('$CLAUDE/launch-control.json')).get('installedVersion','') or '')" 2>/dev/null || true)"

say "1. Local edits"
if [ -z "$BASELINE" ]; then
  if [ -d "$CLAUDE/commands" ]; then
    say "  No baseline recorded - this repo predates the plugin."
    say "  Its copies cannot be meaningfully diffed against v$PLUGIN_VERSION, because"
    say "  the plugin has been generalized since they were made. They are NOT deleted:"
    say "  step 4 moves them to .claude/_pre-plugin/ so you can diff at your leisure."
    say ""
    say "  If you improved a command in place and never propagated it, that work is in"
    say "  _pre-plugin/ and is the thing to review before you delete that folder."
  else
    say "  No baseline and no local copies - clean install."
  fi
else
  LOST=0
  for f in next start mine status done groom reconcile; do
    old="$CLAUDE/commands/$f.md"
    new="$PLUGIN/skills/$f/SKILL.md"
    [ -f "$old" ] || continue
    a="$(sed '1{/^---$/!q};1,/^---$/d' "$old" 2>/dev/null || true)"
    b="$(sed '1{/^---$/!q};1,/^---$/d' "$new" 2>/dev/null || true)"
    if [ "$a" != "$b" ]; then
      n=$(diff <(printf '%s' "$a") <(printf '%s' "$b") | grep -c '^[<>]' || true)
      say "  DIFFERS  commands/$f.md  ($n lines) - edited since v$BASELINE"
      LOST=1
    fi
  done
  if [ "$LOST" -eq 1 ]; then
    say ""
    say "  ^ Edited locally since this repo was installed from v$BASELINE."
    say "    Propagate them into the plugin before applying, or they are lost."
    if [ "$DRY" -eq 0 ]; then
      say "  REFUSING to apply. Reconcile these first, then re-run --apply."
      exit 3
    fi
  else
    say "  none - local copies match v$BASELINE"
  fi
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
# Move ONLY the seven files this plugin owns. The commands directory can hold
# other tools' commands - nightcrew keeps OpenSpec's opsx/ in there - and moving
# the whole directory would silently break them.
FOUND=0
for f in next start mine status done groom reconcile; do
  [ -f "$CLAUDE/commands/$f.md" ] && FOUND=$((FOUND+1))
done
for h in session-start stop; do
  [ -f "$CLAUDE/hooks/$h.sh" ] && FOUND=$((FOUND+1))
done
if [ "$FOUND" -gt 0 ]; then
  act "move $FOUND Launch Control file(s) to .claude/_pre-plugin/ (kept, not deleted)"
  OTHERS=$(ls -A "$CLAUDE/commands" 2>/dev/null | grep -vE '^(next|start|mine|status|done|groom|reconcile)\.md$' || true)
  if [ -n "$OTHERS" ]; then
    say "  leaving in place (not ours): $(echo $OTHERS | tr '\n' ' ')"
  fi
  if [ "$DRY" -eq 0 ]; then
    mkdir -p "$CLAUDE/_pre-plugin/commands" "$CLAUDE/_pre-plugin/hooks"
    for f in next start mine status done groom reconcile; do
      [ -f "$CLAUDE/commands/$f.md" ] && mv "$CLAUDE/commands/$f.md" "$CLAUDE/_pre-plugin/commands/" || true
    done
    for h in session-start stop; do
      [ -f "$CLAUDE/hooks/$h.sh" ] && mv "$CLAUDE/hooks/$h.sh" "$CLAUDE/_pre-plugin/hooks/" || true
    done
    rmdir "$CLAUDE/commands" "$CLAUDE/hooks" 2>/dev/null || true
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

# --------------------------------------------------- 6. stamp the baseline
say "6. Baseline"
act "record installedVersion = $PLUGIN_VERSION in launch-control.json"
if [ "$DRY" -eq 0 ]; then
  python3 - "$CLAUDE/launch-control.json" "$PLUGIN_VERSION" <<'PY2'
import json, sys
p, v = sys.argv[1], sys.argv[2]
cfg = json.load(open(p))
cfg["installedVersion"] = v
json.dump(cfg, open(p, "w"), indent=2)
PY2
fi
say ""

# ----------------------------------------- 7. CLAUDE.md command references
say "7. CLAUDE.md"
if [ -f "$TARGET/CLAUDE.md" ]; then
  HITS=$(python3 - "$TARGET/CLAUDE.md" <<'PY2'
import re, sys
t = open(sys.argv[1]).read()
print(len(re.findall(r"`/(next|mine|start|done|status|groom|reconcile)\b", t)))
PY2
)
  if [ "$HITS" -gt 0 ]; then
    act "rewrite $HITS command references to the /lc: namespace"
    if [ "$DRY" -eq 0 ]; then
      python3 - "$TARGET/CLAUDE.md" <<'PY2'
import re, sys
p = sys.argv[1]
t = open(p).read()
t = re.sub(r"`/(next|mine|start|done|status|groom|reconcile)\b", r"`/lc:\1", t)
open(p, "w").write(t)
PY2
    fi
  else
    say "  no stale command references"
  fi
else
  say "  no CLAUDE.md"
fi
say ""

# ------------------------------------------------ 8. is the config tracked?
say "8. Version control"
if git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
  if git -C "$TARGET" ls-files --error-unmatch .claude/launch-control.json >/dev/null 2>&1; then
    say "  launch-control.json is tracked - a fresh clone will have it"
  else
    say "  !! launch-control.json is NOT tracked by git."
    say "     The hook's first line is [ -f launch-control.json ] || exit 0, so on a fresh"
    say "     clone Launch Control does not warn - it silently does nothing. Commit it:"
    say "       git -C $TARGET add -f .claude/launch-control.json CLAUDE.md"
    say "     launch-control.local.json stays out; that is the point of the split."
  fi
else
  say "  not a git repo"
fi
say ""

say "Next:"
say "  /plugin marketplace add peter3605/launch-control"
say "  /plugin install lc@launch-control"
say "  then start a session here and check that /lc:next resolves."
