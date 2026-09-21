"""Dex — Google Forms transport helpers.

Handles Forms API auth and low-level operations.  Docs and Drive already have
their own helpers (ivy/_docs.py, ivy/_drive.py); Forms is Dex-specific.

Google Forms API v1 is used.  The scope 'https://www.googleapis.com/auth/forms.body'
has been added to _shared/google_auth.py — widening the scope union invalidates
any cached token and requires re-running the one-time consent flow.

Environment variables: none additional — auth is shared via _shared/google_auth.py.

Form creation policy (Dex C5):
  Only create a Google Form if there is a clear collection need — not by default.
  The agent decides; these tools execute.
"""

from __future__ import annotations

from .._shared.google_auth import GoogleAuthError, get_service

# Re-export under the Dex-familiar name so tools.py has a single import.
FormsAuthError = GoogleAuthError


def forms_service():
    """Return an authenticated Google Forms API v1 client."""
    return get_service("forms")


# ── Seed question sets ────────────────────────────────────────────────────────
# Authoritative templates live in skills/dex/google_form_creator/references/form_templates.md.
# These are the runtime defaults used by add_form_questions when collection_type is provided.

_SEED_QUESTIONS: dict[str, list[dict]] = {
    "feedback": [
        {
            "title": "How would you rate this meeting overall?",
            "questionItem": {
                "question": {
                    "required": True,
                    "scaleQuestion": {"low": 1, "high": 5, "lowLabel": "Poor", "highLabel": "Excellent"},
                }
            },
        },
        {
            "title": "What went well?",
            "questionItem": {"question": {"required": False, "textQuestion": {"paragraph": True}}},
        },
        {
            "title": "What could be improved?",
            "questionItem": {"question": {"required": False, "textQuestion": {"paragraph": True}}},
        },
    ],
    "rsvp": [
        {
            "title": "Will you attend the next meeting?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [{"value": "Yes"}, {"value": "No"}, {"value": "Maybe"}],
                    },
                }
            },
        },
        {
            "title": "If you cannot attend, please share your reason (optional).",
            "questionItem": {"question": {"required": False, "textQuestion": {"paragraph": False}}},
        },
    ],
    "action_item_check": [
        {
            "title": "Which action items are you responsible for?",
            "questionItem": {"question": {"required": True, "textQuestion": {"paragraph": True}}},
        },
        {
            "title": "Do you have everything you need to complete your action items?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [{"value": "Yes"}, {"value": "No — I need help"}],
                    },
                }
            },
        },
    ],
}


def get_seed_questions(collection_type: str) -> list[dict]:
    """Return seed question items for a known collection type.

    Args:
        collection_type: One of 'feedback', 'rsvp', 'action_item_check'.

    Returns:
        List of Forms API item dicts, or an empty list if type is unknown.
    """
    return _SEED_QUESTIONS.get(collection_type.lower().replace(" ", "_"), [])
