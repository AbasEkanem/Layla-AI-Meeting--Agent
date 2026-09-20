"""Vera — declarative subagent spec factory.

Vera is a Slack communication specialist: she routes to the right channels,
composes Block Kit messages, manages threads, and posts status updates, then
reports per-channel send status to Layla.

The returned spec is compiled by `create_deep_agent` into a `create_agent`
harness with the full middleware stack; the `skills` key wires SkillsMiddleware
to Vera's own skills/. See deepagents.middleware.subagents.SubAgent.
"""

from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .tools import VERA_TOOLS

_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

_SKILLS = ["subagent_config/vera/skills/"]


def build_spec(model: str | BaseChatModel | None = None) -> dict:
    """Return Vera's declarative SubAgent spec (model=None → inherits Layla's)."""
    spec: dict = {
        "name": "vera",
        "description": (
            "Slack notification specialist. Routes to the right channels, "
            "composes Block Kit messages, manages threads, and posts status "
            "updates. Runs in the step-5 fan-out (parallel with Dex) only "
            "after Milo's ticket summary is confirmed. Reports per-channel "
            "status; PARTIAL if any confirmed channel fails to post."
        ),
        "system_prompt": _PROMPT,
        "tools": VERA_TOOLS,
        "skills": _SKILLS,
    }
    if model is not None:
        spec["model"] = model
    return spec
