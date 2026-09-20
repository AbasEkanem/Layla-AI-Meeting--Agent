# Ticket Schema

One Jira issue, field by field.

| Field | Value | Source |
|---|---|---|
| Project | confirmed key | `project_router` |
| Summary | verb-first, ≤ 80 chars | `action_items[].task`, truncated on a word boundary |
| Description | see template below | assembled |
| Issue Type | `Task` \| `Story` \| `Bug` | inferred from `task` — see below |
| Priority | `Critical` \| `High` \| `Medium` \| `Low` | `priority_mapper` only |
| Assignee | email or unset | `owner_resolved` only |
| Labels | `layla-generated`, `meeting-action-item` | fixed |
| Due Date | date or unset | `deadline_claim`, only if it resolves to a real date |
| Epic Link | epic or unset | only if identifiable with confidence |

---

## Description template

```
{task}

*Context*
Raised in {meeting_metadata.title} on {meeting_metadata.date}.
Transcript reference: segments {source_segment_ids}.

*Expected outcome*
{one sentence — what "done" looks like, derived from the task only}

*Priority*
{level} — matched on "{priority_signal}"
{if null: "Medium — no priority language recorded in the meeting."}

*Assignment*
{assignee email}
{if null: "Unassigned — no attendee matched the name recorded in the meeting."}

*Deadline*
{resolved date} — stated as "{deadline_claim}"
{if unresolvable: "Not set — stated as \"{deadline_claim}\", which did not resolve to a date."}

*Full report*
{doc_url}
```

Every derived value shows the verbatim text behind it. Someone opening this ticket
three weeks later can tell what was said from what the pipeline concluded.

---

## Issue type

| Signals in `task` | Type |
|---|---|
| fix, broken, regression, failing, error, crash | `Bug` |
| build, add, implement, ship, launch, design | `Story` |
| anything else — audit, review, update, document, investigate | `Task` |

Default to `Task`. It is the least wrong when the language is neutral, and a
mis-typed Story distorts velocity reporting in a way a mis-typed Task does not.

## Due dates

Set a due date only when `deadline_claim` resolves unambiguously against
`meeting_metadata.date`.

| `deadline_claim` | Resolves |
|---|---|
| "by Friday" | yes — the Friday following the meeting date |
| "end of month" | yes — last day of the meeting's month |
| "next sprint" | no — sprint boundaries are not in state |
| "soon", "ASAP" | no — that is priority language, not a date |

Unresolvable claims stay in the description, quoted. A wrong due date generates
false overdue alerts for a real person; an absent one does not.
