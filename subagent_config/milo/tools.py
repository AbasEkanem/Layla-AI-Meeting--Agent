"""Milo's tools — Jira (create issue, find assignee, inspect projects).

Exposed as MILO_TOOLS and referenced by agent.py's spec.

Three tools, matching Milo's prompt contract (skills/milo/*):
  - create_jira_issue   : core ticket creation; one per action item (C1), idempotent (C11)
  - find_jira_assignee  : email → Jira Cloud accountId (required before assigning — C9)
  - list_jira_projects  : all project keys visible to the token (backs project_router skill)

Not tools — pure skill/prompt logic:
  - Priority mapping decision  → map_priority() in _jira.py + prompt/priority_mapper skill
  - Project routing decision   → project_router skill + agent reasoning
  - Ticket field templating    → jira_ticket_creator skill references
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langchain.tools import tool

from . import _jira


@tool
def create_jira_issue(
    project_key: str,
    summary: str,
    description: str,
    priority_signal: str = "",
    assignee_account_id: str = "",
    issue_type: str = "Task",
    epic_key: str = "",
    due_date: str = "",
) -> str:
    """Create a single Jira issue for one action item. Never bundles multiple tasks.

    Idempotent: if a ticket with this summary already exists in the project
    (tagged 'layla-generated'), returns the existing key without creating a duplicate.
    Record the returned key immediately — do NOT batch and record at the end (C11).

    Milo constraints enforced here:
    - Applies fixed labels 'layla-generated' and 'meeting-action-item' (C3).
    - Create-only: never modifies existing tickets (C6).
    - Assigns only when assignee_account_id is provided (use find_jira_assignee first).
      A raw spoken name is a routing bug; pass '' to leave unassigned (C9).

    Args:
        project_key:         Confirmed Jira project key (e.g. 'ENG', 'PROD'). Must exist.
        summary:             Verb-first summary ≤80 chars (e.g. 'Audit API rate limits').
        description:         Full description. Must include the Google Doc URL (C4).
                             Rendered as Jira wiki markup or plain text.
        priority_signal:     Verbatim priority_signal from Ivy's report (e.g. 'urgent').
                             Mapped to Jira priority by map_priority(). Pass '' for no signal → Medium.
        assignee_account_id: Jira Cloud accountId from find_jira_assignee. Pass '' to leave unassigned.
        issue_type:          'Task' (default), 'Story', or 'Bug'. Infer from action item content.
        epic_key:            Optional parent epic key (e.g. 'ENG-10'). Linked via Epic Link field.
        due_date:            Optional ISO-8601 date string (e.g. '2026-10-01').

    Returns:
        On success: 'CREATED issue_key=PROJ-42  url=https://...'
        On duplicate: 'EXISTS  issue_key=PROJ-42  url=https://...'
        On error: string beginning with 'ERROR:'
    """
    if not project_key:
        return "ERROR: project_key is required. Confirm the key with list_jira_projects before creating."
    if not summary:
        return "ERROR: summary is required."
    if len(summary) > 80:
        return f"ERROR: summary exceeds 80 characters ({len(summary)}). Shorten it."
    if not description:
        return "ERROR: description is required and must include the Google Doc URL."

    try:
        jira = _jira.jira_client()

        # Idempotency check (C11) — search before create.
        existing = _jira.find_existing_ticket(jira, project_key, summary)
        if existing:
            url = f"{_jira.JIRA_URL}/browse/{existing}"
            return f"EXISTS  issue_key={existing}  url={url}\nNot creating a duplicate — record this key and continue."

        priority_name = _jira.map_priority(priority_signal)

        fields: dict = {
            "project": {"key": project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
            "priority": {"name": priority_name},
            "labels": _jira.LAYLA_LABELS,
        }

        if assignee_account_id:
            fields["assignee"] = {"accountId": assignee_account_id}

        if due_date:
            fields["duedate"] = due_date

        if epic_key:
            # The Epic Link field id varies per instance (see _jira.EPIC_LINK_FIELD).
            # If Jira rejects it below, we retry once WITHOUT it rather than losing
            # the whole ticket over an optional link.
            fields[_jira.EPIC_LINK_FIELD] = epic_key

        epic_note = ""
        try:
            issue = jira.issue_create(fields=fields)
        except Exception as create_err:  # noqa: BLE001
            if epic_key and _jira.is_field_error(create_err):
                fields.pop(_jira.EPIC_LINK_FIELD, None)
                issue = jira.issue_create(fields=fields)
                epic_note = (
                    f"\n⚠️ Epic link to '{epic_key}' was dropped — Jira rejected field "
                    f"'{_jira.EPIC_LINK_FIELD}'. Set JIRA_EPIC_LINK_FIELD to this "
                    f"instance's Epic Link id and link the epic manually if needed."
                )
            else:
                raise

        key = issue.get("key", "?")
        url = f"{_jira.JIRA_URL}/browse/{key}"
        return (
            f"CREATED  issue_key={key}  url={url}\n"
            f"Summary: {summary}\n"
            f"Priority: {priority_name}  Assignee: {assignee_account_id or 'Unassigned'}"
            f"{epic_note}\n"
            f"Record issue_key immediately before creating the next ticket."
        )

    except _jira.JiraAuthError as e:
        return f"ERROR: Jira auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: ticket creation failed — {e}"


@tool
def find_jira_assignee(email: str) -> str:
    """Resolve an email address to a Jira Cloud accountId for ticket assignment.

    Use this BEFORE create_jira_issue when owner_resolved is non-empty.
    Only call with an email from owner_resolved — never from a raw spoken name (C9).

    Args:
        email: The resolved email address (from Layla's owner_resolved field).

    Returns:
        'accountId=abc123  displayName=Jane Smith  email=jane@example.com'
        or 'NOT_FOUND: no Jira user matches <email>'
        or 'ERROR: ...'
    """
    if not email or "@" not in email:
        return f"ERROR: '{email}' is not a valid email. Only pass addresses from owner_resolved."

    try:
        jira = _jira.jira_client()
        # Jira Cloud user search by email. NB: the atlassian-python-api arg is
        # `limit`, not `max_results` — passing max_results raises TypeError.
        users = jira.user_find_by_user_string(query=email, limit=5)
        if not users:
            return f"NOT_FOUND: no Jira user matches '{email}'. Leave ticket unassigned — do not guess."

        # Prefer an exact email match.
        for user in users:
            if user.get("emailAddress", "").lower() == email.lower():
                return (
                    f"accountId={user['accountId']}  "
                    f"displayName={user.get('displayName', '?')}  "
                    f"email={user.get('emailAddress', email)}"
                )

        # Fallback: return the first result with a note.
        u = users[0]
        return (
            f"accountId={u['accountId']}  "
            f"displayName={u.get('displayName', '?')}  "
            f"email={u.get('emailAddress', '?')}  "
            f"(closest match — confirm before assigning)"
        )

    except _jira.JiraAuthError as e:
        return f"ERROR: Jira auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: user lookup failed — {e}"


@tool
def list_jira_projects() -> str:
    """List all Jira project keys and names visible to the configured credentials.

    Use this when the target project is ambiguous to surface the real options
    before asking Layla to confirm (project_router skill, Milo C7).
    Never guess a key — always confirm.

    Returns:
        Markdown table of project keys and names, or 'ERROR: ...'
    """
    try:
        jira = _jira.jira_client()
        projects = jira.projects()

        if not projects:
            return "No Jira projects visible to the configured credentials."

        lines = ["| Key | Name |", "|-----|------|"]
        for p in sorted(projects, key=lambda x: x.get("key", "")):
            lines.append(f"| {p.get('key', '?')} | {p.get('name', '?')} |")

        return "\n".join(lines)

    except _jira.JiraAuthError as e:
        return f"ERROR: Jira auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: project list failed — {e}"


# Grouped export referenced by agent.py's spec.
MILO_TOOLS: list[BaseTool] = [create_jira_issue, find_jira_assignee, list_jira_projects]
