"""Storage Router — TUNTUN Google Brain Layer (Step 1).

Decides WHERE each piece of data should be stored:
  - structured data  → Google Sheets
  - long text        → Google Docs + summary/link in LongNotes sheet
  - files/photos     → Google Drive + row in Attachments sheet
  - everything       → memory_items index (local brain)
  - if Google down   → sync_queue pending, no crash

All functions are local-first: assumes local SQLite object is ALREADY created.
This router only handles the outbound sync + memory indexing.

Public API
──────────
classify_storage_target(message_text, object_type, payload, attachments) -> dict
save_structured_to_google(user_id, object_type, object_id, payload)       -> bool
save_long_text_to_google_doc(user_id, object_type, object_id, payload)    -> str|None
save_file_to_google_drive(user_id, object_type, object_id, payload)       -> str|None
index_saved_object_to_memory(user_id, object_type, object_id, payload, google_url) -> int
route_saved_object(user_id, object_type, object_id, payload)              -> dict
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Object type → Google Sheet name ───────────────────────────────────────────
_OBJECT_TO_SHEET: dict[str, str] = {
    "expense":        "Finance",
    "finance":        "Finance",
    "task":           "Tasks",
    "reminder":       "Reminders",
    "memory":         "Memory",
    "idea":           "Ideas",
    "project":        "Projects",
    "study":          "Study",
    "daily_plan":     "DailyPlans",
    "plan":           "DailyPlans",
    "long_note":      "LongNotes",
    "attachment":     "Attachments",
    "photo":          "Attachments",
    "voice":          "Attachments",
    "document":       "Attachments",
    "file":           "Attachments",
    "backup":         "Attachments",
    "campaign":       "Campaigns",
    "creative":       "Creatives",
    "order":          "Orders",
    "metric":         "Metrics",
    "relation":       "Relations",
    "ads":            "Ads",
    "dynamic_record": "DynamicRecords",
    "dynamic":        "DynamicRecords",
    "memory_index":   "MemoryIndex",
}

# ── Types that always upload to Drive ─────────────────────────────────────────
_DRIVE_TYPES: set[str] = {"attachment", "photo", "voice", "document", "file", "backup"}

# ── Types that always create a Google Doc (regardless of text length) ─────────
_DOC_TYPES: set[str] = {"long_note", "daily_review", "big_idea", "project_description"}

# ── Structured types — always to Sheets, never auto-Doc ───────────────────────
_STRUCTURED_TYPES: set[str] = {
    "expense", "finance", "task", "reminder", "memory", "idea", "project",
    "study", "campaign", "creative", "order", "metric", "relation",
    "ads", "dynamic_record", "dynamic",
}

# ── Text length threshold for automatic Google Doc creation ───────────────────
_DOC_TEXT_THRESHOLD: int = 1500


# ══════════════════════════════════════════════════════════════════════════════
# 1. classify_storage_target  (pure logic, no I/O)
# ══════════════════════════════════════════════════════════════════════════════

def classify_storage_target(
    message_text: Optional[str] = None,
    object_type: Optional[str] = None,
    payload: Optional[dict] = None,
    attachments: Optional[list] = None,
) -> dict:
    """Classify where a piece of data should be stored.

    Returns:
        {
            "target":             "sheets" | "docs" | "drive" | "mixed" | "local_only",
            "sheet_name":         str | None,
            "needs_doc":          bool,
            "needs_drive":        bool,
            "needs_memory_index": bool,
            "reason":             str,
            "confidence":         float,
        }

    No I/O, no OpenAI calls — pure classification.
    """
    payload = payload or {}
    attachments = attachments or []
    otype = (object_type or payload.get("object_type") or "").lower().strip()
    text = message_text or payload.get("content") or payload.get("text") or payload.get("value") or ""
    text_len = len(text)
    sheet_name = _OBJECT_TO_SHEET.get(otype)

    # ── 1. Files / attachments → Drive (always) ───────────────────────────────
    if attachments or otype in _DRIVE_TYPES:
        return {
            "target": "mixed",
            "sheet_name": sheet_name or "Attachments",
            "needs_doc": False,
            "needs_drive": True,
            "needs_memory_index": True,
            "reason": f"file/attachment (type={otype or 'list'}) → Drive + Attachments sheet",
            "confidence": 0.95,
        }

    # ── 2. Long text or explicit doc types → Google Doc ───────────────────────
    if otype in _DOC_TYPES or text_len > _DOC_TEXT_THRESHOLD:
        return {
            "target": "mixed",
            "sheet_name": sheet_name or "LongNotes",
            "needs_doc": True,
            "needs_drive": False,
            "needs_memory_index": True,
            "reason": (
                f"doc type '{otype}'" if otype in _DOC_TYPES
                else f"long text ({text_len} chars > {_DOC_TEXT_THRESHOLD})"
            ) + " → Doc + LongNotes sheet",
            "confidence": 0.90,
        }

    # ── 3. Known structured types → Sheets ────────────────────────────────────
    if otype in _STRUCTURED_TYPES:
        return {
            "target": "sheets",
            "sheet_name": sheet_name or "DynamicRecords",
            "needs_doc": False,
            "needs_drive": False,
            "needs_memory_index": True,
            "reason": f"structured type '{otype}' → {sheet_name or 'DynamicRecords'} sheet",
            "confidence": 0.90,
        }

    # ── 4. Known sheet mapping but not in structured set ──────────────────────
    if sheet_name:
        return {
            "target": "sheets",
            "sheet_name": sheet_name,
            "needs_doc": False,
            "needs_drive": False,
            "needs_memory_index": True,
            "reason": f"mapped type '{otype}' → {sheet_name} sheet",
            "confidence": 0.80,
        }

    # ── 5. Unknown / short note → local only ──────────────────────────────────
    return {
        "target": "local_only",
        "sheet_name": "MemoryIndex",
        "needs_doc": False,
        "needs_drive": False,
        "needs_memory_index": True,
        "reason": f"unknown type '{otype}' or short text → local memory only",
        "confidence": 0.60,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. Content helpers  (no OpenAI — template-based)
# ══════════════════════════════════════════════════════════════════════════════

def _build_content(object_type: str, payload: dict) -> str:
    """Build a human-readable content string from payload. No API calls."""
    otype = object_type.lower()
    p = payload

    if otype in ("expense", "finance"):
        parts = []
        amt = p.get("amount")
        cur = p.get("currency", "USD")
        if amt is not None:
            parts.append(f"{amt} {cur}")
        desc = p.get("description") or p.get("comment")
        if desc:
            parts.append(str(desc))
        proj = p.get("project_name") or p.get("project")
        if proj:
            parts.append(f"проект: {proj}")
        return " — ".join(parts) or str(p)

    if otype == "task":
        title = p.get("title", "")
        desc = p.get("description", "")
        due = p.get("due_date", "")
        parts = [title]
        if desc:
            parts.append(desc)
        if due:
            parts.append(f"срок: {due}")
        return " | ".join(filter(None, parts))

    if otype == "reminder":
        text = p.get("text", "")
        when = p.get("remind_at", "")
        return f"{text} — {when}" if when else text

    if otype in ("idea",):
        title = p.get("title", "")
        desc = p.get("description", "")
        return f"{title}\n{desc}".strip() if desc else title

    if otype == "project":
        name = p.get("name") or p.get("title", "")
        desc = p.get("description", "")
        return f"{name}: {desc}".strip(": ") if desc else name

    if otype in ("campaign",):
        name = p.get("name", "")
        platform = p.get("platform", "")
        budget = p.get("budget_usd") or p.get("budget")
        parts = [name]
        if platform:
            parts.append(platform)
        if budget is not None:
            parts.append(f"бюджет: {budget} USD")
        return " | ".join(filter(None, parts))

    if otype == "metric":
        metric_name = p.get("metric_name", "")
        value = p.get("value", "")
        unit = p.get("unit", "")
        entity = p.get("entity_type", "")
        return f"{entity} {metric_name}: {value} {unit}".strip()

    # Generic: join key: value pairs
    parts = [f"{k}: {v}" for k, v in p.items() if v is not None and str(v).strip()]
    return "\n".join(parts) or object_type


def _build_summary(object_type: str, payload: dict, max_len: int = 300) -> str:
    """Build a short summary without OpenAI calls."""
    content = _build_content(object_type, payload)
    if len(content) <= max_len:
        return content
    cut = content[:max_len]
    for sep in (".", "!", "?", "\n"):
        idx = cut.rfind(sep)
        if idx > max_len // 2:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Save functions
# ══════════════════════════════════════════════════════════════════════════════

async def save_structured_to_google(
    user_id: int,
    object_type: str,
    object_id: int,
    payload: dict,
) -> bool:
    """Sync a structured object to Google Sheets via existing sync layer.

    Uses sync_object_to_google() which handles queue fallback internally.
    Never raises.
    """
    try:
        from bot.integrations.google.auth import is_google_enabled
        if not is_google_enabled():
            logger.debug("save_structured_to_google: Google disabled, skipping user=%s", user_id)
            return False
        from bot.integrations.google.sync import sync_object_to_google
        return await sync_object_to_google(
            user_id=user_id,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
        )
    except Exception as exc:
        logger.warning(
            "save_structured_to_google: user=%s type=%s id=%s: %s",
            user_id, object_type, object_id, exc,
        )
        return False


async def save_long_text_to_google_doc(
    user_id: int,
    object_type: str,
    object_id: int,
    payload: dict,
) -> Optional[str]:
    """Create a Google Doc for long text. Returns doc URL or None.

    Also writes a summary row to LongNotes sheet via sync_long_note().
    Never raises.
    """
    try:
        from bot.integrations.google.auth import is_google_enabled
        if not is_google_enabled():
            logger.debug("save_long_text_to_google_doc: Google disabled, skipping user=%s", user_id)
            return None
        from bot.integrations.google.sync import sync_long_note
        url = await sync_long_note(user_id, object_id, payload)
        return url
    except Exception as exc:
        logger.warning(
            "save_long_text_to_google_doc: user=%s type=%s id=%s: %s",
            user_id, object_type, object_id, exc,
        )
        return None


async def save_file_to_google_drive(
    user_id: int,
    object_type: str,
    object_id: int,
    payload: dict,
) -> Optional[str]:
    """Upload a file to Google Drive. Returns drive URL or None.

    Also writes a row to Attachments sheet via sync_attachment().
    Never raises.
    """
    try:
        from bot.integrations.google.auth import is_google_enabled
        if not is_google_enabled():
            logger.debug("save_file_to_google_drive: Google disabled, skipping user=%s", user_id)
            return None
        from bot.integrations.google.sync import sync_attachment
        url = await sync_attachment(user_id, object_id, payload)
        return url
    except Exception as exc:
        logger.warning(
            "save_file_to_google_drive: user=%s type=%s id=%s: %s",
            user_id, object_type, object_id, exc,
        )
        return None


async def index_saved_object_to_memory(
    user_id: int,
    object_type: str,
    object_id: int,
    payload: dict,
    google_url: Optional[str] = None,
) -> int:
    """Index the saved object into memory_items brain index.

    Deduplicates by (source_type, source_id) — safe to call multiple times.
    Never raises.
    """
    try:
        from bot.modules.memory_indexer import index_memory_item
        content = _build_content(object_type, payload)
        summary = _build_summary(object_type, payload)
        source_date = (
            payload.get("date") or payload.get("due_date") or
            payload.get("remind_at") or payload.get("created_at") or None
        )
        if source_date:
            source_date = str(source_date)[:10]
        importance = int(payload.get("importance", 3))
        source_title = (
            payload.get("title") or payload.get("name") or
            payload.get("text", "")[:60] or object_type
        )
        return await index_memory_item(
            user_id=user_id,
            content=content,
            source_type=object_type,
            source_id=str(object_id),
            summary=summary,
            source_url=google_url,
            source_title=source_title,
            source_date=source_date,
            importance=importance,
        )
    except Exception as exc:
        logger.warning(
            "index_saved_object_to_memory: user=%s type=%s id=%s: %s",
            user_id, object_type, object_id, exc,
        )
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. route_saved_object — main entry point
# ══════════════════════════════════════════════════════════════════════════════

async def route_saved_object(
    user_id: int,
    object_type: str,
    object_id: int,
    payload: dict,
) -> dict:
    """Classify + save to Google (async, non-blocking) + index to memory.

    Call this AFTER the local SQLite object is already created.
    Never raises.

    Returns:
        {
            "target":        str,
            "google_synced": bool,
            "doc_url":       str | None,
            "drive_url":     str | None,
            "memory_id":     int,
            "errors":        list[str],
        }
    """
    report: dict = {
        "target": "local_only",
        "google_synced": False,
        "doc_url": None,
        "drive_url": None,
        "memory_id": 0,
        "errors": [],
    }

    try:
        text = (
            payload.get("content") or payload.get("text") or
            payload.get("value") or payload.get("description") or ""
        )
        attachments = payload.get("attachments") or []

        decision = classify_storage_target(
            message_text=text,
            object_type=object_type,
            payload=payload,
            attachments=attachments,
        )
        report["target"] = decision["target"]

        google_url: Optional[str] = None

        # ── Drive upload ───────────────────────────────────────────────────────
        if decision["needs_drive"]:
            drive_url = await save_file_to_google_drive(user_id, object_type, object_id, payload)
            report["drive_url"] = drive_url
            if drive_url:
                google_url = drive_url
                report["google_synced"] = True
            else:
                report["errors"].append("drive_upload_failed_or_disabled")

        # ── Google Doc ─────────────────────────────────────────────────────────
        elif decision["needs_doc"]:
            doc_url = await save_long_text_to_google_doc(user_id, object_type, object_id, payload)
            report["doc_url"] = doc_url
            if doc_url:
                google_url = doc_url
                report["google_synced"] = True
            else:
                report["errors"].append("doc_creation_failed_or_disabled")

        # ── Google Sheets ──────────────────────────────────────────────────────
        elif decision["target"] in ("sheets", "mixed"):
            synced = await save_structured_to_google(user_id, object_type, object_id, payload)
            report["google_synced"] = synced
            if not synced:
                report["errors"].append("sheets_sync_failed_or_disabled")

        # ── Memory index (always) ──────────────────────────────────────────────
        if decision["needs_memory_index"]:
            mem_id = await index_saved_object_to_memory(
                user_id, object_type, object_id, payload, google_url=google_url,
            )
            report["memory_id"] = mem_id

    except Exception as exc:
        logger.error(
            "route_saved_object: unexpected error user=%s type=%s id=%s: %s",
            user_id, object_type, object_id, exc,
        )
        report["errors"].append(f"unexpected: {exc}")

    return report
