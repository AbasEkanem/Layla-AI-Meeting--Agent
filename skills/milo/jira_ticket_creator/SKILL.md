---
name: jira_ticket_creator
description: >
  Use when Milo needs to convert one action item into a Jira issue.
  Do NOT use to modify an existing ticket — create only.
  Do NOT use before project_router has confirmed the key, or before priority_mapper has run.
---

## Instructions

1. Receive one action item from Layla: `task`, `priority_signal`, `deadline_claim`, `doc_url`, and the item's `owner_resolved` value.
2. Confirm the project key via `project_router`. Stop if it is not confirmed.
3. Get the level from `priority_mapper` — the item arrives with a *signal*, never with a level.
4. Build the issue per `references/ticket_schema.md`.
5. Create it, then record `{item_id: issue_key}` before moving to the next item.
6. Return key, URL, assignee, and priority into `ticket_summary`.

## Assignment

Assign only from `owner_resolved` — an authenticated email Layla matched against
the meeting's attendee list. A `null` creates an unassigned ticket.

`owner_claim` never reaches this skill. If a raw spoken name appears in the input,
that is a routing bug: stop and report it to Layla rather than assigning.

## Hard rules

- One ticket per action item. Never bundle, never split.
- Always include `doc_url` in the description.
- Never create without a confirmed project key.
- Never create for an item already in `idempotency_keys.jira` — that is a re-run, and duplicate tickets assigned to real people are cleanup a human has to do.
- Never assign to an email that is not in `owner_resolved`, however obvious the match seems.
- Record each key as it lands, not in a batch at the end. A crash mid-batch must be recoverable.
