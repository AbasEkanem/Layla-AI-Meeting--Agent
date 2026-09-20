"""Shared Google OAuth for Layla's subagents — one token, one consent, all APIs.

Dex (Gmail) and Ivy (Docs/Drive) authenticate through here so credentials load
in exactly one place. A single cached token covers the union of scopes below, so
the one-time browser consent is done once, not per service.

`get_service(api)` returns an authenticated client for "gmail", "docs", or
"drive". `retry_media(fn)` retries a call through transient connection drops.

Auth: OAuth via a cached token file. Interactive consent (browser) is a one-time
manual step run outside this process — `load_credentials` raises with guidance
rather than blocking on a prompt if no valid token exists.

Environment variables (names only; values live in .env, which is gitignored):
  GOOGLE_OAUTH_TOKEN     path to cached OAuth token JSON (default ./.gmail_token.json)
  GOOGLE_OAUTH_CLIENT    path to OAuth client-secrets JSON (for the one-time consent)
"""

from __future__ import annotations

import logging
import os
import time

_log = logging.getLogger(__name__)

# Union of scopes across all subagents. One token, granted once, serves every
# service. Narrow by design: drive.file (only files the app creates/opens), not
# the broad drive scope — nothing here deletes or bulk-shares arbitrary files.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",  # Dex: drafts.create/update
    "https://www.googleapis.com/auth/gmail.send",     # Dex: drafts.send
    "https://www.googleapis.com/auth/documents",      # Ivy: create + batchUpdate docs
    "https://www.googleapis.com/auth/drive.file",     # Ivy: sharing state of its own doc
]

# Discovery names + versions for build(); one entry per API a subagent may need.
_API_VERSIONS = {
    "gmail": "v1",
    "docs": "v1",
    "drive": "v3",
}

_TOKEN_PATH = os.getenv("GOOGLE_OAUTH_TOKEN", ".gmail_token.json")
_CLIENT_PATH = os.getenv("GOOGLE_OAUTH_CLIENT", "client_secret.json")

_TRANSIENT_NET_ERRORS = (
    ConnectionError,
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    TimeoutError,
    OSError,  # WinError 10053/10054 arrive as OSError subclasses
)
_MEDIA_MAX_ATTEMPTS = 4


class GoogleAuthError(RuntimeError):
    """Raised when OAuth credentials are missing or unusable, with setup guidance."""


def load_credentials():
    """Load cached OAuth credentials, refreshing if expired.

    Does NOT launch interactive consent — that is a one-time manual step. Raises
    GoogleAuthError with instructions if no valid token exists.
    """
    try:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        from google.oauth2.credentials import Credentials  # noqa: PLC0415
    except ImportError as e:  # pragma: no cover - deps are in requirements
        msg = "google-auth is not installed; cannot use Google APIs."
        raise GoogleAuthError(msg) from e

    if not os.path.exists(_TOKEN_PATH):
        msg = (
            f"No Google OAuth token at '{_TOKEN_PATH}'. Run the one-time consent "
            f"flow to create it (client secrets at '{_CLIENT_PATH}', scopes "
            f"{SCOPES}), or set GOOGLE_OAUTH_TOKEN to an existing token."
        )
        raise GoogleAuthError(msg)

    creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(_TOKEN_PATH, "w", encoding="utf-8") as fh:
                fh.write(creds.to_json())
        else:
            msg = f"Google OAuth token at '{_TOKEN_PATH}' is invalid and cannot be refreshed. Re-run consent."
            raise GoogleAuthError(msg)
    return creds


def get_service(api: str):
    """Return an authenticated Google API client for 'gmail', 'docs', or 'drive'."""
    if api not in _API_VERSIONS:
        msg = f"Unknown Google API '{api}'. Known: {sorted(_API_VERSIONS)}."
        raise GoogleAuthError(msg)
    from googleapiclient.discovery import build  # noqa: PLC0415

    return build(api, _API_VERSIONS[api], credentials=load_credentials(), cache_discovery=False)


def _is_transient_net_error(exc: Exception) -> bool:
    if isinstance(exc, _TRANSIENT_NET_ERRORS):
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("10053", "10054", "aborted", "reset by peer", "broken pipe", "connection")
    )


def retry_media(fn, *, what: str = "google api call"):
    """Run a Google API call, retrying transient connection drops with backoff."""
    last_exc: Exception | None = None
    for attempt in range(1, _MEDIA_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - decide retry vs re-raise below
            last_exc = exc
            if attempt >= _MEDIA_MAX_ATTEMPTS or not _is_transient_net_error(exc):
                raise
            backoff = 0.5 * (2 ** (attempt - 1))  # 0.5s, 1s, 2s
            _log.warning(
                "[google_auth] %s transient error (attempt %d/%d): %s — retrying in %.1fs",
                what, attempt, _MEDIA_MAX_ATTEMPTS, exc, backoff,
            )
            time.sleep(backoff)
    if last_exc:
        raise last_exc
    return None
