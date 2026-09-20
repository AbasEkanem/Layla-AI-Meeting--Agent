# Action Item Schema

The `action_items` payload Ivy returns to Layla.

```
{
  items: [
    {
      item_id:            string    // stable within the run, e.g. "ai-01"
      task:               string    // verb-first, <= 120 chars
      owner_claim:        string?   // verbatim, UNTRUSTED
      priority_signal:    string?   // verbatim, UNTRUSTED
      deadline_claim:     string?   // verbatim, UNTRUSTED
      source_segment_ids: [string]  // non-empty
    }
  ]
}
```

## Validation

| Rule | On failure |
|---|---|
| `task` present and non-empty | drop the row |
| `task` starts with a verb | rewrite it verb-first |
| `source_segment_ids` non-empty | drop the row |
| `item_id` unique within the run | re-key |
| No email address in any field | strip it, keep the spoken name |

## Verb-first rewriting

| Heard | `task` |
|---|---|
| "the onboarding emails need updating" | Update the onboarding email sequence |
| "someone should look at the rate limits" | Audit the API rate limits |
| "we need a decision on pricing by Q3" | Decide the Q3 pricing model |

Rewriting the grammar is permitted. Adding scope is not — "look at the rate
limits" does not become "audit and fix the rate limits."

## One row per commitment

| Transcript | Rows |
|---|---|
| "Marcus will audit rate limits and update the docs" | 2 — distinct deliverables |
| "Marcus will draft, review, and ship the migration" | 1 — stages of one deliverable |
| "we should look into caching" *(nobody takes it)* | 1, `owner_claim: null` |
| "great idea, let's park it" | 0 — no commitment |

## Nulls are load-bearing

A `null` means the transcript did not say. It travels downstream as a null:
`owner_claim: null` becomes an unassigned ticket, `priority_signal: null` becomes
Milo's `Medium` default. Filling a null with a plausible guess here is how a
misheard name becomes a real Jira assignment and a real email.
