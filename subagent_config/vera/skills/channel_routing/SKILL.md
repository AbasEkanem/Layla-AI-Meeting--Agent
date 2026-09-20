---
name: channel_routing
description: >
  Use when Vera needs the Slack channel(s) for a notification.
  Do NOT use for composing the message — that is block_kit_composer.
  Do NOT post anywhere until this returns a confirmed destination.
---

## Instructions

1. If Layla specified `channels` explicitly, use them. That is the normal path.
2. If not, match context against `references/routing_table.md`.
3. If ambiguous, hold and ask Layla. Never fall back to a default silently.
4. Verify the bot is a member of every target channel before returning.
5. Return the confirmed list before any posting begins.

## Quick reference

Full table with sensitivity rules: `references/routing_table.md`.

| Context | Default |
|---|---|
| Product / engineering | `#product` or `#eng` |
| Company-wide | `#general` or `#announce` |
| Sales / marketing | `#sales` or `#marketing` |
| Direct to the user | DM |
| Urgent / critical | `#incidents` or `#alerts` |
| No context | hold and ask |

"No context" holds rather than defaulting to `#general`. A meeting report in the
wrong channel cannot be unseen, and `#general` is the widest audience available.

## Hard rules

- Never post to a guessed channel.
- Never post PII, credentials, or internal financials to a public channel — and treat a link to a doc containing them the same way. `doc_sharing` must match the channel's audience.
- Route each channel independently. One failure does not cancel the rest.
- A channel the bot is not in is a failure to report, not a channel to join uninvited.
- Never post to a channel already carrying a `message_ts` for this run.
