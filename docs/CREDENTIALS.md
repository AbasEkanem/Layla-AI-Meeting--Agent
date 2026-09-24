# Getting your credentials

Layla integrates with several external services. **Each one degrades
gracefully** — its tools return an `ERROR: … auth not configured` string until
the relevant variable is set — so you can add credentials one at a time and test
each subagent in isolation.

All secrets live in **`.env`** (gitignored, never committed). Non-secret defaults
are already filled in; this guide covers the ones you need to obtain.

## Summary

| Service | `.env` variable(s) | Needed for | Cost | Get it at |
|---------|--------------------|------------|------|-----------|
| Anthropic | `ANTHROPIC_API_KEY` | The model (Layla + all subagents) | Paid | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| Google OAuth | `GOOGLE_OAUTH_CLIENT`, `GOOGLE_OAUTH_TOKEN` | Ivy (Docs/Drive), Dex (Gmail/Forms), capture (Calendar) | Free | [console.cloud.google.com](https://console.cloud.google.com/) |
| Deepgram *or* | `DEEPGRAM_API_KEY` | Transcription (capture) | Free tier | [console.deepgram.com](https://console.deepgram.com/signup) |
| Attendee.dev | `ATTENDEE_API_KEY` | Meeting-bot transcript (capture) | — | [app.attendee.dev](https://app.attendee.dev) |
| Jira | `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` | Milo (tickets) | Free | [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens) |
| Slack | `SLACK_BOT_TOKEN` | Vera (notifications) | Free | [api.slack.com/apps](https://api.slack.com/apps) |

> You need a model key + Google, one capture source, and (for the full pipeline)
> Jira and Slack — **5 credentials** in total.

---

## 1. Anthropic (the model)

1. Go to **https://console.anthropic.com/settings/keys**.
2. *Create Key*, copy it.
3. Set `ANTHROPIC_API_KEY` in `.env`.

You can swap in OpenAI or Google instead — uncomment the matching line in `.env`
and set that provider's key.

## 2. Google Workspace OAuth

Layla uses **one** OAuth consent that covers five Google APIs — Docs, Drive,
Gmail, Forms, and Calendar. You need a Desktop OAuth client, those APIs enabled,
the consent screen published, and a token minted once.

**Console: https://console.cloud.google.com/**

**a. Enable the five APIs.** At
[the API library](https://console.cloud.google.com/apis/library) enable each of:
*Google Docs API*, *Google Drive API*, *Gmail API*, *Google Forms API*,
*Google Calendar API*.

**b. Create the OAuth client (Desktop app).** At
[Credentials](https://console.cloud.google.com/apis/credentials) →
*Create Credentials → OAuth client ID → Application type: **Desktop app*** →
download the JSON → save it as `client_secret.json` in the project root (or point
`GOOGLE_OAUTH_CLIENT` at wherever you keep it).

**c. Publish the consent screen — this is the 7-day-expiry fix.** At the
[OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
→ **Publish App** (status *In production*). Click through the "unverified app"
warning; you do **not** need Google verification for your own account. Do this
**before** minting the token — refresh tokens issued while the app is in *Testing*
expire after 7 days regardless of the credential file.

**d. Mint the token.** Run:

```bash
python authorize.py
```

It opens your browser, grants the 6 scopes, and writes `.gmail_token.json`. After
that, `google_auth.load_credentials()` authenticates headlessly forever (as long
as the app stays in production).

Fills `GOOGLE_OAUTH_CLIENT` (step b) and `GOOGLE_OAUTH_TOKEN` (step d). Free.

## 3. Transcript capture — pick one

Layla needs a transcript source; you only need **one** of these.

### Option A — Deepgram (direct transcription)

1. Sign up at **https://console.deepgram.com/signup**.
2. In the console, open *API Keys* → *Create a New API Key*.
3. Set `DEEPGRAM_API_KEY`. (`DEEPGRAM_MODEL` defaults to `nova-2-meeting`.)

Free credit tier, then pay-as-you-go.

### Option B — Attendee.dev (meeting bot)

A bot joins the call and returns the transcript — an alternative to transcribing
audio yourself.

1. Sign in at **https://app.attendee.dev** (matches `ATTENDEE_API_BASE`).
2. Open account settings → *API Keys*. Docs: **https://docs.attendee.dev**.
3. Set `ATTENDEE_API_KEY`. (`ATTENDEE_API_BASE` / `ATTENDEE_BOT_NAME` have defaults.)

---

## 4. Jira (Milo → tickets)

1. Create a token at
   **https://id.atlassian.com/manage-profile/security/api-tokens** →
   *Create API token* → sets `JIRA_API_TOKEN`.
2. `JIRA_URL` = your site, e.g. `https://your-company.atlassian.net`.
3. `JIRA_EMAIL` = the Atlassian account email that owns the token.

`JIRA_EPIC_LINK_FIELD` defaults to `customfield_10014`; change it only if your
instance uses a different Epic Link custom field. Free on Atlassian Cloud.

---

## 5. Slack (Vera → notifications)

1. Go to **https://api.slack.com/apps** → *Create New App* → *From scratch*.
2. **OAuth & Permissions** → under **Bot Token Scopes** add: `chat:write`,
   `channels:read`, `groups:read` (Vera posts messages and does a membership
   check before posting).
3. **Install to Workspace**, then copy the **Bot User OAuth Token** (`xoxb-…`)
   into `SLACK_BOT_TOKEN`.
4. **Invite the bot** into each channel it should post to (`/invite @yourbot`) —
   Vera refuses to post to a channel it wasn't invited to.

Free.

---

## Applying your `.env`

Fill each value in `.env` as you obtain it. Note that `.env` is not auto-loaded
everywhere yet (`loadenv.py` is a stub), so until env-loading is wired into the
entrypoint, either export the variables in your shell or make sure `load_dotenv()`
runs at startup.
