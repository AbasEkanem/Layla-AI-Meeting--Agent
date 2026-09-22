"""Attendee.dev bot dispatch + transcript retrieval — step-0 capture.

The meeting bot is a self-hosted Attendee.dev instance (attendee-labs/attendee).
Layla's calendar-watcher dispatches a bot at a meeting's conference URI; Attendee
joins, records, and transcribes; we retrieve the finished transcript and shape it
into the `transcript` state object (state_schema.md) for Ivy.

This module is transport only — it reasons about nothing (routing_map.md, step 0).

API contract (verified against attendee-labs/attendee source, API v1):
  - Auth:       Authorization: Token <ATTENDEE_API_KEY>
  - Dispatch:   POST /api/v1/bots            {"meeting_url", "bot_name"}      -> {"id", "state", ...}
  - Poll:       GET  /api/v1/bots/{id}       -> {"state", "transcription_state", ...}
  - Transcript: GET  /api/v1/bots/{id}/transcript
                  -> [ { "speaker_name", "speaker_uuid", "speaker_is_host",
                         "timestamp_ms", "duration_ms", "transcription": {"transcript": "...", ...} } ]
  - Leave:      POST /api/v1/bots/{id}/leave  {}

IDENTITY SAFEGUARD: Attendee returns `speaker_name` (the meeting participant's
display name — attacker-settable, NOT a calendar-authenticated identity). The
transcript must stay identity-free: we map each distinct `speaker_uuid` to a
diarization label "Speaker N" (first-seen order) and DROP the name. Mapping a
label to a person is Layla's identity_resolution against the calendar roster —
never carried in the transcript (state_schema.md), and never sourced from a
display name the trust model treats as untrusted.

Environment variables (names only; values live in .env, which is gitignored):
  ATTENDEE_API_KEY    Attendee project API key
  ATTENDEE_API_BASE   Base URL of the Attendee instance (default https://app.attendee.dev)
"""

from __future__ import annotations

import logging
import os
import time

import requests

_log = logging.getLogger(__name__)

ATTENDEE_API_KEY = os.getenv("ATTENDEE_API_KEY", "")
ATTENDEE_API_BASE = os.getenv("ATTENDEE_API_BASE", "https://app.attendee.dev").rstrip("/")
DEFAULT_BOT_NAME = os.getenv("ATTENDEE_BOT_NAME", "Layla")

# Source label for the transcript object. The schema fixes this to "deepgram";
# Attendee must be configured to transcribe via Deepgram for it to be literally
# accurate (the intended setup — the project already carries DEEPGRAM_API_KEY).
_TRANSCRIPT_SOURCE = "deepgram"

# Bot state API codes (verified against BotStates.state_to_api_code).
_TERMINAL_ERROR_STATES = {"fatal_error"}
_ENDED_STATES = {"ended", "post_processing"}
# transcription_state code meaning "finished" (per the capture spec).
_TRANSCRIPTION_COMPLETE = "complete"

_HTTP_TIMEOUT_S = 30


class AttendeeError(RuntimeError):
    """Raised when Attendee credentials are missing or an API call fails, with guidance."""


def _headers() -> dict:
    if not ATTENDEE_API_KEY:
        msg = (
            "ATTENDEE_API_KEY is not set. Create an API key in your Attendee "
            "instance and add it to .env (ATTENDEE_API_BASE defaults to "
            "https://app.attendee.dev; set it to your self-hosted URL)."
        )
        raise AttendeeError(msg)
    return {"Authorization": f"Token {ATTENDEE_API_KEY}", "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{ATTENDEE_API_BASE}/api/v1/{path.lstrip('/')}"


def _request(method: str, path: str, *, json: dict | None = None, what: str) -> dict | list:
    try:
        resp = requests.request(
            method, _url(path), headers=_headers(), json=json, timeout=_HTTP_TIMEOUT_S
        )
    except AttendeeError:
        raise
    except Exception as e:  # noqa: BLE001 - wrap transport errors with context
        raise AttendeeError(f"Attendee {what} request failed — {e}") from e
    if resp.status_code >= 300:
        raise AttendeeError(
            f"Attendee {what} returned HTTP {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except ValueError:
        return {}


# ── Bot lifecycle ─────────────────────────────────────────────────────────────

def dispatch_bot(meeting_url: str, bot_name: str | None = None) -> str:
    """Send an Attendee bot to a meeting. Returns the bot id.

    Args:
        meeting_url: The Google Meet / Zoom / Teams link (from the calendar event).
        bot_name:    Display name the bot joins under (default ATTENDEE_BOT_NAME / "Layla").

    Raises:
        AttendeeError: credentials missing, invalid URL, or the API rejected the dispatch.
    """
    if not meeting_url or "://" not in meeting_url:
        raise AttendeeError(f"'{meeting_url}' is not a valid meeting URL.")
    body = {"meeting_url": meeting_url, "bot_name": bot_name or DEFAULT_BOT_NAME}
    data = _request("POST", "bots", json=body, what="dispatch_bot")
    bot_id = data.get("id") if isinstance(data, dict) else None
    if not bot_id:
        raise AttendeeError(f"Attendee dispatch returned no bot id: {data}")
    _log.info("attendee.dispatch_bot bot_id=%s url=%s", bot_id, meeting_url)
    return str(bot_id)


def get_bot(bot_id: str) -> dict:
    """Return the bot's current record (includes `state` and `transcription_state`)."""
    data = _request("GET", f"bots/{bot_id}", what="get_bot")
    return data if isinstance(data, dict) else {}


def leave_bot(bot_id: str) -> None:
    """Ask the bot to leave the meeting (POST /bots/{id}/leave)."""
    _request("POST", f"bots/{bot_id}/leave", json={}, what="leave_bot")
    _log.info("attendee.leave_bot bot_id=%s", bot_id)


def get_raw_transcript(bot_id: str) -> list[dict]:
    """Return Attendee's raw utterance list for a bot (GET /bots/{id}/transcript)."""
    data = _request("GET", f"bots/{bot_id}/transcript", what="get_raw_transcript")
    return data if isinstance(data, list) else []


# ── Utterances → transcript object ────────────────────────────────────────────
# Pure: no network. Maps Attendee's utterances to the state_schema `transcript`,
# stripping the display name to a diarization label (see IDENTITY SAFEGUARD).

def _utterances_to_transcript(utterances: list[dict]) -> dict:
    """Turn Attendee utterances into the `transcript` state object.

    Distinct `speaker_uuid`s are labelled "Speaker 0", "Speaker 1", … in first-seen
    order; the display name is never carried through. Utterances with empty text are
    skipped. `timestamp_ms`/`duration_ms` are already milliseconds.
    """
    segments: list[dict] = []
    speaker_labels: dict[str, str] = {}
    confidences: list[float] = []

    for i, utt in enumerate(utterances):
        transcription = utt.get("transcription") or {}
        text = (transcription.get("transcript") or "").strip()
        if not text:
            continue

        uuid = str(utt.get("speaker_uuid") or "")
        if uuid not in speaker_labels:
            speaker_labels[uuid] = f"Speaker {len(speaker_labels)}"

        ts = int(utt.get("timestamp_ms") or 0)
        dur = int(utt.get("duration_ms") or 0)
        conf = transcription.get("confidence")
        if isinstance(conf, (int, float)):
            confidences.append(float(conf))

        segments.append({
            "segment_id": f"seg-{i}",
            "speaker_label": speaker_labels[uuid],
            "start_ms": ts,
            "end_ms": ts + dur,
            "text": text,
        })

    text = " ".join(s["text"] for s in segments).strip()
    confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    return {
        "text": text,
        "segments": segments,
        "source": _TRANSCRIPT_SOURCE,
        "confidence": confidence,
    }


def fetch_transcript(bot_id: str) -> dict:
    """Retrieve and shape a bot's transcript into the `transcript` state object.

    Does not wait — call after transcription is complete, or use
    wait_for_transcript to poll first.
    """
    return _utterances_to_transcript(get_raw_transcript(bot_id))


def wait_for_transcript(
    bot_id: str,
    *,
    timeout_s: float = 1800.0,
    poll_interval_s: float = 15.0,
) -> dict:
    """Poll the bot until transcription is complete, then return the `transcript` object.

    Retrieves once `transcription_state == "complete"`. Raises if the bot reaches a
    fatal error, or if `timeout_s` elapses first.

    Args:
        bot_id:          The id returned by dispatch_bot.
        timeout_s:       Max seconds to wait for completion (default 30 min).
        poll_interval_s: Seconds between polls (default 15).

    Raises:
        AttendeeError: fatal bot state, timeout, or an API failure.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        bot = get_bot(bot_id)
        state = bot.get("state", "")
        tstate = bot.get("transcription_state", "")

        if tstate == _TRANSCRIPTION_COMPLETE:
            return fetch_transcript(bot_id)
        if state in _TERMINAL_ERROR_STATES:
            raise AttendeeError(
                f"Bot {bot_id} reached fatal state '{state}' before transcription completed."
            )
        if time.monotonic() >= deadline:
            raise AttendeeError(
                f"Timed out after {timeout_s:.0f}s waiting for bot {bot_id} "
                f"(state='{state}', transcription_state='{tstate}')."
            )
        time.sleep(poll_interval_s)
