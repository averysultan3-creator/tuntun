"""Memory, Rules & Learning Layer — TUNTUN Step 3.

Detects user-expressed rules, preferences, definitions, corrections, and strategies.
Stores them in `memory_rules` table and optionally syncs to Google Sheets MemoryIndex.

Public API
──────────
is_memory_message(text)                                       → bool
save_memory_rule(user_id, text, source_message, sync_google)  → dict
get_relevant_memory(text, user_id, scope_candidates, limit)   → list[dict]
process_correction(text, user_id, source_message_id)          → dict
apply_definitions_to_tasks(tasks, definitions)                → list[dict]
build_memory_feedback(save_result)                            → str
"""
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Detection regexes ─────────────────────────────────────────────────────────

# Broad signal: does this message smell like a rule/preference/definition/correction?
_MEMORY_SIGNAL_RE = re.compile(
    r'\bзапомни\b|\bпомни\b'
    r'|\bвсегда\b|\bникогда\b'
    r'|\bисправь\b|\bисправи\b'
    r'|мне\s+(?:не\s+)?нравится'
    r'|делай\s+(?:так|короче|жестче|длиннее|проще|быстрее)'
    r'|не\s+делай\s+так\b'
    r'|это\s+не\s+\w'
    r'|когда\s+(?:я\s+)?говорю\b'
    r'|считай\s+\S+\s+как\s+'
    r'|значит\s+(?:это|ads|кампани|клиент|creativ)',
    re.IGNORECASE,
)

# Correction: "Исправь: CTR был 2.1%, не 1.2%"
_CORRECTION_METRIC_RE = re.compile(
    r'\b(CTR|CPC|CPM|CPA|ROAS|CR|CVR)\b'
    r'(?:.*?)'
    r'(?:был|стал|оказался|дал)\s*([\d,\.]+)\s*(%?)'
    r'(?:.*?)'
    r'(?:не|а\s+не)\s+([\d,\.]+)',
    re.IGNORECASE | re.DOTALL,
)

# "Исправь: X" — generic correction with fix target
_CORRECTION_SIMPLE_RE = re.compile(
    r'исправь\b[:\s]+(.*)',
    re.IGNORECASE,
)

# "это не X, это Y"
_TYPE_CORRECTION_RE = re.compile(
    r'это\s+не\s+(\w+)[,.]?\s+это\s+(\w+)',
    re.IGNORECASE,
)

# Definition: "когда (я) говорю X, значит Y"
_DEFINITION_RE = re.compile(
    r'когда\s+(?:я\s+)?говорю\s+[«"\'"]?([\w\s]+)[»"\'"]?,?\s+значит\s+(.*)',
    re.IGNORECASE,
)
# Alternative: "считай X как Y"
_DEFINITION_ALT_RE = re.compile(
    r'считай\s+[«"\'"]?([\w\s]+)[»"\'"]?\s+как\s+(.*)',
    re.IGNORECASE,
)
# "'плохие объявления' = ads" style
_DEFINITION_EQ_RE = re.compile(
    r'[«"\'"]?([\w\s]{3,30})[»"\'"]?\s*(?:=|==|это)\s*(.+)',
    re.IGNORECASE,
)

# Scope: "для клиента X"
_SCOPE_CLIENT_RE = re.compile(r'для\s+клиента\s+(\S+)', re.IGNORECASE)
_SCOPE_CAMPAIGN_RE = re.compile(r'для\s+кампании\s+(\S+)', re.IGNORECASE)
_SCOPE_CREATIVE_RE = re.compile(r'для\s+(?:этого\s+)?креатива\s+(\S+)', re.IGNORECASE)

# Meaning parser: "ads со статусом low_performance" → {target_type, status}
_MEANING_ADS_RE = re.compile(r'ads\s+(?:со\s+статусом\s+|с\s+)?(\w+)', re.IGNORECASE)
_MEANING_CAMPAIGN_RE = re.compile(r'кампании?\s+(?:со\s+статусом\s+|с\s+)?(\w+)', re.IGNORECASE)
_MEANING_CREATIVE_RE = re.compile(r'креатив\w*\s+(?:со\s+статусом\s+|с\s+)?(\w+)', re.IGNORECASE)


def is_memory_message(text: str) -> bool:
    """Return True if the text appears to express a rule/preference/definition/correction."""
    return bool(_MEMORY_SIGNAL_RE.search(text))


def _classify_memory_type(text: str) -> str:
    """Determine the memory_type from text content.

    Returns one of: rule / preference / definition / correction / strategy / note
    """
    t = text.lower()

    if re.search(r'\bисправь\b|\bисправи\b|это\s+не\s+\w|был\s+[\d,\.]+%?\s+не\s+[\d,\.]+', t):
        return "correction"

    if re.search(
        r'когда\s+(?:я\s+)?говорю|значит\s+(?:это|ads|кампани|клиент|creativ)'
        r'|считай\s+\S+\s+как',
        t,
    ):
        return "definition"

    if re.search(
        r'мне\s+(?:не\s+)?нравятся?|делай\s+так\b|делай\b.{0,30}(?:короче|жестче|длиннее|проще)\b'
        r'|не\s+делай\s+так\b',
        t,
    ):
        return "preference"

    if re.search(r'\bесли\b.*?(?:\bто\b|\bэто\b)|\bвсегда\b|\bникогда\b', t):
        if re.search(r'сначала|потом|порядок|проверяй|стратег', t):
            return "strategy"
        return "rule"

    # "запомни" + any conditional/numeric logic → rule
    if re.search(r'\bзапомни\b', t) and re.search(r'\bесли\b|%|ниже|выше|меньше|больше', t):
        return "rule"

    if re.search(r'\bзапомни\b.*\bправило\b', t):
        return "rule"

    return "note"


def _extract_scope(text: str) -> tuple[str, Optional[str]]:
    """Return (scope_type, scope_name) from message text.

    Returns ("global", None) if no scope found.
    """
    m = _SCOPE_CLIENT_RE.search(text)
    if m:
        return "client", m.group(1).strip(".,;:")

    m = _SCOPE_CAMPAIGN_RE.search(text)
    if m:
        return "campaign", m.group(1).strip(".,;:")

    m = _SCOPE_CREATIVE_RE.search(text)
    if m:
        return "creative", m.group(1).strip(".,;:")

    return "global", None


def _extract_definition(text: str) -> Optional[dict]:
    """Extract {trigger, meaning, parsed_meaning} from a definition phrase."""
    m = _DEFINITION_RE.search(text)
    if m:
        trigger = m.group(1).strip().lower()
        meaning = m.group(2).strip().rstrip(".")
        return {"trigger": trigger, "meaning": meaning, **_parse_meaning(meaning)}

    m = _DEFINITION_ALT_RE.search(text)
    if m:
        trigger = m.group(1).strip().lower()
        meaning = m.group(2).strip().rstrip(".")
        return {"trigger": trigger, "meaning": meaning, **_parse_meaning(meaning)}

    return None


def _parse_meaning(meaning: str) -> dict:
    """Try to extract structured data from a meaning string.

    E.g. "ads со статусом low_performance" → {target_type: "ad", target_status: "low_performance"}
    """
    result = {}
    m = _MEANING_ADS_RE.search(meaning)
    if m:
        result["target_type"] = "ad"
        result["target_status"] = m.group(1).lower()
        return result
    m = _MEANING_CAMPAIGN_RE.search(meaning)
    if m:
        result["target_type"] = "campaign"
        result["target_status"] = m.group(1).lower()
        return result
    m = _MEANING_CREATIVE_RE.search(meaning)
    if m:
        result["target_type"] = "creative"
        result["target_status"] = m.group(1).lower()
        return result
    return result


def _extract_correction_target(text: str) -> Optional[dict]:
    """Extract {metric_name, new_value, old_value} from a correction phrase."""
    m = _CORRECTION_METRIC_RE.search(text)
    if m:
        try:
            return {
                "metric_name": m.group(1).upper(),
                "new_value": float(m.group(2).replace(",", ".")),
                "unit": m.group(3) or "",
                "old_value": float(m.group(4).replace(",", ".")),
            }
        except (ValueError, AttributeError):
            pass

    # "Исправь: CTR 2.1%"
    m = re.search(
        r'исправь[:\s].*?\b(CTR|CPC|CPM|CPA|ROAS|CR|CVR)\b\s*(?:[=:]?\s*)([\d,\.]+)\s*(%?)',
        text, re.IGNORECASE,
    )
    if m:
        try:
            return {
                "metric_name": m.group(1).upper(),
                "new_value": float(m.group(2).replace(",", ".")),
                "unit": m.group(3) or "",
                "old_value": None,
            }
        except ValueError:
            pass

    return None


def _extract_type_correction(text: str) -> Optional[dict]:
    """Extract {old_type, new_type} from 'это не X, это Y'."""
    m = _TYPE_CORRECTION_RE.search(text)
    if m:
        return {"old_type": m.group(1).lower(), "new_type": m.group(2).lower()}
    return None


def _extract_normalized_key(text: str) -> str:
    """Extract keywords from the rule text for fast retrieval later.

    Returns space-separated lowercase words (3+ chars, no stop words).
    """
    _STOP = {
        "это", "что", "для", "как", "так", "его", "ему", "ней", "них",
        "или", "при", "все", "под", "над", "без", "про", "две", "три",
        "что", "который", "которая", "которые", "есть",
    }
    words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    keywords = [w for w in words if len(w) >= 3 and w not in _STOP]
    # Keep at most 15 most informative words (longer = more specific)
    keywords.sort(key=len, reverse=True)
    return " ".join(dict.fromkeys(keywords[:15]))


async def save_memory_rule(
    user_id: int,
    text: str,
    source_message: str = None,
    sync_google: bool = False,
    _force_type: str = None,
) -> dict:
    """Detect, classify and persist a memory rule from a user message.

    Returns a result dict with:
        {rule_id, memory_type, scope_type, scope_name, text,
         definition, correction, clarifications, sync_ok}
    """
    from bot.db.database import db

    memory_type = _force_type or _classify_memory_type(text)
    scope_type, scope_name = _extract_scope(text)
    normalized_key = _extract_normalized_key(text)
    clarifications: list[str] = []

    # Build extra_json based on type
    extra: dict = {}
    if memory_type == "definition":
        defn = _extract_definition(text)
        if defn:
            extra = defn
        else:
            # Fallback: store raw text as the "definition"
            extra = {"trigger": text[:60].lower(), "meaning": text}
            clarifications.append("Не удалось чётко распознать что=что в определении")

    if memory_type == "correction":
        corr = _extract_correction_target(text)
        type_corr = _extract_type_correction(text)
        if corr:
            extra["correction"] = corr
        if type_corr:
            extra["type_correction"] = type_corr

    extra_json = json.dumps(extra, ensure_ascii=False) if extra else None

    # Determine confidence
    confidence = 1.0
    if memory_type == "note":
        confidence = 0.7  # uncertain classification
    if clarifications:
        confidence = 0.8

    rule_id = await db.rule_create(
        user_id=user_id,
        memory_type=memory_type,
        text=text,
        scope_type=scope_type,
        scope_name=scope_name,
        normalized_key=normalized_key,
        extra_json=extra_json,
        confidence=confidence,
        source_message=source_message or text,
    )

    # Sync to MemoryIndex sheet
    sync_ok = False
    if sync_google:
        try:
            from bot.integrations.google.sync import sync_object_to_google
            sync_ok = await sync_object_to_google(
                user_id=user_id,
                object_type="memory_rule",
                object_id=rule_id,
                payload={
                    "memory_type": memory_type,
                    "scope_type": scope_type,
                    "scope_name": scope_name or "",
                    "text": text,
                    "normalized_key": normalized_key,
                },
            )
        except Exception as exc:
            logger.warning("save_memory_rule: sync failed: %s", exc)

    result = {
        "rule_id": rule_id,
        "memory_type": memory_type,
        "scope_type": scope_type,
        "scope_name": scope_name,
        "text": text,
        "clarifications": clarifications,
        "sync_ok": sync_ok,
    }
    if extra.get("correction"):
        result["correction"] = extra["correction"]
    if extra.get("trigger"):
        result["definition"] = extra

    return result


async def get_relevant_memory(
    text: str,
    user_id: int,
    scope_candidates: list[str] = None,
    limit: int = 10,
) -> list[dict]:
    """Return relevant memory rules for the given message text.

    Includes:
    - All global active rules for this user
    - Scoped rules matching any of scope_candidates
    - Rules whose text/normalized_key contains words from the message
    """
    from bot.db.database import db

    # Extract keywords for text matching
    words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    keywords = [w for w in words if len(w) > 3][:10]

    try:
        rows = await db.rule_search(
            user_id=user_id,
            keywords=keywords if keywords else None,
            scope_candidates=scope_candidates,
            limit=limit,
        )
    except Exception as exc:
        logger.warning("get_relevant_memory: search failed: %s", exc)
        rows = []

    # Touch last_accessed_at on memory_items level (optional, skip here to keep it simple)
    return rows


async def process_correction(
    text: str,
    user_id: int,
    source_message_id: int = None,
) -> dict:
    """Handle a correction message.

    1. Extract the correction target (metric, entity type, etc.)
    2. Try to find and update the matching DB record
    3. Save a correction rule
    4. Return a result dict for feedback building
    """
    from bot.db.database import db

    correction = _extract_correction_target(text)
    type_correction = _extract_type_correction(text)
    correction_result: dict = {}
    metric_updated = False

    # ── Try to update metric ─────────────────────────────────────────────────
    if correction:
        metric_name = correction["metric_name"]
        new_value = correction["new_value"]

        try:
            recent = await db._fetchall(
                """SELECT id, metric_value, data_json FROM metrics
                   WHERE user_id=? AND metric_name=?
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id, metric_name),
            )
            if recent:
                row = recent[0]
                old_from_db = row["metric_value"]
                # Preserve old value in data_json
                try:
                    data = json.loads(row["data_json"] or "{}")
                except Exception:
                    data = {}
                data["corrected_from"] = old_from_db
                data["corrected_at"] = __import__("datetime").datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                await db._execute(
                    """UPDATE metrics
                       SET metric_value=?, data_json=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (new_value, json.dumps(data, ensure_ascii=False), row["id"]),
                )
                correction_result = {
                    "metric_name": metric_name,
                    "old_value": old_from_db,
                    "new_value": new_value,
                    "metric_id": row["id"],
                    "updated": True,
                }
                metric_updated = True
        except Exception as exc:
            logger.warning("process_correction: metric update failed: %s", exc)

        if not metric_updated:
            correction_result = {
                "metric_name": metric_name,
                "old_value": correction.get("old_value"),
                "new_value": new_value,
                "updated": False,
            }

    # ── Save correction rule ─────────────────────────────────────────────────
    rule_result = await save_memory_rule(
        user_id=user_id,
        text=text,
        source_message=text,
        sync_google=False,
        _force_type="correction",
    )
    rule_result["correction"] = correction_result
    rule_result["type_correction"] = type_correction

    return rule_result


def apply_definitions_to_tasks(tasks: list[dict], definitions: list[dict]) -> list[dict]:
    """Expand task metadata using definition rules.

    For each task, check if its title matches any definition trigger.
    If yes, add target_type/target_status from the parsed meaning.

    Args:
        tasks: list of task dicts (with at least "title")
        definitions: list of memory_rule rows with memory_type="definition"

    Returns:
        Enriched task list (same length, some tasks may have extra keys added).
    """
    if not definitions or not tasks:
        return tasks

    for task in tasks:
        title_lower = task.get("title", "").lower()
        for defn in definitions:
            extra = defn.get("extra") or {}
            trigger = extra.get("trigger", "")
            if not trigger:
                continue
            # Check if the trigger phrase appears in the task title
            if trigger in title_lower:
                target_type = extra.get("target_type")
                target_status = extra.get("target_status")
                meaning = extra.get("meaning", "")
                if target_type:
                    task.setdefault("target_type", target_type)
                if target_status:
                    task.setdefault("target_status", target_status)
                if meaning and "meaning" not in task:
                    task["meaning"] = meaning
                # Apply only the most specific (first matched) definition
                break

    return tasks


def build_memory_feedback(result: dict) -> str:
    """Build a concise confirmation message for the user.

    Examples:
        "✅ Запомнил правило: «если CTR < 1.5%...»"
        "✅ Запомнил определение: «плохие объявления = ads...»"
        "✅ Исправил CTR: 1.2% → 2.1%. Старое значение сохранено."
    """
    memory_type = result.get("memory_type", "note")
    text = result.get("text", "")
    scope_type = result.get("scope_type", "global")
    scope_name = result.get("scope_name")
    correction = result.get("correction") or {}
    clarifications = result.get("clarifications") or []

    short = (text[:100] + "…") if len(text) > 100 else text

    # Scope suffix
    scope_note = ""
    if scope_name:
        scope_label = {"client": "клиент", "campaign": "кампания", "creative": "креатив"}.get(
            scope_type, scope_type
        )
        scope_note = f" (для {scope_label} «{scope_name}»)"

    # Correction feedback
    if memory_type == "correction":
        metric = correction.get("metric_name")
        old_val = correction.get("old_value")
        new_val = correction.get("new_value")
        type_c = result.get("type_correction") or {}

        if metric and new_val is not None:
            if old_val is not None and correction.get("updated"):
                msg = f"✅ Исправил {metric}: {old_val}% → {new_val}%. Старое значение сохранено в истории."
            elif old_val is not None:
                msg = f"✅ Запомнил исправление {metric}: {old_val}% → {new_val}%. Не нашёл запись для обновления — сохранил как correction note."
            else:
                msg = f"✅ Обновил {metric} до {new_val}%."
            return msg

        if type_c:
            return (
                f"✅ Запомнил исправление: «{type_c['old_type']}» → «{type_c['new_type']}».\n"
                f"Не нашёл конкретную запись, сохранил как correction note."
            )

        return f"✅ Запомнил исправление{scope_note}: «{short}»."

    # Definition feedback
    if memory_type == "definition":
        defn = result.get("definition") or {}
        trigger = defn.get("trigger", "")
        meaning = defn.get("meaning", "")
        if trigger and meaning:
            return f"✅ Запомнил определение{scope_note}: «{trigger}» = {meaning}."
        return f"✅ Запомнил определение{scope_note}: «{short}»."

    # Preference feedback
    if memory_type == "preference":
        return f"✅ Запомнил предпочтение{scope_note}: «{short}»."

    # Rule feedback
    if memory_type == "rule":
        return f"✅ Запомнил правило{scope_note}: «{short}»."

    # Strategy feedback
    if memory_type == "strategy":
        return f"✅ Запомнил стратегию{scope_note}: «{short}»."

    # Generic note
    feedback = f"✅ Запомнил{scope_note}: «{short}»."
    if clarifications:
        feedback += f"\n⚠️ {clarifications[0]}"
    return feedback
