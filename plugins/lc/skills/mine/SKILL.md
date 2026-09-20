---
name: mine
description: Show the work only a human can do, longest lead time first
argument-hint: [project prefix, optional]
---

Report the work that a coding session **cannot** do — the tasks that need a human at a keyboard, a credit card, a login, or a third party. These are the ones that actually gate a launch, and nothing else in this system surfaces them.

The view behind this is filtered on **Agent can do this** and nothing else, so it carries human work of every Type — a Chore that needs a login belongs here as much as a Launch Blocker. Type is in the rows if you want to mention it; do not use it to drop anything.

The ranking lives in `mine.py`, in this skill's base directory. It does the calendar arithmetic and names the pick, so the recommendation is the script's, not a judgement made by eye. It cannot reach Notion, so you query the view and hand it the results.

1. Read `.claude/launch-control.json` for the board URLs.
2. Query the **Your turn** view (`views.yourTurn`) in **view mode**, never SQL mode (SQL is billed). Page to the end with `start_cursor` until `has_more` is false — a dropped page drops the blocker edges that make the chains.
3. Each page must reach the script as the tool returned it. A large result is already saved to disk; use that path as it is, whether the file holds the JSON object or a list of content blocks wrapping it. A small one came back inline; write it verbatim to a file in your scratchpad. Do not transcribe rows by hand.
4. Run `python3 <base directory>/mine.py --view <page 1> [--view <page 2> ...]`. If the user passed a project prefix, add `--prefix <PREFIX>` — the script still reads every row, because a clock in one project can block another. Without one, report across all projects, because the long-lead items rarely live in the repo you happen to be sitting in.
5. **Paste the script's stdout verbatim, in a fenced code block, before you write anything of your own.** Every line it printed, in the order it printed them, character for character — the `earliest finish` dates, the `Chain:` line, the `slack = ... = ...` line and the legend at the end all included. Do not reformat it into a table, do not re-order it, do not reword a line, do not drop the parts that look redundant. The dates and the arithmetic *are* the product; a reply that summarises them has thrown away the only thing this command does that judging by eye does not.

   The known way this fails: the session replaces the block with a prose table — Story / What / Lead time / Blocked? — with the earliest-finish dates, the chain sum and the slack line gone, and the pick reduced to "it has the longest lead time". That reply is a failure of this command even when every sentence in it is true. If you are drawing a table, you have already lost the arithmetic.

6. What the four parts mean. This is background so you can answer a follow-up question — it is **not** a template to rewrite the output into:
   - **Clocks** — `Gating = External`, longest lead first, with the earliest-finish window from today through the blocker chain. These have a lead time you cannot compress, and every day one sits unstarted is a day added to the end of the project.
   - **Unranked** — External items with no **Lead days**. Each is invisible to the ranking until someone fills in Lead days min and max. Do not estimate them yourself.
   - **Your desk** — self-serve and unblocked, smallest estimate first, so the quick ones are visible.
   - **Start today** — one item, with the chain it heads and the slack arithmetic.
7. Before you repeat the pick, verify it: fetch each page in its **Blocked by** relation that is not in the view's rows and confirm it is Done. The script trusts `Status = Ready` for those, as `/lc:next` does. If one is not Done, the board is wrong — say so, and give the runner-up instead.
8. Then, **after** the code block, say plainly which single item to start today and why, in one or two sentences drawn from the arithmetic the script printed. Name one; do not hedge across five. Name no story the script did not print — a paraphrase has been observed to grow a row the script never produced, so if a story is not in the block above, it does not belong in your reply either.

Before you send, check your reply against the block: the `Chain:` line and the `slack = ... = ...` line appear in it character-for-character, and every story ID you mention appears in the script's output. If either is false, you have rewritten the report — send the script's output instead.

If the script exits 1, report its `FAIL` line and stop: a dependency cycle means nothing can be ranked until an edge is removed, and that edge is a human's call.

Do not offer to do these tasks. Some are physically impossible from a terminal, and pretending otherwise wastes the user's time. Where a task has a preparable part — a draft, a checklist, a script, an answer to a form question — offer that specifically.
