"""Ivy's tools — Google Docs & Google Drive.

Exposed as IVY_TOOLS and referenced by agent.py's spec. Populate with the
concrete tool objects (LangChain BaseTool / @tool functions) that create the
doc, write sections, and set sharing. Empty for now — structure pass.
"""

from langchain_core.tools import BaseTool
from langchain.tools import tool

# TODO: add Google Docs (create, write sections) and Drive (sharing) tools.
IVY_TOOLS: list[BaseTool] = []
