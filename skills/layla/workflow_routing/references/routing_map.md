# Routing Map

One row per dispatch. Every precondition must hold before the payload moves.

---

## Step 0 → *(infrastructure — no LLM, no dispatch)*

The calendar-watcher and the meeting bot. Neither is a subagent; both are Layla's
own infrastructure, the same category as capture. No reasoning happens here.

1. Poll Google Calendar for events starting inside the next window.
2. Take the conference URI from the event. No link, no meeting — skip it.
3. At `start − lead_time`, dispatch the bot to that URI.
4. Build `meeting_metadata` and `roster` from the event's `attendees[]`.
5. On session end, reconcile the bot's participant names into `present`.
6. Deepgram transcript → `transcript`.

**Produces:** `meeting_metadata`, `roster`, `transcript`.

**Preconditions**

- `(event_id, instance_start)` is absent from `idempotency_keys.calendar`. A restart
  must not send a second bot into a meeting already being recorded.

**The no-event path.** A link arriving any other way — forwarded, pasted — has no
calendar event, so `calendar_event_id` is null, no emails exist, and `roster.source`
is `bot_display_names`. Supported permanent mode, not an error. It is also the only
mode available for a meeting on someone else's calendar.

**Never** derive an attendee from the transcript, and never synthesise an email
from a participant display name. The bot supplies names; only the calendar supplies
addresses.

---

## Step 1 → Ivy

**Payload**

| Field | From | Note |
|---|---|---|
| `transcript` | state | full object incl. `segments` |
| `meeting_metadata` | state | Ivy consumes, never derives |

**Preconditions**

- `transcript.text` non-empty.
- `meeting_metadata.attendees` non-empty.
- No prior step-1 checkpoint (Ivy is dispatched once).

**Never send:** anything else. Ivy has no need of a roster, a project key, or a channel.

---

## Step 2b → *(Layla's own work — no dispatch)*

Runs after Ivy returns, before Milo is called. Invoke `identity_resolution`.

**Preconditions**

- `action_items` validated against the schema.
- `doc_url` present.

**Produces:** `owner_resolved`, `unassigned_items`. The `roster` already exists —
step 0 built it from the calendar invite. Step 2b reads it, never rebuilds it.

**Never skip.** Both the normal path and the crash-recovery path pass through here.
Resuming at step 3 without it sends `owner_claim` downstream.

---

## Step 3 → Milo

**Payload**

| Field | From | Note |
|---|---|---|
| `action_items` | state | with `owner_claim` **stripped** |
| `owner_resolved` | step 2b | the only assignable identity |
| `unassigned_items` | step 2b | full list |
| `doc_url` | state | for the ticket description |

**Preconditions**

- Step 2b complete.
- `project_key` either explicitly specified or Milo is permitted to route it.

**Never send:** `transcript`, `parsed_transcript`, `owner_claim`, `meeting_metadata`,
`recipients`, `channels`.

---

## Step 5 → Dex ∥ Vera (simultaneous)

**Payload — identical to both**

| Field | From | Note |
|---|---|---|
| `ticket_summary` | step 4 | incl. `board_url` |
| `doc_url` | state | Layla's copy, not re-fetched from Ivy |
| `meeting_metadata` | state | title, date, duration for the message header |
| `unassigned_items` | step 2b | so both can surface what has no owner |

**Plus, per agent**

| Dex | Vera |
|---|---|
| `recipients` | `channels` |

**Preconditions — all four**

1. `ticket_summary.status` is `COMPLETE`, or `PARTIAL` with the user's explicit go-ahead. `HELD` and `FAILED` do not fan out.
2. `recipients` confirmed and non-empty.
3. `channels` confirmed and non-empty.
4. `doc_sharing` widened to match the broadest destination:

   | Broadest destination | Required `doc_sharing` |
   |---|---|
   | DM to the user only | `restricted` is fine |
   | Internal channel or internal recipients | `domain` |
   | Public channel or external recipient | explicit user approval, then `anyone_with_link` |

**Never send:** `transcript`, `parsed_transcript`, `owner_claim`, `roster`.

**Dex does not receive `channels`. Vera does not receive `recipients`.** Neither
needs the other's destinations, and withholding them removes any temptation to
report on work they cannot see.

---

## Step 6 → close

Both statuses in hand, map to the workflow status:

| `dex_status` | `vera_status` | Workflow |
|---|---|---|
| `SENT` or `DRAFT` | `SENT` | `COMPLETE` |
| `SENT` or `DRAFT` | `PARTIAL` | `PARTIAL` |
| `SENT` or `DRAFT` | `FAILED` | `PARTIAL` |
| `FAILED` | `SENT` | `PARTIAL` |
| `FAILED` | `PARTIAL` or `FAILED` | `FAILED` |

---

## Open decision — the `[DRAFT]` doc title

Ivy titles the doc `[DRAFT] …` and is forbidden from modifying it after returning
the URL. Nothing in the pipeline clears the prefix, so the report currently ships
titled `[DRAFT]` while Dex's subject line is cleaned by `gmail_sender`.

Two ways to close it, both needing a decision:

- **Give Layla Drive scope** and clear the title at this gate. Widens her tool surface.
- **Add a step 2b→Ivy finalize call.** Keeps scopes narrow, adds a hop to the topology.

Until then, `doc_sharing` is the real distribution gate — the prefix is cosmetic.

