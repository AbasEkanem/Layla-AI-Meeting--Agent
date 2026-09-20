---
name: status_reporter
description: >
  Use when Vera has finished every posting attempt and needs to report to Layla.
  Do NOT wait for Dex — report as soon as Vera's own attempts complete.
  Do NOT report before every confirmed channel has been attempted.
---

## Instructions

1. Collect every posting attempt: target, kind, status, URL or error.
2. Write each `message_ts` into `idempotency_keys.slack` as it lands, not in a batch.
3. Compute `overall` from the table below.
4. Return the report to Layla.

## Status enum

Two levels. Layla branches on `overall`, so the casing matters.

| Level | Values |
|---|---|
| Per target | `sent` \| `failed` |
| Vera overall | `SENT` \| `PARTIAL` \| `FAILED` |

| Condition | `overall` |
|---|---|
| Every confirmed channel sent | `SENT` |
| At least one sent, at least one failed | `PARTIAL` |
| Every channel failed | `FAILED` |
| No channel was confirmed | `FAILED` — nothing was attempted |

## Output

```
## Vera Notification Report

| # | Target | Kind | Status | Link / Error |
|---|---|---|---|---|
| 1 | #eng | channel post | sent | {url} |
| 2 | #eng | thread reply | sent | {url} |
| 3 | @user | dm | failed | not_in_channel |

Overall: PARTIAL
Attempted: 3   Sent: 2   Failed: 1

_Layla AI | {timestamp}_
```

## Hard rules

- Report every attempt — successes and failures both. A report listing only successes is not a status.
- Failures carry the Slack error verbatim (`not_in_channel`, `channel_not_found`, `ratelimited`). "Failed" alone tells Layla nothing she can act on.
- Never report on Dex, or wait for him. Layla holds both statuses at step 6; Vera holds one.
- `PARTIAL` is a real outcome, not a rounding of `SENT`. Layla maps it to a `PARTIAL` workflow.
- Return immediately once Vera's attempts finish, even if Dex is still working.
