---
name: thread_manager
description: >
  Use when Vera's ticket list exceeds five rows or carries a full action item table.
  Do NOT use for short messages — those post directly via block_kit_composer.
  Do NOT put in a thread anything barred from the channel itself.
---

## Instructions

1. Post the summary variant from `block_kit_composer` to the channel — five rows maximum, highest priority first.
2. Include `:thread: Full details in thread` at the bottom of the channel post.
3. Reply in-thread with the full list: every ticket, every assignee, every unassigned item.
4. Return both URLs — channel post and thread reply — to `status_reporter`.

## Split

| Channel post | Thread reply |
|---|---|
| Ticket count, report link, board link | Every ticket with key, summary, assignee, priority |
| Executive summary, 2–3 sentences | Full unassigned list with reasons |
| Critical and High items only | Medium and Low items |
| Unassigned count | Open questions and blockers from the report |

## Hard rules

- The channel post must stand alone. Someone who never opens the thread should still know a meeting was processed, how many tickets exist, and where the report is.
- The thread is supplementary, never load-bearing. Nothing actionable appears only in the thread.
- Sensitivity rules apply identically in a thread. A thread in a public channel is public, so the same gate holds: no compensation, credentials, unreleased financials, or personnel matters, and no link to a doc containing them.
- Return both URLs separately. A single URL leaves Layla unable to report where the detail went.
- One thread per channel post. Never chain a second reply as an afterthought.
