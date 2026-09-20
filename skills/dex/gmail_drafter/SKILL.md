---
name: gmail_drafter
description: >
  Use when Dex needs to compose the meeting summary email before sending.
  Do NOT send — that is gmail_sender. Always draft first.
  Do NOT infer a recipient; an unconfirmed list is a hold.
---

## Instructions

1. Receive `ticket_summary`, `doc_url`, `meeting_metadata`, `unassigned_items`, and `recipients` from Layla — never from Milo or Ivy directly.
2. If `recipients` is absent or empty, hold and request it from Layla. Do not draft to a guessed list.
3. Render `references/email_template.md`.
4. Prefix the subject with `[DRAFT]`.
5. BCC the user.
6. Return the draft for approval. Do not send.

## Per-recipient scoping

Each assignee sees their own tickets first, then the rest as context. Send one
draft per recipient rather than one draft to everyone — a person who has to find
their name in a list of thirty rows usually does not.

`unassigned_items` goes to the meeting organiser, not to every recipient.

## Hard rules

- Never send. `gmail_sender` sends, and only on explicit approval from Layla or the user.
- Always BCC the user.
- Link to the report. Never inline the full content — the doc is the source of truth and it can be corrected after the fact; an email cannot.
- Address recipients from `recipients` only. Never from `owner_claim`, and never an address assembled from a display name.
- If `doc_sharing` is `restricted`, say so in the body rather than linking silently to something the recipient cannot open.
- Do not wait for Vera. Report to Layla and stop.
