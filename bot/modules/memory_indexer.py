"""Memory V2 Indexer — TUNTUN bot.

All functions are cheap (no OpenAI calls).
Writes to memory_items via db.memory_item_upsert().

Public API
──────────
make_memory_hash(user_id, source_type, source_id, content) -> str
guess_category(text, source_type=None)                     -> str
extract_tags(text, category=None)                          -> list[str]
compact_summary(text, max_len=400)                         -> str
index_memory_item(...)                                     -> int
index_explicit_memory(memory_row)                          -> int
index_telegram_message(...)                                -> int
index_voice_transcript(...)                                -> int
index_vision_result(...)                                   -> int
index_dynamic_record(...)                                  -> int
index_task(...)                                            -> int
index_reminder(...)                                        -> int
index_finance_record(...)                                  -> int
backfill_old_memory_to_items(user_id=None)                 -> dict
"""
import hashlib
import json
import logging
import re
from typing import Optional

from bot.db.database import db

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Category detection helpers
# ──────────────────────────────────────────────────────────────────────────────

_CATEGORY_PATTERNS: list[tuple[str, list[str]]] = [
    ("finance",    ["расход", "трата", "бюджет", "деньги", "expense", "стоимость",
                    "зарплата", "доход", "плачу", "заплатил", "купил", "куп"]),
    ("health",     ["здоровье", "самочувствие", "тренировка", "бег", "спорт",
                    "либидо", "энергия", "питание", "еда", "сон", "будильник"]),
    ("study",      ["учёба", "учеба", "задание", "экзамен", "лекция", "пара",
                    "предмет", "коллоквиум", "study", "конспект"]),
    ("task",       ["задача", "задачи", "дела", "todo", "сделать", "task"]),
    ("reminder",   ["напоминание", "напомни", "reminder", "будильник"]),
    ("project",    ["проект", "project", "работа", "разработка"]),
    ("idea",       ["идея", "идеи", "idea", "придумал", "мысль"]),
    ("photo",      ["фото", "фотография", "снимок", "photo", "image", "картинка"]),
    ("voice",      ["голосовое", "аудио", "voice", "запись"]),
    ("schedule",   ["расписание", "событие", "встреча", "schedule", "event"]),
    ("ads",        ["реклама", "кабинет", "кампания", "ads", "facebook", "fb",
                    "meta", "креатив"]),
    ("car",        ["машина", "авто", "car", "бензин", "топливо", "заправка"]),
    ("plan",       ["план", "план на", "планирование", "daily", "daily plan"]),
]


def guess_category(text: str, source_type: Optional[str] = None) -> str:
    """Return a category string based on source_type hint + text patterns.

    Never calls external APIs.
    """
    # source_type shortcuts
    _source_map = {
        "explicit_memory": None,  # fall through to text
        "telegram_message": None,
        "voice": "voice",
        "vision": "photo",
        "task": "task",
        "reminder": "reminder",
        "dynamic": None,
        "expense": "finance",
        "finance": "finance",
        "idea": "idea",
        "plan": "plan",
        "study": "study",
        "schedule": "schedule",
    }
    if source_type and source_type in _source_map and _source_map[source_type] is not None:
        return _source_map[source_type]

    t = text.lower().replace("ё", "е")
    for category, keywords in _CATEGORY_PATTERNS:
        for kw in keywords:
            if kw in t:
                return category
    return "general"


# ──────────────────────────────────────────────────────────────────────────────
# Tag extraction
# ──────────────────────────────────────────────────────────────────────────────

_TAG_PATTERNS: dict[str, list[str]] = {
    "срочно":   ["срочно", "urgent", "important", "важно", "asap"],
    "деньги":   ["расход", "трата", "деньги", "бюджет", "expense"],
    "здоровье": ["здоровье", "тренировка", "спорт", "сон"],
    "учёба":    ["учёба", "учеба", "экзамен", "задание"],
    "идея":     ["идея", "мысль"],
    "задача":   ["задача", "дела", "todo"],
    "машина":   ["машина", "авто", "бензин"],
    "реклама":  ["реклама", "facebook", "ads", "кабинет"],
    "план":     ["план", "планирование", "daily"],
}


def extract_tags(text: str, category: Optional[str] = None) -> list:
    """Extract relevant string tags from text (no API calls). Max 8 tags."""
    t = text.lower().replace("ё", "е")
    tags: list[str] = []
    if category and category not in ("general", None):
        tags.append(category)
    for tag, keywords in _TAG_PATTERNS.items():
        if tag not in tags:
            for kw in keywords:
                if kw in t:
                    tags.append(tag)
                    break
    return tags[:8]


# ──────────────────────────────────────────────────────────────────────────────
# Summary helper
# ──────────────────────────────────────────────────────────────────────────────

def compact_summary(text: str, max_len: int = 400) -> str:
    """Return first `max_len` chars of text after basic cleanup. No OpenAI calls."""
    if not text:
        return ""
    # collapse whitespace
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= max_len:
        return text
    # try to cut at last sentence boundary before max_len
    cut = text[:max_len]
    for sep in (".", "!", "?", "\n"):
        idx = cut.rfind(sep)
        if idx > max_len // 2:
            return cut[: idx + 1].strip()
    return cut.rstrip() + "…"


# ──────────────────────────────────────────────────────────────────────────────
# Hash
# ──────────────────────────────────────────────────────────────────────────────

def make_memory_hash(
    user_id: int,
    source_type: str,
    source_id: Optional[str],
    content: str,
) -> str:
    """Deterministic SHA-256 hash for deduplication."""
    raw = f"{user_id}|{source_type}|{source_id or ''}|{content[:1000]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ──────────────────────────────────────────────────────────────────────────────
# Core indexer
# ──────────────────────────────────────────────────────────────────────────────

async def index_memory_item(
    user_id: int,
    content: str,
    source_type: str,
    source_id=None,
    summary: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[list] = None,
    importance: int = 3,
    source_url: Optional[str] = None,
    source_title: Optional[str] = None,
    source_date: Optional[str] = None,
) -> int:
    """Index one item into memory_items. No OpenAI calls.

    Returns the row id.
    """
    if not content or not content.strip():
        return 0

    sid = str(source_id) if source_id is not None else None
    cat = category or guess_category(content, source_type)
    tag_list = tags if tags is not None else extract_tags(content, cat)
    summ = summary or compact_summary(content, max_len=300)
    h = make_memory_hash(user_id, source_type, sid, content)
    tags_json = json.dumps(tag_list, ensure_ascii=False) if tag_list else None

    try:
        row_id = await db.memory_item_upsert(
            user_id=user_id,
            content=content,
            hash=h,
            source_type=source_type,
            source_id=sid,
            summary=summ,
            category=cat,
            tags_json=tags_json,
            importance=importance,
            source_url=source_url,
            source_title=source_title,
            source_date=source_date,
        )
        return row_id
    except Exception as exc:
        logger.warning("index_memory_item failed (user=%s source=%s/%s): %s",
                       user_id, source_type, sid, exc)
        return 0


# ──────────────────────────────────────────────────────────────────────────────
# Source-specific indexers
# ──────────────────────────────────────────────────────────────────────────────

async def index_explicit_memory(memory_row: dict) -> int:
    """Index a row from the old `memory` table into memory_items."""
    user_id = memory_row.get("user_id")
    value = str(memory_row.get("value") or "").strip()
    if not user_id or not value:
        return 0
    category = memory_row.get("category") or "general"
    key_name = memory_row.get("key_name")
    source_title = f"{category}: {key_name}" if key_name else category
    importance = int(memory_row.get("importance") or 3)
    source_id = str(memory_row["id"]) if memory_row.get("id") else None
    source_date = (memory_row.get("created_at") or "")[:10] or None
    return await index_memory_item(
        user_id=user_id,
        content=value,
        source_type="explicit_memory",
        source_id=source_id,
        category=category,
        source_title=source_title,
        importance=importance,
        source_date=source_date,
    )


async def index_telegram_message(
    user_id: int,
    message_id,
    text: str,
    source_date: Optional[str] = None,
    importance: int = 2,
) -> int:
    """Index a Telegram text message into memory_items."""
    if not text or not text.strip():
        return 0
    return await index_memory_item(
        user_id=user_id,
        content=text,
        source_type="telegram_message",
        source_id=str(message_id) if message_id is not None else None,
        importance=importance,
        source_date=source_date,
    )


async def index_voice_transcript(
    user_id: int,
    attachment_id,
    transcript: str,
    source_date: Optional[str] = None,
    importance: int = 3,
) -> int:
    """Index a voice transcript."""
    if not transcript or not transcript.strip():
        return 0
    return await index_memory_item(
        user_id=user_id,
        content=transcript,
        source_type="voice",
        source_id=str(attachment_id) if attachment_id is not None else None,
        category="voice",
        importance=importance,
        source_date=source_date,
    )


async def index_vision_result(
    user_id: int,
    attachment_id,
    summary: str,
    extracted_text: Optional[str] = None,
    photo_type: Optional[str] = None,
    source_date: Optional[str] = None,
    importance: int = 3,
) -> int:
    """Index a vision/photo analysis result."""
    content = summary or ""
    if extracted_text:
        content = f"{content}\n{extracted_text}".strip()
    if not content:
        return 0
    return await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="vision",
        source_id=str(attachment_id) if attachment_id is not None else None,
        summary=summary,
        category="photo",
        source_title=f"Фото ({photo_type})" if photo_type else "Фото",
        importance=importance,
        source_date=source_date,
    )


async def index_dynamic_record(
    user_id: int,
    record_id,
    section_name: str,
    data: str,
    source_date: Optional[str] = None,
    importance: int = 3,
) -> int:
    """Index a dynamic section record."""
    if not data or not data.strip():
        return 0
    return await index_memory_item(
        user_id=user_id,
        content=data,
        source_type="dynamic",
        source_id=str(record_id) if record_id is not None else None,
        source_title=section_name,
        source_date=source_date,
        importance=importance,
    )


async def index_task(
    user_id: int,
    task_id,
    title: str,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    priority: str = "normal",
    importance: int = 3,
) -> int:
    """Index a task into memory_items."""
    content = title
    if description:
        content = f"{title}\n{description}"
    if due_date:
        importance = max(importance, 4) if priority in ("high", "urgent") else importance
    return await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="task",
        source_id=str(task_id) if task_id is not None else None,
        category="task",
        source_title=title,
        importance=importance,
        source_date=due_date,
    )


async def index_reminder(
    user_id: int,
    reminder_id,
    text: str,
    remind_at: Optional[str] = None,
    importance: int = 4,
) -> int:
    """Index a reminder."""
    if not text or not text.strip():
        return 0
    source_date = (remind_at or "")[:10] or None
    return await index_memory_item(
        user_id=user_id,
        content=text,
        source_type="reminder",
        source_id=str(reminder_id) if reminder_id is not None else None,
        category="reminder",
        importance=importance,
        source_date=source_date,
    )


async def index_finance_record(
    user_id: int,
    expense_id,
    amount: float,
    currency: str = "USD",
    description: Optional[str] = None,
    project_name: Optional[str] = None,
    date: Optional[str] = None,
    importance: int = 3,
) -> int:
    """Index a finance/expense record."""
    parts = [f"{amount} {currency}"]
    if description:
        parts.append(description)
    if project_name:
        parts.append(f"проект: {project_name}")
    content = " — ".join(parts)
    return await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="finance",
        source_id=str(expense_id) if expense_id is not None else None,
        category="finance",
        source_date=date,
        importance=importance,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Backfill
# ──────────────────────────────────────────────────────────────────────────────

async def backfill_old_memory_to_items(user_id: Optional[int] = None) -> dict:
    """Import rows from the old `memory` table into `memory_items`.

    Idempotent: runs upsert per source_id, so safe to call multiple times.
    Returns {"imported": N, "skipped": N, "errors": N}.
    """
    report = {"imported": 0, "skipped": 0, "errors": 0}

    try:
        if user_id is not None:
            rows = await db.memory_recall(user_id)
        else:
            # Fetch all rows (no user filter)
            rows = await db._fetchall("SELECT * FROM memory ORDER BY created_at")
    except Exception as exc:
        logger.error("backfill: failed to fetch old memory: %s", exc)
        return report

    for row in rows:
        try:
            value = str(row.get("value") or "").strip()
            if not value:
                report["skipped"] += 1
                continue
            rid = await index_explicit_memory(row)
            if rid:
                report["imported"] += 1
            else:
                report["skipped"] += 1
        except Exception as exc:
            logger.warning("backfill: error on row id=%s: %s", row.get("id"), exc)
            report["errors"] += 1

    logger.info(
        "backfill_old_memory_to_items complete: imported=%d skipped=%d errors=%d",
        report["imported"], report["skipped"], report["errors"],
    )
    return report
