---
name: action_item_extractor
description: >
  Use when Ivy needs to turn parsed transcript data into the structured action
  item table Layla routes to Milo.
  Do NOT use before transcript_parser has run — this consumes parser output, not raw text.
  Do NOT assign a priority level or resolve an owner.
---

## Instructions

1. Receive `parsed_transcript` from `transcript_parser`.
2. Emit one row per distinct commitment, per `references/action_item_schema.md`.
3. Write `task` verb-first — "Update onboarding email sequence", not "Onboarding email sequence update".
4. Copy `owner_claim`, `priority_signal`, and `deadline_claim` **verbatim** from the transcript, or `null` if absent.
5. Carry `source_segment_ids` on every row.
6. Return the table to Layla alongside `doc_url`.

## Output

| # | Task | Owner claim | Priority signal | Deadline claim |
|---|---|---|---|---|
| 1 | Audit API rate limits | "Marcus" | "this is a blocker" | "by Friday" |
| 2 | Refresh the pricing deck | `null` | "nice to have" | `null` |

Quoted columns are unresolved transcript text. `owner_claim` becomes an assignee
only after Layla's `identity_resolution`; `priority_signal` becomes a level only
after Milo's `priority_mapper`.

## Hard rules

- One row per distinct commitment. Never bundle unrelated tasks; never split one task into stages.
- A row with no `source_segment_ids` is invalid — drop it rather than ship it.
- Never write an email address. Never grade urgency. Never fill a null with a guess.
- Return to Layla only. Do not pass directly to Milo.
