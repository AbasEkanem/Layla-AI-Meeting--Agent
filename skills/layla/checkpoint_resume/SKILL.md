---
name: checkpoint_resume
description: >
  Use when the pipeline must survive a crash and resume without re-running
  completed steps or re-sending anything already delivered.
  Do NOT use for normal step transitions — only for restart and recovery.
---

## Instructions

1. After each step confirms completion, write `{ step, state_snapshot, timestamp, idempotency_keys }`.
2. On restart, read the last checkpoint and look up its row in `references/resume_matrix.md`.
3. Resume at the step that row names — not the step that was in flight.
4. Before re-running any outbound step, check its idempotency key against what was already delivered.

## Checkpoint granularity

Checkpoint on **confirmation**, not dispatch. A checkpoint at step 3 means Milo
confirmed receipt; it does not mean he finished. Recovery therefore keys off the
last *confirmed* step, and a step whose confirmation never arrived is re-run.

| Confirmed | Resume at |
|---|---|
| 0 | step 1 — dispatch Ivy |
| 2 | step 2b — resolve identities, then step 3 |
| 2b | step 3 — dispatch Milo |
| 4 | step 5 — fan out |
| 5, one side failed | retry that side only |
| 5, both failed | step 5 — retry both |

Partial and ambiguous cases, including partial Jira and partial Slack:
`references/resume_matrix.md`.

## Hard rules

- Never re-run step 0. Meeting capture is terminal on failure — abort and report.
- Never re-run a step that already confirmed success.
- Resuming from a step-2 checkpoint always re-runs step 2b. Skipping it sends `owner_claim` downstream.
- Never re-send an email or re-post to Slack without checking the idempotency key. A duplicate broadcast is worse than a late one.
- If no checkpoint exists, start from step 0.
