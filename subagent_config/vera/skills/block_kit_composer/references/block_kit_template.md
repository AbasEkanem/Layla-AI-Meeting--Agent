# Block Kit Template

Single source of truth for Vera's Slack posts.
`prompts_engineering/subagents/vera.md` points here rather than carrying a copy.

---

## Channel post — five or fewer tickets

```
:rocket: *Meeting processed* — {meeting_metadata.title}

:memo: *Report:* <{doc_url}|View report>
:ticket: *Tickets:* {n} created — <{board_url}|View board>
:email: *Email digest:* being sent by Dex in parallel

*Summary*
{2–3 sentences from the report's executive summary}

*Action items*
• <{ticket.url}|{ticket.key}> {ticket.summary} — <@{assignee}> · {priority}
• <{ticket.url}|{ticket.key}> {ticket.summary} — _unassigned_ · {priority}

{if unassigned_items}
:warning: *{n} item(s) need an owner* — see the report
{/if}

_Layla AI | {timestamp}_
```

## Channel post — more than five tickets

Summary only. Full list goes to the thread via `thread_manager`.

```
:rocket: *Meeting processed* — {meeting_metadata.title}

:memo: *Report:* <{doc_url}|View report>
:ticket: *Tickets:* {n} created across {m} assignee(s) — <{board_url}|View board>
:email: *Email digest:* being sent by Dex in parallel

*Summary*
{2–3 sentences}

*Highest priority*
• <{url}|{key}> {summary} — <@{assignee}> · Critical

{if unassigned_items}:warning: *{n} item(s) need an owner*{/if}

:thread: Full details in thread

_Layla AI | {timestamp}_
```

## DM — plain text, no Block Kit

```
{meeting_metadata.title} — {meeting_metadata.date}

You have {n} ticket(s):
• {key} {summary} — {priority} — {url}

Report: {doc_url}
Board: {board_url}

Layla AI | {timestamp}
```

---

## Rules

| Rule | Why |
|---|---|
| Never assert Dex's status | Vera posts in parallel and cannot know it |
| `@mention` only assignees in this run | a tag is an interrupt; spend them on people with work |
| No `@here` / `@channel` | never warranted by an automated summary |
| Link tickets, never inline descriptions | Jira stays correctable; a Slack post does not |
| Footer timestamp on every post | tells a reader whether they are looking at today's run |
| Unassigned count surfaced, never hidden | it is the one thing needing a human |
| `:white_check_mark:` / `:x:` only for status | any other emoji is decoration |

## Priority display

Show `Critical` and `High` inline. `Medium` and `Low` are omitted from the channel
post and kept in the thread — the channel post's job is to show what needs
attention now, and four levels on every row makes none of them stand out.

## Empty runs

Zero tickets still posts. The report exists and people were in the meeting.

```
:memo: *Meeting processed* — {meeting_metadata.title}
No action items were recorded. <{doc_url}|View report>
_Layla AI | {timestamp}_
```

Silence would read as the pipeline having failed.
