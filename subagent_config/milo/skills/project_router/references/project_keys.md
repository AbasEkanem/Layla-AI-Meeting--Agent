# Project Key Registry

**Configure this before first run.** The keys below are placeholders — Milo may
only route to keys that actually exist in the connected Jira instance.

A key absent from this file does not exist. Milo never invents one.

---

## Registry

| Key | Board | Scope | Context signals |
|---|---|---|---|
| `PROJ` | *(set me)* | default catch-all | anything unmatched, when a default is configured |
| `INFRA` | *(set me)* | deploys, environments, CI | deploy, pipeline, staging, prod, rollback, runner |
| `API` | *(set me)* | backend services | endpoint, rate limit, schema, service, latency |
| `WEB` | *(set me)* | frontend | page, UI, component, layout, accessibility |
| `DATA` | *(set me)* | pipelines, warehouse | ETL, warehouse, migration, report, dashboard |
| `SEC` | *(set me)* | security, access | credential, permission, audit, vulnerability, key rotation |

Delete the rows that do not apply. An unconfigured row that matches on a keyword
is worse than no row — it routes real tickets to a board nobody watches.

## Default behaviour

| Config | Unmatched item |
|---|---|
| A default key is set | route the batch there |
| No default key | ambiguous — hold and ask Layla |

Set a default only if there is a board someone actually triages. Routing to an
unwatched board loses the ticket more quietly than holding does.

## Matching

1. Explicit key from Layla — always wins, no matching.
2. All items match one key — use it.
3. Items match two or more keys — ambiguous, hold the batch, list the candidates.
4. Nothing matches — default if configured, otherwise ambiguous.

Match on context signals in `task`, not on the speaker and not on `owner_claim`.
Who said it does not determine which board it belongs to.

## Ambiguity is the expected outcome

Most meetings touch more than one area. A batch spanning `API` and `WEB` is the
normal case, not an error, and Layla asking the user once per meeting is cheaper
than tickets scattered across boards. Hold freely.
