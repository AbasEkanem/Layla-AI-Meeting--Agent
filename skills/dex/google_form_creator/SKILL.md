---
name: google_form_creator
description: >
  Use when Dex needs a Google Form for sign-off, acknowledgement, or feedback.
  Do NOT use by default — only on an explicit collection need from Layla or the user.
  Do NOT block the email on form failure.
---

## Instructions

1. Confirm an explicit collection need. No stated need returns `SKIPPED` immediately.
2. Pick the question set from `references/form_templates.md` by collection type.
3. Title it `{meeting_metadata.title} — {purpose} {meeting_metadata.date}`.
4. Set the response destination — Google Sheets for anything with more than three questions, email notification otherwise.
5. Restrict responses to `recipients` where the form asks who someone is.
6. Return the form URL for inclusion in the email, or `SKIPPED`.

## Failure is not fatal

A form that fails to create is flagged and skipped. The email still goes out — the
tickets and the report are the payload, and the form is an optional attachment to
them.

## Hard rules

- Never create speculatively. "Might be useful" is not a collection need.
- Return `SKIPPED` when the purpose is unclear, and say why.
- Report the form's state in the Dex Completion Report whether `ACTIVE` or `SKIPPED`.
- Never collect a field the meeting did not call for. A sign-off form asking for a phone number is a form nobody completes.
- Never make a form the only path to a ticket. Everything it asks must also be doable in Jira.
