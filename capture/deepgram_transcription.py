"""Deepgram transcription — step-0 capture, audio → the `transcript` state object.

The meeting bot records audio; this module turns that audio (a local file or a
URL) into the `transcript` object Layla holds and forwards to Ivy at step 1. It
reasons about nothing — it is transport, the same category as the calendar-watcher
and the bot (routing_map.md, step 0).

Output shape (state_management/references/state_schema.md → `transcript`):

    {
      "text":       str,          # full transcript, non-empty for a usable meeting
      "segments":   [ { "segment_id", "speaker_label", "start_ms", "end_ms", "text" } ],
      "source":     "deepgram",
      "confidence": float,        # overall confidence of the best alternative
    }

`speaker_label` is a diarization label ("Speaker 0"), NEVER an identity — mapping a
label to a person is Layla's `identity_resolution`, downstream. This module emits
labels only, and no email ever (the bot's schema has no email field).

Diarization is requested (`diarize=True`) and segments come from Deepgram's
`utterances` — one utterance per contiguous speaker turn, which is exactly the
granularity the schema's `segments` wants. Emptiness is NOT raised here: an empty
transcript is a valid state that Layla aborts on at step 1, so this module returns
it faithfully and lets validation happen upstream.

SDK: deepgram-sdk 7.x (Fern-generated) — `DeepgramClient().listen.v1.media`.

Environment variables (names only; values live in .env, which is gitignored):
  DEEPGRAM_API_KEY   Deepgram project API key
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")

# nova-2-meeting is Deepgram's model tuned for multi-speaker meeting audio, which
# is exactly this pipeline's input. Overridable for medical/finance/other domains.
DEFAULT_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-2-meeting")

# Transcription options shared by the file and URL paths. diarize + utterances is
# what yields per-speaker segments; smart_format/punctuate make the text readable
# for Ivy's extraction.
_LISTEN_OPTS: dict = {
    "diarize": True,
    "utterances": True,
    "punctuate": True,
    "smart_format": True,
}


class DeepgramError(RuntimeError):
    """Raised when Deepgram credentials are missing or the API call fails, with guidance."""


def _client():
    """Return an authenticated DeepgramClient.

    Raises DeepgramError if DEEPGRAM_API_KEY is unset — never silently falls back
    to an unauthenticated client.
    """
    if not DEEPGRAM_API_KEY:
        msg = (
            "Deepgram credentials not configured. Set DEEPGRAM_API_KEY in .env "
            "(create a key at https://console.deepgram.com → API Keys)."
        )
        raise DeepgramError(msg)
    try:
        from deepgram import DeepgramClient  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - dep is in requirements
        msg = "deepgram-sdk is not installed; cannot transcribe."
        raise DeepgramError(msg) from e
    return DeepgramClient(api_key=DEEPGRAM_API_KEY)


# ── Response → transcript object ──────────────────────────────────────────────
# Pure: takes the SDK response, returns the state_schema `transcript` dict. Kept
# free of any network/SDK calls so the mapping is unit-testable against a stub.

def _best_alternative(response):
    """Return the top alternative of the first channel, or None if absent."""
    results = getattr(response, "results", None)
    channels = getattr(results, "channels", None) or []
    if not channels:
        return None
    alternatives = getattr(channels[0], "alternatives", None) or []
    return alternatives[0] if alternatives else None


def _segments_from_utterances(response) -> list[dict]:
    """Map Deepgram utterances → transcript segments (one per speaker turn).

    Deepgram reports utterance start/end in SECONDS (floats); the schema wants
    integer milliseconds. `speaker` is a diarization index → "Speaker N" label.
    """
    results = getattr(response, "results", None)
    utterances = getattr(results, "utterances", None) or []
    segments: list[dict] = []
    for i, utt in enumerate(utterances):
        start_s = getattr(utt, "start", 0.0) or 0.0
        end_s = getattr(utt, "end", 0.0) or 0.0
        speaker = getattr(utt, "speaker", None)
        speaker_label = f"Speaker {speaker}" if speaker is not None else "Speaker 0"
        # Prefer Deepgram's own utterance id; fall back to a stable positional id.
        seg_id = getattr(utt, "id", None) or f"seg-{i}"
        segments.append({
            "segment_id": str(seg_id),
            "speaker_label": speaker_label,
            "start_ms": int(round(start_s * 1000)),
            "end_ms": int(round(end_s * 1000)),
            "text": (getattr(utt, "transcript", "") or "").strip(),
        })
    return segments


def _build_transcript(response) -> dict:
    """Turn a Deepgram ListenV1Response into the `transcript` state object.

    Falls back to a single whole-transcript segment when no utterances are present
    (e.g. diarization disabled or silent audio), so `segments` is never empty when
    there is text. Never raises on empty audio — returns an empty-text transcript
    that Layla validates and aborts on at step 1.
    """
    alt = _best_alternative(response)
    text = (getattr(alt, "transcript", "") if alt else "") or ""
    confidence = float(getattr(alt, "confidence", 0.0) or 0.0) if alt else 0.0

    segments = _segments_from_utterances(response)
    if not segments and text.strip():
        # No diarized utterances but we do have text — keep the contract that a
        # non-empty transcript carries at least one segment.
        segments = [{
            "segment_id": "seg-0",
            "speaker_label": "Speaker 0",
            "start_ms": 0,
            "end_ms": 0,
            "text": text.strip(),
        }]

    return {
        "text": text.strip(),
        "segments": segments,
        "source": "deepgram",
        "confidence": confidence,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def transcribe_file(
    audio_path: str,
    *,
    model: str | None = None,
    language: str | None = None,
) -> dict:
    """Transcribe a local audio file into the `transcript` state object.

    Args:
        audio_path: Path to the recorded meeting audio (wav/mp3/m4a/opus/…).
        model:      Deepgram model override (default DEEPGRAM_MODEL / nova-2-meeting).
        language:   Optional BCP-47 language hint (e.g. "en", "es"). None → auto.

    Returns:
        The `transcript` dict (see module docstring). Empty `text` is possible and
        is the caller's (Layla's) signal to abort at step 1.

    Raises:
        DeepgramError: credentials missing, file unreadable, or the API call failed.
    """
    if not audio_path or not os.path.isfile(audio_path):
        raise DeepgramError(f"Audio file not found: '{audio_path}'.")

    opts = dict(_LISTEN_OPTS, model=model or DEFAULT_MODEL)
    if language:
        opts["language"] = language

    try:
        with open(audio_path, "rb") as fh:
            audio_bytes = fh.read()
        client = _client()
        response = client.listen.v1.media.transcribe_file(request=audio_bytes, **opts)
    except DeepgramError:
        raise
    except Exception as e:  # noqa: BLE001 - wrap SDK/transport errors with context
        raise DeepgramError(f"Deepgram transcription of '{audio_path}' failed — {e}") from e

    transcript = _build_transcript(response)
    _log.info(
        "deepgram.transcribe_file path=%s segments=%d chars=%d confidence=%.3f",
        audio_path, len(transcript["segments"]), len(transcript["text"]), transcript["confidence"],
    )
    return transcript


def transcribe_url(
    audio_url: str,
    *,
    model: str | None = None,
    language: str | None = None,
) -> dict:
    """Transcribe audio at a public URL into the `transcript` state object.

    Args:
        audio_url: A URL Deepgram can fetch (e.g. the bot's uploaded recording).
        model:     Deepgram model override (default DEEPGRAM_MODEL / nova-2-meeting).
        language:  Optional BCP-47 language hint. None → auto.

    Returns:
        The `transcript` dict (see module docstring).

    Raises:
        DeepgramError: credentials missing or the API call failed.
    """
    if not audio_url or "://" not in audio_url:
        raise DeepgramError(f"'{audio_url}' is not a valid audio URL.")

    opts = dict(_LISTEN_OPTS, model=model or DEFAULT_MODEL)
    if language:
        opts["language"] = language

    try:
        client = _client()
        response = client.listen.v1.media.transcribe_url(url=audio_url, **opts)
    except DeepgramError:
        raise
    except Exception as e:  # noqa: BLE001 - wrap SDK/transport errors with context
        raise DeepgramError(f"Deepgram transcription of '{audio_url}' failed — {e}") from e

    transcript = _build_transcript(response)
    _log.info(
        "deepgram.transcribe_url segments=%d chars=%d confidence=%.3f",
        len(transcript["segments"]), len(transcript["text"]), transcript["confidence"],
    )
    return transcript
