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

Two modes, same output schema:
  - Prerecorded (`transcribe_file` / `transcribe_url`): a finished recording →
    transcript in one call, segments from Deepgram's `utterances`.
  - Live (`LiveSession`): a WebSocket the meeting bot streams PCM into in real
    time; `TranscriptAccumulator` groups the word stream into per-speaker segments
    and builds the same transcript object when the session ends.

SDK: deepgram-sdk 7.x (Fern-generated) — `DeepgramClient().listen.v1.media`
(prerecorded) and `.listen.v1.connect(...)` (live WebSocket).

Environment variables (names only; values live in .env, which is gitignored):
  DEEPGRAM_API_KEY   Deepgram project API key
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Callable

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


# ── Live streaming ────────────────────────────────────────────────────────────
# The meeting bot streams raw PCM into a Deepgram WebSocket in real time. Deepgram
# returns word-level results with speaker labels; TranscriptAccumulator groups the
# words into per-speaker segments and produces the same `transcript` object the
# prerecorded path does.

@dataclass
class _Utterance:
    """One accumulated speaker turn, built from Deepgram's streamed word events."""
    speaker_label: str
    start_s: float
    end_s: float
    words: list[str] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(self.words)

    def to_segment(self, index: int) -> dict:
        return {
            "segment_id": f"seg-{index}",
            "speaker_label": self.speaker_label,
            "start_ms": int(round(self.start_s * 1000)),
            "end_ms": int(round(self.end_s * 1000)),
            "text": self.text.strip(),
        }


class TranscriptAccumulator:
    """Thread-safe builder that turns Deepgram's streamed word events into the
    `transcript` schema.

    Only FINAL results contribute to the transcript. Interim (`is_final=False`)
    messages repeat words as a turn is refined, so accumulating them would double
    count — they are for live display only and are dropped here. Words are grouped
    into a segment per contiguous speaker; a segment flushes when the speaker
    changes or a final message ends.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._segments: list[dict] = []
        self._current: _Utterance | None = None
        self._all_confidences: list[float] = []
        self._seg_index = 0

    def on_results(self, message) -> None:
        """Feed one Deepgram Results message (ListenV1Results). Non-Results/interim ignored."""
        try:
            # Only Results messages carry a channel; Metadata/UtteranceEnd don't.
            channel = getattr(message, "channel", None)
            if channel is None:
                return
            if not bool(getattr(message, "is_final", False)):
                return  # interim → display only, never accumulated

            alternatives = getattr(channel, "alternatives", None) or []
            if not alternatives:
                return
            words = getattr(alternatives[0], "words", None) or []
            if not words:
                return

            with self._lock:
                for w in words:
                    text = getattr(w, "punctuated_word", None) or getattr(w, "word", "") or ""
                    speaker_label = f"Speaker {getattr(w, 'speaker', 0) or 0}"
                    start_s = float(getattr(w, "start", 0.0) or 0.0)
                    end_s = float(getattr(w, "end", start_s) or start_s)
                    conf = float(getattr(w, "confidence", 0.0) or 0.0)

                    if self._current is None:
                        self._current = _Utterance(speaker_label, start_s, end_s)
                    elif speaker_label != self._current.speaker_label:
                        self._flush_current()
                        self._current = _Utterance(speaker_label, start_s, end_s)

                    self._current.words.append(text)
                    self._current.confidences.append(conf)
                    self._current.end_s = end_s
                    self._all_confidences.append(conf)

                # A final message ends a turn — flush what we have.
                self._flush_current()
        except Exception as e:  # noqa: BLE001 - a bad event must not kill the stream
            _log.warning("[deepgram] error processing results event: %s", e)

    def _flush_current(self) -> None:
        """Append _current to segments and clear it. Caller holds the lock."""
        if self._current and self._current.words:
            self._segments.append(self._current.to_segment(self._seg_index))
            self._seg_index += 1
        self._current = None

    def build_transcript(self) -> dict:
        """Return the assembled `transcript` object (state_schema.md format)."""
        with self._lock:
            if self._current and self._current.words:
                self._flush_current()
            segs = list(self._segments)
            all_conf = list(self._all_confidences)
        text = " ".join(s["text"] for s in segs).strip()
        confidence = round(sum(all_conf) / len(all_conf), 4) if all_conf else 0.0
        return {
            "text": text,
            "segments": segs,
            "source": "deepgram",
            "confidence": confidence,
        }


class LiveSession:
    """A Deepgram live-transcription WebSocket session for the meeting bot.

    Usage:
        session = LiveSession()
        with session.connect() as conn:
            while audio_available:
                conn.send(pcm_chunk)      # raw linear16 PCM bytes
        transcript = session.get_transcript()

    The audio source (the meeting bot) is external — this class owns only the
    Deepgram side. `start_listening()` blocks, so it runs on a background thread;
    `conn.send()` feeds media from the caller's thread. Errors surfaced by the
    socket are captured and readable via `had_error()` / `error()`.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        language: str | None = None,
        encoding: str = "linear16",
        sample_rate: int = 16000,
        channels: int = 1,
        on_interim: Callable[[str], None] | None = None,
    ) -> None:
        """Args mirror a PCM bot feed. `on_interim` (optional) receives interim
        transcript text for live display; pass None to disable interim results."""
        self._model = model or DEFAULT_MODEL
        self._language = language
        self._encoding = encoding
        self._sample_rate = sample_rate
        self._channels = channels
        self._on_interim = on_interim
        self._accumulator = TranscriptAccumulator()
        self._error: Exception | None = None

    def connect(self):
        """Context manager: open the WebSocket and yield a handle with `.send(bytes)`."""
        client = _client()  # raises DeepgramError if key/SDK missing
        try:
            from deepgram.core.events import EventType  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            raise DeepgramError("deepgram-sdk is missing the streaming API.") from e

        opts: dict = {
            "model": self._model,
            "encoding": self._encoding,
            "sample_rate": self._sample_rate,
            "channels": self._channels,
            "diarize": True,
            "punctuate": True,
            "smart_format": True,
            # Interim results only matter when someone consumes them for display.
            "interim_results": self._on_interim is not None,
        }
        if self._language:
            opts["language"] = self._language

        session = self

        class _Conn:
            def __init__(self, socket):
                self._socket = socket

            def send(self, chunk: bytes) -> None:
                """Send a chunk of raw PCM audio to Deepgram."""
                self._socket.send_media(chunk)

        def _on_message(message):
            # Interim results (if requested) feed the live-display callback only.
            if session._on_interim is not None:
                ch = getattr(message, "channel", None)
                if ch is not None and not bool(getattr(message, "is_final", False)):
                    try:
                        txt = ch.alternatives[0].transcript
                        if txt:
                            session._on_interim(txt)
                    except Exception:  # noqa: BLE001
                        pass
            session._accumulator.on_results(message)

        def _on_error(err):
            _log.error("[deepgram] websocket error: %s", err)
            session._error = err if isinstance(err, Exception) else Exception(str(err))

        class _CM:
            _connect_cm = None
            _socket = None
            _thread: threading.Thread | None = None

            def __enter__(cm):
                try:
                    cm._connect_cm = client.listen.v1.connect(**opts)
                    cm._socket = cm._connect_cm.__enter__()
                except Exception as e:  # noqa: BLE001
                    raise DeepgramError(f"Deepgram live connect failed — {e}") from e

                cm._socket.on(EventType.MESSAGE, _on_message)
                cm._socket.on(EventType.ERROR, _on_error)
                # start_listening() blocks running the recv loop — run it off-thread
                # so the caller can send media on this one.
                cm._thread = threading.Thread(
                    target=cm._socket.start_listening, name="deepgram-listen", daemon=True
                )
                cm._thread.start()
                return _Conn(cm._socket)

            def __exit__(cm, *exc):
                try:
                    # Signal end-of-audio so Deepgram emits final results and closes.
                    cm._socket.send_close_stream()
                except Exception:  # noqa: BLE001 - best effort; close the CM regardless
                    pass
                try:
                    cm._connect_cm.__exit__(*exc)  # closes the WebSocket
                except Exception as e:  # noqa: BLE001
                    _log.warning("[deepgram] error closing live session: %s", e)
                finally:
                    if cm._thread is not None:
                        cm._thread.join(timeout=10.0)
                return False

        return _CM()

    def get_transcript(self) -> dict:
        """Return the assembled `transcript` object after the session ends."""
        return self._accumulator.build_transcript()

    def had_error(self) -> bool:
        return self._error is not None

    def error(self) -> Exception | None:
        return self._error
