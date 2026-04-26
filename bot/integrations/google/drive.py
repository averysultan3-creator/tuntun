"""Google Drive integration for TUNTUN — upload files, manage folders."""
import logging
from pathlib import Path
from typing import Optional


def _get_service():
    from bot.integrations.google.auth import get_credentials
    creds = get_credentials()
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logging.error("Google Drive: failed to build service: %s", e)
        return None


def get_file_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def get_folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


_FOLDER_CACHE: dict[str, str] = {}


def _get_or_create_folder_sync(svc, name: str, parent_id: str = None) -> Optional[str]:
    cache_key = f"{parent_id}:{name}"
    if cache_key in _FOLDER_CACHE:
        return _FOLDER_CACHE[cache_key]
    try:
        q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        result = svc.files().list(q=q, fields="files(id,name)", spaces="drive").execute()
        files = result.get("files", [])
        if files:
            _FOLDER_CACHE[cache_key] = files[0]["id"]
            return files[0]["id"]

        # Create
        meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            meta["parents"] = [parent_id]
        folder = svc.files().create(body=meta, fields="id").execute()
        fid = folder["id"]
        _FOLDER_CACHE[cache_key] = fid
        return fid
    except Exception as e:
        logging.error("Google Drive: get_or_create_folder(%s) error: %s", name, e)
        return None


def _upload_file_sync(svc, local_path: str, file_name: str,
                       folder_id: str = None) -> Optional[str]:
    try:
        import mimetypes
        from googleapiclient.http import MediaFileUpload

        mime_type, _ = mimetypes.guess_type(local_path)
        mime_type = mime_type or "application/octet-stream"

        meta = {"name": file_name}
        if folder_id:
            meta["parents"] = [folder_id]

        media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
        result = svc.files().create(
            body=meta, media_body=media, fields="id"
        ).execute()
        return result.get("id")
    except Exception as e:
        logging.error("Google Drive: upload_file error: %s", e)
        return None


async def upload_file(local_path: str, file_name: str = None,
                      subfolder: str = None,
                      user_id: int = 0, object_type: str = "file",
                      object_id: int = 0) -> Optional[str]:
    """Upload a local file to Google Drive. Returns public URL or None."""
    import asyncio
    import config

    svc = _get_service()
    if not svc:
        return None

    loop = asyncio.get_event_loop()

    # Resolve folder
    root_id = config.GOOGLE_DRIVE_ROOT_FOLDER_ID or None
    folder_id = root_id

    if subfolder:
        folder_id = await loop.run_in_executor(
            None, _get_or_create_folder_sync, svc, subfolder, root_id
        )

    fname = file_name or Path(local_path).name
    file_id = await loop.run_in_executor(
        None, _upload_file_sync, svc, local_path, fname, folder_id
    )

    if not file_id:
        return None

    # Make readable by anyone with link
    try:
        def _share():
            svc.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()
        await loop.run_in_executor(None, _share)
    except Exception:
        pass

    url = get_file_url(file_id)

    if user_id:
        from bot.db.database import db
        await db.google_link_save(
            user_id=user_id,
            object_type=object_type,
            object_id=object_id,
            google_type="drive_file",
            drive_file_id=file_id,
            url=url,
        )

    return url


async def get_or_create_folder(name: str, parent_id: str = None) -> Optional[str]:
    import asyncio
    svc = _get_service()
    if not svc:
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _get_or_create_folder_sync, svc, name, parent_id
    )
