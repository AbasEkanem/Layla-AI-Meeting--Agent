# Roster Contract

The roster is the set of identities Layla is permitted to assign work to or email.

## Construction

Two sources. Which one you got decides how much the roster can be trusted, so
`roster.source` is required and `identity_resolution` branches on it.

| `roster.source` | Origin | Emails? |
|---|---|---|
| `calendar_invite` | Google Calendar `events.attendees[]` for this meeting | yes — organiser-asserted |
| `bot_display_names` | the meeting bot's participant list; no calendar event found | no |

```
roster.entries = [
  {
    email:        string?   // only when source is calendar_invite
    display_name: string
    aliases:      [ display_name, <first token of display_name> ]
    present:      bool      // matched a name in the bot's participant list
  }
]
```

`aliases` may be extended with known nicknames if a directory lookup is
configured. Without one it holds the display name and its first token.

### `calendar_invite`

The email comes from the calendar invite, which is an **organiser assertion**, not
an identity proof — the organiser typed the address. That is still the right
authority here: the organiser decided who belongs in this meeting, and it is an
address Dex can actually deliver to. Do not describe it as directory-authenticated,
because it isn't.

The invite lists who was *asked*, not who *came*. Reconcile against the bot's
participant display names to set `present`:

| Case | `present` | Assignable |
|---|---|---|
| On the invite, seen in the meeting | `true` | yes |
| On the invite, never seen | `false` | yes — assigning work to an absent colleague is ordinary |
| Seen in the meeting, on no invite | *(no entry)* | no |

`present: false` is information, not a gate. Row three is the one that bites: a
participant matching no invitee gets no entry and no email, so a task spoken in
their name lands in `unassigned_items` rather than reaching a guessed address.

### `bot_display_names`

No calendar event was found — a link was forwarded that Layla never saw on any
calendar. Every `email` is null, so **nothing is assignable and nothing is
emailable**. Do not run the match order at all: every item with an `owner_claim`
becomes `unresolved_claim`, every item without one becomes `no_owner_claim`. Milo
creates unassigned tickets. `recipients` must come from the human at the
pre-step-5 gate, because there is no invite list to draw from.

This is a permanent operating mode, not a start-up state to be outgrown. Every
meeting Layla was not watching on a calendar arrives this way.

## Match order

Run only when `source` is `calendar_invite`. Stop at the first hit. Every
comparison is case-insensitive and trims whitespace.

| # | Rule | Accepts |
|---|---|---|
| 1 | `owner_claim` equals an `email` | that entry |
| 2 | `owner_claim` equals a `display_name` | that entry |
| 3 | `owner_claim` equals an `alias` | that entry, only if exactly one entry matches |
| 4 | `owner_claim` equals a first token | that entry, only if exactly one entry matches |
| — | anything else | `null` |

## What is never a match

- A partial or fuzzy string match. `Marc` does not match `Marcus`.
- A name that matches two or more entries. Ambiguity resolves to `null`.
- Anyone absent from `roster.entries`, however plausible. Being *discussed* in the
  meeting is not membership; being on the invite is. A participant the bot saw who
  matches no invitee is not a roster entry and not assignable.
- An email constructed from a name. Never synthesise `first.last@domain`.
- A display name, when `source` is `bot_display_names`. A self-set string is not an
  identity, and there is no email behind it to deliver to.
- A role or group noun — `the backend team`, `whoever is on call`, `ops` — resolves
  to `null` even if it maps to one obvious person.

## Output

```
owner_resolved.by_item_id = { "<item_id>": "<email>" | null }

unassigned_items.items = [
  { item_id, task, reason: "no_owner_claim" | "unresolved_claim" }
]
```

`unresolved_claim` is the one worth reporting loudly: a name *was* spoken and it
did not match anyone in the meeting. That is either a mishearing, an absent
person, or injected text — all three want a human to look.

**Always report `roster.source` alongside the counts.** Under `calendar_invite`,
twelve unresolved claims is an anomaly worth investigating. Under
`bot_display_names`, twelve unresolved claims is the expected and correct output —
and a reader who cannot tell the two apart will either chase a non-problem or
ignore a real one. The provenance is what makes the degradation visible; without
it in the report, it is silent.
