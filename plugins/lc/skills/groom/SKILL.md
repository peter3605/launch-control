---
name: groom
description: File a newly discovered item into the Launch Control backlog
argument-hint: <what you found>
---

File **$ARGUMENTS** into the Launch Control backlog.

1. Read `.claude/launch-control.json` for the project page ID, the stories data source, and the story-ID prefix.
2. Decide whether this is a **Launch Blocker** (users cannot be served without it), **Backlog** (better product, does not block shipping), or a **Chore**. Say which and why, in one line.
3. Search the Stories database first - with `notion-search`, not a data-source query. If something equivalent exists, update that story rather than creating a duplicate.
4. **Allocate the Story ID by re-read-and-retry.** This is the chosen method, and it is a loop rather than a lookup — read it as one. Launch blockers take plain numbers (`ABC-22`); backlog items take the `-B` series (`ABC-B12`), and the two are separate sequences, so scan only the one you are allocating from.

   Every read in this loop is the project's **road view** (`views.road`) in **view mode**, paged with `start_cursor` until `has_more` is false. Each page the tool saved to a file is passed by its path. A page that came back inline - the last one usually does - is **not** written to a file: give it on the command line as `--inline-page <rows on that page> <its has_more, true or false> --row <Story ID> <Status> <page url> <Blocked by URLs comma-separated, or ->` with one `--row` per row, in order (`-` for a blank Story ID). Those are short values you can state exactly; the script checks the count and every URL, and refuses rather than answers when one is off. The road view covers the whole sequence because a prefix belongs to exactly one project. **Read the road here, not the `open` view**: allocation must see every ID ever issued, Done ones included, or it hands out a number a Done story already carries - and the duplicate check after the create needs them for the same reason. Hand the pages to `<base directory>/../doctor/ids.py` rather than reading rows by eye - a road view runs to hundreds of thousands of characters. Never use a rows-mode or SQL query: Notion's free plan meters both from one workspace allowance, and a groom makes several reads.

   a. `python3 <base directory>/../doctor/ids.py next <page files...> --prefix <PREFIX>` (add `--backlog` for the `-B` series) prints the highest number in your sequence plus one: that is the candidate. It refuses to answer from a read that stopped before the last page.

   b. **Re-read the board immediately before the create in step 5** — not before you drafted the page, not a paragraph earlier. The window between reading the highest number and writing the new row is the entire bug, so make that window as small as you can: the re-read is the last thing you do before creating the page.

   c. If the candidate is taken by the time you re-read, take the new highest, add one, and **retry from (b)**. Repeat until the create succeeds or five candidates in a row come back taken; if five are taken, stop and say so rather than forcing a number through.

   d. After the create, re-read the road view and run `ids.py find <page files...> --id <new ID>`: exit 0 means its Story ID appears exactly once across the prefix, exit 2 means twice. A brand-new row can lag the view by a few seconds; if it is not found yet, re-read once or twice before worrying. If it appears twice you lost the race — renumber the row you just created. Do not delete it, and do not renumber the other one; the other session is still using it.

   Why this rather than just taking the next free number: two sessions grooming the same prefix at once both read the same highest number and both write it. That is not theoretical — it happened three times in a single day during development, and once to the very story filed to fix it. IDs are per-prefix, so the race is per-prefix: you collide only with another session grooming this same project.

5. Create the page with: Name (short, imperative), Story ID, Project relation, Type, Epic, Seq, Estimate, Gating, **Done when**, **Lead time** and **Lead days min**/**max** if Gating is External (calendar days, business days converted; a clock without the numbers is unranked in `/lc:mine`), **Agent can do this**, and **Notes and traps** if you learned something worth not re-learning. If it depends on other stories, set the **Blocked by** relation to their pages — it is a relation, not text, so pass page URLs.
6. Set **Status** to `Ready` if nothing blocks it, `Backlog` otherwise.
7. Report the new story ID and where it lands in the sequence.

Two things to get right rather than fast. **Done when** must be checkable by someone who was not in this conversation — a command that exits 0, a file that contains a value, a screen that shows a thing. Restating the title is not acceptance criteria. And **Agent can do this** must be honest: uncheck it if the task needs a GUI, a login, a payment, a physical device, or a third party, so it lands in `/lc:mine` rather than being offered to a session that cannot do it. That checkbox alone decides it — the `yourTurn` view `/lc:mine` reads filters on nothing else, so a Chore or a Backlog item shows up there exactly like a Launch Blocker. Type answers a different question ("does this block shipping?"); never bend it to make something visible.

Estimates: XS under an hour, S 1-3 hours, M half a day, L 1-2 days, XL 3+ days.
