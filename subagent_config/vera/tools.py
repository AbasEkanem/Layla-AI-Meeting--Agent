"""Vera's tools — Slack (messages, DMs, threads, user lookup, membership check).

Exposed as VERA_TOOLS and referenced by agent.py's spec.

Six tools, matching Vera's prompt contract (skills/vera/*):
  - post_slack_message          : Block Kit channel post; records message_ts (C10, S2)
  - reply_in_thread             : thread reply to an existing post (thread_manager skill)
  - send_slack_dm               : DM to a user ID (plain text, not Block Kit — per skill)
  - lookup_slack_user_by_email  : email → Slack user ID (for @mentions and DMs)
  - check_channel_membership    : is the bot in this channel? (C11 — never joins uninvited)
  - get_permalink               : stable URL for a posted message (S2 — channel+thread reported separately)

Not tools — pure skill/prompt logic:
  - SENT / PARTIAL / FAILED status computation → status_reporter skill + agent reasoning
  - Channel routing decision                  → channel_routing skill + agent reasoning
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain.tools import tool

from . import _slack


@tool
def post_slack_message(
    channel: str,
    blocks: str,
    text: str,
    already_posted_ts: str = "",
) -> str:
    """Post a Block Kit message to a Slack channel. Records message_ts immediately.

    Vera must verify bot membership (check_channel_membership) before calling this.
    Idempotent: if already_posted_ts is non-empty it is treated as proof this channel
    already received its post for this run — the tool returns without posting again (C10).

    Args:
        channel:           Channel name (e.g. '#eng') or Slack channel ID ('C0123ABC').
        blocks:            JSON string of Slack Block Kit blocks array.
                           Use the template in skills/vera/block_kit_composer/references/.
        text:              Fallback plain text (shown in notifications / accessibility).
                           Required — do not leave empty even when blocks are provided.
        already_posted_ts: If non-empty, treated as proof this channel already posted
                           (Layla's idempotency record). The tool stops instead of reposting.

    Returns:
        'POSTED  channel=C0123  ts=1234567890.123456  (record ts before next post)'
        'ALREADY_POSTED (idempotency): ts=...'
        or 'ERROR: ...'
    """
    if already_posted_ts:
        return f"ALREADY_POSTED (idempotency): ts={already_posted_ts}. Not reposting."
    if not channel:
        return "ERROR: channel is required. Confirm routing with channel_routing skill first."
    if not text:
        return "ERROR: text (fallback) is required even when blocks are provided."

    import json  # noqa: PLC0415

    try:
        client = _slack.slack_client()
        channel_id = _slack.resolve_channel(client, channel)

        # Parse blocks if provided as a string.
        parsed_blocks = None
        if blocks:
            try:
                parsed_blocks = json.loads(blocks)
            except json.JSONDecodeError as e:
                return f"ERROR: blocks is not valid JSON — {e}. Check block_kit_composer output."

        kwargs: dict = {"channel": channel_id, "text": text}
        if parsed_blocks:
            kwargs["blocks"] = parsed_blocks

        resp = client.chat_postMessage(**kwargs)
        ts = resp["ts"]
        return (
            f"POSTED  channel={channel_id}  ts={ts}\n"
            f"Record ts immediately. Call get_permalink({channel_id}, {ts}) for the report URL."
        )

    except _slack.SlackAuthError as e:
        return f"ERROR: Slack auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        err = str(e)
        if "not_in_channel" in err:
            return (
                f"ERROR: not_in_channel — the bot is not a member of '{channel}'. "
                "Report this failure to Layla. Do not attempt to join the channel."
            )
        return f"ERROR: post failed — {err}"


@tool
def reply_in_thread(
    channel: str,
    thread_ts: str,
    blocks: str,
    text: str,
    already_posted_ts: str = "",
) -> str:
    """Post a reply in an existing Slack thread (thread_manager skill).

    Use for long content: summary in the channel post, details in the thread.
    The prompt rule is: >5 rows in the ticket table → split to thread.

    Args:
        channel:           Channel name or ID of the parent post.
        thread_ts:         The ts from the parent post_slack_message call.
        blocks:            JSON string of Block Kit blocks. May be empty for plain replies.
        text:              Fallback plain text. Required.
        already_posted_ts: Idempotency guard — same contract as post_slack_message.

    Returns:
        'THREAD_REPLIED  channel=C0123  ts=...'
        or 'ERROR: ...'
    """
    if already_posted_ts:
        return f"ALREADY_POSTED (idempotency): ts={already_posted_ts}. Not reposting."
    if not channel:
        return "ERROR: channel is required."
    if not thread_ts:
        return "ERROR: thread_ts is required. Use the ts returned by post_slack_message."
    if not text:
        return "ERROR: text is required."

    import json  # noqa: PLC0415

    try:
        client = _slack.slack_client()
        channel_id = _slack.resolve_channel(client, channel)

        parsed_blocks = None
        if blocks:
            try:
                parsed_blocks = json.loads(blocks)
            except json.JSONDecodeError as e:
                return f"ERROR: blocks is not valid JSON — {e}."

        kwargs: dict = {"channel": channel_id, "thread_ts": thread_ts, "text": text}
        if parsed_blocks:
            kwargs["blocks"] = parsed_blocks

        resp = client.chat_postMessage(**kwargs)
        ts = resp["ts"]
        return (
            f"THREAD_REPLIED  channel={channel_id}  ts={ts}  thread_ts={thread_ts}\n"
            f"Record ts. Call get_permalink({channel_id}, {ts}) for the thread reply URL."
        )

    except _slack.SlackAuthError as e:
        return f"ERROR: Slack auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: thread reply failed — {e}"


@tool
def send_slack_dm(
    user_id: str,
    text: str,
    already_posted_ts: str = "",
) -> str:
    """Send a direct message to a Slack user (plain text — DMs skip Block Kit).

    Opens a DM conversation and posts plain text.  Requires a Slack user ID
    (use lookup_slack_user_by_email first).

    Args:
        user_id:           Slack user ID (e.g. 'U0123ABC'). Must start with 'U' or 'W'.
        text:              The message body. Plain text only — no blocks for DMs.
        already_posted_ts: Idempotency guard — if set, skip without sending.

    Returns:
        'DM_SENT  user=U0123  ts=...'
        or 'ERROR: ...'
    """
    if already_posted_ts:
        return f"ALREADY_SENT (idempotency): ts={already_posted_ts}. Not resending."
    if not user_id or not (user_id.startswith("U") or user_id.startswith("W")):
        return (
            f"ERROR: '{user_id}' does not look like a Slack user ID (must start with U or W). "
            "Use lookup_slack_user_by_email to get the correct ID."
        )
    if not text:
        return "ERROR: text is required."

    try:
        client = _slack.slack_client()
        # Open (or retrieve) the DM channel.
        conv = client.conversations_open(users=[user_id])
        dm_channel = conv["channel"]["id"]
        resp = client.chat_postMessage(channel=dm_channel, text=text)
        ts = resp["ts"]
        return f"DM_SENT  user={user_id}  channel={dm_channel}  ts={ts}"

    except _slack.SlackAuthError as e:
        return f"ERROR: Slack auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: DM send failed — {e}"


@tool
def lookup_slack_user_by_email(email: str) -> str:
    """Resolve an email address to a Slack user ID and display name.

    Use before send_slack_dm and before any actionable @mention in Block Kit.
    Only call with an email from owner_resolved — never from a spoken name.

    Args:
        email: Confirmed email address (from Layla's owner_resolved or recipients).

    Returns:
        'user_id=U0123ABC  display_name=Jane Smith  email=jane@example.com'
        'NOT_FOUND: no Slack user matches <email>'
        or 'ERROR: ...'
    """
    if not email or "@" not in email:
        return f"ERROR: '{email}' is not a valid email address."

    try:
        client = _slack.slack_client()
        resp = client.users_lookupByEmail(email=email)
        user = resp["user"]
        return (
            f"user_id={user['id']}  "
            f"display_name={user.get('real_name', user.get('name', '?'))}  "
            f"email={user.get('profile', {}).get('email', email)}"
        )

    except _slack.SlackAuthError as e:
        return f"ERROR: Slack auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        err = str(e)
        if "users_not_found" in err or "user_not_found" in err:
            return f"NOT_FOUND: no Slack user matches '{email}'. Do not @mention or DM — report unresolved."
        return f"ERROR: user lookup failed — {err}"


@tool
def check_channel_membership(channel: str) -> str:
    """Check whether the bot is a member of a Slack channel.

    Vera must call this before post_slack_message. A channel the bot is not in
    is a failure to report to Layla — never an invitation to join uninvited (C11).

    Args:
        channel: Channel name (e.g. '#eng') or Slack channel ID ('C0123ABC').

    Returns:
        'MEMBER  channel=C0123ABC  name=#eng'
        'NOT_MEMBER  channel=C0123ABC  name=#eng  → Report failure to Layla. Do not join.'
        or 'ERROR: ...'
    """
    if not channel:
        return "ERROR: channel is required."

    try:
        client = _slack.slack_client()
        channel_id = _slack.resolve_channel(client, channel)
        is_member = _slack.is_bot_in_channel(client, channel_id)

        # Get channel name for the report.
        try:
            info = client.conversations_info(channel=channel_id)
            name = "#" + info["channel"].get("name", channel_id)
        except Exception:  # noqa: BLE001
            name = channel_id

        if is_member:
            return f"MEMBER  channel={channel_id}  name={name}"
        return (
            f"NOT_MEMBER  channel={channel_id}  name={name}\n"
            "Report this as a failure to Layla. Do not attempt to join the channel."
        )

    except _slack.SlackAuthError as e:
        return f"ERROR: Slack auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: membership check failed — {e}"


@tool
def get_permalink(channel_id: str, message_ts: str) -> str:
    """Get the permanent URL for a posted Slack message.

    Channel post and thread reply URLs are reported separately (Vera S2).
    Call this after every successful post_slack_message or reply_in_thread.

    Args:
        channel_id:  Slack channel ID (e.g. 'C0123ABC') — not a name.
        message_ts:  The ts returned by the post tool.

    Returns:
        'permalink=https://yourworkspace.slack.com/archives/C0123/p1234567890123456'
        or 'ERROR: ...'
    """
    if not channel_id:
        return "ERROR: channel_id is required (use the ID returned by post_slack_message)."
    if not message_ts:
        return "ERROR: message_ts is required."

    try:
        client = _slack.slack_client()
        resp = client.chat_getPermalink(channel=channel_id, message_ts=message_ts)
        return f"permalink={resp['permalink']}"

    except _slack.SlackAuthError as e:
        return f"ERROR: Slack auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: permalink fetch failed — {e}"


# Grouped export referenced by agent.py's spec.
VERA_TOOLS: list[BaseTool] = [
    post_slack_message,
    reply_in_thread,
    send_slack_dm,
    lookup_slack_user_by_email,
    check_channel_membership,
    get_permalink,
]
