"""Step-0 capture infrastructure — the non-reasoning layer that produces
`transcript`, `roster`, and `meeting_metadata` before Layla dispatches Ivy.

No LLM and no dispatch happens here (routing_map.md: "Step 0 → infrastructure").

Currently implemented:
  - deepgram_transcription: audio → the `transcript` state object, either
    prerecorded (file/URL) or live (a WebSocket the bot streams PCM into).

Still to build: the calendar-watcher (roster + meeting_metadata) and the meeting
bot (audio capture + participant display names) that drives LiveSession.
"""

from .deepgram_transcription import (
    DeepgramError,
    LiveSession,
    TranscriptAccumulator,
    transcribe_file,
    transcribe_url,
)

__all__ = [
    "DeepgramError",
    "LiveSession",
    "TranscriptAccumulator",
    "transcribe_file",
    "transcribe_url",
]
