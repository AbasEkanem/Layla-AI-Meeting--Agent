"""LAYLA.py — orchestrator runtime harness (imports scaffold).

Layla is the hub-and-spoke supervisor: capture (step 0) hands her a transcript +
roster, then she drives Ivy -> (2b identity resolution) -> Milo -> Dex || Vera,
checkpointing after every hop. Contract in LAYLA.md; step map in
skills/layla/ .

This module currently only ARRANGES the imports the harness needs. The wiring
(building the deep agent, selecting a checkpointer, the step-0..6 loop) is done
by hand below the import block.
"""

from __future__ import annotations

# --- Standard library --------------------------------------------------------
import logging
import os

# --- deepagents / LangGraph framework ----------------------------------------
# create_deep_agent compiles Layla + the subagent specs into a LangGraph agent
# wrapped in the middleware stack (filesystem, summarization, skills, ...).
from deepagents import (
    DeepAgentState,
    SubAgent,
    create_deep_agent,
)

# Checkpointer (C8: checkpoint after every hop) — pick one when wiring:
#   from langgraph.checkpoint.memory import InMemorySaver     # dev / tests
#   from langgraph.checkpoint.postgres import PostgresSaver   # prod
from langgraph.checkpoint.sqlite import SqliteSaver

# --- Subagent spec factories (declarative build_spec(model) -> dict) ---------
from subagent_config.ivy.agent import build_spec as build_ivy_spec
from subagent_config.milo.agent import build_spec as build_milo_spec
from subagent_config.dex.agent import build_spec as build_dex_spec
from subagent_config.vera.agent import build_spec as build_vera_spec

# --- Step 0: capture (calendar watcher + Attendee bot) -----------------------
from capture import (
    # Calendar watcher: roster + meeting_metadata + where to send the bot.
    poll_upcoming_meetings,
    build_meeting_metadata,
    build_roster,
    conference_uri,
    get_lead_time_seconds,
    # Attendee meeting-bot: dispatch -> wait -> transcript state object.
    AttendeeError,
    dispatch_bot,
    wait_for_transcript,
    get_bot,
    leave_bot,
)

# Direct Deepgram path (alternative transcript source to the Attendee bot).
from capture.deepgram_transcription import (
    DeepgramError,
    LiveSession,
    transcribe_file,
    transcribe_url,
)

# --- Shared Google OAuth (one cached token, union of scopes) -----------------
from subagent_config._shared.google_auth import (
    GoogleAuthError,
    get_service,
    load_credentials,
)

# --- Not yet built — wire these in yourself ----------------------------------
# Memory (langmem): manage/search tools + consolidation into experiences.md.
#   from memory_manager import ...        # your task
# Env loading: populate os.environ from .env before creds are read above.
#   from loadenv import load_env          # loadenv.py is currently empty
# Failure mitigation (Nemotron):
#   from Harness_Engineering import ...   # Harness_Engineering.py is currently empty

_log = logging.getLogger("layla")

# Layla's own skill cheatsheets (SkillsMiddleware path, POSIX-relative to root).
LAYLA_SKILLS = ["skills/layla/"]

# -----------------------------------------------------------------------------
# WIRING GOES HERE (you'll do this):
#   1. load env  2. pick model
#   3. subagents = [build_ivy_spec(model), build_milo_spec(model),
#                   build_dex_spec(model), build_vera_spec(model)]
#   4. agent = create_deep_agent(..., subagents=subagents, skills=LAYLA_SKILLS,
#                                checkpointer=SqliteSaver(...))
#   5. step-0 capture -> step-6 close loop
# -----------------------------------------------------------------------------
