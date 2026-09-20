---
name: google_doc_creator
description: >
  Use when Ivy needs to create and share the structured meeting report as a Google Doc.
  Do NOT use for emailing or posting the report — that is Dex and Vera.
  Do NOT widen sharing beyond restricted; only Layla decides the audience.
---

## Instructions

1. Title the doc `[DRAFT] {meeting_metadata.title} — Report {meeting_metadata.date}`.
2. Render the template in `references/report_template.md`, section by section.
3. Populate the header from `meeting_metadata` — never from the transcript.
4. Show `owner_claim` and `priority_signal` verbatim in the action item table.
5. Create at sharing `restricted`. Return `doc_url` and `doc_sharing` to Layla.

## Sharing

Ivy always creates at `restricted`. Widening happens at Layla's pre-step-5 gate,
matched to the broadcast audience — a `restricted` doc posted to a channel is a
dead link, and an `anyone_with_link` doc posted to a public channel is a leak.
Ivy does not know the audience at step 2, so she does not choose.

## Hard rules

- Keep the `[DRAFT]` prefix. Ivy never removes it.
- Do not email, post, or share the doc. Return the URL to Layla only.
- Do not modify the doc after returning the URL unless Layla instructs.
- Executive Summary is 3–5 sentences, facts only — no opinion, no recommendation, no assessment of how the meeting went.
- Every action item row carries its source segment reference. The doc is the audit trail.
- Unassigned items appear in the table as `Unassigned`, never omitted and never filled with a plausible name.
