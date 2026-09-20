"""Dex — Gmail transport layer (OAuth API primary, SMTP fallback).

Shared auth + MIME + rendering helpers used by tools.py. Kept private (leading
underscore) so tools.py exposes only the two @tool functions Dex actually calls.

Transport contract (matches subagent_config/dex/skills/gmail_*):
  - Drafting  → Gmail API `users.drafts.create` (a real draft object → stable
    draft_id, which is what the approval gate approves).
  - Sending   → Gmail API `users.drafts.send` primary; SMTP the resilience path.

Auth: OAuth via a cached token file. Interactive consent (browser) is a one-time
manual step run outside this process — see `load_credentials` for the env vars
and the setup error message.

Environment variables (names only; values live in .env, which is gitignored):
  GMAIL_ADDRESS          sending account; also the default BCC target
  GMAIL_OAUTH_TOKEN      path to cached OAuth token JSON (default ./.gmail_token.json)
  GMAIL_OAUTH_CLIENT     path to OAuth client-secrets JSON (for the one-time consent)
  GMAIL_APP_PASSWORD     app password for the SMTP fallback path only
"""

from __future__ import annotations

import base64
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

# Scopes: compose covers drafts.create/update; send covers drafts.send.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
_TOKEN_PATH = os.getenv("GMAIL_OAUTH_TOKEN", ".gmail_token.json")
_CLIENT_PATH = os.getenv("GMAIL_OAUTH_CLIENT", "client_secret.json")

_DRAFT_PREFIX = re.compile(r"^\s*\[DRAFT\]\s*", re.IGNORECASE)


class GmailAuthError(RuntimeError):
    """Raised when OAuth credentials are missing or unusable, with setup guidance."""


def load_credentials():
    """Load cached OAuth credentials, refreshing if expired.

    Does NOT launch interactive consent — that is a one-time manual step. If no
    valid token exists, raises GmailAuthError with instructions rather than
    blocking on a browser prompt.
    """
    try:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        from google.oauth2.credentials import Credentials  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - deps are in requirements
        msg = "google-auth is not installed; cannot use the Gmail API."
        raise GmailAuthError(msg) from e

    if not os.path.exists(_TOKEN_PATH):
        msg = (
            f"No Gmail OAuth token at '{_TOKEN_PATH}'. Run the one-time consent "
            f"flow to create it (using client secrets at '{_CLIENT_PATH}' and "
            f"scopes {SCOPES}), or set GMAIL_OAUTH_TOKEN to an existing token. "
            "The SMTP fallback still works with GMAIL_ADDRESS + GMAIL_APP_PASSWORD."
        )
        raise GmailAuthError(msg)

    creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(_TOKEN_PATH, "w", encoding="utf-8") as fh:
                fh.write(creds.to_json())
        else:
            msg = f"Gmail OAuth token at '{_TOKEN_PATH}' is invalid and cannot be refreshed. Re-run consent."
            raise GmailAuthError(msg)
    return creds


def gmail_service():
    """Return an authenticated Gmail API service client."""
    from googleapiclient.discovery import build  # noqa: PLC0415

    return build("gmail", "v1", credentials=load_credentials(), cache_discovery=False)


# ── Rendering ────────────────────────────────────────────────────────────────
def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML for email bodies (headings, lists, emphasis)."""
    lines = text.split("\n")
    out: list[str] = []
    in_ul = False

    def close() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    def inline(s: str) -> str:
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
        return s

    for raw in lines:
        line = raw.rstrip()
        h = re.match(r"^(#{1,4})\s+(.*)", line)
        bullet = re.match(r"^\s*[-*•]\s+(.*)", line)
        if h:
            close()
            lvl = len(h.group(1))
            out.append(f'<h{lvl} style="margin:16px 0 6px;color:#1a1a2e;">{inline(h.group(2))}</h{lvl}>')
        elif bullet:
            if not in_ul:
                out.append('<ul style="margin:8px 0 8px 20px;color:#333;">')
                in_ul = True
            out.append(f'<li style="margin:3px 0;">{inline(bullet.group(1))}</li>')
        elif not line:
            close()
            out.append('<div style="height:8px;"></div>')
        else:
            close()
            out.append(f'<p style="margin:0 0 6px;color:#333;line-height:1.6;">{inline(line)}</p>')
    close()
    return "\n".join(out)


def build_html_email(subject: str, body: str) -> str:
    """Wrap a rendered body in a neutral, client-safe HTML shell."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;padding:28px 12px;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;border:1px solid #e3e5e8;overflow:hidden;">
        <tr><td style="padding:20px 28px 8px;">
          <h1 style="margin:0;font-size:18px;font-weight:700;color:#1a1a2e;line-height:1.35;">{subject}</h1>
        </td></tr>
        <tr><td style="padding:4px 28px 24px;font-size:14px;">{_md_to_html(body)}</td></tr>
        <tr><td style="padding:14px 28px;border-top:1px solid #eceef0;background:#fafbfc;">
          <p style="margin:0;font-size:11px;color:#8a8f98;text-align:center;">Sent by Layla AI on behalf of the meeting organiser</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


# ── MIME ─────────────────────────────────────────────────────────────────────
def build_mime(*, to: str, subject: str, body: str, bcc: str = "", cc: str = "") -> MIMEMultipart:
    """Build a multipart/alternative message (plain + HTML) with headers set."""
    msg = MIMEMultipart("alternative")
    msg["From"] = f"Layla AI <{GMAIL_ADDRESS}>" if GMAIL_ADDRESS else "Layla AI"
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(build_html_email(subject, body), "html", "utf-8"))
    return msg


def mime_to_raw(msg: MIMEMultipart) -> str:
    """base64url-encode a MIME message for the Gmail API `raw` field."""
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def strip_draft_prefix(subject: str) -> str:
    """Remove a leading [DRAFT] token from a subject (gmail_sender step 2)."""
    return _DRAFT_PREFIX.sub("", subject)


def smtp_send(msg: MIMEMultipart) -> None:
    """Send an already-built MIME message via Gmail SMTP (fallback path)."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        msg_err = "SMTP fallback needs GMAIL_ADDRESS + GMAIL_APP_PASSWORD."
        raise GmailAuthError(msg_err)
    recipients = [msg[h] for h in ("To", "Cc", "Bcc") if msg[h]]
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, recipients, msg.as_string())
