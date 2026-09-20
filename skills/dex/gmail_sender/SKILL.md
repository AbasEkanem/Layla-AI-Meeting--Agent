---
name: gmail_sender
description: >
  Use when Dex has an approved draft and needs to send it via Gmail.
  Do NOT use without explicit approval; gmail_drafter must have run first.
  Do NOT use to re-send after a partial failure without checking idempotency keys.
---

## Instructions

1. Verify explicit approval from Layla or the user. No approval is a stop, not a delay.
2. Remove the `[DRAFT]` prefix from the subject.
3. Confirm `recipients` is unchanged since approval. A changed list needs re-approval.
4. Check `idempotency_keys.gmail`. A non-null value means this was already sent — stop.
5. Send with BCC to the user.
6. Write the message ID, then return status to Layla.

## Output

```
Email status: SENT | DRAFT | FAILED
To: {recipients.to}
BCC: {recipients.bcc}
Message ID: {id}
Per-recipient: [ { target, status: sent | failed, error? } ]
```

`DRAFT` is a success state — it means drafted and awaiting approval. It is not a
failure and Layla does not treat it as one.

## Hard rules

- Never send without verified approval. Approval for one draft is not approval for a revised one.
- Never send to a recipient list that changed after approval.
- On failure, return the error with recipient and reason. Never retry silently — a duplicate send cannot be recalled.
- Write the message ID before returning. An unrecorded send is a send that will happen twice on the next resume.
- Do not wait for Vera. Report to Layla and stop.
