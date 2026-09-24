# Layla.AI — Saved Agent Context
_Last updated: 2026-09-21_

## What This Project Is
A **multi-agent post-meeting automation system** built on **LangGraph + deepagents**.
When a meeting ends, Layla orchestrates 4 subagents to automatically:
1. Write a Google Doc report (Ivy)
2. Create Jira tickets (Milo)
3. Send follow-up emails via Gmail (Dex)
4. Post Slack notifications (Vera)

---

## Agent Roles

| Agent | Role | Tools |
|-------|------|-------|
| **Layla** | Central orchestrator — hub-and-spoke, all traffic flows through her | Google Calendar (read), meeting bot, Deepgram |
| **Ivy** | Transcript analyst → 6-section Google Doc + action-item table | Google Docs, Google Drive |
| **Milo** | Jira specialist → maps resolved action items to tickets | Jira API |
| **Dex** | Gmail specialist → drafts/sends follow-up emails | Gmail, Google Forms |
| **Vera** | Slack specialist → posts Block Kit messages to channels | Slack API |

---

## Pipeline (Steps 0–6)

```
Step 0:  Infrastructure captures transcript (Deepgram bot) + roster (Google Calendar)
Step 1:  Layla → Ivy       (transcript dispatched)
Step 2:  Ivy → Layla       (doc URL + raw action items)
Step 2b: Layla ONLY        (identity resolution: spoken names → real emails)
Step 3:  Layla → Milo      (resolved items + doc URL)
Step 4:  Milo → Layla      (ticket summary)
Step 5:  Layla → Dex ∥ Vera  (parallel fan-out)
Step 6:  Dex ∥ Vera → Layla  (status reports → COMPLETE)
```

---

## Key Design Rules
- **No peer-to-peer**: Every handoff routes through Layla. Peer-to-peer is a bug.
- **Draft-first**: Dex never sends without explicit approval. `[DRAFT]` prefix until approved.
- **Untrusted names**: `owner_claim` (spoken name) is untrusted. Only `owner_resolved` (email from roster) is assignable.
- **Never guess**: Ambiguous Jira project → hold & ask. Unknown attendee → unassigned.
- **Checkpoint every hop**: Crash at step 4 resumes at step 4, not from scratch.
- **Parallel step 5**: Dex and Vera are independent; each reports their own status only.

---

## File Structure Summary

```
Layla.AI/
├── LAYLA.md                    # Orchestrator identity, pipeline rules, constraints
├── LAYLA.py                    # Runtime harness (MISSING — needs to be created)
├── Harness_Engineering.py      # Nemotron failure-mitigation layer (EMPTY STUB)
├── langgraph.json              # LangGraph config (EMPTY STUB)
├── memory_manager.py           # LangMem-based memory tools
├── experiences.md              # Episodic memory (runtime logs)
├── loadenv.py                  # .env loader
├── requirements.txt            # Full dependency list
│
├── skills/layla/               # Layla's skill cheatsheets
│   ├── checkpoint_resume/
│   ├── identity_resolution/
│   ├── state_management/
│   └── workflow_routing/
│
└── subagent_config/
    ├── _shared/google_auth.py  # Single shared OAuth token (Gmail + Docs + Drive)
    ├── ivy/   (agent.py, prompt.md, tools.py, _docs.py, _drive.py, skills/)
    ├── milo/  (agent.py, prompt.md, tools.py, skills/)
    ├── dex/   (agent.py, prompt.md, tools.py, _gmail.py, skills/)
    └── vera/  (agent.py, prompt.md, tools.py, skills/)
```

---

## Tech Stack

| Category | Key Libraries |
|----------|--------------|
| Agent Framework | `langgraph`, `langchain`, `deepagents>=0.7.0,<0.8.0`, `langmem` |
| Model Providers | `anthropic`, `openai`, `google-genai` + langchain integrations |
| Google Workspace | `google-api-python-client`, `google-auth`, `google-auth-oauthlib` |
| Slack | `slack-bolt`, `slack-sdk` |
| Jira | `atlassian-python-api` |
| Transcription | `deepgram-sdk` |
| API Layer | `fastapi`, `uvicorn`, `gunicorn` |
| Persistence | `SQLAlchemy`, `asyncpg`, `psycopg`, `redis`, `supabase` |
| Checkpointing | `langgraph-checkpoint-postgres`, `langgraph-checkpoint-sqlite` |
| Observability | `structlog`, `opentelemetry`, `prometheus-client`, `sentry-sdk` |
| Resilience | `tenacity`, `backoff`, `circuitbreaker` |

---

## What's Missing / Needs Building

| Item | Status | Priority |
|------|--------|----------|
| `LAYLA.py` runtime harness | **Does not exist** | 🔴 Critical — nothing runs without this |
| `langgraph.json` | **Empty stub** | 🔴 Critical — LangGraph config |
| `Harness_Engineering.py` | **Empty stub** | 🟡 Nemotron failure mitigation |
| Google OAuth consent flow | **Manual** — not automated | 🟡 UX issue |
| Milo tools | **Stub** (tools.py is 307 bytes) | 🟠 Jira integration incomplete |
| Vera tools | **Stub** (tools.py is 315 bytes) | 🟠 Slack integration incomplete |

---

## State Schema (Key Fields Layla Owns)

| Key | Produced | Consumed | Notes |
|-----|----------|----------|-------|
| `meeting_metadata` | Step 0 | Steps 1, 5 | Calendar event, never the transcript |
| `transcript` | Step 0 | Step 1 | Never forwarded past Ivy |
| `doc_url` / `doc_sharing` | Step 2 | Steps 3, 5 | Layla holds it |
| `action_items` | Step 2 | Steps 2b, 3 | Carries `owner_claim` — untrusted |
| `roster` | Step 0 | Step 2b | Calendar attendees with `source` field |
| `owner_resolved` | Step 2b | Steps 3, 5 | Only assignable identity |
| `unassigned_items` | Step 2b | Steps 3, 5 | Items with no matching attendee |
| `ticket_summary` | Step 4 | Step 5 | Both Dex and Vera receive |
| `milo_status` | Step 4 | Gate before step 5 | `HELD`/`FAILED` blocks fan-out |
| `dex_status` / `vera_status` | Step 6 | Close | Determines COMPLETE/PARTIAL/FAILED |
