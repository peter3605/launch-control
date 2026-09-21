#!/usr/bin/env bash
# Launch Control - this file is a signpost, not a script that does anything.
#
# Until 0.6.0 this name belonged to the MIGRATION script, which moves a repo off
# the older copied-files layout. Anyone arriving at this repo for the first time
# reasonably read "install.sh" as the installer, ran it, and got a usage error
# about a repo path they did not have. The migration script is now ./migrate.sh
# and the installer is ./setup.sh, so the two jobs have the two names.
#
# This shim exits non-zero on purpose: it did not do what you asked, and a script
# that prints advice and exits 0 reads as success.
#
# It can be deleted once nothing points here any more.
set -eu

cat >&2 <<'MSG'
install.sh no longer does anything. There are two scripts, for two different jobs:

  ./setup.sh              SETTING UP A MACHINE for the first time.
  ./setup.sh --apply      Checks claude, python3, git and gh; adds the Notion MCP
                          server, the marketplace and the plugin; then prints the
                          three steps no script can do for you. Dry run by default.

  ./migrate.sh <repo>     MOVING AN EXISTING REPO off the older copied-files
  ./migrate.sh <repo> --apply
                          layout, where Launch Control's commands and hooks were
                          copied into that repo's own .claude/ directory. Only for
                          repos that predate the plugin. Dry run by default.

If you are not sure which you want, you want ./setup.sh.
MSG
exit 2
