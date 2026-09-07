#!/usr/bin/env bash
# Launch Control - inject the current story binding at session start.
# Runs from the plugin; reads its config from the PROJECT.
# Never fails the session: any error exits 0 silently.
set -uo pipefail
PROJ="${CLAUDE_PROJECT_DIR:-$PWD}/.claude"
[ -f "$PROJ/launch-control.json" ] || exit 0
ROOT="${CLAUDE_PLUGIN_ROOT:-}"

python3 - "$PROJ" "$ROOT" <<'PY' 2>/dev/null || exit 0
import json, os, sys

proj, root = sys.argv[1], sys.argv[2]

def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

cfg = load(os.path.join(proj, "launch-control.json"))
if not cfg:
    sys.exit(0)

# launch-control.local.json is gitignored and holds anything that should not be
# committed - spend figures, account state, private infrastructure notes.
# Its keys override the shared file, EXCEPT `notice`, which is appended.
local = load(os.path.join(proj, "launch-control.local.json"))
shared_notice = (cfg.get("notice") or "").strip()
local_notice = (local.get("notice") or "").strip()
for k, v in local.items():
    if k != "notice":
        cfg[k] = v
notice = "\n\n".join(n for n in (shared_notice, local_notice) if n)

version = ""
if root:
    version = (load(os.path.join(root, ".claude-plugin", "plugin.json")) or {}).get("version", "")

cur = ""
p = os.path.join(proj, ".current-story")
if os.path.exists(p):
    try:
        cur = open(p).read().strip()
    except Exception:
        cur = ""

title = "## Launch Control" + (f" `v{version}`" if version else "")
lines = [
    title,
    "",
    f"This repo is tracked as project **{cfg.get('project','?')}** "
    f"(story IDs `{cfg.get('prefix','?')}...`). The backlog is the source of truth "
    "for what to work on and what counts as finished.",
    "",
]
if cur:
    lines += [
        f"**This session is bound to story `{cur}`.**",
        "",
        "Before doing anything else, fetch that story and re-read its **Done when** and "
        "**Notes and traps** fields. When the work is finished, run `/lc:done` so it is "
        "ticked off and the next stories are unblocked. Put the story ID in every commit "
        "subject.",
    ]
else:
    lines += [
        "**No story is bound to this session yet.**",
        "",
        "If the user asks what to work on, run `/lc:next`. If they name specific work, check "
        "with `/lc:next` or a board search whether it is already a story and run "
        "`/lc:start <ID>`; if it genuinely is not on the backlog, run `/lc:groom` to file it "
        "first. Untracked work is how the last tracker went stale.",
    ]

if notice:
    lines += ["", "### Read this before you start", "", notice]

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "\n".join(lines),
    }
}))
PY
