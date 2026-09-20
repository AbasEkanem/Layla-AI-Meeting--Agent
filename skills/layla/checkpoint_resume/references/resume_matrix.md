# Resume Matrix

## Checkpoint record

```
{
  step:             0 | 2 | "2b" | 4 | 5 | 6
  state_snapshot:   <all keys valid at that step>
  timestamp:        ISO-8601
  idempotency_keys: {
    jira:  { "<item_id>": "<issue_key>" }     // written as each ticket lands
    gmail: "<message_id>" | null
    slack: { "<channel>": "<message_ts>" }    // written as each post lands
  }
}
```

Idempotency keys are written **incrementally**, as each side effect completes —
not in a batch at the end. That is what makes a mid-fan-out crash recoverable.

---

## Full matrix

| Last confirmed | In-flight when it died | Resume at | Re-runs |
|---|---|---|---|
| *(none)* | — | step 0 | everything |
| *(none)* | bot dispatched, meeting still live | poll the bot, then step 1 | nothing — see below |
| 0 | step 1 dispatch | step 1 | Ivy |
| 0 | Ivy mid-work | step 1 | Ivy — she has no side effects to undo |
| 2 | step 2b | step 2b | identity resolution, then step 3 |
| 2b | step 3 dispatch | step 3 | Milo |
| 2b | Milo mid-work | step 3, skipping created tickets | see partial-Jira below |
| 4 | step 5 dispatch | step 5 | both sides |
| 4 | Dex mid-work | step 5 | Dex only if `gmail` key is null |
| 4 | Vera mid-work | step 5 | Vera, skipping channels in `slack` keys |
| 5 | Dex failed only | retry Dex | Dex only |
| 5 | Vera failed only | retry Vera | Vera only |
| 5 | both failed | step 5 | both |
| 6 | close | nothing | report from state |

---

## Partial Jira

Milo returning an error after creating some tickets is the most likely partial.
`milo_status.overall` becomes `PARTIAL`, and both `milo_status.created` and
`idempotency_keys.jira` hold what already exists. On a `HELD` or `FAILED` there may
be no `ticket_summary` at all — branch on `milo_status`, which always exists.

1. Re-dispatch step 3 with only the `item_id`s absent from `idempotency_keys.jira`.
2. Merge the new tickets into the existing `ticket_summary`.
3. If the retry fails again, set `status: PARTIAL` and **ask the user** whether to
   fan out with an incomplete ticket set.

Never re-create a ticket that has a key. Duplicate Jira issues assigned to real
people are cleanup work for a human.

---

## Partial Slack

Vera posting to three channels and failing on the second leaves two live posts.

1. Re-dispatch Vera with only the channels absent from `idempotency_keys.slack`.
2. `vera_status.overall` is `PARTIAL` until every confirmed channel has a `message_ts`.

Never re-post to a channel that has a `message_ts`.

---

## Step 0 — partly resumable

Split it in two.

The **calendar poll is idempotent**. `idempotency_keys.calendar` holds
`(event_id, instance_start)` for every meeting already dispatched, so a watcher
restart re-reads the calendar and sends no second bot into a meeting already being
recorded.

The **bot session is not resumable**. If a recording is interrupted, the audio for
that window is gone — a bot rejoining mid-meeting captures the remainder, not the
start. Report `FAILED` for that meeting and say plainly that no transcript, or only
a partial one, was obtained. A resumed workflow that silently produces a report
from half a meeting is worse than a clear failure.

But check before declaring loss. The bot runs out of process, so a harness crash
usually leaves the recording intact and only the webhook receiver missing. On
restart, poll the bot for sessions whose transcript completed while the harness was
down, and resume those at step 1.
