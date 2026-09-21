---
name: Bug report
about: Something in Launch Control does not do what it says it does
title: ''
labels: bug
assignees: ''
---

<!--
Please fill in the four boxes under "Versions". They are not boilerplate: most
reports here turn out to be either a config that has silently regressed or a
plugin version that stopped updating, and those four answers separate the two
immediately. A report without them usually needs a round trip before anyone can
start on it.

This repository is public. Please do not paste real Notion page or database IDs,
spend figures, or account state. Redact them as <redacted> - the shape of the
value is almost always enough.
-->

## What happened

<!-- What you ran, and what it did. Exact command, exact output where it is short. -->

## What you expected instead

## Steps to reproduce

1.
2.
3.

## Versions

**Launch Control plugin version:** <!-- The `v0.0.0` in the "## Launch Control"
banner that the SessionStart hook prints at the top of a session in a tracked
repo. If there is no banner, say so - that is itself a finding, and it usually
means .claude/launch-control.json is missing or untracked. -->

**Claude Code version:** <!-- `claude --version` -->

**Operating system:** <!-- e.g. macOS 15.3 (Apple Silicon), Ubuntu 24.04, Windows 11 + WSL2 -->

**`/lc:doctor` output:**

<!-- Run /lc:doctor in the affected repo and paste the whole thing, including the
lines that passed. Which checks passed is as informative as which failed. If
/lc:doctor is itself what is broken, say that here instead. -->

```
paste here
```

## Anything else

<!-- If the Notion connector is involved, `claude mcp list` is useful (it shows
whether the `notion` server is configured and whether its health check passes).
docs/troubleshooting.md covers the common ones, including the three different
ways the connector can be half-set-up - it is worth a look first, and if it sent
you the wrong way that is worth reporting too. -->
