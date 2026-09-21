"""Vera — Slack transport helpers.

Auth and low-level Slack SDK operations live here so tools.py stays focused on
the tool contract.  Mirrors the pattern in dex/_gmail.py.

Authentication uses a Slack Bot Token (xoxb-...).  The bot must be installed in
any channel it posts to — "not in channel" is a failure to report to Layla, not
an invitation to join uninvited (Vera C11).

Environment variables (names only; values live in .env, which is gitignored):
  SLACK_BOT_TOKEN   Slack Bot OAuth token — starts with xoxb-
"""

from __future__ import annotations

import os

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")


class SlackAuthError(RuntimeError):
    """Raised when the Slack bot token is missing or invalid, with setup guidance."""


def slack_client():
    """Return an authenticated slack_sdk.WebClient.

    Raises SlackAuthError if SLACK_BOT_TOKEN is unset.
    """
    if not SLACK_BOT_TOKEN:
        msg = (
            "Slack credentials not configured. "
            "Set SLACK_BOT_TOKEN to a Bot OAuth token (xoxb-...) in .env. "
            "Obtain one from https://api.slack.com/apps → OAuth & Permissions."
        )
        raise SlackAuthError(msg)

    try:
        from slack_sdk import WebClient  # noqa: PLC0415
    except ImportError as e:
        msg = "slack-sdk is not installed; cannot use Slack API."
        raise SlackAuthError(msg) from e

    return WebClient(token=SLACK_BOT_TOKEN)


# ── Channel membership ────────────────────────────────────────────────────────

def is_bot_in_channel(client, channel_id: str) -> bool:
    """Return True if the bot is a member of the given channel.

    Uses conversations.info — does NOT join the channel.  A False result means
    Vera must report a failure to Layla, not attempt to join.
    """
    try:
        resp = client.conversations_info(channel=channel_id)
        return bool(resp.get("channel", {}).get("is_member", False))
    except Exception:  # noqa: BLE001
        return False


# ── Channel ID resolution ─────────────────────────────────────────────────────

def resolve_channel(client, channel: str) -> str:
    """Resolve a channel name (e.g. '#eng') or raw ID to a Slack channel ID.

    Strips a leading '#'.  If the value already looks like a Slack channel ID
    (starts with 'C'), returns it unchanged.

    Returns the channel ID string, or raises SlackAuthError if not found.
    """
    channel = channel.lstrip("#")
    # Slack channel names are always lowercase, so an all-uppercase token starting
    # with C (public), G (legacy private) or D (DM) is already an ID — pass it
    # through. startswith("C") alone missed private-channel/DM ids.
    if channel[:1] in ("C", "G", "D") and channel.isupper():
        return channel  # already an ID

    try:
        # conversations.list paginates; iterate until found or exhausted. Include
        # private channels — a name-based lookup of a private channel returns
        # nothing under the default public-only types.
        cursor = None
        while True:
            kwargs: dict = {
                "limit": 200,
                "exclude_archived": True,
                "types": "public_channel,private_channel",
            }
            if cursor:
                kwargs["cursor"] = cursor
            resp = client.conversations_list(**kwargs)
            for ch in resp.get("channels", []):
                if ch.get("name") == channel or ch.get("name_normalized") == channel:
                    return ch["id"]
            cursor = resp.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
    except Exception as e:  # noqa: BLE001
        raise SlackAuthError(f"Slack API error resolving channel '{channel}': {e}") from e

    raise SlackAuthError(
        f"Channel '#{channel}' not found. Check the name or add the bot to the workspace."
    )
