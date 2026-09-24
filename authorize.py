#!/usr/bin/env python
"""One-time OAuth consent bootstrap for Layla's Google APIs (project-layla).

`subagent_config/_shared/google_auth.py::load_credentials()` deliberately never
opens a browser — it only *reads* an already-minted token and refreshes it. This
script performs that one-time interactive consent: it opens the Google consent
screen for the project-layla Desktop OAuth client and writes the resulting token
(including a refresh token) to GOOGLE_OAUTH_TOKEN, so every subagent can then
authenticate headlessly.

Run once — and again only if the scope set in google_auth.SCOPES changes:

    python authorize.py

It reads the SAME env vars / defaults as google_auth.py so the two stay in sync:
    GOOGLE_OAUTH_CLIENT   client-secrets JSON  (default: client_secret.json)
    GOOGLE_OAUTH_TOKEN    where to write token (default: .gmail_token.json)

Override per run:
    python authorize.py --client "C:\\path\\to\\client_secret_2039....json"

SECURITY: neither the client secret nor the minted token is ever committed (both
are gitignored). The token grants offline access to your Google account — treat
.gmail_token.json as a secret.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Keep the consent scopes identical to what the app actually requests at runtime.
from subagent_config._shared.google_auth import SCOPES

_DEFAULT_CLIENT = os.getenv("GOOGLE_OAUTH_CLIENT", "client_secret.json")
_DEFAULT_TOKEN = os.getenv("GOOGLE_OAUTH_TOKEN", ".gmail_token.json")


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="One-time Google OAuth consent for Layla (project-layla).")
    p.add_argument("--client", default=_DEFAULT_CLIENT,
                   help="OAuth client-secrets JSON (Desktop app). Default: %(default)s")
    p.add_argument("--token", default=_DEFAULT_TOKEN,
                   help="Where to write the authorized token JSON. Default: %(default)s")
    p.add_argument("--port", type=int, default=0,
                   help="Local port for the consent redirect (0 = auto-pick). Default: %(default)s")
    p.add_argument("--force", action="store_true",
                   help="Re-run consent even if a valid token covering all scopes already exists.")
    return p.parse_args(argv)


def _already_authorized(token_path: str) -> bool:
    """True if token_path already holds a refresh token covering the full SCOPES set.

    Reads the granted scopes straight from the token JSON (not via Credentials,
    which would just echo back the scopes we pass in) so the check reflects what
    Google actually granted.
    """
    if not os.path.exists(token_path):
        return False
    try:
        with open(token_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    granted = set(data.get("scopes") or [])
    return bool(data.get("refresh_token")) and set(SCOPES).issubset(granted)


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
    except ImportError:
        print("ERROR: google-auth-oauthlib is not installed.\n"
              "       pip install google-auth-oauthlib", file=sys.stderr)
        return 2

    if not os.path.exists(args.client):
        print(f"ERROR: client-secrets file not found: {args.client}\n"
              "       Point --client at your project-layla Desktop OAuth client, e.g.\n"
              '       python authorize.py --client "C:\\Users\\...\\client_secret_2039...json"',
              file=sys.stderr)
        return 2

    if not args.force and _already_authorized(args.token):
        print(f"A valid token already exists at '{args.token}' covering all scopes — "
              "nothing to do (use --force to re-consent).")
        return 0

    flow = InstalledAppFlow.from_client_secrets_file(args.client, SCOPES)
    # access_type=offline + prompt=consent => Google returns a refresh token, even
    # on re-auth. The refresh token is what survives long-term; its 7-day expiry
    # only applies while the OAuth consent screen is still in "Testing".
    creds = flow.run_local_server(
        port=args.port,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Opening your browser to authorize Layla for Google APIs…",
        success_message="Authorization complete — you can close this tab and return to the terminal.",
    )

    with open(args.token, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())

    if not creds.refresh_token:
        print("WARNING: no refresh token was returned. Re-run with --force and make sure you "
              "grant offline access at the consent screen.", file=sys.stderr)

    print(f"\n\u2713 Token written to '{args.token}'  ({len(SCOPES)} scopes: "
          "gmail.compose/send, documents, drive, forms.body, calendar.readonly).")
    print("  google_auth.load_credentials() will now authenticate headlessly.")
    print("\nReminder: if the OAuth consent screen is still in 'Testing', this token's refresh "
          "stops working after 7 days. Publish the app to 'In production' (project-layla-509609) "
          "to remove that limit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
