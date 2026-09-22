"""Step-0 capture infrastructure — the non-reasoning layer that produces
`transcript`, `roster`, and `meeting_metadata` before Layla dispatches Ivy.

No LLM and no dispatch happens here (routing_map.md: "Step 0 → infrastructure").

Currently implemented:
  - _calendar: poll Google Calendar, build meeting_metadata + roster, and expose
    the event's conference URI (calendar-watcher tool).
  - _attendee: dispatch an Attendee.dev bot to a meeting and retrieve its
    transcript as the `transcript` state object (meeting-bot tool).
  - deepgram_transcription: audio → the `transcript` state object directly, either
    prerecorded (file/URL) or live (a WebSocket a bot streams PCM into) — the
    alternative capture path when Attendee is not used.

The step-0 flow (driven by Layla / the orchestrator): poll → build roster from
attendees[] → dispatch bot at the conference URI → wait for the transcript →
hand ONLY the transcript to Ivy. No scheduler/dispatch loop lives here yet.
"""

from ._attendee import (
    AttendeeError,
    dispatch_bot,
    fetch_transcript,
    get_bot,
    leave_bot,
    wait_for_transcript,
)
from ._calendar import (
    build_meeting_metadata,
    build_roster,
    conference_uri,
    get_lead_time_seconds,
    poll_upcoming_meetings,
)
from .deepgram_transcription import (
    DeepgramError,
    LiveSession,
    TranscriptAccumulator,
    transcribe_file,
    transcribe_url,
)

__all__ = [
    # Calendar-watcher tool
    "poll_upcoming_meetings",
    "build_meeting_metadata",
    "build_roster",
    "conference_uri",
    "get_lead_time_seconds",
    # Attendee meeting-bot tool
    "AttendeeError",
    "dispatch_bot",
    "get_bot",
    "wait_for_transcript",
    "fetch_transcript",
    "leave_bot",
    # Direct Deepgram path (alternative to Attendee)
    "DeepgramError",
    "LiveSession",
    "TranscriptAccumulator",
    "transcribe_file",
    "transcribe_url",
]
