#!/usr/bin/env bash
# Launch Control - get a machine ready to run it.
#
#   ./setup.sh              dry run: report what WOULD be done
#   ./setup.sh --apply      actually do the parts that can be automated
#   ./setup.sh --help
#
# This is the installer for a NEW user. If you are moving an existing repo off
# the older copied-files layout, that is a different job and a different script:
# ./migrate.sh <repo-path>.
#
# Dry run is the default because this runs commands that change your Claude Code
# configuration, and you should see the list before it does.
#
# THREE STEPS CANNOT BE AUTOMATED and this script does not pretend otherwise:
# Notion's OAuth flow, sharing the Notion page with the connector, and turning on
# auto-update for a third-party marketplace. It prints them as work still to do.
# A setup script that exited green while the Notion page was unshared would
# recreate the exact "connected connector that returns nothing" failure that is
# the most common way to arrive at a broken /lc:init.
#
# PORTABILITY: this must parse and run under stock macOS /bin/bash, which is
# 3.2 (2007). No associative arrays, no ${var,,}, no mapfile, no |&. Check any
# edit with `/bin/bash -n setup.sh`, not with whatever bash is on PATH.
set -euo pipefail

MARKETPLACE_NAME="launch-control"
MARKETPLACE_SOURCE="peter3605/launch-control"
PLUGIN_ID="lc@launch-control"
NOTION_SERVER="notion"
NOTION_URL="https://mcp.notion.com/mcp"

DRY=1
for arg in "$@"; do
  case "$arg" in
    --apply) DRY=0 ;;
    -h|--help)
      sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'setup.sh: unknown option %s\n' "$arg" >&2
      printf 'usage: ./setup.sh [--apply]   (see ./setup.sh --help)\n' >&2
      exit 2
      ;;
  esac
done

say()  { printf '%s\n' "$*"; }
ok()   { printf '  ok        %s\n' "$*"; }
note() { printf '  note      %s\n' "$*"; }
warn() { printf '  WARN      %s\n' "$*"; }
miss() { printf '  MISSING   %s\n' "$*"; }
act()  { if [ "$DRY" -eq 1 ]; then printf '  would     %s\n' "$*"; else printf '  doing     %s\n' "$*"; fi; }

# Stop naming the first hard requirement that is absent. Hard means: without it
# this script cannot even report accurately, so continuing would print a page of
# guesses. Exits 1 so a caller can branch on it.
die_missing() {
  say ""
  say "  STOPPING at the first missing requirement: $1"
  say "  $2"
  say ""
  say "  Nothing has been changed."
  exit 1
}

# First line only. `gh --version` prints three.
first_line() { printf '%s\n' "$1" | sed -n '1p'; }

say "Launch Control setup"
if [ "$DRY" -eq 1 ]; then
  say "(dry run - nothing will be changed. Pass --apply to do the automatable steps.)"
else
  say "(--apply: the steps below will be carried out)"
fi
say ""

# ------------------------------------------------------- 1. tools this needs
# Order matters: the FIRST missing hard requirement is the one reported, because
# a reader fixing four things at once fixes none of them. `gh` is deliberately
# not hard - it is used by /lc:done alone, and everything else works without it.
say "1. Tools this needs"

if ! command -v claude >/dev/null 2>&1; then
  miss "claude is not on PATH"
  die_missing "claude" \
"Launch Control is a Claude Code plugin; its commands are Claude Code skills and
  its two hooks are Claude Code hooks. Install Claude Code first:
  https://code.claude.com/docs"
fi
ok "claude      $(first_line "$(claude --version 2>&1)")"

if ! command -v python3 >/dev/null 2>&1; then
  miss "python3 is not on PATH"
  die_missing "python3" \
"Every skill shells out to python3, and so do both hooks, migrate.sh and this
  script. Without it the commands fail quietly rather than loudly, which is
  worse. Install python3 and re-run."
fi
ok "python3     $(first_line "$(python3 -V 2>&1)")"

if ! command -v git >/dev/null 2>&1; then
  miss "git is not on PATH"
  die_missing "git" \
"/lc:start cuts the working branch and /lc:done commits on it. You can run the
  board without shipping by setting git.enabled false in a repo's
  .claude/launch-control.json, but git is assumed present by default."
fi
ok "git         $(first_line "$(git --version 2>&1)")"

# Soft from here down: report the real state, do not stop.
GH_READY=0
if ! command -v gh >/dev/null 2>&1; then
  warn "gh          not on PATH - /lc:done cannot push, open the PR or read checks."
  note "            Everything else works. https://cli.github.com"
else
  # Never redirect a failing command's stderr to /dev/null: `gh auth status`
  # reports WHY it is unhappy there, and that message is the whole fix.
  if GH_AUTH="$(gh auth status 2>&1)"; then
    GH_READY=1
    ok "gh          $(first_line "$(gh --version 2>&1)"), authenticated"
  else
    warn "gh          $(first_line "$(gh --version 2>&1)") is installed but not authenticated:"
    printf '%s\n' "$GH_AUTH" | sed 's/^/              /'
    note "            Run: gh auth login      (/lc:done needs this; nothing else does)"
  fi
fi
say ""

# --------------------------------------------------- 2. the Notion connector
# Every single command reads or writes the board through Notion's MCP tools.
# There is no local or offline mode, so this is the step that decides whether
# anything at all will work.
say "2. Notion MCP server"

MCP_OUT=""
MCP_RC=0
MCP_OUT="$(claude mcp list 2>&1)" || MCP_RC=$?

MCP_STATE="error"
if [ "$MCP_RC" -eq 0 ]; then
  # Parse in python3 rather than grep: the output carries a health check, may
  # carry ANSI colour, and server names contain spaces and colons. Match on the
  # server NAME only - the URL and the health verdict are not ours to assume.
  MCP_STATE="$(printf '%s\n' "$MCP_OUT" | python3 -B -c '
import re, sys
text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", sys.stdin.read())
want = "'"$NOTION_SERVER"'"
state, similar = "missing", []
for line in text.splitlines():
    line = line.strip()
    if not line or ":" not in line:
        continue
    name, rest = line.split(":", 1)
    name = name.strip()
    if name == want:
        state = "connected" if ("Connected" in rest or "✔" in rest) else "configured"
        break
    if want in name.lower():
        similar.append(name)
print(state if state != "missing" or not similar else "similar:" + ",".join(similar))
')" || MCP_STATE="error"
fi

case "$MCP_STATE" in
  connected)
    ok "\`$NOTION_SERVER\` is configured, and the health check reports it connected"
    ;;
  configured)
    ok "\`$NOTION_SERVER\` is configured"
    warn "the health check did not report it connected - see step 1 of section 4"
    ;;
  similar:*)
    warn "no server named \`$NOTION_SERVER\`, but these look related: ${MCP_STATE#similar:}"
    note "The commands look the server up by the name \`$NOTION_SERVER\`. Rename it, or"
    note "add it under that name with the command below."
    act "claude mcp add --transport http $NOTION_SERVER $NOTION_URL --scope user"
    if [ "$DRY" -eq 0 ]; then
      claude mcp add --transport http "$NOTION_SERVER" "$NOTION_URL" --scope user
    fi
    ;;
  error)
    warn "could not read \`claude mcp list\` (exit $MCP_RC). Its output was:"
    printf '%s\n' "$MCP_OUT" | sed 's/^/              /'
    note "Skipping the Notion step rather than guessing at its state."
    ;;
  *)
    miss "no MCP server named \`$NOTION_SERVER\`"
    act "claude mcp add --transport http $NOTION_SERVER $NOTION_URL --scope user"
    note "--scope user makes it available in every repo rather than just this one."
    if [ "$DRY" -eq 0 ]; then
      claude mcp add --transport http "$NOTION_SERVER" "$NOTION_URL" --scope user
      ok "added. It is NOT authorised yet - that is step 1 of section 4."
    fi
    ;;
esac
note "Notion's own guide is the current truth about the endpoint and the auth flow:"
note "https://developers.notion.com/guides/mcp/get-started-with-mcp"
say ""

# ------------------------------------------------------------ 3. the plugin
# `claude plugin marketplace add` and `claude plugin install` are checked for
# rather than assumed: they are newer than the slash commands they mirror, and
# on a Claude Code that predates them this script must print the slash commands
# instead of running something that does not exist.
say "3. The plugin"

PLUGIN_HELP=""
PLUGIN_CLI=0
if PLUGIN_HELP="$(claude plugin --help 2>&1)"; then
  case "$PLUGIN_HELP" in
    *marketplace*) PLUGIN_CLI=1 ;;
  esac
  case "$PLUGIN_HELP" in
    *install*) : ;;
    *) PLUGIN_CLI=0 ;;
  esac
fi

# Ask the CLI what is installed, in JSON, which is a contract; the human-readable
# listing is not. Anything unexpected comes back as "unknown" and is reported as
# unknown rather than as absent.
have_marketplace() {
  claude plugin marketplace list --json 2>/dev/null | python3 -B -c '
import json, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    sys.exit(3)
if not isinstance(rows, list):
    sys.exit(3)
want = sys.argv[1]
sys.exit(0 if any(isinstance(r, dict) and r.get("name") == want for r in rows) else 1)
' "$1"
}

installed_version() {
  claude plugin list --json 2>/dev/null | python3 -B -c '
import json, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    sys.exit(3)
if not isinstance(rows, list):
    sys.exit(3)
want = sys.argv[1]
for r in rows:
    if isinstance(r, dict) and r.get("id") == want:
        print(r.get("version") or "?")
        sys.exit(0)
sys.exit(1)
' "$1"
}

if [ "$PLUGIN_CLI" -eq 0 ]; then
  warn "this Claude Code has no \`claude plugin marketplace\`/\`install\` subcommands."
  note "Run these two inside Claude Code instead, then come back:"
  note "  /plugin marketplace add $MARKETPLACE_SOURCE"
  note "  /plugin install $PLUGIN_ID"
else
  MP_RC=0
  have_marketplace "$MARKETPLACE_NAME" || MP_RC=$?
  case "$MP_RC" in
    0) ok "marketplace \`$MARKETPLACE_NAME\` is already added" ;;
    1)
      act "claude plugin marketplace add $MARKETPLACE_SOURCE"
      if [ "$DRY" -eq 0 ]; then
        claude plugin marketplace add "$MARKETPLACE_SOURCE"
      fi
      ;;
    *)
      warn "could not read the marketplace list as JSON - not guessing."
      note "  /plugin marketplace add $MARKETPLACE_SOURCE"
      ;;
  esac

  PL_RC=0
  PL_VERSION="$(installed_version "$PLUGIN_ID")" || PL_RC=$?
  case "$PL_RC" in
    0) ok "plugin \`$PLUGIN_ID\` is installed (v$PL_VERSION)" ;;
    1)
      act "claude plugin install $PLUGIN_ID"
      if [ "$DRY" -eq 0 ]; then
        # A fresh marketplace add in the same run means the catalogue may not be
        # readable yet on every Claude Code; report rather than fail the script.
        if claude plugin install "$PLUGIN_ID"; then
          ok "installed. Restart Claude Code, or run /reload-plugins, to pick it up."
        else
          warn "the install did not succeed. Run /plugin install $PLUGIN_ID inside"
          warn "Claude Code, which reports the reason interactively."
        fi
      fi
      ;;
    *)
      warn "could not read the plugin list as JSON - not guessing."
      note "  /plugin install $PLUGIN_ID"
      ;;
  esac
fi
note "Third-party marketplaces do NOT auto-update. This one is third-party, so"
note "the plugin will sit at whatever version you installed until you say"
note "otherwise - see step 3 of section 4."
say ""

# ------------------------------------------ 4. the parts no script can do
# Each of these is a browser flow or a UI menu. Printing them as a numbered list
# of REMAINING work is the point: claiming them done is how a green setup run
# ends at a board that answers every query with nothing.
say "4. What no script can do for you"
say ""
say "  1. AUTHORISE the Notion connector."
say "     Run /mcp inside Claude Code, or \`claude mcp login $NOTION_SERVER\`, and"
say "     complete Notion's OAuth flow in the browser. Adding the server above was"
say "     configuration; this is what grants access."
say ""
say "  2. SHARE the page the board will live under."
say "     In Notion, open that page, then its \`···\` menu -> Add connections -> the"
say "     Notion connector. Notion connectors see only what you share with them, and"
say "     access cascades to everything inside that page. Skipping this is the"
say "     failure that looks like a working connector returning nothing."
say ""
say "  3. TURN ON auto-update for this marketplace."
say "     /plugin -> Marketplaces -> $MARKETPLACE_NAME -> Enable auto-update, or set"
say "     \"autoUpdate\": true under extraKnownMarketplaces in your settings."
say "     Official Anthropic marketplaces auto-update; third-party ones do not."
say "     Without this you stay on today's version indefinitely, and the first"
say "     symptom is a command behaving like a version you no longer have."
say ""
say "Then, in the repo you want on the board:"
say ""
say "  /lc:init          provisions both Notion databases, every property and view,"
say "                    checks what it built, and writes this repo's config"
say "  /lc:next          hands you the first story a session can actually do"
say ""
if [ "$GH_READY" -eq 0 ] && command -v gh >/dev/null 2>&1; then
  say "Remember gh auth login before your first /lc:done."
  say ""
fi
if [ "$DRY" -eq 1 ]; then
  say "This was a dry run and changed nothing. Re-run with --apply to carry out"
  say "the \`would\` lines above. Sections 1, 2 and 3 are idempotent: a second"
  say "--apply reports everything already done and changes nothing."
fi
