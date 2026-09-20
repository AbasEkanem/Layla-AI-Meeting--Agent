"""Milo — declarative subagent spec factory.

Milo is a project-management specialist: he maps action items to Jira tickets,
resolves the project key, grades priority, and creates/assigns/links tickets,
then returns a ticket summary to Layla.

The returned spec is compiled by `create_deep_agent` into a `create_agent`
harness with the full middleware stack; the `skills` key wires SkillsMiddleware
to Milo's own skills/. See deepagents.middleware.subagents.SubAgent.
"""

from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .tools import MILO_TOOLS

_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

_SKILLS = ["subagent_config/milo/skills/"]


def build_spec(model: str | BaseChatModel | None = None) -> dict:
    """Return Milo's declarative SubAgent spec (model=None → inherits Layla's)."""
    spec: dict = {
        "name": "milo",
        "description": (
            "Jira action-item specialist. Maps resolved action items to Jira "
            "tickets: routes the project key, grades priority from Ivy's "
            "verbatim signal, then creates, assigns, and links tickets. Use "
            "after Ivy and Layla's identity resolution (step 2b), before Dex "
            "and Vera. Holds and asks Layla when the project is ambiguous — "
            "never guesses a key."
        ),
        "system_prompt": _PROMPT,
        "tools": MILO_TOOLS,
        "skills": _SKILLS,
    }
    if model is not None:
        spec["model"] = model
    return spec
