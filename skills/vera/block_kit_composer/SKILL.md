---
name: block_kit_composer
description: >
  Use when Vera needs to build a structured Slack message with Block Kit.
  Do NOT use for channel selection — that is channel_routing.
  Do NOT use for DMs — Block Kit is for channel posts; DMs go as plain text.
---

## Instructions

1. Receive `ticket_summary`, `doc_url`, `meeting_metadata`, and `unassigned_items` from Layla.
2. Build the blocks per `references/block_kit_template.md`.
3. Include a timestamp in every automated post.
4. `@mention` only people with an assigned ticket in this run.
5. Hand off to `thread_manager` when the ticket list exceeds five rows.

## What Vera cannot say

Vera and Dex run in parallel. Vera does not know whether the email was sent,
drafted, or failed at the moment she posts, so the template says the digest is
"being sent by Dex in parallel" and never asserts a status.

The same applies in reverse: nothing in this message reports on Dex's outcome, and
Layla — holding both statuses at step 6 — is the only one who can.

## Hard rules

- Bold key labels. Bullet action items. Never a wall of text.
- Always close with the `_Layla AI | {timestamp}_` footer.
- `@mention` only actionable assignees. Never `@here`, never `@channel`, never a passive tag for visibility.
- Use `:white_check_mark:` for success and `:x:` for failure. Nothing else carries status.
- Never state Dex's email status, or any other agent's.
- Never inline ticket descriptions. Link, so a correction in Jira is not contradicted by a frozen Slack post.
