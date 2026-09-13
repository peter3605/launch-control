---
name: mine
description: Show the launch blockers only a human can do, longest lead time first
argument-hint: [project prefix, optional]
---

Report the work that a coding session **cannot** do — the tasks that need a human at a keyboard, a credit card, a login, or a third party. These are the ones that actually gate a launch, and nothing else in this system surfaces them.

The ranking lives in `mine.py`, in this skill's base directory. It does the calendar arithmetic and names the pick, so the recommendation is the script's, not a judgement made by eye. It cannot reach Notion, so you query the view and hand it the results.

1. Read `.claude/launch-control.json` for the board URLs.
2. Query the **Your turn** view (`views.yourTurn`) in **view mode**, never SQL mode (SQL is billed). Page to the end with `start_cursor` until `has_more` is false — a dropped page drops the blocker edges that make the chains.
3. Each page must reach the script as the tool returned it, a JSON object with a `results` list. A large result is already saved to disk; use that path. A small one came back inline; write it verbatim to a file in your scratchpad. Do not transcribe rows by hand.
4. Run `python3 <base directory>/mine.py --view <page 1> [--view <page 2> ...]`. If the user passed a project prefix, add `--prefix <PREFIX>` — the script still reads every row, because a clock in one project can block another. Without one, report across all projects, because the long-lead items rarely live in the repo you happen to be sitting in.
5. Show the output as it printed. It has four parts:
   - **Clocks** — `Gating = External`, longest lead first, with the earliest-finish window from today through the blocker chain. These have a lead time you cannot compress, and every day one sits unstarted is a day added to the end of the project.
   - **Unranked** — External items with no **Lead days**. Name each one and say that it is invisible to the ranking until someone fills in Lead days min and max. Do not estimate them yourself in the report.
   - **Your desk** — self-serve and unblocked, smallest estimate first, so the quick ones are visible.
   - **Start today** — one item, with the chain it heads and the slack arithmetic.
6. Before you repeat the pick, verify it: fetch each page in its **Blocked by** relation that is not in the view's rows and confirm it is Done. The script trusts `Status = Ready` for those, as `/lc:next` does. If one is not Done, the board is wrong — say so, and give the runner-up instead.
7. Then say plainly which single item to start today and why, in one or two sentences drawn from the arithmetic. Do not hedge across five things — name one.

If the script exits 1, report its `FAIL` line and stop: a dependency cycle means nothing can be ranked until an edge is removed, and that edge is a human's call.

Do not offer to do these tasks. Some are physically impossible from a terminal, and pretending otherwise wastes the user's time. Where a task has a preparable part — a draft, a checklist, a script, an answer to a form question — offer that specifically.
