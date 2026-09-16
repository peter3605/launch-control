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

# Print a file with its YAML frontmatter removed, or whole if it has none.
# This was a sed one-liner until 2026-09-15. BSD sed - the sed on every macOS -
# rejects "1{/^---$/!q};1,/^---$/d" with "extra characters at the end of q command",
# and the caller sent that error to /dev/null, so BOTH sides of the drift compare
# came back empty, every file looked identical, and the check silently passed on
# every edit it exists to catch. Use python3, which the rest of this script needs
# anyway, rather than a sed dialect that differs between GNU and BSD.
strip_frontmatter() {
  python3 -c "
import sys
lines = open(sys.argv[1], encoding='utf-8', errors='replace').read().split('\n')
if lines and lines[0].strip() == '---':
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            sys.stdout.write('\n'.join(lines[i+1:])); sys.exit(0)
    sys.exit(0)  # unterminated frontmatter: no body
sys.stdout.write('\n'.join(lines))
" "$1" 2>/dev/null || true
}

# Report why $2 is not a usable JSON config, and return non-zero. Used only from
# step 0, before anything has been written.
#
# "Usable" means a top-level OBJECT, not merely well-formed: every caller here does
# cfg.get(...) or cfg[...] = ..., so a file holding a bare list parses fine and then
# raises several steps later, which is the whole failure this guard exists to stop.
# Pass the parser's own message through - "line 5 column 3" is what makes the file
# fixable, and a generic "invalid JSON" is not.
json_problem() {
  local label="$1" path="$2" hint="${3:-}" err
  if [ ! -f "$path" ]; then
    say "  MISSING  $label"
    say "           $path"
    [ -n "$hint" ] && say "           $hint"
    return 1
  fi
  if ! err="$(python3 -c "
import json, sys
cfg = json.load(open(sys.argv[1], encoding='utf-8'))
if not isinstance(cfg, dict):
    raise SystemExit('top-level value is %s, expected a JSON object' % type(cfg).__name__)
" "$path" 2>&1)"; then
    say "  INVALID  $label is not usable JSON:"
    say "           $path"
    printf '%s\n' "$err" | tail -n 1 | sed 's/^/           /'
    [ -n "$hint" ] && say "           $hint"
    return 1
  fi
  return 0
}

say "Launch Control -> $TARGET"
[ "$DRY" -eq 1 ] && say "(dry run - pass --apply to make these changes)"
say ""

# ------------------------------------------ 0. can this script run here at all?
# EVERY write happens after this block: step 4 MOVES command and hook files into
# _pre-plugin/, step 5 appends to .gitignore, step 6 rewrites launch-control.json.
# So everything the script depends on is validated HERE, before the first write,
# and a failure leaves the repo untouched.
#
# Until 2026-09-15 this block checked only for other work in flight, and the
# dependencies were never checked at all. An unparseable launch-control.json got
# past step 1 (whose python ends in `|| true`) and step 2 (wrapped in
# `if ... then :; fi`), let steps 4 and 5 move files and edit .gitignore, and only
# then hit the unguarded json.load in step 6, which raised under `set -euo pipefail`
# and killed the script: repo half-migrated, no baseline stamped, steps 7-8 skipped,
# no summary, nothing undone. A missing python3 took the identical path. That is the
# second time the installer was found able to leave a repo half-migrated (see the
# header, and the BSD-sed note on strip_frontmatter), so new dependencies are added
# HERE, never checked downstream.
say "0. Can this run here?"
BUSY=0
STOP=0
PLUGIN_VERSION=""

if command -v python3 >/dev/null 2>&1; then
  json_problem "launch-control.json" "$CLAUDE/launch-control.json" \
    "Copy examples/launch-control.example.json there and fill it in first." || STOP=1
  json_problem "the plugin manifest" "$PLUGIN/.claude-plugin/plugin.json" \
    "This checkout looks incomplete - re-clone launch-control." || STOP=1
  if [ "$STOP" -eq 0 ]; then
    PLUGIN_VERSION="$(python3 -c "
import json, sys
print(json.load(open(sys.argv[1], encoding='utf-8')).get('version', '') or '')
" "$PLUGIN/.claude-plugin/plugin.json")"
    if [ -z "$PLUGIN_VERSION" ]; then
      say "  NO VERSION  the plugin manifest has no \"version\":"
      say "              $PLUGIN/.claude-plugin/plugin.json"
      say "              Step 6 stamps that version into this repo as its drift"
      say "              baseline, so an empty one makes every later drift check lie."
      STOP=1
    fi
  fi
else
  say "  NO PYTHON  python3 is not on PATH."
  say "             Steps 1, 2, 3, 6 and 7 are all python3. Without it this script"
  say "             gets as far as moving your command files aside and then stops."
  say "             Install python3 and re-run."
  STOP=1
fi

# If a session is live in the target it may be rewriting the same files: on
# 2026-09-08 one did, dropped the ignore lines this script had just added, and the
# next commit swept launch-control.local.json into git. So refuse while anything
# looks in flight. Untracked files are not counted - a freshly created
# launch-control.json is the normal starting point for an install.
STORY=""
[ -f "$CLAUDE/.current-story" ] && STORY="$(tr -d '[:space:]' < "$CLAUDE/.current-story")"
if [ -n "$STORY" ]; then
  say "  BOUND    .claude/.current-story names $STORY - a session is working that story here."
  say "           Finish it with /lc:done in that session, or, if no session is running,"
  say "           empty the file (: > $CLAUDE/.current-story)."
  BUSY=1
fi
if git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
  DIRTY="$(git -C "$TARGET" status --porcelain --untracked-files=no -- .claude .gitignore)"
  if [ -n "$DIRTY" ]; then
    say "  DIRTY    uncommitted changes to files this script edits:"
    printf '%s\n' "$DIRTY" | sed 's/^/             /'
    say "           Commit or stash them (git -C $TARGET stash), then re-run."
    BUSY=1
  fi
fi
# A missing dependency stops BOTH modes. Unlike work in flight, it is not something
# --apply could be forced past, and a dry run that continued would just print
# tracebacks where its report should be.
if [ "$STOP" -eq 1 ]; then
  say ""
  say "  STOPPING. Nothing has been changed."
  exit 1
fi
if [ "$BUSY" -eq 1 ]; then
  if [ "$DRY" -eq 0 ]; then
    say "  REFUSING to apply. Nothing has been changed."
    exit 4
  fi
  say "  ^ --apply will refuse until these are cleared."
else
  say "  none"
fi
say ""

# ---------------------------------------------------------------- 1. drift check
# A true drift check needs a BASELINE: the plugin version this repo was last
# installed from. Without one we cannot tell "you edited this locally" from
# "the plugin moved on since you copied it" - and reporting the second as the
# first is crying wolf on every single install.
#
# A baseline also has to MATCH the plugin to mean anything. Diffing a repo stamped
# v0.1.0 against v0.5.1 surfaces every change the PLUGIN made since, reports them as
# local edits, and refuses. That refusal is permanent: the stamp only advances in
# step 6, which this check runs before, so the repo can never reach a baseline that
# would let it pass. An older baseline is an un-run migration, not drift - treat it
# as no baseline and fall through, exactly as the comment above says to.
# PLUGIN_VERSION came from step 0, which refused to get this far without one. An
# absent installedVersion, by contrast, is a legitimate state - it means "never
# installed from a plugin" - so an empty BASELINE here is data, not an error. It no
# longer hides a parse failure: step 0 has already proved the file is a JSON object.
BASELINE="$(python3 -c "
import json, sys
print(json.load(open(sys.argv[1], encoding='utf-8')).get('installedVersion', '') or '')
" "$CLAUDE/launch-control.json")"
# same | older | newer | unknown (unset, or not a dotted-numeric version)
BASELINE_REL="$(python3 -c "
import sys
def parse(v):
    out = []
    for seg in v.strip().split('.'):
        digits = ''
        for ch in seg:
            if ch.isdigit(): digits += ch
            else: break
        if not digits: return None
        out.append(int(digits))
    return tuple(out) if out else None
a, b = parse(sys.argv[1]), parse(sys.argv[2])
if a is None or b is None:
    print('unknown')
else:
    n = max(len(a), len(b))
    a += (0,) * (n - len(a)); b += (0,) * (n - len(b))
    print('same' if a == b else ('older' if a < b else 'newer'))
" "$BASELINE" "$PLUGIN_VERSION" 2>/dev/null || true)"
[ -n "$BASELINE_REL" ] || BASELINE_REL="unknown"

say "1. Local edits"
if [ "$BASELINE_REL" != "same" ]; then
  # Not diffable. The two situations below look identical from the outside, so name
  # the one that was picked - that line is the whole audit trail for not refusing.
  if [ -z "$BASELINE" ]; then
    say "  MODE: no baseline recorded - this repo predates the plugin."
  elif [ "$BASELINE_REL" = "older" ]; then
    say "  MODE: un-run migration - baseline v$BASELINE is older than plugin v$PLUGIN_VERSION."
    say "  The copies here were made from v$BASELINE and the plugin has moved on since, so"
    say "  a diff against v$PLUGIN_VERSION shows the plugin's changes, not yours. That is"
    say "  not local drift and it is not grounds to refuse."
  elif [ "$BASELINE_REL" = "newer" ]; then
    say "  MODE: baseline v$BASELINE is NEWER than this plugin checkout (v$PLUGIN_VERSION)."
    say "  This checkout is behind the plugin the repo was installed from, so applying"
    say "  restamps the baseline DOWN to v$PLUGIN_VERSION. Pull this repo first if that"
    say "  is not what you want."
  else
    say "  MODE: baseline '$BASELINE' is not a version comparable to v$PLUGIN_VERSION."
    say "  Treating it as no baseline rather than guessing."
  fi
  if [ -d "$CLAUDE/commands" ]; then
    say ""
    say "  The copies are NOT deleted: step 4 moves them to .claude/_pre-plugin/ so you"
    say "  can diff at your leisure. If you improved a command in place and never"
    say "  propagated it, that work is in _pre-plugin/ and is the thing to review before"
    say "  you delete that folder."
  else
    say "  No local copies here - nothing that could have been edited."
  fi
  say "  Step 6 stamps the baseline to v$PLUGIN_VERSION."
else
  say "  MODE: drift check - baseline v$BASELINE matches the plugin, so anything that"
  say "  differs below is a local edit."
  LOST=0
  for f in next start mine status done groom reconcile; do
    old="$CLAUDE/commands/$f.md"
    new="$PLUGIN/skills/$f/SKILL.md"
    [ -f "$old" ] || continue
    a="$(strip_frontmatter "$old")"
    b="$(strip_frontmatter "$new")"
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
# Remove only the handlers the copied layout installed, and leave every other
# SessionStart or Stop hook alone. Every pre-plugin repo checked on 2026-09-14
# (four product repos) wired exactly
#   "$CLAUDE_PROJECT_DIR"/.claude/hooks/session-start.sh   under SessionStart
#   "$CLAUDE_PROJECT_DIR"/.claude/hooks/stop.sh            under Stop
# and step 4 moves those two scripts away, so a handler running either is ours by
# construction. Filter per handler, not per matcher group - a user may have put
# their own handler in the same group - and drop a group or event key only once
# it is empty. The file is rewritten only when something is actually removed.
if [ -f "$CLAUDE/settings.json" ]; then
  python3 - "$CLAUDE/settings.json" "$DRY" 2>/dev/null <<'PY' || say "  !! could not read settings.json as JSON - left untouched; check its hooks by hand"
import json, re, sys
p, dry = sys.argv[1], sys.argv[2] == "1"
OURS = {"SessionStart": "session-start.sh", "Stop": "stop.sh"}
s = json.load(open(p))
hooks = s.get("hooks")
if not isinstance(hooks, dict):
    print("  no hooks"); sys.exit(0)

def is_ours(event, handler):
    if not isinstance(handler, dict) or handler.get("type", "command") != "command":
        return False
    cmd = str(handler.get("command", "")).replace('"', "").replace("'", "").strip()
    return re.search(r"(^|/)\.claude/hooks/" + re.escape(OURS[event]) + r"$", cmd) is not None

removed = kept = 0
for event in OURS:
    groups = hooks.get(event)
    if not isinstance(groups, list):
        continue
    left_groups = []
    for g in groups:
        handlers = g.get("hooks") if isinstance(g, dict) else None
        if not isinstance(handlers, list):
            left_groups.append(g); continue
        left = []
        for hd in handlers:
            cmd = hd.get("command", "?") if isinstance(hd, dict) else "?"
            if is_ours(event, hd):
                removed += 1
                print("  %s %-12s %s" % ("would remove" if dry else "removed     ", event, cmd))
            else:
                kept += 1
                left.append(hd)
                print("  keep         %-12s %s  (not Launch Control's)" % (event, cmd))
        if left:
            g["hooks"] = left
            left_groups.append(g)
    if left_groups:
        hooks[event] = left_groups
    else:
        hooks.pop(event, None)

if removed == 0:
    print("  none found" if kept == 0 else "  no Launch Control entries - nothing to remove")
    sys.exit(0)
if not dry:
    if hooks: s["hooks"] = hooks
    else: s.pop("hooks", None)
    json.dump(s, open(p, "w"), indent=2)
PY
else
  say "  no settings.json"
fi
say ""

# ------------------------------------------------------- 4. retire the copies
say "4. Retire the copied command and hook files"
# Move ONLY the seven files this plugin owns. The commands directory can hold
# other tools' commands - one repo keeps another tool's commands in there - and moving
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
  # The backtick is spelled \x60 here, not literally. Stock macOS bash 3.2 scans a
  # heredoc inside $( ) for backticks even when the delimiter is quoted, so a literal
  # one fails to parse the whole if-block - after steps 1-6 have already written.
  # Check any edit with /bin/bash -n install.sh, not whatever bash is on PATH.
  HITS=$(python3 - "$TARGET/CLAUDE.md" <<'PY2'
import re, sys
t = open(sys.argv[1]).read()
print(len(re.findall(r"\x60/(next|mine|start|done|status|groom|reconcile)\b", t)))
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
