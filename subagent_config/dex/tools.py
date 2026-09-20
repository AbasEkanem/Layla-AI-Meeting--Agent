"""Dex's tools — Gmail (OAuth API primary, SMTP fallback).

Two tools, matching Dex's draft-first contract (skills/gmail_drafter, gmail_sender):
  - create_draft: compose a real Gmail draft (never sends). Approval gate acts on it.
  - send_draft:   strip [DRAFT], send the approved draft; SMTP fallback; idempotent.

Dex owns the email body: it renders references/email_template.md (assignee /
organiser / restricted-doc variants) and passes the finished text as `body`.
These tools do transport only — they never invent recipients or content.

Transport/auth helpers live in _gmail.py.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain.tools import tool

from . import _gmail


@tool
def create_draft(
    to_email: str,
    subject: str,
    body: str,
    bcc: str = "",
    cc: str = "",
) -> str:
    """Create a Gmail draft for one recipient. Does NOT send.

    Use this to compose the meeting follow-up. One draft per recipient (their own
    tickets first). Keep the `[DRAFT]` prefix in the subject — send_draft removes
    it on approval. Always BCC the user (pass their address as `bcc`).

    Args:
        to_email: The single confirmed recipient (from Layla's `recipients` — never
            a guessed or display-name-derived address).
        subject: Subject line, `[DRAFT]`-prefixed (e.g. "[DRAFT] Your action items — ...").
        body: The fully rendered email body (from references/email_template.md).
            Link the report via `doc_url`; never inline the full report.
        bcc: BCC address — normally the user. Required by contract in practice.
        cc: Optional CC address.

    Returns:
        The draft id and a confirmation, or an error string beginning with "ERROR:".
    """
    if not to_email or "@" not in to_email:
        return f"ERROR: '{to_email}' is not a valid recipient address."
    if not subject:
        return "ERROR: subject is required."
    try:
        msg = _gmail.build_mime(to=to_email, subject=subject, body=body, bcc=bcc, cc=cc)
        service = _gmail.gmail_service()
        draft = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": _gmail.mime_to_raw(msg)}})
            .execute()
        )
        return (
            f"DRAFT created (not sent)\n"
            f"draft_id: {draft['id']}\n"
            f"To: {to_email}   BCC: {bcc or '(none)'}\n"
            f"Subject: {subject}\n"
            f"Awaiting approval — call send_draft with this draft_id once approved."
        )
    except _gmail.GmailAuthError as e:
        return f"ERROR: Gmail auth not configured — {e}"
    except Exception as e:  # noqa: BLE001 - surface transport errors to the agent
        return f"ERROR: draft creation failed — {e}"


@tool
def send_draft(
    draft_id: str,
    already_sent_message_id: str = "",
) -> str:
    """Send a previously created, approved Gmail draft. Strips the [DRAFT] prefix first.

    Only call after explicit approval from Layla or the user. Idempotent: if this
    draft was already sent (pass the recorded message id as `already_sent_message_id`),
    it returns without re-sending — a duplicate send cannot be recalled.

    Tries the Gmail API first; on API failure, falls back to Gmail SMTP.

    Args:
        draft_id: The id returned by create_draft.
        already_sent_message_id: If non-empty, treated as proof this draft already
            sent (Layla's `idempotency_keys.gmail`); the tool stops instead of resending.

    Returns:
        Send status with the message id, or an error string beginning with "ERROR:".
    """
    if already_sent_message_id:
        return f"ALREADY SENT (idempotency): message_id {already_sent_message_id}. Not resending."
    if not draft_id:
        return "ERROR: draft_id is required."
    try:
        service = _gmail.gmail_service()
        # Fetch the draft's raw MIME so we can strip [DRAFT] and reuse it for SMTP fallback.
        draft = service.users().drafts().get(userId="me", id=draft_id, format="raw").execute()
        import base64  # noqa: PLC0415
        import email as _email  # noqa: PLC0415

        raw_bytes = base64.urlsafe_b64decode(draft["message"]["raw"])
        parsed = _email.message_from_bytes(raw_bytes)
        old_subject = parsed.get("Subject", "")
        new_subject = _gmail.strip_draft_prefix(old_subject)
        if new_subject != old_subject:
            parsed.replace_header("Subject", new_subject)
        new_raw = base64.urlsafe_b64encode(parsed.as_bytes()).decode()

        # Primary: update the draft's subject, then send the approved object.
        try:
            service.users().drafts().update(
                userId="me", id=draft_id, body={"message": {"raw": new_raw}}
            ).execute()
            sent = service.users().drafts().send(userId="me", body={"id": draft_id}).execute()
            return (
                f"SENT via Gmail API\n"
                f"message_id: {sent['id']}\n"
                f"Subject: {new_subject}\n"
                f"Record message_id as idempotency_keys.gmail before returning to Layla."
            )
        except Exception as api_err:  # noqa: BLE001 - fall back to SMTP
            _gmail.smtp_send(_email.message_from_bytes(base64.urlsafe_b64decode(new_raw)))
            mid = parsed.get("Message-ID", "(smtp — see Message-ID header)")
            return (
                f"SENT via SMTP fallback (Gmail API failed: {api_err})\n"
                f"message_id: {mid}\n"
                f"Subject: {new_subject}\n"
                f"Record message_id as idempotency_keys.gmail before returning to Layla."
            )
    except _gmail.GmailAuthError as e:
        return f"ERROR: Gmail auth not configured — {e}"
    except Exception as e:  # noqa: BLE001 - surface transport errors to the agent
        return f"ERROR: send failed — {e}. Do not retry blindly; check whether it sent."


# Grouped export referenced by agent.py's spec.
DEX_TOOLS: list[BaseTool] = [create_draft, send_draft]
