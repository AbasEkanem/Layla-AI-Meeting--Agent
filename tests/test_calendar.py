"""Capture step-0 pure logic: conference-URI selection (never a phone number),
roster derivation, and meeting_metadata assembly / presence reconciliation."""

from capture._calendar import build_meeting_metadata, build_roster, conference_uri


def test_conference_uri_prefers_video():
    event = {
        "conferenceData": {"entryPoints": [
            {"entryPointType": "phone", "uri": "tel:+123"},
            {"entryPointType": "video", "uri": "https://meet.google.com/abc"},
        ]},
        "hangoutLink": "https://meet.google.com/legacy",
    }
    assert conference_uri(event) == "https://meet.google.com/abc"


def test_conference_uri_falls_back_hangout_then_sip():
    e1 = {
        "conferenceData": {"entryPoints": [{"entryPointType": "phone", "uri": "tel:+1"}]},
        "hangoutLink": "https://meet.google.com/legacy",
    }
    assert conference_uri(e1) == "https://meet.google.com/legacy"
    e2 = {"conferenceData": {"entryPoints": [{"entryPointType": "sip", "uri": "sip:room@x"}]}}
    assert conference_uri(e2) == "sip:room@x"


def test_conference_uri_never_returns_phone():
    e = {"conferenceData": {"entryPoints": [{"entryPointType": "phone", "uri": "tel:+1555"}]}}
    assert conference_uri(e) is None


def test_conference_uri_none_when_absent():
    assert conference_uri({}) is None


def test_build_roster_calendar_invite_keeps_emails_and_aliases():
    md = {
        "calendar_event_id": "evt1",
        "attendees": [{"display_name": "Marcus Chen", "email": "marcus@x.com", "present": True}],
    }
    r = build_roster(md)
    assert r["source"] == "calendar_invite"
    entry = r["entries"][0]
    assert entry["email"] == "marcus@x.com"
    assert entry["aliases"] == ["Marcus Chen", "Marcus"]
    assert entry["present"] is True


def test_build_roster_bot_display_names_nulls_email_and_dedupes_alias():
    md = {
        "calendar_event_id": None,
        "attendees": [{"display_name": "Marcus", "email": None, "present": True}],
    }
    r = build_roster(md)
    assert r["source"] == "bot_display_names"
    assert r["entries"][0]["email"] is None
    assert r["entries"][0]["aliases"] == ["Marcus"]


def test_build_meeting_metadata_bot_only_path():
    event = {}  # no calendar id -> bot_display_names path
    bot = {
        "bot_id": "bot-9",
        "started_at": "2026-09-23T10:00:00Z",
        "ended_at": "2026-09-23T10:30:00Z",
        "participants": ["Dana", "Eli"],
    }
    md = build_meeting_metadata(event, bot)
    assert md["calendar_event_id"] is None
    assert md["meeting_id"] == "bot-9"
    assert md["duration_minutes"] == 30
    assert sorted(a["display_name"] for a in md["attendees"]) == ["Dana", "Eli"]
    assert all(a["email"] is None and a["present"] is True for a in md["attendees"])


def test_build_meeting_metadata_calendar_path_reconciles_presence():
    event = {
        "id": "evt1",
        "summary": "Sync",
        "start": {"dateTime": "2026-09-23T10:00:00Z"},
        "attendees": [
            {"displayName": "Dana", "email": "dana@x.com"},
            {"displayName": "Frank", "email": "frank@x.com"},
        ],
        "conferenceData": {"entryPoints": [{"entryPointType": "video", "uri": "https://meet.google.com/z"}]},
    }
    bot = {"started_at": "2026-09-23T10:00:00Z", "ended_at": "2026-09-23T10:20:00Z", "participants": ["Dana"]}
    md = build_meeting_metadata(event, bot)
    assert md["calendar_event_id"] == "evt1"
    assert md["meeting_id"] == "evt1#2026-09-23T10:00:00Z"
    assert md["conference_uri"] == "https://meet.google.com/z"
    by_name = {a["display_name"]: a for a in md["attendees"]}
    assert by_name["Dana"]["present"] is True
    assert by_name["Frank"]["present"] is False
    assert by_name["Frank"]["email"] == "frank@x.com"
