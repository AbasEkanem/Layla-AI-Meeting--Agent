"""Ivy — Google Drive CRUD tools.

Adopted from an external Drive toolset and adapted to this project:
  - auth + transient-drop retry come from the shared module
    (subagent_config/_shared/google_auth.py), not a duplicated local copy;
  - errors return an "ERROR:" prefix so the agent can detect failure the same
    way it does for Dex's Gmail tools;
  - GoogleAuthError is surfaced with setup guidance rather than a raw traceback.

Scope: these tools operate on the full `drive` scope (see google_auth.SCOPES).
Search/bulk-share/delete reach arbitrary files in the account, not just files
Ivy created — handle destructive tools (trash, delete, revoke) with care.

Grouped export: IVY_DRIVE_TOOLS, merged into IVY_TOOLS by tools.py.
"""

from __future__ import annotations

import io
import json
import logging

from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from langchain_core.tools import BaseTool
from langchain.tools import tool

from .._shared.google_auth import GoogleAuthError, get_service, retry_media

_log = logging.getLogger(__name__)

# Include Shared Drives / cross-domain items in listings and lookups.
_SHARED_DRIVE_FLAGS = {
    "supportsAllDrives": True,
    "includeItemsFromAllDrives": True,
}


def _svc():
    """Authenticated Drive v3 client (via the shared auth module)."""
    return get_service("drive")


@tool
def search_drive_files(query: str = "", max_results: int = 20) -> str:
    """Search Google Drive for files and folders matching a query string or Drive filter.

    Examples:
        query: "name contains 'Q3 Report'"
        query: "mimeType = 'application/vnd.google-apps.presentation'"
    """
    try:
        # Treat a bare word as a name-substring search; pass a real Drive filter through.
        q_str = (
            f"name contains '{query}' and trashed = false"
            if query and "trashed" not in query and "=" not in query
            else (query or "trashed = false")
        )
        # Cap pageSize defensively: an unbounded/huge page strains a large Drive.
        page_size = max(1, min(int(max_results or 20), 100))
        results = retry_media(
            lambda: _svc()
            .files()
            .list(
                q=q_str,
                pageSize=page_size,
                # Most recently touched first, so a bounded page stays relevant.
                orderBy="modifiedTime desc",
                fields="files(id, name, mimeType, modifiedTime, webViewLink, parents)",
                corpora="allDrives",
                **_SHARED_DRIVE_FLAGS,
            )
            .execute(),
            what="search_drive_files",
        )
        files = results.get("files", [])
        if not files:
            return f"No Drive files found matching query: '{query}'"

        out = [f"Found {len(files)} file(s):"]
        for f in files:
            out.append(
                f"- **{f['name']}** (ID: `{f['id']}` | Type: `{f['mimeType']}`)\n"
                f"  Link: {f.get('webViewLink', 'N/A')}"
            )
        return "\n".join(out)
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001 - surface API errors to the agent
        return f"ERROR: Drive search failed — {e}"


@tool
def upload_file_to_drive(
    local_path: str,
    name: str | None = None,
    parent_folder_id: str | None = None,
    mime_type: str | None = None,
) -> str:
    """Upload a local file to Google Drive.

    Args:
        local_path: Local path to the file to upload.
        name: Optional custom filename in Drive.
        parent_folder_id: Optional parent Google Drive folder ID.
        mime_type: Optional MIME type (e.g. 'application/pdf').
    """
    try:
        filename = name or local_path.split("/")[-1].split("\\")[-1]
        file_metadata: dict[str, str | list[str]] = {"name": filename}
        if parent_folder_id:
            file_metadata["parents"] = [parent_folder_id]

        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        created = retry_media(
            lambda: _svc()
            .files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            )
            .execute(),
            what="upload_file_to_drive",
        )
        return (
            f"✅ File uploaded to Drive: **{created['name']}** (ID: `{created['id']}`)\n"
            f"Link: {created.get('webViewLink')}"
        )
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: upload failed — {e}"


@tool
def download_file_from_drive(file_id: str, destination_path: str) -> str:
    """Download a raw (binary) file from Google Drive to a local path.

    For Google-native files (Docs/Sheets/Slides) use export_drive_file instead.

    Args:
        file_id: The ID of the file in Google Drive.
        destination_path: Destination local path to write the downloaded file.
    """
    try:
        request = _svc().files().get_media(fileId=file_id)
        with io.FileIO(destination_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                # Retry each chunk on a transient connection drop instead of
                # failing the whole download.
                _, done = retry_media(downloader.next_chunk, what="download_file")
        return f"✅ File downloaded successfully to `{destination_path}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: download failed — {e}"


@tool
def export_drive_file(
    file_id: str, destination_path: str, mime_type: str = "application/pdf"
) -> str:
    """Export a Google-native file (Doc/Sheet/Slide) to another format (PDF, PNG, CSV…).

    Args:
        file_id: The ID of the Google Doc/Sheet/Slide.
        destination_path: Destination local path (e.g. 'report.pdf').
        mime_type: Target export format (e.g. 'application/pdf', 'image/png', 'text/csv').
    """
    try:
        request = _svc().files().export_media(fileId=file_id, mimeType=mime_type)
        with io.FileIO(destination_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = retry_media(downloader.next_chunk, what="export_file")
        return f"✅ Exported file `{file_id}` to `{destination_path}` as `{mime_type}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: export file failed — {e}"


@tool
def create_drive_folder(name: str, parent_folder_id: str | None = None) -> str:
    """Create a new folder in Google Drive.

    Args:
        name: Name for the new folder.
        parent_folder_id: Optional parent folder ID to nest inside.
    """
    try:
        metadata: dict[str, str | list[str]] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        created = retry_media(
            lambda: _svc()
            .files()
            .create(body=metadata, fields="id, name, webViewLink", supportsAllDrives=True)
            .execute(),
            what="create_drive_folder",
        )
        return (
            f"✅ Folder created: **{created['name']}** (ID: `{created['id']}`)\n"
            f"Link: {created.get('webViewLink')}"
        )
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: create folder failed — {e}"


@tool
def move_drive_file(file_id: str, new_parent_folder_id: str) -> str:
    """Move a file to a different folder in Google Drive.

    Args:
        file_id: The ID of the file to move.
        new_parent_folder_id: Destination parent folder ID.
    """
    try:
        file = _svc().files().get(
            fileId=file_id, fields="parents", supportsAllDrives=True
        ).execute()
        previous_parents = ",".join(file.get("parents", []))
        retry_media(
            lambda: _svc()
            .files()
            .update(
                fileId=file_id,
                addParents=new_parent_folder_id,
                removeParents=previous_parents,
                fields="id, parents",
                supportsAllDrives=True,
            )
            .execute(),
            what="move_drive_file",
        )
        return f"✅ Moved file `{file_id}` to folder `{new_parent_folder_id}`"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: move file failed — {e}"


@tool
def rename_drive_file(file_id: str, new_name: str) -> str:
    """Rename a file or folder in Google Drive.

    Args:
        file_id: The ID of the file or folder.
        new_name: New name string.
    """
    try:
        updated = retry_media(
            lambda: _svc()
            .files()
            .update(fileId=file_id, body={"name": new_name}, fields="id, name", supportsAllDrives=True)
            .execute(),
            what="rename_drive_file",
        )
        return f"✅ Renamed file `{file_id}` to **{updated['name']}**"
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: rename file failed — {e}"


@tool
def share_drive_file(file_id: str, email: str, role: str = "writer", notify: bool = True) -> str:
    """Share a Google Drive file or folder with a specific user email.

    Args:
        file_id: The ID of the file/folder.
        email: Recipient email address.
        role: One of 'reader', 'commenter', 'writer', 'owner'. Default 'writer'.
        notify: Whether to send an email notification (default True).
    """
    if not email or "@" not in email:
        return f"ERROR: '{email}' is not a valid email address."
    try:
        permission = {"type": "user", "role": role, "emailAddress": email}
        # An ownership transfer must be requested explicitly, or Drive rejects it.
        transfer = role == "owner"
        perm = retry_media(
            lambda: _svc()
            .permissions()
            .create(
                fileId=file_id,
                body=permission,
                sendNotificationEmail=notify,
                transferOwnership=transfer,
                fields="id",
                supportsAllDrives=True,
            )
            .execute(),
            what="share_drive_file",
        )
        return f"✅ Shared file `{file_id}` with `{email}` as `{role}` (Perm ID: `{perm['id']}`)."
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: share file failed — {e}"


@tool
def bulk_share_drive_files(
    email: str,
    query: str = "",
    file_ids: str = "",
    role: str = "writer",
    notify: bool = False,
    max_files: int = 200,
) -> str:
    """Share MANY Google Drive files with one user in a SINGLE call.

    Use this instead of calling share_drive_file repeatedly. It is the correct
    tool for requests like "share all my Google Docs with X".

    Provide `email` plus EITHER `query` OR `file_ids` (not both):
      - query: a Drive search filter, e.g.
          "mimeType='application/vnd.google-apps.document'" (all Google Docs)
          "name contains 'Q3'" (files whose name contains Q3)
        The tool discovers the matching files itself.
      - file_ids: a JSON array OR comma-separated string of explicit file IDs,
          e.g. ["idA","idB"] or "idA,idB".

    Args:
        email: Recipient email address to grant access to.
        query: Drive search filter selecting files (mutually exclusive with file_ids).
        file_ids: JSON array or comma-separated list of file IDs (mutually exclusive with query).
        role: One of 'reader', 'commenter', 'writer'. Default 'writer'. ('owner' is
            rejected here — a bulk ownership transfer is never what you want.)
        notify: Whether to send an email notification per file (default False for bulk).
        max_files: Safety cap on how many files to share in one call (default 200).
    """
    if not email or "@" not in email:
        return f"ERROR: '{email}' is not a valid email address."
    if role == "owner":
        return "ERROR: refusing to bulk-transfer ownership. Use share_drive_file for a single owner change."
    try:
        # ── Resolve target IDs from an explicit list or a query.
        ids: list[str] = []
        if file_ids and file_ids.strip():
            raw = file_ids.strip()
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                ids = [str(x).strip() for x in parsed if str(x).strip()]
            else:
                ids = [part.strip() for part in raw.split(",") if part.strip()]
        elif query and query.strip():
            q = query.strip()
            if "trashed" not in q:
                q = f"({q}) and trashed = false"
            page_token = None
            while True:
                resp = retry_media(
                    lambda pt=page_token: _svc()
                    .files()
                    .list(
                        q=q,
                        pageSize=100,
                        fields="nextPageToken, files(id, name)",
                        pageToken=pt,
                        corpora="allDrives",
                        **_SHARED_DRIVE_FLAGS,
                    )
                    .execute(),
                    what="bulk_share_discover",
                )
                for f in resp.get("files", []):
                    ids.append(f["id"])
                page_token = resp.get("nextPageToken")
                if not page_token or len(ids) >= max_files:
                    break
        else:
            return "ERROR: bulk_share_drive_files needs either `query` or `file_ids`."

        if not ids:
            return f"No files matched — nothing shared with `{email}`."

        ids = ids[:max_files]

        shared = 0
        failures: list[str] = []
        for fid in ids:
            try:
                retry_media(
                    lambda fid=fid: _svc()
                    .permissions()
                    .create(
                        fileId=fid,
                        body={"type": "user", "role": role, "emailAddress": email},
                        sendNotificationEmail=notify,
                        fields="id",
                        supportsAllDrives=True,
                    )
                    .execute(),
                    what="bulk_share_apply",
                )
                shared += 1
            except Exception as e:  # noqa: BLE001 - collect per-file errors, keep going
                failures.append(f"{fid}: {e}")

        summary = [f"✅ Shared {shared}/{len(ids)} file(s) with `{email}` as `{role}`."]
        if failures:
            summary.append(f"⚠️ {len(failures)} failed:")
            summary.extend(f"  - {f}" for f in failures[:10])
            if len(failures) > 10:
                summary.append(f"  …and {len(failures) - 10} more.")
        return "\n".join(summary)
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: bulk share failed — {e}"


@tool
def share_drive_file_with_anyone(file_id: str, role: str = "reader") -> str:
    """Make a file accessible to ANYONE with the link. Public exposure — use with care.

    Args:
        file_id: The ID of the file.
        role: One of 'reader', 'commenter', 'writer'. Default 'reader'.
    """
    try:
        permission = {"type": "anyone", "role": role}
        perm = retry_media(
            lambda: _svc()
            .permissions()
            .create(fileId=file_id, body=permission, fields="id", supportsAllDrives=True)
            .execute(),
            what="share_with_anyone",
        )
        return (
            f"✅ File `{file_id}` is now accessible by anyone with the link as "
            f"`{role}` (Perm ID: `{perm['id']}`)."
        )
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: share with anyone failed — {e}"


@tool
def list_drive_file_permissions(file_id: str) -> str:
    """List all user permissions and access rules on a Google Drive file/folder.

    Args:
        file_id: The ID of the file or folder.
    """
    try:
        res = retry_media(
            lambda: _svc()
            .permissions()
            .list(
                fileId=file_id,
                fields="permissions(id, type, role, emailAddress)",
                supportsAllDrives=True,
            )
            .execute(),
            what="list_permissions",
        )
        perms = res.get("permissions", [])
        if not perms:
            return f"No explicit permissions found for file `{file_id}`."

        out = [f"🔒 Permissions for file `{file_id}` ({len(perms)}):"]
        for p in perms:
            email = p.get("emailAddress", "Anyone / Public")
            out.append(
                f"- ID: `{p['id']}` | User: `{email}` | Role: `{p['role']}` | Type: `{p['type']}`"
            )
        return "\n".join(out)
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: list permissions failed — {e}"


@tool
def revoke_drive_file_permission(file_id: str, permission_id: str) -> str:
    """Revoke/delete a user's permission from a Google Drive file or folder.

    Args:
        file_id: The ID of the file.
        permission_id: The ID of the permission rule to delete (from list_drive_file_permissions).
    """
    try:
        retry_media(
            lambda: _svc()
            .permissions()
            .delete(fileId=file_id, permissionId=permission_id, supportsAllDrives=True)
            .execute(),
            what="revoke_permission",
        )
        return f"✅ Revoked permission `{permission_id}` from file `{file_id}`."
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: revoke permission failed — {e}"


@tool
def trash_drive_file(file_id: str) -> str:
    """Move a file to Google Drive trash (recoverable).

    Args:
        file_id: The ID of the file to move to trash.
    """
    try:
        retry_media(
            lambda: _svc()
            .files()
            .update(fileId=file_id, body={"trashed": True}, fields="id, trashed", supportsAllDrives=True)
            .execute(),
            what="trash_drive_file",
        )
        return f"✅ Moved file `{file_id}` to trash."
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: trash file failed — {e}"


@tool
def delete_drive_file(file_id: str) -> str:
    """PERMANENTLY delete a file or folder from Google Drive (bypasses trash, unrecoverable).

    Prefer trash_drive_file unless a permanent delete is explicitly required.

    Args:
        file_id: The ID of the file or folder to permanently delete.
    """
    try:
        retry_media(
            lambda: _svc().files().delete(fileId=file_id, supportsAllDrives=True).execute(),
            what="delete_drive_file",
        )
        return f"✅ Permanently deleted file `{file_id}` from Google Drive."
    except GoogleAuthError as e:
        return f"ERROR: Google auth not configured — {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: delete file failed — {e}"


# Grouped export, merged into IVY_TOOLS by tools.py.
IVY_DRIVE_TOOLS: list[BaseTool] = [
    search_drive_files,
    upload_file_to_drive,
    download_file_from_drive,
    export_drive_file,
    create_drive_folder,
    move_drive_file,
    rename_drive_file,
    share_drive_file,
    bulk_share_drive_files,
    share_drive_file_with_anyone,
    list_drive_file_permissions,
    revoke_drive_file_permission,
    trash_drive_file,
    delete_drive_file,
]
