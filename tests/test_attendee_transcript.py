"""Trust-critical: the Attendee bot transcript shaper must strip attacker-settable
display names down to first-seen diarization labels and never leak them."""

import pytest

from capture._attendee import AttendeeError, _utterances_to_transcript, dispatch_bot


def _utt(uuid, name, text, ts=0, dur=1000, conf=None):
    transcription = {"transcript": text}
    if conf is not None:
        transcription["confidence"] = conf
    return {
        "speaker_uuid": uuid,
        "speaker_name": name,
        "timestamp_ms": ts,
        "duration_ms": dur,
        "transcription": transcription,
    }


def test_display_names_dropped_and_labelled_first_seen():
    utts = [
        _utt("uuid-A", "Alice Attacker", "hello", ts=0, dur=1000),
        _utt("uuid-B", "Bob", "hi there", ts=1000, dur=500),
        _utt("uuid-A", "Alice Attacker", "again", ts=2000, dur=1000),
    ]
    out = _utterances_to_transcript(utts)
    labels = [s["speaker_label"] for s in out["segments"]]
    assert labels == ["Speaker 0", "Speaker 1", "Speaker 0"]
    # No spoken/display name may survive into any field of the state object.
    blob = repr(out)
    for leak in ("Alice", "Attacker", "Bob"):
        assert leak not in blob


def test_empty_and_whitespace_text_skipped():
    utts = [
        _utt("u", "X", "   "),
        _utt("u", "X", ""),
        _utt("u", "X", "real"),
    ]
    out = _utterances_to_transcript(utts)
    assert len(out["segments"]) == 1
    assert out["segments"][0]["text"] == "real"


def test_timing_source_and_text_join():
    utts = [
        _utt("u", "X", "one", ts=0, dur=1000),
        _utt("v", "Y", "two", ts=1000, dur=500),
    ]
    out = _utterances_to_transcript(utts)
    assert out["source"] == "deepgram"
    assert out["text"] == "one two"
    assert (out["segments"][0]["start_ms"], out["segments"][0]["end_ms"]) == (0, 1000)
    assert (out["segments"][1]["start_ms"], out["segments"][1]["end_ms"]) == (1000, 1500)


def test_confidence_mean_and_zero_when_absent():
    out = _utterances_to_transcript([_utt("u", "X", "a", conf=0.9), _utt("u", "X", "b", conf=0.7)])
    assert out["confidence"] == pytest.approx(0.8)
    assert _utterances_to_transcript([_utt("u", "X", "a")])["confidence"] == 0.0


def test_empty_input_is_empty_transcript():
    out = _utterances_to_transcript([])
    assert out["text"] == ""
    assert out["segments"] == []
    assert out["confidence"] == 0.0
    assert out["source"] == "deepgram"


def test_dispatch_bot_rejects_bad_url_before_network():
    with pytest.raises(AttendeeError):
        dispatch_bot("not-a-url")
    with pytest.raises(AttendeeError):
        dispatch_bot("")
