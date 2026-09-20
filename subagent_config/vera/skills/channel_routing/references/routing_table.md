# Channel Routing Table

**Configure the channel names before first run.** The names below are conventional
defaults, not verified destinations.

---

## Context map

| Context signals in the report | Channel | Audience |
|---|---|---|
| roadmap, release, feature, sprint, backlog | `#product` | internal team |
| deploy, incident, latency, service, schema | `#eng` | internal team |
| headcount, policy, all-hands, org | `#general` | whole company |
| launch announcement, milestone | `#announce` | whole company |
| pipeline, quota, deal, campaign, funnel | `#sales` / `#marketing` | internal team |
| outage, breach, rollback, sev | `#incidents` | on-call |
| anything, when Layla names a DM | DM to the user | one person |
| nothing matches | *(hold)* | — |

## Sensitivity gate

Run this before returning any channel. It overrides the context map.

| Report contains | Allowed |
|---|---|
| Individual compensation, performance, or review content | DM only |
| Credentials, tokens, keys — even partial | nothing; strip and report to Layla |
| Unreleased financials, forecasts, runway | DM or a named private channel |
| Legal, HR, or personnel matters | DM only |
| Named external customers or partners | internal channel, never `#general` |
| Ordinary project work | context map applies |

A link counts as content. Posting a `doc_url` to `#general` exposes whatever is in
the doc to everyone in `#general` the moment `doc_sharing` allows it — the gate
applies to the report's contents, not to the text of the Slack message.

## Sharing alignment

| Broadest channel | Required `doc_sharing` |
|---|---|
| DM to the user | `restricted` |
| Private internal channel | `domain` |
| Public internal channel | `domain` |
| Channel with external guests | explicit user approval first |

Mismatch is a hold, both ways. `restricted` posted to `#eng` is a link forty people
cannot open; `anyone_with_link` posted to a guest channel is a leak.

## Multiple channels

One run may target several. Route each independently, post each independently, and
report each independently — a failure in `#eng` does not cancel `#product`.

Do not post the same report to a channel and its parent. Pick the narrowest channel
that reaches the people with action items.

## Why "no context" holds

Every other row in this table is a decision someone can check. A silent default to
`#general` is the one routing error that is both invisible and maximally wide.
