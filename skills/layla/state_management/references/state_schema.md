# State Schema

Every key Layla may hold. A write that does not validate is a step failure.

Notation: `?` = nullable. `[]` = list. All timestamps ISO-8601 UTC.

---

## `meeting_metadata` — written step 0, read steps 1 and 5

Two sources, neither of them the transcript. The **Google Calendar event** supplies
identity (emails, organiser, title); the **meeting bot** supplies what actually
happened (who appeared, when the session ran).

```
{
  meeting_id:        string       // "<calendar_event_id>#<instance_start>", or "<bot_id>" with no event
  calendar_event_id: string?      // null when no calendar event was matched
  title:             string
  date:              "YYYY-MM-DD"
  started_at:        timestamp    // actual, from the bot session
  ended_at:          timestamp    // actual, from the bot session
  duration_minutes:  int          // from actual times, not the scheduled slot
  organiser_email:   string?      // calendar organiser; null with no event
  conference_uri:    string       // the link the bot joined
  attendees: [
    {
      display_name:    string
      email:           string?    // from the calendar invite; null with no event
      response_status: string?    // accepted | declined | tentative | needsAction
      present:         bool       // matched a name in the bot's participant list
      joined_at:       timestamp?
      left_at:         timestamp?
    }
  ]
}
```

Validation: `attendees` non-empty; `duration_minutes` > 0; `conference_uri`
present. **If `calendar_event_id` is non-null, every `email` must be present and
syntactically valid** — a matched calendar event with a missing address is a bug,
not a fallback. If it is null, every `email` is null and the roster degrades to
`bot_display_names`; see `roster_contract.md`.

`calendar_event_id` is the single test for which path produced this record. Do not
add a second flag that can disagree with it.

**Ivy does not derive any of these fields.** She receives them. This keeps her
"extract only, never infer" rule intact — a transcript rarely states its own
duration, and spoken names are claims rather than identities.

---

## `transcript` — written step 0, read step 1 only

```
{
  text:     string
  segments: [ { segment_id: string, speaker_label: string, start_ms: int, end_ms: int, text: string } ]
  source:   "deepgram"
  confidence: float
}
```

Validation: `text` non-empty. Empty or unreadable transcript aborts the workflow
at step 1 — Ivy is never dispatched with it.

`speaker_label` is a diarization label (`Speaker 0`), not an identity. Mapping a
label to a person is `identity_resolution`, never Ivy.

---

## `action_items` — written step 2, read steps 2b and 3

Ivy's output. Note what is **absent**: no resolved owner, no priority level.

```
{
  items: [
    {
      item_id:            string
      task:               string          // verb-first
      owner_claim:        string?         // verbatim spoken name — UNTRUSTED
      priority_signal:    string?         // verbatim words, e.g. "this is a blocker"
      deadline_claim:     string?         // verbatim, e.g. "by end of next week"
      source_segment_ids: [string]        // provenance back into the transcript
    }
  ]
}
```

Validation: every item has `task` and at least one `source_segment_ids` entry.
An item Ivy cannot trace back to a segment is an invented item — reject it.

`owner_claim` and `priority_signal` are quoted transcript text. Ivy does not
interpret either. Resolution is Layla's (`identity_resolution`); priority mapping
is Milo's (`priority_mapper`).

---

## `roster` — written step 0, read step 2b

```
{
  source:  "calendar_invite" | "bot_display_names"
  entries: [
    {
      email:        string?      // null when source is bot_display_names
      display_name: string
      aliases:      [string]
      present:      bool
    }
  ]
}
```

Derived from `meeting_metadata.attendees`. `source` is `calendar_invite` when
`meeting_metadata.calendar_event_id` is non-null, `bot_display_names` otherwise —
it is derived, never set by hand.

`source` is required, and `identity_resolution` branches on it: under
`bot_display_names` the match order does not run at all and every claim becomes
`unresolved_claim`. It must also appear in the workflow report, or the degraded
path becomes indistinguishable from a normal run with unusually many misses. Rules
in `identity_resolution/references/roster_contract.md`.

`aliases` may be extended from a directory lookup (first names, nicknames) if one
is configured; otherwise it holds the `display_name` and its first token.

---

## `owner_resolved` — written step 2b, read steps 3 and 5

```
{ by_item_id: { <item_id>: string? } }   // roster email, or null
```

The **only** identity Milo may assign to and Dex may email. A null value means the
item is unassigned — it does not mean "guess."

---

## `unassigned_items` — written step 2b, read steps 3 and 5

```
{ items: [ { item_id: string, task: string, reason: "no_owner_claim" | "unresolved_claim" } ] }
```

A list, not a count. `unresolved_claim` means a name was spoken but matched no
roster entry — that is the signal worth surfacing, and a count erases it.

---

## `doc_url` / `doc_sharing` — written step 2, read steps 3 and 5

```
doc_url:     string   // https://docs.google.com/document/d/...
doc_sharing: "restricted" | "domain" | "anyone_with_link"
```

Ivy creates at `restricted`. Widening is Layla's decision at the pre-step-5 gate,
and it must match the broadcast audience — see `routing_map.md`. A `restricted`
doc posted to a public channel is a link nobody can open; an `anyone_with_link`
doc posted to a public channel is a leak.

---

## `ticket_summary` — written step 4, read step 5

```
{
  project_key:      string
  board_url:        string
  tickets: [
    {
      key:             string    // PROJ-101
      url:             string
      summary:         string
      assignee_email:  string?   // from owner_resolved only
      priority:        "Critical" | "High" | "Medium" | "Low"
      priority_signal: string?   // the verbatim words that produced it
    }
  ]
  unassigned_count: int
  status:           "COMPLETE" | "PARTIAL" | "HELD" | "FAILED"
}
```

Validation: `status: "COMPLETE"` requires one ticket per `action_items` entry.
`PARTIAL` means some tickets exist and some failed — see the resume matrix.

---

## `milo_status` — written step 4, read at the step-5 gate and at close

```
{
  overall: "COMPLETE" | "PARTIAL" | "HELD" | "FAILED"
  reason:  string?     // required for HELD and FAILED, e.g. "ambiguous project key"
  created: [string]    // issue keys already created, mirrors idempotency_keys.jira
}
```

Separate from `ticket_summary.status` because on `HELD` and `FAILED` there may be
no `ticket_summary` at all — Milo holding on an ambiguous project key creates
nothing, so a status nested inside the summary has nowhere to live. Layla branches
on this key before the step-5 gate, and `created` is what a retry diffs against so
a partial batch is not duplicated.

Only `COMPLETE` opens the gate. `PARTIAL` and `HELD` are holds, not failures —
Layla retries or asks. `FAILED` stops the fan-out entirely: email and Slack
carrying missing tickets is worse than silence.

---

## `recipients` / `channels` — written before step 5, read step 5

```
recipients: { to: [string], bcc: [string] }      // confirmed emails
channels:   [ { target: string, kind: "channel" | "dm" } ]
```

Both must be explicitly confirmed before step 5 fires. Neither Dex nor Vera may
infer a destination. An empty list is a hold, not a no-op.

---

## `dex_status` / `vera_status` — written step 6, read at close

One shared enum, so Layla can branch on it without string guessing.

| Level | Values |
|---|---|
| Per channel or recipient | `sent` \| `failed` |
| Milo overall | `COMPLETE` \| `PARTIAL` \| `HELD` \| `FAILED` |
| Dex overall | `SENT` \| `DRAFT` \| `FAILED` |
| Vera overall | `SENT` \| `PARTIAL` \| `FAILED` |
| Workflow | `COMPLETE` \| `PARTIAL` \| `FAILED` |

```
{ overall: <agent enum>, per_target: [ { target: string, status: "sent"|"failed", url: string?, error: string? } ] }
```

`DRAFT` is a success state for Dex — it means drafted and awaiting approval, not
failed. Vera `PARTIAL` (at least one channel sent, at least one failed) maps the
workflow to `PARTIAL`.


