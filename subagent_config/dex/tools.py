"""Dex — Gmail & Google Forms tools.

Two Gmail tools (built), four Google Forms tools (now added):

Gmail (draft-first, idempotent):
  - create_draft   : compose a real Gmail draft; never sends. Approval gate acts on it.
  - send_draft     : strip [DRAFT], send the approved draft; SMTP fallback; idempotent.

Google Forms (Dex C5 — only when there is a clear collection need):
  - create_google_form            : new form with title + description
  - add_form_questions            : append questions from a seed set or custom list
  - set_form_response_destination : link to Google Sheets (>3 q's) or email notification
  - get_form_url                  : return the responder URL (or SKIPPED)

Dex owns the email body (rendered from references/email_template.md) and the form
decision (rendered from references/form_templates.md).  These tools do transport
only — they never invent recipients, questions, or content.

Gmail transport/auth helpers live in _gmail.py.
Forms transport helpers live in _forms.py.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain.tools import tool

from . import _gmail
from . import _forms


# ── Gmail tools ───────────────────────────────────────────────────────────────

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


# ── Google Forms tools ────────────────────────────────────────────────────────

@tool
def create_google_form(title: str, description: str = "") -> str:
    """Create a new Google Form. Call only when there is a clear collection need (C5).

    The form is created in DRAFT state — no responder link is live until
    get_form_url is called to confirm it.  Title follows the convention:
    '{meeting} — {purpose} {date}' (see skills/dex/google_form_creator/references/).

    Args:
        title:       Form title. Convention: '<Meeting Name> — <Purpose> <Date>'.
        description: Optional form description shown to respondents.

    Returns:
        'CREATED  form_id=abc123  edit_url=https://docs.google.com/forms/d/abc123/edit'
        or 'ERROR: ...'
    """
    if not title:
        return "ERROR: title is required."

    try:
        service = _forms.forms_service()
        # Forms API create() accepts ONLY info.title (and documentTitle); any other
        # info field — including description — is rejected. Set the description in a
        # follow-up updateFormInfo batchUpdate instead.
        form = service.forms().create(body={"info": {"title": title}}).execute()
        form_id = form["formId"]

        if description:
            service.forms().batchUpdate(
                formId=form_id,
                body={
                    "requests": [
                        {
                            "updateFormInfo": {
                                "info": {"description": description},
                                "updateMask": "description",
                            }
                        }
                    ]
                },
            ).execute()

        edit_url = f"https://docs.google.com/forms/d/{form_id}/edit"
        return (
            f"CREATED  form_id={form_id}\n"
            f"edit_url={edit_url}\n"
            f"Call add_form_questions to seed questions, then get_form_url for the responder link."
        )

    except _forms.FormsAuthError as e:
        return f"ERROR: Forms auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: form creation failed — {e}"


@tool
def add_form_questions(
    form_id: str,
    collection_type: str = "",
    custom_questions_json: str = "",
) -> str:
    """Append questions to an existing Google Form.

    Either provide a collection_type to use a seed set from form_templates.md,
    or provide custom_questions_json for a bespoke list.  Both can be combined —
    seed questions are added first, then custom ones.

    Args:
        form_id:               The form_id returned by create_google_form.
        collection_type:       One of 'feedback', 'rsvp', 'action_item_check'.
                               Uses the seed set from skills/dex/google_form_creator/references/.
        custom_questions_json: Optional JSON array of additional question objects
                               in Forms API item format. Added after the seed set.

    Returns:
        'QUESTIONS_ADDED  form_id=...  count=N'
        or 'ERROR: ...'
    """
    if not form_id:
        return "ERROR: form_id is required."
    if not collection_type and not custom_questions_json:
        return "ERROR: provide collection_type, custom_questions_json, or both."

    import json  # noqa: PLC0415

    questions: list[dict] = []

    if collection_type:
        seed = _forms.get_seed_questions(collection_type)
        if not seed:
            known = list(_forms._SEED_QUESTIONS.keys())
            return (
                f"ERROR: unknown collection_type '{collection_type}'. "
                f"Known types: {known}. Use custom_questions_json for bespoke questions."
            )
        questions.extend(seed)

    if custom_questions_json:
        try:
            extra = json.loads(custom_questions_json)
            if not isinstance(extra, list):
                return "ERROR: custom_questions_json must be a JSON array of question objects."
            questions.extend(extra)
        except json.JSONDecodeError as e:
            return f"ERROR: custom_questions_json is not valid JSON — {e}"

    if not questions:
        return "ERROR: no questions to add."

    try:
        service = _forms.forms_service()

        # Build batchUpdate requests.
        requests = [
            {"createItem": {"item": q, "location": {"index": i}}}
            for i, q in enumerate(questions)
        ]
        service.forms().batchUpdate(
            formId=form_id, body={"requests": requests}
        ).execute()

        return f"QUESTIONS_ADDED  form_id={form_id}  count={len(questions)}"

    except _forms.FormsAuthError as e:
        return f"ERROR: Forms auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: adding questions failed — {e}"


@tool
def set_form_response_destination(
    form_id: str,
    destination_type: str = "email",
    spreadsheet_id: str = "",
) -> str:
    """Report how to collect a Google Form's responses. (Forms API v1 limitation — read carefully.)

    IMPORTANT: the Google Forms API v1 CANNOT link a Sheets response destination
    or toggle per-response email notifications — those are Forms-UI-only actions.
    There is no `responseReceipts` field in FormSettings, and `forms.watches` push
    to a Cloud Pub/Sub topic, not to a Drive/Sheets file. This tool therefore does
    NOT mutate the form; it verifies the form exists and returns the supported path
    so Dex can route correctly instead of silently failing.

    Responses are ALWAYS retained on the form regardless of destination, and can be
    read programmatically via forms.responses.list.

    Args:
        form_id:          The form_id returned by create_google_form.
        destination_type: 'sheets' or 'email'. Informational — see the note above.
        spreadsheet_id:   Ignored (kept for call-site compatibility); the API cannot
                          link a spreadsheet. Left in the guidance for the human step.

    Returns:
        'DESTINATION_NOOP  form_id=...  type=...  <guidance>'  (not an error — the
        form is usable; only the destination wiring is a manual/read-side step)
        or 'ERROR: ...' if the form_id is invalid or auth is missing.
    """
    if not form_id:
        return "ERROR: form_id is required."

    dtype = destination_type.lower().strip()
    if dtype not in ("sheets", "email"):
        return f"ERROR: destination_type must be 'sheets' or 'email', got '{destination_type}'."

    try:
        service = _forms.forms_service()
        # A real, valid call: confirm the form exists (and that auth works) rather
        # than issuing an unsupported updateSettings/watches request that would 400.
        service.forms().get(formId=form_id).execute()

        if dtype == "sheets":
            target = f" (intended target: {spreadsheet_id})" if spreadsheet_id else ""
            return (
                f"DESTINATION_NOOP  form_id={form_id}  type=sheets{target}\n"
                "Forms API v1 cannot link a Sheets destination. Link it once in the "
                "Forms UI (Responses → Link to Sheets), or read responses directly via "
                "forms.responses.list. Responses are retained on the form regardless."
            )

        return (
            f"DESTINATION_NOOP  form_id={form_id}  type=email\n"
            "Forms API v1 cannot enable per-response email notifications. Turn them on "
            "in the Forms UI (Responses → ⋮ → Get email notifications), or poll "
            "forms.responses.list. Responses are retained on the form regardless."
        )

    except _forms.FormsAuthError as e:
        return f"ERROR: Forms auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: could not verify form {form_id} — {e}"


@tool
def get_form_url(form_id: str) -> str:
    """Return the responder URL for a published Google Form.

    Include this URL in the meeting follow-up email body so recipients can
    fill in the form.  Returns SKIPPED if form_id is empty (meaning no form
    was created this run — Dex C5).

    Args:
        form_id: The form_id returned by create_google_form. Pass '' to skip.

    Returns:
        'form_url=https://docs.google.com/forms/d/e/<publishedId>/viewform'
        'SKIPPED  (no form created this run)'
        or 'ERROR: ...'
    """
    if not form_id:
        return "SKIPPED  (no form created this run — no collection need identified)"

    try:
        service = _forms.forms_service()
        form = service.forms().get(formId=form_id).execute()
        responder_uri = form.get("responderUri", "")
        if responder_uri:
            return f"form_url={responder_uri}"
        # Fall back to constructing from the published ID if present.
        pub_id = form.get("publishedFormId", "")
        if pub_id:
            return f"form_url=https://docs.google.com/forms/d/e/{pub_id}/viewform"
        return (
            f"ERROR: form {form_id} has no responder URI yet. "
            "Ensure the form has been published (it may need at least one question)."
        )

    except _forms.FormsAuthError as e:
        return f"ERROR: Forms auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: fetching form URL failed — {e}"


# Grouped exports referenced by agent.py's spec.
DEX_TOOLS: list[BaseTool] = [
    # Gmail
    create_draft,
    send_draft,
    # Google Forms
    create_google_form,
    add_form_questions,
    set_form_response_destination,
    get_form_url,
]
