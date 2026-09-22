"""Step 0 — Google Calendar poller.

Polls Google Calendar for meetings about to start, pulls attendees[] into
meeting_metadata + roster, and returns the conference URI so the capture
orchestrator knows where to send the bot.

This is infrastructure, not a subagent — no reasoning happens here.

Auth: shared via subagent_config/_shared/google_auth.py.
Scope required: https://www.googleapis.com/auth/calendar.readonly
(Added to _shared/google_auth.py SCOPES before calling this module.)

Environment variables (names only; values live in .env):
  CALENDAR_POLL_WINDOW_MINUTES   How far ahead to look for meetings (default: 10)
  CALENDAR_LEAD_TIME_SECONDS     How many seconds before start to dispatch bot (default: 60)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

_log = logging.getLogger(__name__)

POLL_WINDOW_MINUTES = int(os.getenv("CALENDAR_POLL_WINDOW_MINUTES", "10"))
LEAD_TIME_SECONDS = int(os.getenv("CALENDAR_LEAD_TIME_SECONDS", "60"))

# entryPointType values the bot can actually JOIN as a meeting, in fallback
# order. "phone" (a tel: dial-in) is deliberately excluded — step 3 dispatches
# the bot to this URI, and the bot joins a video/SIP meeting, not a phone number.
_JOINABLE_ENTRY_TYPES = ("video", "sip", "more")


def _calendar_service():
    """Return an authenticated Google Calendar API v3 client."""
    # calendar.readonly scope must be in _shared/google_auth.py SCOPES.
    from subagent_config._shared.google_auth import get_service  # noqa: PLC0415
    return get_service("calendar")


def _extract_conference_uri(event: dict) -> str | None:
    """Return a conference URI the bot can join, or None.

    Prefers a Google Meet video endpoint, then the legacy hangoutLink, then any
    other joinable (SIP/generic) endpoint. A phone (tel:) dial-in is never
    returned — the bot joins a meeting, not a phone number.
    """
    entry_points = event.get("conferenceData", {}).get("entryPoints", [])
    # 1) Prefer a video endpoint (Google Meet).
    for entry in entry_points:
        if entry.get("entryPointType") == "video" and entry.get("uri"):
            return entry["uri"]
    # 2) Legacy Google Meet field.
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    # 3) Last resort: another joinable (non-phone) endpoint.
    for entry in entry_points:
        if entry.get("entryPointType") in _JOINABLE_ENTRY_TYPES and entry.get("uri"):
            return entry["uri"]
    return None


def _build_attendee(raw: dict, present_names: set[str]) -> dict:
    """Convert a raw calendar attendee dict to Layla's attendee schema."""
    display = raw.get("displayName") or raw.get("email", "").split("@")[0]
    return {
        "display_name": display,
        "email": raw.get("email"),           # authoritative identity — never None from calendar
        "response_status": raw.get("responseStatus"),
        "present": display in present_names, # reconciled after bot session ends
        "joined_at": None,                   # filled by reconcile_participants()
        "left_at": None,
    }


def poll_upcoming_meetings(
    calendars: list[str] | None = None,
) -> list[dict]:
    """Return calendar events starting within the next POLL_WINDOW_MINUTES.

    Args:
        calendars: List of calendar IDs to check. Defaults to ['primary'].

    Returns:
        List of raw Google Calendar event objects that have a conference URI.
    """
    service = _calendar_service()
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(minutes=POLL_WINDOW_MINUTES)

    calendars = calendars or ["primary"]
    upcoming: list[dict] = []

    for cal_id in calendars:
        try:
            events_result = (
                service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=now.isoformat(),
                    timeMax=window_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            for event in events_result.get("items", []):
                # A cancelled instance still appears under singleEvents — never
                # dispatch a bot to a meeting that was called off.
                if event.get("status") == "cancelled":
                    continue
                uri = _extract_conference_uri(event)
                if uri:
                    upcoming.append(event)
        except Exception as e:  # noqa: BLE001
            _log.warning("[calendar] Could not fetch calendar '%s': %s", cal_id, e)

    return upcoming


def build_meeting_metadata(
    event: dict,
    bot_session: dict,
) -> dict:
    """Assemble meeting_metadata from a calendar event + bot session record.

    Args:
        event:       Raw Google Calendar event object.
        bot_session: Dict produced by the meeting bot after the session ends.
                     Expected keys: started_at, ended_at, participants (list of display names).

    Returns:
        meeting_metadata dict matching state_schema.md.
    """
    cal_event_id = event.get("id")
    instance_start = (
        event.get("start", {}).get("dateTime")
        or event.get("start", {}).get("date", "")
    )
    meeting_id = f"{cal_event_id}#{instance_start}" if cal_event_id else bot_session.get("bot_id", "unknown")

    started_at = bot_session.get("started_at", instance_start)
    ended_at = bot_session.get("ended_at")

    # Duration from actual times, not the scheduled slot.
    try:
        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        duration_minutes = max(1, int((end_dt - start_dt).total_seconds() / 60))
    except Exception:  # noqa: BLE001
        duration_minutes = 0

    # Reconcile bot participants against the invite. Bot participant display names
    # only set `present` on invitees — they never become attendees themselves.
    present_names: set[str] = {p.strip() for p in bot_session.get("participants", [])}

    if cal_event_id:
        # calendar_invite path: attendees are the invitees ONLY. A participant the
        # bot saw who is not on the invite gets NO entry (roster_contract row 3) —
        # a task spoken in their name resolves to unresolved_claim downstream, never
        # to a synthesised, unassignable identity. A display name is also
        # attacker-settable, so admitting one into the roster would let injected
        # transcript text resolve against it instead of being flagged.
        attendees = [_build_attendee(a, present_names) for a in event.get("attendees", [])]
    else:
        # bot_display_names path: no invite list exists, so the bot's participants
        # ARE the roster — email None, nothing assignable, per roster_contract.
        attendees = [
            {
                "display_name": name,
                "email": None,
                "response_status": None,
                "present": True,
                "joined_at": None,
                "left_at": None,
            }
            for name in sorted(present_names)
        ]

    organiser = event.get("organizer", {}).get("email")

    return {
        "meeting_id": meeting_id,
        "calendar_event_id": cal_event_id,
        "title": event.get("summary", "Untitled Meeting"),
        "date": instance_start[:10] if instance_start else "",
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_minutes": duration_minutes,
        "organiser_email": organiser,
        "conference_uri": _extract_conference_uri(event) or bot_session.get("conference_uri", ""),
        "attendees": attendees,
    }


def build_roster(meeting_metadata: dict) -> dict:
    """Derive roster from meeting_metadata per state_schema.md.

    source is 'calendar_invite' when calendar_event_id is non-null,
    'bot_display_names' otherwise. Determined here, never set by hand.
    """
    has_calendar = meeting_metadata.get("calendar_event_id") is not None
    source = "calendar_invite" if has_calendar else "bot_display_names"

    entries = []
    for a in meeting_metadata.get("attendees", []):
        display = a["display_name"]
        # Aliases in contract order: [display_name, first token]. Dedupe a
        # single-word name without reordering (a set would lose the order).
        first = display.split()[0] if display else ""
        aliases = [display] + ([first] if first and first != display else [])
        entries.append({
            "email": a["email"] if has_calendar else None,
            "display_name": display,
            "aliases": aliases,
            "present": a.get("present", False),
        })

    return {"source": source, "entries": entries}


def conference_uri(event: dict) -> str | None:
    """Public accessor: the joinable conference URI for a calendar event, or None.

    This is the link the Attendee bot is dispatched to (capture._attendee.dispatch_bot).
    """
    return _extract_conference_uri(event)


def get_lead_time_seconds() -> int:
    """Seconds before a meeting starts at which the bot should be dispatched."""
    return LEAD_TIME_SECONDS
