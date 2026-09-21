"""Ivy — Google Docs tools (create, read, append, insert, replace, style, page break).

Adopted from an external Docs toolset and adapted to this project:
  - auth + transient-drop retry come from the shared module, not a local copy;
  - errors return an "ERROR:" prefix so the agent detects failure the same way
    it does for Dex's Gmail tools;
  - GoogleAuthError is surfaced with setup guidance rather than a raw traceback.

The create_google_doc idempotency guard (a short-TTL title→doc cache) is kept
verbatim in intent — it bounds a runaway/looping model to one doc per title.

INDEX CAVEAT: insert_text_at_index, delete_doc_text_range, and style_doc_text_range
take raw character indices. Google Docs indices SHIFT after every edit, so a
computed/guessed index corrupts the doc. Read the doc first (read_google_doc /
the raw get) to find real indices, or prefer append_text_to_doc (which reads the
document's true end index) and replace_text_in_doc (which matches text, not
positions). See the note this project opened with: read real indices, never
compute them.

Grouped export: IVY_DOCS_TOOLS, merged into IVY_TOOLS by tools.py.
"""

from __future__ import annotations

import json
import logging
import time

from langchain_core.tools import BaseTool
from langchain.tools import tool

from .._shared.google_auth import GoogleAuthError, get_service, retry_media

_log = logging.getLogger(__name__)

# ── Idempotency guard for create_google_doc ──────────────────────────────────
# A weak/looping subagent model can call create_google_doc many times with the
# same title (observed: duplicate docs when the model never received the real
# body and kept retrying). Cache the most recent (title → doc_id, link) for a
# short window so repeat calls with the SAME title return the already-created
# doc, bounding a runaway loop to one document per title.
_RECENT_DOC_TTL_S = 120.0
_recent_docs: dict[str, tuple[float, str, str]] = {}  # title → (ts, doc_id, link)


def _svc():
    """Authenticated Docs v1 client (via the shared auth module)."""
    return get_service("docs")


def _drive():
    """Authenticated Drive v3 client — used only to read a new doc's webViewLink."""
    return get_service("drive")


@tool
def create_google_doc(title: str, initial_content: str | None = None) -> str:
    """Create a new Google Document.

    Args:
        title: Title of the document.
        initial_content: Optional initial text content to insert.
    """
    try:
        # Idempotency: if a doc with this exact title was created moments ago,
        # return it instead of creating a duplicate.
        now = time.monotonic()
        cached = _recent_docs.get(title)
        if cached is not None:
            ts, cached_id, cached_link = cached
            if now - ts < _RECENT_DOC_TTL_S:
                _log.warning(
                    "create_google_doc.idempotent_hit title=%r doc_id=%s "
                    "(returning existing doc instead of creating a duplicate)",
                    title, cached_id,
                )
                return (
                    f"✅ Google Doc **{title}** already exists (ID: `{cached_id}`)\n"
                    f"Link: {cached_link}\n"
                    f"(Reused the doc created moments ago — did NOT create a duplicate. "
                    f"To add content, call append_text_to_doc with this document ID.)"
                )
            _recent_docs.pop(title, None)

        doc = retry_media(
            lambda: _svc().documents().create(body={"title": title}).execute(),
            what="create_google_doc",
        )
        doc_id = doc["documentId"]

        if initial_content:
            requests = [{"insertText": {"location": {"index": 1}, "text": initial_content}}]
            retry_media(
                lambda: _svc()
                .documents()
                .batchUpdate(documentId=doc_id, body={"requests": requests})
                .execute(),
                what="create_google_doc.initial_content",
            )

        file_meta = retry_media(
            lambda: _drive().files().get(fileId=doc_id, fields="webViewLink").execute(),
            what="create_google_doc.link",
        )
        link = file_meta.get("webViewLink")

        # Remember this creation so immediate repeat calls are deduplicated,
        # and sweep expired entries.
        _recent_docs[title] = (now, doc_id, link)
        for _t, (_ts, _id, _l) in list(_recent_docs.items()):
            if now - _ts >= _RECENT_DOC_TTL_S:
                _recent_docs.pop(_t, None)

        return f"✅ Created Google Doc: **{title}** (ID: `{doc_id}`)\nLink: {link}"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001 - surface API errors to the agent
        return f"ERROR: doc creation failed — {e}"


@tool
def read_google_doc(doc_id: str) -> str:
    """Read the full text content of a Google Document.

    Args:
        doc_id: The Google Document ID.
    """
    try:
        doc = retry_media(
            lambda: _svc().documents().get(documentId=doc_id).execute(),
            what="read_google_doc",
        )
        title = doc.get("title", "Untitled Document")
        body = doc.get("body", {}).get("content", [])

        text_runs = []
        for element in body:
            paragraph = element.get("paragraph")
            if not paragraph:
                continue
            for run in paragraph.get("elements", []):
                text_run = run.get("textRun")
                if text_run:
                    text_runs.append(text_run.get("content", ""))

        full_text = "".join(text_runs).strip()
        return f"📄 **{title}** (`{doc_id}`):\n\n{full_text}"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: read doc failed — {e}"


@tool
def append_text_to_doc(doc_id: str, text: str) -> str:
    """Append text to the very end of a Google Document.

    Reads the document's real end index rather than computing one, so it stays
    correct regardless of prior edits.

    Args:
        doc_id: The Google Document ID.
        text: The text string to append.
    """
    try:
        doc = retry_media(
            lambda: _svc().documents().get(documentId=doc_id).execute(),
            what="append_text_to_doc.get",
        )
        content = doc.get("body", {}).get("content", [])
        end_index = content[-1]["endIndex"] - 1 if content else 1

        requests = [{"insertText": {"location": {"index": end_index}, "text": f"\n{text}"}}]
        retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute(),
            what="append_text_to_doc.update",
        )
        return f"✅ Appended text to document `{doc_id}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: append text failed — {e}"


@tool
def insert_text_at_index(doc_id: str, index: int, text: str) -> str:
    """Insert text at a specific character index within a Google Document.

    CAUTION: indices shift after every edit. A stale or guessed index inserts in
    the wrong place. Read the doc first to find a real index, or use
    append_text_to_doc when you just want text at the end.

    Args:
        doc_id: The Google Document ID.
        index: Character index location (1-based start index).
        text: Text string to insert.
    """
    try:
        requests = [{"insertText": {"location": {"index": index}, "text": text}}]
        retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute(),
            what="insert_text_at_index",
        )
        return f"✅ Inserted text at index {index} in document `{doc_id}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: insert text failed — {e}"


@tool
def replace_text_in_doc(doc_id: str, find: str, replace: str, match_case: bool = True) -> str:
    """Global find & replace across a Google Document (e.g. swapping {{PLACEHOLDER}} tokens).

    Position-independent — matches text, not indices — so it is the safe way to
    fill a templated doc.

    Args:
        doc_id: The Google Document ID.
        find: Target search string.
        replace: Replacement text string.
        match_case: Case sensitivity boolean (default True).
    """
    try:
        requests = [{
            "replaceAllText": {
                "containsText": {"text": find, "matchCase": match_case},
                "replaceText": replace,
            }
        }]
        res = retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute(),
            what="replace_text_in_doc",
        )
        occurrences = (
            res.get("replies", [{}])[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
        )
        return f"✅ Replaced {occurrences} occurrence(s) of '{find}' with '{replace}' in doc `{doc_id}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: replace text failed — {e}"


@tool
def delete_doc_text_range(doc_id: str, start_index: int, end_index: int) -> str:
    """Delete a range of characters from a Google Document.

    CAUTION: indices shift after every edit. Read the doc first to find real
    indices — a stale range deletes the wrong content.

    Args:
        doc_id: The Google Document ID.
        start_index: Starting character index.
        end_index: Ending character index.
    """
    try:
        requests = [{"deleteContentRange": {"range": {"startIndex": start_index, "endIndex": end_index}}}]
        retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute(),
            what="delete_doc_text_range",
        )
        return f"✅ Deleted text range [{start_index}:{end_index}] from document `{doc_id}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: delete text range failed — {e}"


@tool
def style_doc_text_range(
    doc_id: str,
    start_index: int,
    end_index: int,
    bold: bool | None = None,
    italic: bool | None = None,
    underline: bool | None = None,
    font_size_pt: float | None = None,
) -> str:
    """Apply character formatting (bold, italic, underline, font size) to a text range.

    CAUTION: indices shift after every edit — read the doc first for real indices.

    Args:
        doc_id: The Google Document ID.
        start_index: Starting character index.
        end_index: Ending character index.
        bold: Optional boolean for bold formatting.
        italic: Optional boolean for italic formatting.
        underline: Optional boolean for underline formatting.
        font_size_pt: Optional font size in points (e.g. 14.0).
    """
    try:
        text_style: dict = {}
        fields = []
        if bold is not None:
            text_style["bold"] = bold
            fields.append("bold")
        if italic is not None:
            text_style["italic"] = italic
            fields.append("italic")
        if underline is not None:
            text_style["underline"] = underline
            fields.append("underline")
        if font_size_pt is not None:
            text_style["fontSize"] = {"magnitude": font_size_pt, "unit": "PT"}
            fields.append("fontSize")

        if not fields:
            return "ERROR: no styling properties specified to apply."

        requests = [{
            "updateTextStyle": {
                "range": {"startIndex": start_index, "endIndex": end_index},
                "textStyle": text_style,
                "fields": ",".join(fields),
            }
        }]
        retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute(),
            what="style_doc_text_range",
        )
        return f"✅ Applied styling ({', '.join(fields)}) to range [{start_index}:{end_index}] in doc `{doc_id}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: style text failed — {e}"


@tool
def insert_doc_page_break(doc_id: str, index: int) -> str:
    """Insert a page break at a specific character index in a Google Document.

    CAUTION: indices shift after every edit — read the doc first for a real index.

    Args:
        doc_id: The Google Document ID.
        index: Character index location to insert the page break.
    """
    try:
        requests = [{"insertPageBreak": {"location": {"index": index}}}]
        retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute(),
            what="insert_doc_page_break",
        )
        return f"✅ Inserted page break at index {index} in document `{doc_id}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: insert page break failed — {e}"


# ── Native action-item table (Ivy S2) ────────────────────────────────────────
# The action-item table in report_template.md is a real 6-column Google Docs
# table. Building it correctly is the construction this project opened with:
# insert an empty table, RE-FETCH the doc, read each cell's real startIndex from
# what the API returns, and write cells — never compute an index.
#
# The one non-obvious rule: Docs indices shift as you insert. Writing cell text
# lowest-index-first would invalidate every later cell's position. So we insert
# HIGHEST-index-first — each insertion only moves indices after it, which are
# already written. The helpers below are pure so this ordering is unit-testable.

# Column headers, matching report_template.md §4 exactly.
_ACTION_TABLE_HEADERS = ["#", "Task", "Owner (as spoken)", "Priority signal", "Deadline", "Source"]


def _render_action_rows(items: list[dict]) -> list[list[str]]:
    """Turn Ivy's action_items into the grid of cell strings (header + one row each).

    Verbatim fields (owner_claim, priority_signal, deadline_claim) are quoted when
    present and rendered as the template's fallbacks when null. Every cell is
    non-empty — an empty insertText would be rejected, and "—" is the template's
    own placeholder.
    """
    grid: list[list[str]] = [list(_ACTION_TABLE_HEADERS)]
    if not items:
        # S2 edge case: no action items. Keep the table, flag it in-cell.
        grid.append(["1", "None recorded", "—", "—", "—", "—"])
        return grid
    for i, it in enumerate(items, start=1):
        task = (it.get("task") or "").strip() or "(missing task)"
        owner = (it.get("owner_claim") or "").strip()
        priority = (it.get("priority_signal") or "").strip()
        deadline = (it.get("deadline_claim") or "").strip()
        segs = it.get("source_segment_ids") or []
        source = ", ".join(str(s) for s in segs) if segs else "—"
        grid.append([
            str(i),
            task,
            f'"{owner}"' if owner else "Unassigned",
            f'"{priority}"' if priority else "—",
            f'"{deadline}"' if deadline else "—",
            source,
        ])
    return grid


def _find_last_table(doc: dict) -> dict | None:
    """Return the last table element in the document body, or None if there is none.

    Used right after inserting our table, before anything else is appended, so the
    last table is the one we just created.
    """
    content = doc.get("body", {}).get("content", [])
    last = None
    for element in content:
        if "table" in element:
            last = element
    return last


def _cell_insertion_index(cell: dict) -> int | None:
    """Real startIndex to insert text into an (empty) table cell.

    A freshly inserted cell holds one empty paragraph; its startIndex is where
    text goes. Read from the API response — never computed.
    """
    cell_content = cell.get("content", [])
    if not cell_content:
        return None
    return cell_content[0].get("startIndex")


def _ordered_cell_writes(table_element: dict, grid: list[list[str]]) -> list[tuple[int, str]]:
    """Pair each cell's real startIndex with its text, ordered HIGHEST index first.

    Highest-first is the correctness crux: inserting text shifts every index after
    it, so writing later cells before earlier ones keeps every remaining target
    valid. Returns (index, text) tuples ready to become insertText requests.
    """
    table = table_element.get("table", {})
    rows = table.get("tableRows", [])
    writes: list[tuple[int, str]] = []
    for r, row in enumerate(rows):
        cells = row.get("tableCells", [])
        for c, cell in enumerate(cells):
            if r >= len(grid) or c >= len(grid[r]):
                continue
            text = grid[r][c]
            if not text:
                continue
            idx = _cell_insertion_index(cell)
            if idx is None:
                continue
            writes.append((idx, text))
    # Descending by index → apply late cells first so earlier indices stay valid.
    writes.sort(key=lambda w: w[0], reverse=True)
    return writes


@tool
def insert_action_item_table(doc_id: str, action_items_json: str) -> str:
    """Insert Ivy's native 6-column action-item table (report_template.md §4) into a doc.

    Builds a REAL Google Docs table (not tab-separated text), appended at the end
    of the document. Indices are never computed: the table is inserted, the doc is
    re-fetched, and each cell's true startIndex is read from the API response
    before its text is written.

    Args:
        doc_id: The Google Document ID (from create_google_doc).
        action_items_json: JSON array of Ivy's action items, each an object with
            keys: task, owner_claim, priority_signal, deadline_claim,
            source_segment_ids (list). owner/priority/deadline are quoted verbatim
            when present and shown as Unassigned / — when null. An empty array is
            valid — the table is still created and flagged as "None recorded".

    Returns:
        Confirmation with the row count, or an error string beginning with "ERROR:".
    """
    try:
        try:
            items = json.loads(action_items_json) if action_items_json.strip() else []
        except json.JSONDecodeError as e:
            return f"ERROR: action_items_json is not valid JSON — {e}"
        if not isinstance(items, list):
            return "ERROR: action_items_json must be a JSON array of action-item objects."

        grid = _render_action_rows(items)
        n_rows, n_cols = len(grid), len(_ACTION_TABLE_HEADERS)

        # 1) Insert the empty table at the true end of the body.
        doc = retry_media(
            lambda: _svc().documents().get(documentId=doc_id).execute(),
            what="insert_action_item_table.get_end",
        )
        content = doc.get("body", {}).get("content", [])
        end_index = content[-1]["endIndex"] - 1 if content else 1
        retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(
                documentId=doc_id,
                body={"requests": [{
                    "insertTable": {
                        "location": {"index": end_index},
                        "rows": n_rows,
                        "columns": n_cols,
                    }
                }]},
            )
            .execute(),
            what="insert_action_item_table.insert_table",
        )

        # 2) RE-FETCH so we read real cell indices instead of guessing them.
        doc2 = retry_media(
            lambda: _svc().documents().get(documentId=doc_id).execute(),
            what="insert_action_item_table.refetch",
        )
        table_element = _find_last_table(doc2)
        if table_element is None:
            return "ERROR: table was inserted but could not be located on re-fetch."

        # 3) Write every cell, highest index first, in one batch.
        writes = _ordered_cell_writes(table_element, grid)
        if not writes:
            return "ERROR: no cell insertion points found in the inserted table."
        requests = [
            {"insertText": {"location": {"index": idx}, "text": text}}
            for idx, text in writes
        ]
        retry_media(
            lambda: _svc()
            .documents()
            .batchUpdate(documentId=doc_id, body={"requests": requests})
            .execute(),
            what="insert_action_item_table.fill_cells",
        )

        item_count = 0 if (len(items) == 0) else len(items)
        return (
            f"✅ Inserted native action-item table into doc `{doc_id}`: "
            f"{n_rows} rows × {n_cols} cols ({item_count} action item(s), header included)."
        )
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: insert action-item table failed — {e}"


# Grouped export, merged into IVY_TOOLS by tools.py.
IVY_DOCS_TOOLS: list[BaseTool] = [
    create_google_doc,
    read_google_doc,
    append_text_to_doc,
    insert_text_at_index,
    replace_text_in_doc,
    delete_doc_text_range,
    style_doc_text_range,
    insert_doc_page_break,
    insert_action_item_table,
]
