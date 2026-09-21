"""Milo — Jira transport helpers.

Auth and low-level Jira operations live here so tools.py stays focused on the
tool contract.  Mirrors the pattern in dex/_gmail.py and _shared/google_auth.py.

Authentication is Jira Cloud API token (Basic auth via atlassian-python-api).
All three credentials are required; the client raises JiraAuthError with setup
guidance if any are missing.

Environment variables (names only; values live in .env, which is gitignored):
  JIRA_URL         Atlassian base URL  e.g. https://yourorg.atlassian.net
  JIRA_EMAIL       Atlassian account email
  JIRA_API_TOKEN   API token from https://id.atlassian.com/manage-profile/security
"""

from __future__ import annotations

import os
import re

JIRA_URL = os.getenv("JIRA_URL", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

# Fixed labels applied to every Layla-generated ticket (Milo C3).
LAYLA_LABELS: list[str] = ["layla-generated", "meeting-action-item"]

# The Epic Link custom field id varies per Jira instance. 'customfield_10014' is
# the common Jira Cloud default, but company-managed/older instances differ and
# team-managed projects use `parent` instead. Make it overridable so a wrong id
# doesn't force a code change; create_jira_issue also retries WITHOUT the epic
# field if Jira rejects it, so a bad id never sinks an otherwise-valid ticket.
EPIC_LINK_FIELD = os.getenv("JIRA_EPIC_LINK_FIELD", "customfield_10014")


def is_field_error(exc: Exception) -> bool:
    """Heuristic: did Jira reject the request because of an unknown/invalid field?

    Used to decide whether to retry a create without the optional epic-link field.
    """
    msg = str(exc).lower()
    return any(
        tok in msg
        for tok in ("customfield", "epic", "field", "cannot be set", "unknown", "screen")
    )


class JiraAuthError(RuntimeError):
    """Raised when Jira credentials are missing or invalid, with setup guidance."""


def jira_client():
    """Return an authenticated atlassian.Jira client.

    Raises JiraAuthError if any of JIRA_URL, JIRA_EMAIL, or JIRA_API_TOKEN
    is unset — never silently falls back to unauthenticated.
    """
    missing = [
        name
        for name, val in (
            ("JIRA_URL", JIRA_URL),
            ("JIRA_EMAIL", JIRA_EMAIL),
            ("JIRA_API_TOKEN", JIRA_API_TOKEN),
        )
        if not val
    ]
    if missing:
        msg = (
            f"Jira credentials not configured. Missing env vars: {missing}. "
            "Set JIRA_URL (e.g. https://yourorg.atlassian.net), JIRA_EMAIL, "
            "and JIRA_API_TOKEN (from https://id.atlassian.com/manage-profile/security)."
        )
        raise JiraAuthError(msg)

    try:
        from atlassian import Jira  # noqa: PLC0415
    except ImportError as e:
        msg = "atlassian-python-api is not installed; cannot use Jira API."
        raise JiraAuthError(msg) from e

    return Jira(url=JIRA_URL, username=JIRA_EMAIL, password=JIRA_API_TOKEN, cloud=True)


# ── Priority mapping ──────────────────────────────────────────────────────────
# Authoritative table is skills/milo/priority_mapper/references/priority_table.md.
# This is the runtime lookup used by create_jira_issue.

# Signals per tier, mirroring the rows in priority_table.md. Strongest tier first
# so conflict resolution ("Critical > High > Medium > Low") falls out of the scan
# order. Bare "priority" from the reference is intentionally omitted — it collides
# with "low priority"/"high priority" and is too generic to grade on alone.
_PRIORITY_TIERS: list[tuple[str, tuple[str, ...]]] = [
    ("Critical", (
        "urgent", "critical", "asap", "blocker", "blocking", "blocked on",
        "on fire", "drop everything", "right now", "before anything else",
    )),
    ("High", (
        "important", "high priority", "high-priority", "needed", "need to",
        "must", "has to", "have to", "top of the list", "this sprint",
        "before the release",
    )),
    ("Medium", (
        "should", "recommended", "soon", "plan to", "want to", "would like",
        "next sprint", "fairly soon",
    )),
    ("Low", (
        "consider", "optional", "nice to have", "nice-to-have", "explore",
        "eventually", "at some point", "if there's time", "backlog", "park it",
        "someday", "low priority", "low-priority",
    )),
]

# A negation anywhere in the signal makes the grade ambiguous. priority_table.md
# is explicit: "If a priority_signal arrives with a negation in it, return Medium"
# (otherwise "not urgent" contains "urgent" and would wrongly map to Critical).
_NEGATION_RE = re.compile(r"n't\b|\b(?:not|never|no longer|isn't|aren't|wasn't|won't)\b")


def _signal_matches(needle: str, keyword: str) -> bool:
    """Whole-word match for single words, substring match for multi-word phrases.

    Per priority_table.md: "Substring match on the phrase, whole-word match on
    single words." Whole-word stops "urgent" matching inside "urgently"? no — it
    stops false hits like "must" inside "mustard" or "soon" inside "spoon".
    """
    if " " in keyword or "-" in keyword:
        return keyword in needle
    return re.search(rf"\b{re.escape(keyword)}\b", needle) is not None


def map_priority(priority_signal: str | None) -> str:
    """Map a verbatim priority_signal from Ivy's report to a Jira priority name.

    Falls back to "Medium" when the signal is absent, negated, or unrecognised —
    per priority_table.md (no signal / negation / no match → Medium). Never
    guesses Critical.

    Args:
        priority_signal: The raw string extracted by Ivy (may be None or empty).

    Returns:
        One of "Critical", "High", "Medium", "Low".
    """
    if not priority_signal:
        return "Medium"
    needle = priority_signal.strip().lower()
    if _NEGATION_RE.search(needle):
        return "Medium"
    # Strongest tier first → strongest signal wins on conflict.
    for level, keywords in _PRIORITY_TIERS:
        if any(_signal_matches(needle, kw) for kw in keywords):
            return level
    return "Medium"


# ── Idempotency ───────────────────────────────────────────────────────────────

def _escape_jql_string(value: str) -> str:
    r"""Escape a value for use inside a double-quoted JQL string literal.

    Backslash and double-quote carry meaning inside a JQL quoted string, so an
    unescaped summary containing " would break the query (or allow injection).
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def find_existing_ticket(jira, project_key: str, summary: str) -> str | None:
    """Return an existing issue key if a ticket with this EXACT summary already exists.

    Used before create_jira_issue to avoid duplicate tickets on retry (Milo C11).
    JQL is narrow: project + layla-generated label + summary phrase match. JQL's
    `summary ~` is a fuzzy text operator, so candidates are then filtered down to
    an EXACT (case-insensitive, trimmed) summary match before we call it a dupe —
    a fuzzy-only match could wrongly dedupe two similar-but-distinct action items.

    Returns the issue key (e.g. "PROJ-42") or None.
    """
    label = LAYLA_LABELS[0]  # "layla-generated"
    esc_project = _escape_jql_string(project_key)
    # Wrap the phrase in escaped quotes so Lucene treats it as one phrase, not tokens.
    esc_summary = _escape_jql_string(summary)
    jql = (
        f'project = "{esc_project}" '
        f'AND labels = "{label}" '
        f'AND summary ~ "\\"{esc_summary}\\""'
    )
    try:
        results = jira.jql(jql, limit=10, fields=["summary"])
        target = summary.strip().casefold()
        for issue in (results or {}).get("issues", []):
            found = (issue.get("fields", {}).get("summary") or "").strip().casefold()
            if found == target:
                return issue["key"]
    except Exception:  # noqa: BLE001 — surface nothing here; caller handles
        pass
    return None
