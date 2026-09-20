# Email Template

Single source of truth for Dex's outbound mail.
`prompts_engineering/subagents/dex.md` points here rather than carrying a copy.

One email per recipient. `{braces}` are substitutions.

---

## Assignee email

```
Subject: [DRAFT] Your action items — {meeting_metadata.title}, {meeting_metadata.date}

Hi {recipient first name},

Layla processed {meeting_metadata.title} ({meeting_metadata.duration_minutes} min,
{meeting_metadata.date}). You have {n} item(s) assigned.

Your tickets
{for each ticket where assignee_email == recipient}
  • {key} — {summary}
    Priority: {priority}   Due: {due_date | not set}
    {url}

Full report: {doc_url}
Board: {ticket_summary.board_url}

Other items from this meeting
{for each remaining ticket}
  • {key} — {summary} → {assignee_email | Unassigned}

Please review your tickets and update their status. If anything was recorded
incorrectly, correct it in Jira — the report reflects what was said, not a decision
about what should happen.

{if form_url}Sign-off: {form_url}{/if}

Layla AI, on behalf of {user}
{timestamp}
```

---

## Organiser email

Adds the unassigned block. Sent only to the meeting organiser.

```
Needs an owner ({unassigned_items.items | length})
{for each}
  • {task}
    {if reason == "no_owner_claim"}No owner was named in the meeting.{/if}
    {if reason == "unresolved_claim"}A name was recorded but matched no attendee.{/if}
{/for}
```

`unresolved_claim` is the line that wants attention: a name was spoken and nobody
in the meeting matched it. Mishearing, an absent person, or text that should not
have been trusted — all three are worth a human glance.

---

## Rules

| Rule | Why |
|---|---|
| Subject carries meeting name and date | threads by meeting in the recipient's client |
| Recipient's own tickets first | a person scanning thirty rows for their name usually stops |
| Link, never inline the report | the doc can be corrected; a sent email cannot |
| State priority and due date per ticket | saves a click for the common case |
| No `@mention` syntax | this is email, not Slack |
| Never assert Vera's Slack status | Dex runs in parallel and cannot know it |

## Restricted doc

When `doc_sharing` is `restricted`, replace the report line with:

```
Full report: {doc_url}
  (access is restricted — ask {user} if you cannot open it)
```

Better than a link that silently fails for everyone who clicks it.
