# Layla.AI — Multi-Agent Meeting Agent

> When a meeting ends, Layla takes it from raw audio to a written record, tracked
> work, sent follow-ups, and a posted summary — automatically, with a human
> approval gate on anything that leaves the building.

Layla.AI is a **multi-agent post-meeting automation system** built on
[**LangGraph**](https://langchain-ai.github.io/langgraph/) +
[**deepagents**](https://pypi.org/project/deepagents/). A single orchestrator,
**Layla**, runs a hub-and-spoke pipeline over four specialist subagents. Every
handoff is checkpointed, so a crash resumes at the step it died on rather than
from scratch.

> **Project status: under active construction.** The capture layer, all four
> subagents' tools, the memory layer, the OAuth bootstrap, and the test suite are
> built. The orchestrator entrypoint (`LAYLA.py`) is currently an imports-only
> scaffold — nothing runs end-to-end *yet*. See [Project status](#project-status)
> for the honest built-vs-missing breakdown.

---

## What it does

1. **Capture** — pulls the meeting transcript (via a meeting bot or Deepgram) and
   the attendee roster (from Google Calendar).
2. **Ivy** writes a six-section Google Doc report with an action-item table.
3. **Layla** resolves spoken names to real email addresses against the roster.
4. **Milo** turns resolved action items into Jira tickets.
5. **Dex** drafts a follow-up email (Gmail) and any Google Forms — *draft-first,
   never sent without approval*.
6. **Vera** posts a Slack Block Kit summary to the right channel.

---

## Architecture

Hub-and-spoke: **all** traffic flows through Layla. There is no peer-to-peer
messaging between subagents — a direct subagent-to-subagent handoff is a bug.

| Agent     | Role                                                        | Integrations                     |
|-----------|-------------------------------------------------------------|----------------------------------|
| **Layla** | Central orchestrator, identity resolution, memory           | Google Calendar, meeting bot, Deepgram |
| **Ivy**   | Transcript → 6-section Google Doc + action-item table       | Google Docs, Google Drive        |
| **Milo**  | Resolved action items → Jira tickets (idempotent)           | Jira                             |
| **Dex**   | Follow-up email (draft-first) + Google Forms                | Gmail, Google Forms              |
| **Vera**  | Slack Block Kit notifications                               | Slack                            |

Subagents are **declarative**: each `subagent_config/<name>/agent.py` exposes a
`build_spec(model)` returning a dict (name, description, system prompt, tools,
skills); `create_deep_agent` compiles them. Prompts live in `prompt.md`, and each
agent's know-how lives in a three-tier `skills/` layout (frontmatter always
loaded, `SKILL.md` on invocation, `references/` on demand).

---

## The pipeline (steps 0–6)

```
Step 0   Capture: meeting bot / Deepgram → transcript,  Google Calendar → roster
Step 1   Layla → Ivy        (transcript dispatched)
Step 2   Ivy → Layla        (doc URL + raw action items)
Step 2b  Layla only         (identity resolution: spoken name → roster email)
Step 3   Layla → Milo       (resolved items + doc URL)
Step 4   Milo → Layla       (ticket summary)
Step 5   Layla → Dex ∥ Vera (parallel fan-out)
Step 6   Dex ∥ Vera → Layla (status reports → COMPLETE / PARTIAL / FAILED)
```

A checkpoint is written at every hop.

---

## Design principles (the trust model)

The meeting transcript is **untrusted input** — it is data, never instructions.
Several rules follow from that:

- **Untrusted identities.** A spoken/display name (`owner_claim`) is never
  assignable. Only `owner_resolved` — an email matched against the calendar
  roster — can own a ticket or receive an email. Unknown attendee → unassigned.
- **Speaker anonymization.** Attacker-settable display names from the meeting bot
  are stripped to `Speaker N` before the transcript is shaped.
- **Draft-first.** Dex never sends without explicit approval; drafts carry a
  `[DRAFT]` prefix until approved.
- **Never guess.** Ambiguous Jira project → hold and ask, don't pick one.
- **Prompt-injection guard (MEM-01).** Long-term memory writes run through
  `guardrails/input_guard.py::contains_injection` first, so a transcript can't
  poison Layla's durable memory with "ignore previous instructions"-style text.
- **Checkpoint every hop.** A crash at step 4 resumes at step 4.

---

## Transcript capture (`capture/`)

Three interchangeable transcript sources, all implemented:

- **`_attendee.py`** — dispatches an [Attendee.dev](https://attendee.dev) meeting
  bot, polls it, and shapes the transcript (identity-stripped to `Speaker N`).
- **`_calendar.py`** — polls Google Calendar for the event, building the roster,
  `meeting_metadata`, and the conference URI (prefers the video link, never a
  dial-in number).
- **`deepgram_transcription.py`** — direct Deepgram transcription of a file/URL,
  plus a live WebSocket streaming path.

---

## Long-term memory (`memory_manager.py`)

Layla remembers across runs via [langmem](https://pypi.org/project/langmem/) over
two **separate**, per-user (`{user_id}`) cross-thread stores:

- **`layla_memory`** — durable **user facts** only: the operator's identity,
  email, and standing preferences. Kept small and high-signal.
- **`layla_experience`** — Layla's **experience diary**: one-line, append-style
  notes of what each subagent delegation did and the key learning/ID.

Four tools are exposed to the agent: `manage_memory` / `search_memory` (facts) and
`log_experience` / `search_experience` (diary). Both **write** tools are wrapped by
the MEM-01 injection guard.

> **Runtime contract:** these tools resolve their store from the LangGraph runtime
> (`get_store()`), so Layla's graph must be compiled **with** a store
> (`InMemoryStore` for dev; Postgres for prod) and pass `user_id` in
> `config={"configurable": {"user_id": ...}}`. Semantic search additionally needs
> the store built with an embedding index — see `memory_config.py`.

---

## Repository layout

```
Layla.AI/
├── LAYLA.py                     # Orchestrator entrypoint (imports-only scaffold)
├── LAYLA.md                     # Orchestrator contract: identity, pipeline rules
├── authorize.py                 # One-time Google OAuth consent bootstrap
├── memory_manager.py            # langmem tools (facts + experience), MEM-01 guarded
├── memory_config.py             # Lazy HuggingFace embeddings + Postgres store config
├── guardrails/input_guard.py    # Prompt-injection detector (contains_injection)
├── langgraph.json               # LangGraph deploy config (stub)
├── loadenv.py                   # .env loader (stub)
├── requirements.txt             # Runtime deps   ·   requirements-dev.txt (tooling)
│
├── capture/                     # Step-0 transcript + roster sources
│   ├── _attendee.py  _calendar.py  deepgram_transcription.py
│
├── subagent_config/
│   ├── _shared/google_auth.py   # One shared OAuth token for all Google APIs
│   ├── ivy/   (agent.py, prompt.md, tools.py, _docs.py, _drive.py, skills/)
│   ├── milo/  (agent.py, prompt.md, tools.py, _jira.py, skills/)
│   ├── dex/   (agent.py, prompt.md, tools.py, _gmail.py, _forms.py, skills/)
│   └── vera/  (agent.py, prompt.md, tools.py, _slack.py, skills/)
│
├── skills/layla/                # Layla's skills: checkpoint_resume, identity_resolution,
│                                #   state_management, workflow_routing
└── tests/                       # pytest suite (see below)
```

---

## Getting started

### Prerequisites

- **Python 3.11+**
- A Google Cloud project with a **Desktop OAuth client** (for Docs/Drive/Gmail/
  Forms/Calendar), and API keys for whichever integrations you enable (Deepgram,
  Jira, Slack, Attendee.dev, and a model provider such as Anthropic).

### Install

```bash
python -m venv project_venv
# Windows:  project_venv\Scripts\activate    ·    macOS/Linux:  source project_venv/bin/activate

python -m pip install -U -r requirements.txt      # runtime deps
python -m pip install -U -r requirements-dev.txt   # test/lint tooling (optional)
```

### Google OAuth (one-time)

Layla's Google APIs share a single OAuth token. `google_auth.py` never opens a
browser — it only reads a token. Mint that token once:

```bash
# 1. Put your Desktop OAuth client JSON at ./client_secret.json
#    (or point GOOGLE_OAUTH_CLIENT at it)
# 2. Run the consent flow — opens your browser, writes .gmail_token.json
python authorize.py
```

> **Avoiding the 7-day expiry.** If your OAuth consent screen is in **Testing**
> mode, refresh tokens expire after 7 days regardless of the credential file. Fix
> it in Google Cloud Console → *OAuth consent screen* → **Publish App** (status
> *In production*). You do **not** need Google verification for your own account —
> just click through the "unverified app" warning. Do this **before** running
> `authorize.py`.

`client_secret.json`, `.gmail_token.json`, and `.env` are all gitignored — they
are never committed.

### Environment variables

Set these in a `.env` file (gitignored). Every integration degrades gracefully:
its tools return an `ERROR: … auth not configured` string until the relevant
variable is present, rather than crashing.

| Variable | Used by | Default |
|----------|---------|---------|
| `GOOGLE_OAUTH_CLIENT` | Google auth (consent) | `client_secret.json` |
| `GOOGLE_OAUTH_TOKEN` | Google auth (runtime) | `.gmail_token.json` |
| `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` | Dex — Gmail SMTP fallback | — |
| `DEEPGRAM_API_KEY` / `DEEPGRAM_MODEL` | Capture — transcription | model: `nova-2-meeting` |
| `ATTENDEE_API_KEY` / `ATTENDEE_API_BASE` / `ATTENDEE_BOT_NAME` | Capture — meeting bot | base: `https://app.attendee.dev`, name: `Layla` |
| `JIRA_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` | Milo — Jira | — |
| `JIRA_EPIC_LINK_FIELD` | Milo — epic linking | `customfield_10014` |
| `SLACK_BOT_TOKEN` | Vera — Slack | — |
| `CALENDAR_POLL_WINDOW_MINUTES` / `CALENDAR_LEAD_TIME_SECONDS` | Capture — calendar poller | `10` / `60` |
| `POSTGRES_CONN_STRING` | Memory store (prod) | — |
| Model provider keys (e.g. `ANTHROPIC_API_KEY`) | LLM calls via LangChain | — |

---

## Tests

```bash
pytest            # config in pytest.ini; conftest.py puts the repo root on sys.path
```

The suite covers the pure, trust-critical logic — the parts where a bug would be a
security or correctness hole:

- **`test_attendee_transcript.py`** — transcript identity-stripping (display names
  → `Speaker N`), empty-text skipping, and bad-URL rejection.
- **`test_calendar.py`** — conference-URI selection (video over phone), roster
  building, and `meeting_metadata` reconciliation.
- **`test_jira_priority.py`** — priority mapping, whole-word signal matching, and
  JQL string escaping.
- **`test_gmail_render.py`** — draft-prefix stripping, MIME assembly, markdown→HTML.
- **`test_input_guard.py`** — the MEM-01 guard flags injections and lets ordinary
  meeting content through.

---

## Project status

| Area | Status |
|------|--------|
| Step-0 capture (Attendee bot, Calendar poller, Deepgram file/URL/live) | ✅ Built |
| Ivy / Milo / Dex / Vera tools + real API integrations | ✅ Built (gated on runtime creds) |
| Shared Google OAuth + `authorize.py` consent bootstrap | ✅ Built |
| Long-term memory (langmem, 2 namespaces, MEM-01 guard) | ✅ Built |
| Prompt-injection guard (`guardrails/`) | ✅ Built |
| Test suite | ✅ Green |
| **`LAYLA.py` orchestrator** (build agent, checkpointer, step 0–6 loop) | 🔴 Imports-only scaffold — being wired |
| `langgraph.json`, `loadenv.py` | 🟡 Stubs |
| End-to-end run | 🔴 Not yet — no scheduler connects `capture/` to the pipeline |

"Built" means real code gated on runtime credentials, not that credentials exist.
Nothing runs end-to-end until the orchestrator entrypoint is wired.

---

## Tech stack

**Framework:** langgraph, langchain, deepagents, langmem ·
**Models:** anthropic, openai, google-genai (via LangChain) ·
**Google Workspace:** google-api-python-client, google-auth(-oauthlib) ·
**Integrations:** slack-bolt/-sdk, atlassian-python-api, deepgram-sdk ·
**Persistence/checkpointing:** Postgres & SQLite savers, SQLAlchemy, redis ·
**Embeddings:** sentence-transformers ·
**Resilience/observability:** tenacity, backoff, structlog, opentelemetry.

Full list in [`requirements.txt`](requirements.txt).

---

## Security

- Secrets (`.env`, `client_secret*.json`, `*token*.json`) are gitignored and must
  never be committed.
- The transcript is untrusted; identity resolution and the MEM-01 memory guard
  exist specifically to contain prompt-injection and impersonation from meeting
  content.
- Outbound actions (email) are draft-first and require human approval.

---

## License

No license file is present yet; treat this repository as **all rights reserved**
until one is added.
