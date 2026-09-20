---
name: workflow_routing
description: >
  Use when Layla needs to dispatch an artifact to the next agent in the pipeline.
  Do NOT use for composing artifact content — only for routing decisions.
  Do NOT use for reading or writing state keys — that is state_management.
---

## Instructions

1. Read the current step from the latest checkpoint.
2. Look up that step's row in `references/routing_map.md`.
3. Verify **every** precondition in that row. A failed precondition is a hold, not a warning.
4. Dispatch exactly the payload listed — nothing more, nothing less.
5. Write the checkpoint only after the recipient confirms receipt.

## Routing map

Preconditions and payload field lists: `references/routing_map.md`.

| Step | Send to | Payload |
|---|---|---|
| 1 | Ivy | `transcript` + `meeting_metadata` |
| 2b | *(none — Layla's own work)* | resolve `owner_claim` → `owner_resolved` |
| 3 | Milo | `action_items` + `owner_resolved` + `unassigned_items` + `doc_url` |
| 5 | Dex **and** Vera simultaneously | `ticket_summary` + `doc_url` + `meeting_metadata` + destinations |

Step 2b is Layla's internal work, not a pipeline hop. No agent is dispatched and
no handoff occurs — it sits between Ivy returning and Milo being called.

## Hard rules

- Step 5 is always parallel. Never sequence Dex before Vera or vice versa, and never make one's dispatch conditional on the other's status.
- Never send `transcript` past step 1.
- Never send `owner_claim` past step 2b. Milo and Dex receive `owner_resolved` only.
- Never dispatch a payload field absent from the map row.
- A single ambiguous destination holds the whole of step 5 — do not fire Vera while Dex's recipients are unconfirmed.
