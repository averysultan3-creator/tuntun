"""Google sync engine for TUNTUN.

sync_object_to_google() — sync one object to Google (with fallback to queue).
process_sync_queue()    — retry pending items from the queue (called by scheduler).

Supported object types / targets:
    expense     → Finance sheet
    task        → Tasks sheet
    reminder    → Reminders sheet
    memory      → Memory sheet
    idea        → Ideas sheet
    long_note   → LongNotes sheet + Google Doc
    attachment  → Attachments sheet + Google Drive
    backup      → Google Drive
"""
import json
import logging
from datetime import date
from typing import Optional

from bot.integrations.google.auth import is_google_enabled


async def _get_spreadsheet(user_id: int) -> Optional[str]:
    """Return spreadsheet_id for user, creating one if needed."""
    from bot.db.database import db
    from bot.integrations.google.sheets import get_or_create_spreadsheet
    sid = await db.google_spreadsheet_get(user_id)
    if not sid:
        sid = await get_or_create_spreadsheet("TUNTUN — Personal Database", user_id)
    return sid


async def sync_expense(user_id: int, expense_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    today = payload.get("date") or date.today().strftime("%Y-%m-%d")
    row = [
        today,
        payload.get("amount", ""),
        payload.get("currency", "USD"),
        payload.get("description", ""),
        payload.get("project_name", ""),
        payload.get("comment", ""),
        str(expense_id),
    ]
    result = await append_row(sid, "Finance", row, user_id=user_id,
                               object_type="expense", object_id=expense_id)
    return result is not None


async def sync_task(user_id: int, task_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(task_id),
        payload.get("title", ""),
        payload.get("priority", "normal"),
        payload.get("due_date", ""),
        payload.get("status", "pending"),
    ]
    result = await append_row(sid, "Tasks", row, user_id=user_id,
                               object_type="task", object_id=task_id)
    return result is not None


async def sync_reminder(user_id: int, reminder_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(reminder_id),
        payload.get("text", ""),
        payload.get("remind_at", ""),
        "active",
    ]
    result = await append_row(sid, "Reminders", row, user_id=user_id,
                               object_type="reminder", object_id=reminder_id)
    return result is not None


async def sync_memory(user_id: int, memory_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(memory_id),
        payload.get("category", ""),
        payload.get("key_name", ""),
        payload.get("value", ""),
    ]
    result = await append_row(sid, "Memory", row, user_id=user_id,
                               object_type="memory", object_id=memory_id)
    return result is not None


async def sync_idea(user_id: int, idea_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(idea_id),
        payload.get("title", ""),
        payload.get("category", "general"),
        payload.get("status", "new"),
        payload.get("related_project", ""),
    ]
    result = await append_row(sid, "Ideas", row, user_id=user_id,
                               object_type="idea", object_id=idea_id)
    return result is not None


async def sync_long_note(user_id: int, note_id: int, payload: dict) -> Optional[str]:
    """Create a Google Doc and index it in LongNotes sheet. Returns doc URL."""
    from bot.integrations.google.docs import create_doc, make_summary
    from bot.integrations.google.sheets import append_row

    title = payload.get("title", "Заметка")
    content = payload.get("content", "")
    category = payload.get("category", "note")
    tags = payload.get("tags", "")

    # AI summary
    summary = await make_summary(content)

    # Create Google Doc
    import config
    folder_id = config.GOOGLE_DRIVE_ROOT_FOLDER_ID or None
    doc_url = await create_doc(
        title=title,
        content=content,
        folder_id=folder_id,
        user_id=user_id,
        object_type="long_note",
        object_id=note_id,
    )

    # Index in LongNotes sheet
    sid = await _get_spreadsheet(user_id)
    if sid:
        row = [
            date.today().strftime("%Y-%m-%d"),
            title,
            category,
            summary,
            doc_url or "",
            tags,
        ]
        await append_row(sid, "LongNotes", row, user_id=user_id,
                          object_type="long_note", object_id=note_id)

    return doc_url


async def sync_attachment(user_id: int, attachment_id: int, payload: dict) -> Optional[str]:
    """Upload file to Drive and index in Attachments sheet. Returns drive URL."""
    from bot.integrations.google.drive import upload_file
    from bot.integrations.google.sheets import append_row

    local_path = payload.get("local_path", "")
    file_type = payload.get("file_type", "file")
    caption = payload.get("caption", "")
    section = payload.get("section_name", "")

    # Determine subfolder
    subfolder_map = {"photo": "Photos", "document": "Documents", "voice": "Voice"}
    subfolder = subfolder_map.get(file_type, "Files")

    drive_url = None
    if local_path:
        drive_url = await upload_file(
            local_path=local_path,
            subfolder=subfolder,
            user_id=user_id,
            object_type="attachment",
            object_id=attachment_id,
        )

    sid = await _get_spreadsheet(user_id)
    if sid:
        row = [
            date.today().strftime("%Y-%m-%d"),
            file_type,
            section,
            caption,
            local_path,
            drive_url or "",
            payload.get("summary", ""),
        ]
        await append_row(sid, "Attachments", row, user_id=user_id,
                          object_type="attachment", object_id=attachment_id)

    return drive_url


# ── Dispatcher ────────────────────────────────────────────────────────────────

_SYNC_HANDLERS = {
    "expense":    sync_expense,
    "task":       sync_task,
    "reminder":   sync_reminder,
    "memory":     sync_memory,
    "idea":       sync_idea,
}


async def sync_object_to_google(user_id: int, object_type: str, object_id: int,
                                 payload: dict, target: str = "sheets") -> bool:
    """Attempt to sync to Google. On failure, enqueue for retry.

    Returns True if sync succeeded immediately.
    """
    if not is_google_enabled():
        return False

    try:
        if object_type == "long_note":
            result = await sync_long_note(user_id, object_id, payload)
            return result is not None
        if object_type == "attachment":
            result = await sync_attachment(user_id, object_id, payload)
            return result is not None

        handler = _SYNC_HANDLERS.get(object_type)
        if handler:
            return await handler(user_id, object_id, payload)
        return False

    except Exception as e:
        logging.warning(
            "google_sync: failed for %s#%s user=%s: %s — queuing",
            object_type, object_id, user_id, e
        )
        await _enqueue(user_id, object_type, object_id, target, "create", payload)
        return False


async def _enqueue(user_id: int, object_type: str, object_id: int,
                   target: str, action: str, payload: dict):
    try:
        from bot.db.database import db
        await db.google_sync_enqueue(user_id, object_type, object_id, target, action, payload)
    except Exception as e:
        logging.error("google_sync: failed to enqueue: %s", e)


async def process_sync_queue():
    """Process pending sync queue items. Called by the scheduler."""
    if not is_google_enabled():
        return

    from bot.db.database import db
    pending = await db.google_sync_pending(limit=20)
    if not pending:
        return

    logging.info("google_sync: processing %d pending items", len(pending))

    for item in pending:
        row_id = item["id"]
        retry_count = item.get("retry_count", 0) + 1
        try:
            payload = json.loads(item.get("payload_json") or "{}")
            success = await sync_object_to_google(
                user_id=item["user_id"],
                object_type=item["object_type"],
                object_id=item.get("object_id", 0),
                payload=payload,
                target=item.get("target", "sheets"),
            )
            if success:
                await db.google_sync_mark_done(row_id)
            else:
                await db.google_sync_mark_error(row_id, "handler returned False", retry_count)
        except Exception as e:
            await db.google_sync_mark_error(row_id, str(e), retry_count)
