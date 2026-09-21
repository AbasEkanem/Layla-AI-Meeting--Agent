"""Ivy's tools — Google Docs & Google Drive.

Exposed as IVY_TOOLS and referenced by agent.py's spec.

  - Drive: full CRUD suite in _drive.py (IVY_DRIVE_TOOLS) — search, upload,
    download, export, folder, move, rename, share, bulk-share, share-with-anyone,
    list/revoke permissions, trash, delete. Runs on the full `drive` scope.
  - Docs: create + batchUpdate (render the six-section report, insert the
    action-item table). Still TODO — the Docs half of Ivy's contract.
"""

from langchain_core.tools import BaseTool

from ._docs import IVY_DOCS_TOOLS
from ._drive import IVY_DRIVE_TOOLS

IVY_TOOLS: list[BaseTool] = [*IVY_DOCS_TOOLS, *IVY_DRIVE_TOOLS]
