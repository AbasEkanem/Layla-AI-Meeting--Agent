# Priority Table

The only signal-to-priority mapping in the pipeline.

Match case-insensitively against `priority_signal`. Substring match on the phrase,
whole-word match on single words.

---

## Critical

| Signal | |
|---|---|
| urgent | critical |
| ASAP | blocker |
| blocking | blocked on |
| on fire | drop everything |
| right now | before anything else |

## High

| Signal | |
|---|---|
| important | high priority |
| needed | must |
| has to | have to |
| top of the list | priority |
| this sprint | before the release |

## Medium

| Signal | |
|---|---|
| should | recommended |
| soon | plan to |
| want to | would like |
| next sprint | fairly soon |

## Low

| Signal | |
|---|---|
| consider | optional |
| nice to have | explore |
| eventually | at some point |
| if there's time | backlog |
| park it | someday |

---

## Conflict resolution

Strongest wins. `Critical > High > Medium > Low`.

| `priority_signal` | Level | Why |
|---|---|---|
| "important but not urgent" | High | `important` beats the absence of `urgent` |
| "urgent, or at least soon" | Critical | `urgent` outranks `soon` |
| "nice to have, but needed for launch" | High | `needed` outranks `nice to have` |

Negation is **not** parsed. "Not urgent" contains `urgent` and would map to
Critical, which is wrong — so Ivy's extraction rule is to quote the signal phrase,
not the surrounding clause. If a `priority_signal` arrives with a negation in it,
return `Medium` and note the ambiguity in the ticket description.

## No match

`null`, an empty string, or a phrase matching no row returns `Medium` with
`priority_signal` preserved verbatim in the description so a human can regrade.

Never return `Critical` on a guess. An inbox of Critical tickets is an inbox with
no priorities at all, and every level here ends up in front of a real person.

## Extending the table

Add signals as rows, not as judgement in the skill body. A word not in this table
does not map — that is the design, and it keeps the mapping auditable.
