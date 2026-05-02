"""Google sync engine for TUNTUN.

sync_object_to_google() — sync one object to Google (with fallback to queue).
process_sync_queue()    — retry pending items from the queue (called by scheduler).

Supported object types / targets:
    expense     → Finance sheet
    task        → Tasks sheet
    reminder    → Reminders sheet
    memory      → Memory sheet
    idea        → Ideas sheet
    entity      → Entities sheet
    relation    → Relations sheet
    event       → Events sheet
    metric      → Metrics sheet
    campaign    → Campaigns sheet
    creative    → Creatives sheet
    order       → Orders sheet
    ads         → Ads sheet
    memory_rule → MemoryIndex sheet
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


async def sync_entity(user_id: int, entity_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(entity_id),
        payload.get("type", ""),
        payload.get("name", ""),
        payload.get("title", ""),
        payload.get("canonical_key", ""),
        payload.get("status", "active"),
        payload.get("data_json", ""),
    ]
    result = await append_row(sid, "Entities", row, user_id=user_id,
                               object_type="entity", object_id=entity_id)
    return result is not None


async def sync_relation(user_id: int, relation_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(relation_id),
        payload.get("from_type", ""),
        payload.get("from_id", ""),
        payload.get("relation_type", ""),
        payload.get("to_type", ""),
        payload.get("to_id", ""),
        payload.get("confidence", 1.0),
        payload.get("source_message_id", ""),
        payload.get("data_json", ""),
    ]
    result = await append_row(sid, "Relations", row, user_id=user_id,
                               object_type="relation", object_id=relation_id)
    return result is not None


async def sync_event(user_id: int, event_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(event_id),
        payload.get("entity_type", ""),
        payload.get("entity_id", ""),
        payload.get("event_type", ""),
        payload.get("date", ""),
        payload.get("title", ""),
        payload.get("source_message_id", ""),
        payload.get("data_json", ""),
    ]
    result = await append_row(sid, "Events", row, user_id=user_id,
                               object_type="event", object_id=event_id)
    return result is not None


async def sync_metric(user_id: int, metric_id: int, payload: dict) -> bool:
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(metric_id),
        payload.get("entity_type", ""),
        payload.get("entity_id", ""),
        payload.get("metric_name", ""),
        payload.get("metric_value", ""),
        payload.get("unit", ""),
        payload.get("date", ""),
        payload.get("source", ""),
        payload.get("data_json", ""),
    ]
    result = await append_row(sid, "Metrics", row, user_id=user_id,
                               object_type="metric", object_id=metric_id)
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


async def sync_dynamic_record(user_id: int, record_id: int, payload: dict) -> bool:
    """Sync a dynamic section record to DynamicRecords sheet."""
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    import json as _json
    section_name = payload.get("section_name", "")
    data = payload.get("data") or {}
    data_json = _json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
    summary = payload.get("summary", str(data)[:120])
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(record_id),
        section_name,
        data_json,
        summary,
        date.today().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    result = await append_row(sid, "DynamicRecords", row, user_id=user_id,
                               object_type="dynamic_record", object_id=record_id)
    return result is not None


async def sync_campaign(user_id: int, campaign_id: int, payload: dict) -> bool:
    """Sync a campaign to Campaigns sheet (separate handler)."""
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(campaign_id),
        payload.get("project_id", ""),
        payload.get("name", ""),
        payload.get("platform", ""),
        payload.get("launch_date", payload.get("date_start", "")),
        payload.get("status", "active"),
        str(payload.get("budget_usd") or payload.get("budget_amount") or payload.get("budget") or ""),
        payload.get("budget_currency", "USD"),
        payload.get("notes", ""),
    ]
    result = await append_row(sid, "Campaigns", row, user_id=user_id,
                               object_type="campaign", object_id=campaign_id)
    return result is not None


async def sync_creative(user_id: int, creative_id: int, payload: dict) -> bool:
    """Sync a creative to Creatives sheet."""
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    # Creatives headers: date, id, campaign_id, name, format, status, asset_link, notes
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(creative_id),
        str(payload.get("campaign_id", "")),
        payload.get("name", ""),
        payload.get("format", ""),
        payload.get("status", "active"),
        payload.get("asset_link", ""),
        payload.get("notes", ""),
    ]
    result = await append_row(sid, "Creatives", row, user_id=user_id,
                               object_type="creative", object_id=creative_id)
    return result is not None


async def sync_order(user_id: int, order_id: int, payload: dict) -> bool:
    """Sync an order to Orders sheet."""
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        payload.get("date") or date.today().strftime("%Y-%m-%d"),
        str(order_id),
        str(payload.get("project_id", "")),
        str(payload.get("campaign_id") or payload.get("source_campaign") or ""),
        str(payload.get("amount") or payload.get("amount_usd") or ""),
        payload.get("currency", "USD"),
        payload.get("status", "new"),
        payload.get("customer", ""),
        payload.get("notes", ""),
    ]
    result = await append_row(sid, "Orders", row, user_id=user_id,
                               object_type="order", object_id=order_id)
    return result is not None


async def sync_ads(user_id: int, ad_id: int, payload: dict) -> bool:
    """Sync an ad/account status row to Ads sheet."""
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    row = [
        payload.get("date") or date.today().strftime("%Y-%m-%d"),
        str(ad_id),
        payload.get("platform", ""),
        payload.get("account", ""),
        str(payload.get("project_id", "")),
        payload.get("status", "active"),
        payload.get("notes", ""),
    ]
    result = await append_row(sid, "Ads", row, user_id=user_id,
                               object_type="ads", object_id=ad_id)
    return result is not None


async def sync_memory_index(user_id: int, item_id: int, payload: dict) -> bool:
    """Sync a memory_items row reference to MemoryIndex sheet."""
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(item_id),
        payload.get("source_type", ""),
        str(payload.get("source_id", "")),
        payload.get("category", ""),
        payload.get("summary", ""),
        payload.get("tags", ""),
        payload.get("google_link", ""),
    ]
    result = await append_row(sid, "MemoryIndex", row, user_id=user_id,
                               object_type="memory_index", object_id=item_id)
    return result is not None


async def sync_episode(user_id: int, episode_id: int, payload: dict) -> bool:
    """Sync a conversation episode to ConversationEpisodes sheet."""
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    import json as _json

    # Format list fields as semicolon-separated strings
    def _fmt(val):
        if isinstance(val, list):
            return "; ".join(str(x) for x in val if x)
        return str(val) if val else ""

    people = payload.get("people") or []
    people_str = "; ".join(
        p.get("name", "") if isinstance(p, dict) else str(p)
        for p in people if p
    )

    row = [
        payload.get("date") or date.today().strftime("%Y-%m-%d"),
        str(episode_id),
        payload.get("title", ""),
        payload.get("summary", "")[:500],
        _fmt(payload.get("decisions")),
        people_str,
        _fmt(payload.get("projects")),
        _fmt(payload.get("tasks")),
        payload.get("google_doc_url") or "",
    ]
    result = await append_row(sid, "ConversationEpisodes", row, user_id=user_id,
                               object_type="episode", object_id=episode_id)
    return result is not None


async def sync_memory_rule(user_id: int, rule_id: int, payload: dict) -> bool:
    """Sync a memory_rule to MemoryIndex sheet.

    Uses the same MemoryIndex sheet with source_type='memory_rule'.
    MemoryIndex columns: date, id, source_type, source_id, category, summary, tags, google_link
    """
    sid = await _get_spreadsheet(user_id)
    if not sid:
        return False
    from bot.integrations.google.sheets import append_row
    scope = payload.get("scope_type", "global")
    scope_name = payload.get("scope_name", "")
    scope_tag = f"{scope}:{scope_name}" if scope_name else scope
    row = [
        date.today().strftime("%Y-%m-%d"),
        str(rule_id),
        "memory_rule",
        str(rule_id),
        payload.get("memory_type", "rule"),
        payload.get("text", ""),
        f"{scope_tag} {payload.get('normalized_key', '')}".strip(),
        "",  # no google_link for rules
    ]
    result = await append_row(sid, "MemoryIndex", row, user_id=user_id,
                               object_type="memory_rule", object_id=rule_id)
    return result is not None


# ── Dispatcher ────────────────────────────────────────────────────────────────

_SYNC_HANDLERS = {
    "expense":        sync_expense,
    "finance":        sync_expense,
    "task":           sync_task,
    "reminder":       sync_reminder,
    "memory":         sync_memory,
    "idea":           sync_idea,
    "entity":         sync_entity,
    "relation":       sync_relation,
    "event":          sync_event,
    "metric":         sync_metric,
    "dynamic_record": sync_dynamic_record,
    "dynamic":        sync_dynamic_record,
    "campaign":       sync_campaign,
    "creative":       sync_creative,
    "order":          sync_order,
    "ads":            sync_ads,
    "ad":             sync_ads,
    "memory_index":   sync_memory_index,
    "memory_rule":    sync_memory_rule,
    "episode":        sync_episode,
}


async def sync_object_to_google(user_id: int, object_type: str, object_id: int,
                                 payload: dict, target: str = "sheets") -> bool:
    """Attempt to sync to Google. On failure, enqueue for retry.

    Returns True if sync succeeded immediately.
    """
    if not is_google_enabled():
        try:
            import config
            if getattr(config, "GOOGLE_ENABLED", False):
                await _enqueue(user_id, object_type, object_id, target, "create", payload)
        except Exception as e:
            logging.warning(
                "google_sync: unavailable for %s#%s user=%s and queue failed: %s",
                object_type, object_id, user_id, e
            )
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
