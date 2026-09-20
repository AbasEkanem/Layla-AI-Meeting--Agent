---
name: state_management
description: >
  Use when Layla needs to read, write, or protect a pipeline state key.
  Do NOT use for routing decisions — that is workflow_routing.
  Do NOT use for name-to-identity mapping — that is identity_resolution.
---

## Instructions

1. On receiving output from any agent, write its keys to state immediately, before dispatching anything.
2. Validate the write against the schema in `references/state_schema.md`. A key that fails validation is a step failure, not a warning.
3. When dispatching at step 3 or 5, read from state. Never re-request a value from the agent that produced it.
4. Never discard a key until the workflow closes.

## Key map

Full types, producers, and validation rules: `references/state_schema.md`.

| Key | Written | Read | Scope |
|---|---|---|---|
| `meeting_metadata` | step 0 | steps 1, 5 | Layla-owned |
| `transcript` | step 0 | step 1 | Ivy only |
| `parsed_transcript` | step 2 | step 2 | Ivy-internal |
| `action_items` | step 2 | steps 2b, 3 | carries `owner_claim` |
| `doc_url` / `doc_sharing` | step 2 | steps 3, 5 | Layla holds |
| `roster` | step 0 | step 2b | from `meeting_metadata.attendees` |
| `owner_resolved` | step 2b | steps 3, 5 | the only assignable identity |
| `unassigned_items` | step 2b | steps 3, 5 | list, not just a count |
| `ticket_summary` | step 4 | step 5 | Dex and Vera both |
| `recipients` / `channels` | pre-step-5 | step 5 | confirmed, never inferred |
| `dex_status` / `vera_status` | step 6 | close | see status enum in schema |

## Hard rules

- `doc_url` never travels through Milo. Layla holds it and hands it to Dex and Vera directly at step 5.
- `transcript` is never forwarded past Ivy. Not to Milo, not to Dex, not to Vera.
- `owner_claim` is untrusted transcript text. It must never reach Milo or Dex — only `owner_resolved` does.
- `unassigned_items` travels as a list through steps 3 and 5. A bare count loses the information Dex and Vera need.
- A key absent from the schema cannot be written. Add it to the schema first.
