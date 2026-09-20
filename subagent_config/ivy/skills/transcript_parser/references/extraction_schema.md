# Extraction Schema

`parsed_transcript`, Ivy's step-2 intermediate. Every field traces to segments.

```
{
  topics: [
    { title: string, summary: string, source_segment_ids: [string] }
  ],
  decisions: [
    { statement: string, source_segment_ids: [string] }
  ],
  action_items: [
    {
      item_id:            string
      task:               string
      owner_claim:        string?
      priority_signal:    string?
      deadline_claim:     string?
      source_segment_ids: [string]
    }
  ],
  open_questions: [
    { question: string, raised_by_claim: string?, source_segment_ids: [string] }
  ],
  blockers: [
    { description: string, source_segment_ids: [string] }
  ],
  next_meeting_claim: string?
}
```

## Category boundaries

| Category | Is | Is not |
|---|---|---|
| `topics` | what was discussed | what was decided |
| `decisions` | a settled, declarative outcome | a proposal, a preference, or an option raised |
| `action_items` | a commitment to do something | an idea nobody took on |
| `open_questions` | asked and left unanswered | asked and answered in the same meeting |
| `blockers` | something stated as preventing progress | something merely described as difficult |

When a statement fits two categories, place it in the more specific one and do not
duplicate it. "We decided Marcus will audit the rate limits" is one decision *and*
one action item — those are genuinely two records, and both are kept.

## Verbatim fields

`owner_claim`, `priority_signal`, `deadline_claim`, `raised_by_claim`, and
`next_meeting_claim` are quoted source text. Copy the words that appeared.

| Transcript | `priority_signal` |
|---|---|
| "honestly this is a blocker for the release" | `"this is a blocker"` |
| "would be nice to have eventually" | `"nice to have"` |
| "let's get to it at some point" | `null` |

Trim to the signal phrase; do not paraphrase it, and do not extend it into a
judgement. `null` where no signal language appears — Milo defaults those.

## Provenance

`source_segment_ids` references `transcript.segments[].segment_id`. It is the
audit trail from a Jira ticket back to the sentence that caused it, and it is what
lets a human check whether an odd action item was actually said.

An extraction that cannot name a segment is not an extraction. Drop it.
