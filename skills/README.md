# Layla.AI Skill Harness

Three tiers. The harness pays for each one only when the model needs it.

| Tier | Content | Loaded | Budget |
|---|---|---|---|
| 1 | `name` + `description` frontmatter | always, every skill | ~30 tokens each |
| 2 | `SKILL.md` body | when that skill is invoked | ≤ 60 lines |
| 3 | `references/*.md` | only when a body points at it | unbounded |

Tier 2 is a **procedure**: numbered steps, preconditions, hard rules. It never
carries a lookup table, a template, or a schema — those are tier 3. A skill that
only needs to route a payload should not pay for a template it will not render.

## Rules for adding or editing a skill

1. `description` states when to use it **and** when not to.
2. Frontmatter `name` equals the directory name.
3. Body over ~60 lines means bulk belongs in `references/`.
4. Never reference across agents (`../../ivy/...`). Cross-agent contracts live in
   `layla/state_management/references/state_schema.md`; restate the minimal slice
   inline where another agent needs it.
5. Every `references/` path named in a body must exist. No dangling pointers.

## Single-owner table

Each value has exactly one producer. Everyone else reads it.

| Value | Sole owner | Everyone else |
|---|---|---|
| `meeting_metadata` | Layla — step 0, Calendar event + bot session | consumes; never derives from transcript |
| `transcript` | Layla — step 0, bot → Deepgram | Ivy only, never past step 1 |
| `roster` | Layla — step 0, Calendar `attendees[]` | read at 2b; carries `source`, never rebuilt |
| `owner_resolved` | Layla — `identity_resolution` | Milo/Dex assign from this, never from `owner_claim` |
| `priority` | Milo — `priority_mapper` | Ivy records the verbatim signal only |
| `project_key` | Milo — `project_router` | — |
| `doc_url` | Ivy — step 2, held by Layla | never re-fetched from Ivy |
| `recipients` | Layla — confirmed before step 5 | Dex never guesses |
| `channels` | Layla — confirmed before step 5 | Vera never guesses |

## Index

| Agent | Skill | Tier 3 |
|---|---|---|
| Layla | `workflow_routing` | `routing_map.md` |
| Layla | `state_management` | `state_schema.md` |
| Layla | `identity_resolution` | `roster_contract.md` |
| Layla | `checkpoint_resume` | `resume_matrix.md` |
| Ivy | `transcript_parser` | `extraction_schema.md` |
| Ivy | `action_item_extractor` | `action_item_schema.md` |
| Ivy | `google_doc_creator` | `report_template.md` |
| Milo | `project_router` | `project_keys.md` |
| Milo | `priority_mapper` | `priority_table.md` |
| Milo | `jira_ticket_creator` | `ticket_schema.md` |
| Dex | `gmail_drafter` | `email_template.md` |
| Dex | `gmail_sender` | — |
| Dex | `google_form_creator` | `form_templates.md` |
| Vera | `channel_routing` | `routing_table.md` |
| Vera | `block_kit_composer` | `block_kit_template.md` |
| Vera | `thread_manager` | — |
| Vera | `status_reporter` | — |

Step 0 has no skill and needs none — the calendar-watcher, the meeting bot, and
Deepgram are infrastructure, and nothing in them reasons. Its contract lives in
`layla/workflow_routing/references/routing_map.md`; the trust rules for what it
produces live in `layla/identity_resolution/references/roster_contract.md`.
