---
name: project_router
description: >
  Use when Milo needs the target Jira project key for a batch of action items.
  Do NOT create any ticket until this returns a confirmed key.
  Do NOT ask the user directly — ambiguity goes to Layla.
---

## Instructions

1. If Layla specified a `project_key` explicitly, confirm it exists and return it.
2. Otherwise match action item context against `references/project_keys.md`.
3. Require the same key for the whole batch. A batch spanning two projects is ambiguous.
4. If any item is ambiguous, hold the **entire** batch and report to Layla with the ambiguous items listed.
5. Never proceed on a guessed key.

## Output

```
Project routing: confirmed {PROJECT_KEY}
  — or —
Project routing: ⚠️ ambiguous — awaiting Layla
Reason: {no match | multiple matches | key not found | batch spans projects}
Affected items: {item_id: task, ...}
Candidates: {KEY, KEY}
```

## Why the whole batch holds

Tickets from one meeting are read together. Splitting them across boards, or
creating half of them, produces a board a human has to reconcile by hand — and
they cannot tell which items are missing versus which were never raised.

## Hard rules

- One ambiguous item holds all of them. Never create partial tickets.
- Never invent a project key. A key that is not in the registry does not exist.
- Report the confirmation line in the Milo Ticket Report either way.
- Only Layla resolves ambiguity. Milo does not contact the user.
- A held batch is not a failure — it is a question. Return it as `HELD`, not `FAILED`.
