---
name: priority_mapper
description: >
  Use when Milo needs a Jira priority level for an action item.
  This is the ONLY place a priority level is assigned anywhere in the pipeline.
  Do NOT use for routing or ticket creation. Do NOT re-map an already-mapped level.
---

## Instructions

1. Read `priority_signal` — the verbatim words Ivy quoted from the transcript.
2. Match it against the table in `references/priority_table.md`.
3. Return the mapped level plus the matched signal word, for traceability.
4. If two signals conflict, take the stronger one.
5. If `priority_signal` is `null` or matches nothing, return `Medium`.

## Quick reference

Authoritative table with match rules and edge cases: `references/priority_table.md`.

| Signal words | Jira priority |
|---|---|
| urgent, critical, ASAP, blocker, blocking, on fire | Critical |
| important, high priority, needed, must, has to | High |
| should, recommended, soon, plan to, want to | Medium |
| consider, optional, nice to have, explore, eventually | Low |
| *(null or no match)* | Medium |

## Sole ownership

Ivy quotes the language. Milo maps it. Nobody else grades urgency, and the level
is computed exactly once per item — so the doc and the ticket can never disagree,
because the doc shows words and the ticket shows a level derived from them.

## Hard rules

- Write the matched signal word into the ticket description. A `Critical` nobody can trace is a `Critical` nobody trusts.
- Never adjust a level on judgement, seniority of the speaker, or how the meeting felt. The table is the whole authority.
- Never upgrade on volume — a signal repeated five times is the same signal.
- `null` means the transcript was silent. `Medium` is the default for silence, not an inference about the work.
