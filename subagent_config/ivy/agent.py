"""Ivy — declarative subagent spec factory.

Ivy is a transcript analyst: she turns a meeting transcript into a Google Doc
report with an action-item table, then returns the doc URL + items to Layla.

This module builds no agent itself. In the declarative model, `create_deep_agent`
compiles the returned spec into a `create_agent` harness and wraps it in the full
middleware stack (filesystem, summarization, prompt-caching, and — because we set
the `skills` key — SkillsMiddleware pointed at Ivy's own skills/).

See deepagents.middleware.subagents.SubAgent for the full field contract.
"""

from pathlib import Path

from langchain_core.language_models import BaseChatModel

from .tools import IVY_TOOLS

_PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")

# POSIX path relative to the backend root — consumed by SkillsMiddleware.
_SKILLS = ["subagent_config/ivy/skills/"]


def build_spec(model: str | BaseChatModel | None = None) -> dict:
    """Return Ivy's declarative SubAgent spec.

    Args:
        model: Optional model override. When None, Ivy inherits Layla's model
            (deepagents falls back to the parent model — graph.py:656).
    """
    spec: dict = {
        "name": "ivy",
        "description": (
            "Transcript analyst and report writer. Turns a meeting transcript "
            "into a [DRAFT] Google Doc with a six-section report and an "
            "action-item table (owner + priority signal quoted verbatim). "
            "Use after capture (step 0), before Milo. Returns doc URL + items "
            "to Layla; never contacts other subagents."
        ),
        "system_prompt": _PROMPT,
        "tools": IVY_TOOLS,
        "skills": _SKILLS,
    }
    if model is not None:
        spec["model"] = model
    return spec
