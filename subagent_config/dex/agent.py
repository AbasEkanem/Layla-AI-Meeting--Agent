"""Dex — declarative subagent spec factory.

Dex is a Gmail & Google Forms specialist: he drafts and sends the meeting
follow-up email and creates any feedback/RSVP forms, then reports send status
to Layla.

The returned spec is compiled by `create_deep_agent` into a `create_agent`
harness with the full middleware stack; the `skills` key wires SkillsMiddleware
to Dex's own skills/. See deepagents.middleware.subagents.SubAgent.
"""

from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .tools import DEX_TOOLS

_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

_SKILLS = ["subagent_config/dex/skills/"]


def build_spec(model: str | BaseChatModel | None = None) -> dict:
    """Return Dex's declarative SubAgent spec (model=None → inherits Layla's)."""
    spec: dict = {
        "name": "dex",
        "description": (
            "Gmail and Google Forms specialist. Drafts/sends the meeting "
            "follow-up email to confirmed recipients and creates feedback or "
            "RSVP forms. Runs in the step-5 fan-out (parallel with Vera) only "
            "after Milo's ticket summary is confirmed. Never guesses "
            "recipients — Layla confirms them first."
        ),
        "system_prompt": _PROMPT,
        "tools": DEX_TOOLS,
        "skills": _SKILLS,
    }
    if model is not None:
        spec["model"] = model
    return spec
