"""Google Sheets integration for TUNTUN.

Public API:
    append_row(spreadsheet_id, sheet_name, row, user_id) -> row_number | None
    ensure_sheet(spreadsheet_id, sheet_name, headers) -> bool
    get_or_create_spreadsheet(title, user_id) -> spreadsheet_id | None
    read_sheet(spreadsheet_id, sheet_name, limit) -> list[dict]
    find_rows(spreadsheet_id, sheet_name, column, value) -> list[dict]
    get_spreadsheet_url(spreadsheet_id) -> str

Sheet headers per data type:
    Finance:   date, amount, currency, category, project, comment, object_id
    Tasks:     date, id, title, priority, due_date, status
    Reminders: date, id, text, remind_at, status
    Memory:    date, id, category, key_name, value
    Ideas:     date, id, title, category, status, project
    LongNotes: date, title, category, summary, doc_link, tags
    Attachments: date, type, section, caption, local_path, drive_link, summary
"""
import logging
from typing import Optional

_SHEET_HEADERS: dict[str, list[str]] = {
    "Finance":     ["date", "amount", "currency", "category", "project", "comment", "object_id"],
    "Tasks":       ["date", "id", "title", "priority", "due_date", "status"],
    "Reminders":   ["date", "id", "text", "remind_at", "status"],
    "Memory":      ["date", "id", "category", "key_name", "value"],
    "Ideas":       ["date", "id", "title", "category", "status", "project"],
    "LongNotes":   ["date", "title", "category", "summary", "doc_link", "tags"],
    "Attachments": ["date", "type", "section", "caption", "local_path", "drive_link", "summary"],
    "Projects":    ["date", "id", "name", "title", "description"],
    "Study":       ["date", "id", "subject", "type", "content", "due_date", "status"],
    "DailyPlans":  ["date", "summary", "tasks_count", "doc_link"],
    "Logs":        ["date", "user_id", "message_type", "text_preview", "actions"],
}


def _get_service():
    from bot.integrations.google.auth import get_credentials
    creds = get_credentials()
    if creds is None:
        return None
    try:
        from googleapiclient.discovery import build
        return build("sheets", "v4", credentials=creds, cache_discovery=False)
    except Exception as e:
        logging.error("Google Sheets: failed to build service: %s", e)
        return None


def get_spreadsheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


async def get_or_create_spreadsheet(title: str, user_id: int) -> Optional[str]:
    """Find existing spreadsheet in Google Drive or create a new one.

    Stores the spreadsheet_id in the user's settings for reuse.
    Returns spreadsheet_id or None on failure.
    """
    from bot.db.database import db

    # Check cached ID
    stored = await db.google_spreadsheet_get(user_id)
    if stored:
        return stored

    # Check config for global default
    try:
        import config
        if config.GOOGLE_SPREADSHEET_ID:
            await db.google_spreadsheet_set(user_id, config.GOOGLE_SPREADSHEET_ID)
            return config.GOOGLE_SPREADSHEET_ID
    except Exception:
        pass

    svc = _get_service()
    if not svc:
        return None

    try:
        # Create via Drive API inside the shared root folder
        from googleapiclient.discovery import build as _build
        import config as _cfg
        drive_svc = _build("drive", "v3", credentials=svc._http.credentials, cache_discovery=False)

        # Create spreadsheet file in the shared folder
        file_meta = {
            "name": title,
            "mimeType": "application/vnd.google-apps.spreadsheet",
        }
        if _cfg.GOOGLE_DRIVE_ROOT_FOLDER_ID:
            file_meta["parents"] = [_cfg.GOOGLE_DRIVE_ROOT_FOLDER_ID]
        file_result = drive_svc.files().create(body=file_meta, fields="id").execute()
        sid = file_result["id"]

        # Add all sheet tabs
        sheet_requests = []
        for sheet_name in list(_SHEET_HEADERS.keys())[1:]:  # skip first (already exists as Sheet1)
            sheet_requests.append({"addSheet": {"properties": {"title": sheet_name}}})
        # Rename first sheet
        meta = svc.spreadsheets().get(spreadsheetId=sid).execute()
        first_sheet_id = meta["sheets"][0]["properties"]["sheetId"]
        sheet_requests.insert(0, {
            "updateSheetProperties": {
                "properties": {"sheetId": first_sheet_id, "title": list(_SHEET_HEADERS.keys())[0]},
                "fields": "title",
            }
        })
        svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": sheet_requests}).execute()

        await db.google_spreadsheet_set(user_id, sid)
        logging.info("Google Sheets: created spreadsheet %s for user %s", sid, user_id)
        return sid
    except Exception as e:
        logging.error("Google Sheets: create spreadsheet failed: %s", e)
        return None


def _get_sheet_id(svc, spreadsheet_id: str, sheet_name: str) -> Optional[int]:
    try:
        meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for s in meta.get("sheets", []):
            if s["properties"]["title"] == sheet_name:
                return s["properties"]["sheetId"]
    except Exception:
        pass
    return None


def ensure_sheet_sync(svc, spreadsheet_id: str, sheet_name: str) -> bool:
    """Create sheet tab and write headers if it doesn't exist. Synchronous."""
    try:
        existing_id = _get_sheet_id(svc, spreadsheet_id, sheet_name)
        if existing_id is None:
            # Create sheet
            body = {"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]}
            svc.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()

        # Write headers (row 1) if missing
        headers = _SHEET_HEADERS.get(sheet_name, [])
        if headers:
            range_name = f"{sheet_name}!A1:{chr(64 + len(headers))}1"
            result = svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name
            ).execute()
            existing = result.get("values", [])
            if not existing or existing[0] != headers:
                svc.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption="RAW",
                    body={"values": [headers]},
                ).execute()
        return True
    except Exception as e:
        logging.error("Google Sheets: ensure_sheet(%s) error: %s", sheet_name, e)
        return False


def append_row_sync(svc, spreadsheet_id: str, sheet_name: str, row: list) -> Optional[int]:
    """Append a row. Returns the 1-based row number or None on failure."""
    try:
        ensure_sheet_sync(svc, spreadsheet_id, sheet_name)
        range_name = f"{sheet_name}!A:A"
        result = svc.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        updated = result.get("updates", {}).get("updatedRange", "")
        # Parse row number from "SheetName!A5:G5"
        try:
            row_num = int(updated.split("!")[-1].split(":")[0][1:])
            return row_num
        except Exception:
            return None
    except Exception as e:
        logging.error("Google Sheets: append_row(%s) error: %s", sheet_name, e)
        return None


async def append_row(spreadsheet_id: str, sheet_name: str, row: list,
                     user_id: int = 0, object_type: str = None,
                     object_id: int = None) -> Optional[int]:
    """Async wrapper — runs sync Sheets API call in executor."""
    import asyncio
    svc = _get_service()
    if not svc:
        return None
    loop = asyncio.get_event_loop()
    row_num = await loop.run_in_executor(
        None, append_row_sync, svc, spreadsheet_id, sheet_name, row
    )
    if row_num and user_id and object_type:
        from bot.db.database import db
        await db.google_link_save(
            user_id=user_id,
            object_type=object_type,
            object_id=object_id or 0,
            google_type="sheet_row",
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name,
            row_number=row_num,
            url=f"{get_spreadsheet_url(spreadsheet_id)}#gid=0",
        )
    return row_num


async def read_sheet(spreadsheet_id: str, sheet_name: str, limit: int = 100) -> list[dict]:
    """Read sheet and return list of dicts keyed by header row."""
    import asyncio
    svc = _get_service()
    if not svc:
        return []

    def _read():
        try:
            result = svc.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1:Z{limit + 1}",
            ).execute()
            values = result.get("values", [])
            if len(values) < 2:
                return []
            headers = values[0]
            rows = []
            for row in values[1:]:
                row += [""] * (len(headers) - len(row))
                rows.append(dict(zip(headers, row)))
            return rows
        except Exception as e:
            logging.error("Google Sheets: read_sheet(%s) error: %s", sheet_name, e)
            return []

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _read)
