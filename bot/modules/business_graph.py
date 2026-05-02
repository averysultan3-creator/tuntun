"""Business Graph helpers for TUNTUN.

This is the normalized layer for objects that need relations and metrics:
project -> campaign -> creative -> spend -> orders -> result.

The module is deliberately small and local-first:
1. write to SQLite;
2. index to memory_items;
3. optionally enqueue/sync to Google Sheets.

Public API (foundation):
    create_or_update_entity(...)  → entity_id
    create_or_update_relation(...)→ relation_id
    record_event(...)             → event_id
    record_metric(...)            → metric_id
    get_entity_graph(...)         → dict

Public API (ingestion — Step 1):
    is_business_message(text)     → bool
    ingest_business_text(...)     → IngestResult dict
"""
import asyncio
import json
import logging
import re
from datetime import date, timedelta
from typing import Optional

import config
from bot.db.database import db
from bot.modules.memory_indexer import index_memory_item

logger = logging.getLogger(__name__)


def _json(data: Optional[dict]) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


async def _sync_google(object_type: str, user_id: int, object_id: int, payload: dict) -> None:
    """Best-effort Google sync. Never blocks the local graph write."""
    if not getattr(config, "GOOGLE_ENABLED", False):
        return
    try:
        from bot.integrations.google.sync import sync_object_to_google
        asyncio.create_task(sync_object_to_google(
            user_id=user_id,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
        ))
    except Exception as exc:
        logger.warning("business_graph: failed to schedule google sync: %s", exc)


async def create_or_update_entity(
    user_id: int,
    type: str,
    name: str,
    title: str = None,
    canonical_key: str = None,
    status: str = "active",
    data: dict = None,
    source_message_id: int = None,
    sync_google: bool = True,
) -> int:
    """Create/update an entity and index it for semantic-style retrieval later."""
    entity_id = await db.entity_upsert(
        user_id=user_id,
        type=type,
        name=name,
        title=title,
        canonical_key=canonical_key,
        status=status,
        data=data,
    )

    content_parts = [f"{type}: {title or name}"]
    if status:
        content_parts.append(f"status: {status}")
    if data:
        content_parts.append(_json(data))
    content = "\n".join(content_parts)

    await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="entity",
        source_id=str(entity_id),
        category=type,
        source_title=title or name,
        importance=4 if type in ("project", "campaign", "creative", "order") else 3,
    )

    if sync_google:
        await _sync_google("entity", user_id, entity_id, {
            "type": type,
            "name": name,
            "title": title or name,
            "canonical_key": canonical_key or name,
            "status": status,
            "data_json": _json(data),
            "source_message_id": source_message_id or "",
        })

    return entity_id


async def create_or_update_relation(
    user_id: int,
    from_type: str,
    from_id: int,
    relation_type: str,
    to_type: str,
    to_id: int,
    confidence: float = 1.0,
    source_message_id: int = None,
    data: dict = None,
    sync_google: bool = True,
) -> int:
    """Create/update a relation between two graph objects."""
    relation_id = await db.relation_upsert(
        user_id=user_id,
        from_type=from_type,
        from_id=from_id,
        relation_type=relation_type,
        to_type=to_type,
        to_id=to_id,
        confidence=confidence,
        source_message_id=source_message_id,
        data=data,
    )

    content = (
        f"{from_type}#{from_id} {relation_type} {to_type}#{to_id}"
        + (f"\n{_json(data)}" if data else "")
    )
    await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="relation",
        source_id=str(relation_id),
        category="relation",
        source_title=relation_type,
        importance=3,
    )

    if sync_google:
        await _sync_google("relation", user_id, relation_id, {
            "from_type": from_type,
            "from_id": from_id,
            "relation_type": relation_type,
            "to_type": to_type,
            "to_id": to_id,
            "confidence": confidence,
            "source_message_id": source_message_id or "",
            "data_json": _json(data),
        })

    return relation_id


async def record_event(
    user_id: int,
    event_type: str,
    entity_type: str = None,
    entity_id: int = None,
    date: str = None,
    title: str = None,
    data: dict = None,
    source_message_id: int = None,
    sync_google: bool = True,
) -> int:
    event_id = await db.event_create(
        user_id=user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        date=date,
        title=title,
        data=data,
        source_message_id=source_message_id,
    )

    content = f"{event_type}: {title or ''}".strip()
    if entity_type and entity_id:
        content += f"\nentity: {entity_type}#{entity_id}"
    if data:
        content += f"\n{_json(data)}"
    await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="event",
        source_id=str(event_id),
        category=event_type,
        source_title=title or event_type,
        source_date=date,
        importance=3,
    )

    if sync_google:
        await _sync_google("event", user_id, event_id, {
            "entity_type": entity_type or "",
            "entity_id": entity_id or "",
            "event_type": event_type,
            "date": date or "",
            "title": title or "",
            "source_message_id": source_message_id or "",
            "data_json": _json(data),
        })

    return event_id


async def record_metric(
    user_id: int,
    entity_type: str,
    entity_id: int,
    metric_name: str,
    metric_value: float = None,
    unit: str = None,
    date: str = None,
    source: str = None,
    data: dict = None,
    sync_google: bool = True,
) -> int:
    metric_id = await db.metric_create(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        metric_name=metric_name,
        metric_value=metric_value,
        unit=unit,
        date=date,
        source=source,
        data=data,
    )

    value = "" if metric_value is None else str(metric_value)
    content = f"{entity_type}#{entity_id}: {metric_name}={value} {unit or ''}".strip()
    if data:
        content += f"\n{_json(data)}"
    await index_memory_item(
        user_id=user_id,
        content=content,
        source_type="metric",
        source_id=str(metric_id),
        category="metric",
        source_title=metric_name,
        source_date=date,
        importance=3,
    )

    if sync_google:
        await _sync_google("metric", user_id, metric_id, {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "metric_name": metric_name,
            "metric_value": "" if metric_value is None else metric_value,
            "unit": unit or "",
            "date": date or "",
            "source": source or "",
            "data_json": _json(data),
        })

    return metric_id


async def get_entity_graph(user_id: int, entity_type: str, entity_id: int) -> dict:
    """Return a compact graph bundle for analytics/retrieval code."""
    entity = await db.entity_get(user_id, entity_id)
    relations = await db.relations_for_entity(user_id, entity_type, entity_id)
    events = await db.events_for_entity(user_id, entity_type, entity_id)
    metrics = await db.metrics_for_entity(user_id, entity_type, entity_id)
    return {
        "entity": entity,
        "relations": relations,
        "events": events,
        "metrics": metrics,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Business Text Ingestion  (Step 1)
# Deterministic extraction — no LLM required.
# ══════════════════════════════════════════════════════════════════════════════

# ── Russian number words → int ────────────────────────────────────────────────
_RU_NUMBERS: dict[str, int] = {
    "один": 1, "одну": 1, "одна": 1,
    "два": 2, "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}

_NUM_WORD_PAT = "|".join(_RU_NUMBERS.keys())  # "один|одну|..."

# ── Regex patterns ────────────────────────────────────────────────────────────

# "для клиента X" / "клиент X"
_CLIENT_RE = re.compile(
    r'клиент(?:а|у|е|ом|ов)?\s+([А-ЯA-Zа-яa-z0-9_\-\.]{1,40})',
    re.IGNORECASE | re.UNICODE,
)

# "3 кампании" / "два кампании"
_CAMPAIGN_COUNT_RE = re.compile(
    rf'(\d+|{_NUM_WORD_PAT})\s+кампани\w*',
    re.IGNORECASE,
)

# "два креатива" / "3 креатива"
_CREATIVE_COUNT_RE = re.compile(
    rf'(\d+|{_NUM_WORD_PAT})\s+креатив\w*',
    re.IGNORECASE,
)

# Metrics: "CTR 2.4%", "CPC 0.5", "ROAS 3.2", "CTR вышел 1.8%"
_METRIC_RE = re.compile(
    r'\b(CTR|CPC|CPM|CPA|ROAS|CR|CVR|leads|spend|revenue)'
    r'(?:\s*[=:—\-]?\s*|\s+\w+\s+)'
    r'([\d,\.]+)\s*(%?)',
    re.IGNORECASE,
)

# "не понравил" near "креатив"
_NEGATIVE_CREATIVE_RE = re.compile(
    r'(?:(?:\d+|два|три|четыре|пять|несколько)\s+)?креатив\w*\s+не\s+понравил'
    r'|не\s+понравил\w*\s+(?:(?:\d+|два|три|четыре|пять|несколько)\s+)?креатив',
    re.IGNORECASE,
)

# "плохие объявления" / "плохой креатив"
_NEGATIVE_RE = re.compile(r'не\s+понравил\w*|плох(?:ой|ие|их|ого|ому)\b|негатив\w*', re.IGNORECASE)

# "дал CTR" / "один дал"
_POSITIVE_METRIC_RE = re.compile(
    r'(?:один|одна|одну|\d+)?\s*(?:из\s+\w+\s+)?(?:дал|показал|имеет)\s+(\w+)\s+([\d,\.]+)\s*(%?)',
    re.IGNORECASE,
)

# Quick business-signal detector
_BUSINESS_SIGNAL_RE = re.compile(
    r'кампани|креатив|клиент|CTR|CPC|CPM|CPA|ROAS|CR\b|CVR|лид(?:ы|ов)?'
    r'|объявлен|рекламу?\b|бюджет\b|spend|revenue|трафик|конверси',
    re.IGNORECASE,
)


def is_business_message(text: str) -> bool:
    """Return True if text appears to contain business/marketing graph content.

    Fast heuristic — no LLM, no DB calls.
    """
    return bool(_BUSINESS_SIGNAL_RE.search(text))


def _parse_number(s: str) -> int:
    """Parse 'два' → 2, '3' → 3, etc. Returns 1 on unknown."""
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    return _RU_NUMBERS.get(s, 1)


def _extract_client_name(text: str) -> Optional[str]:
    m = _CLIENT_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_campaign_count(text: str) -> int:
    """Return detected campaign count, 0 if not found."""
    m = _CAMPAIGN_COUNT_RE.search(text)
    return _parse_number(m.group(1)) if m else 0


def _extract_creative_count(text: str) -> int:
    m = _CREATIVE_COUNT_RE.search(text)
    return _parse_number(m.group(1)) if m else 0


def _extract_metrics(text: str) -> list[dict]:
    """Extract list of {name, value, unit} dicts."""
    results: list[dict] = []
    seen: set[str] = set()
    for m in _METRIC_RE.finditer(text):
        name = m.group(1).upper()
        if name in seen:
            continue
        seen.add(name)
        raw_val = m.group(2).replace(",", ".")
        try:
            value = float(raw_val)
        except ValueError:
            continue
        unit = "%" if m.group(3) else ""
        results.append({"name": name, "value": value, "unit": unit})
    # Also check "X дал CTR N%"
    for m in _POSITIVE_METRIC_RE.finditer(text):
        name = m.group(1).upper()
        if name in seen or name not in {"CTR", "CPC", "CPM", "CPA", "ROAS", "CR", "CVR"}:
            continue
        seen.add(name)
        raw_val = m.group(2).replace(",", ".")
        try:
            value = float(raw_val)
        except ValueError:
            continue
        unit = "%" if m.group(3) else ""
        results.append({"name": name, "value": value, "unit": unit})
    return results


def _extract_tasks(text: str, date_today: str, date_tomorrow: str) -> list[dict]:
    """Extract task-like phrases from text.

    Handles:
      "завтра надо/нужно X и Y"
      "надо/нужно X" (today implied)
    """
    tasks: list[dict] = []
    seen: set[str] = set()

    def _add(title: str, due: str) -> None:
        title = title.strip().rstrip(".,;:")
        if len(title) < 4 or title in seen:
            return
        seen.add(title)
        tasks.append({"title": title, "due_date": due})

    # "завтра надо/нужно ... и ..."
    m = re.search(
        r'завтра\s+(?:надо|нужно|необходимо)?\s+(.*?)(?:\.|$)',
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        chunk = m.group(1).strip()
        for part in re.split(r'\s+и\s+', chunk):
            part = part.strip()
            if part:
                _add(part, date_tomorrow)

    # "надо/нужно X" without explicit day → today
    for m2 in re.finditer(
        r'(?<![а-яa-z])(?:надо|нужно|необходимо)\s+((?:проверить|выключить|посмотреть|сделать|запустить|обновить|остановить|создать)[^,\.;]+)',
        text,
        re.IGNORECASE,
    ):
        chunk = m2.group(1).strip()
        # If this chunk was already captured under "tomorrow", skip
        already = any(t["title"] in chunk or chunk in t["title"] for t in tasks)
        if not already:
            _add(chunk, date_today)

    return tasks


async def ingest_business_text(
    text: str,
    user_id: int,
    date_today: str = None,
    date_tomorrow: str = None,
    source: str = "message",
    source_message_id: int = None,
    sync_google: bool = True,
    rules: list = None,
) -> dict:
    """Parse raw user text into Business Graph objects (deterministic, no LLM).

    Creates in local SQLite:
      - entities  : client, campaign(s), creative(s)
      - relations : client→campaign, campaign→creative
      - metrics   : CTR/CPC/etc. on creative entities
      - events    : negative/positive feedback, tasks-as-events
      - real tasks: via db.task_create (tomorrow/today)

    rules (optional): pre-fetched memory rules from memory_rules table.
    If None, will auto-fetch from DB. Pass [] to skip rule application.

    Optionally syncs to Google Sheets via existing sync layer.

    Returns IngestResult dict:
      {
        "entities":      list of {id, type, name},
        "relations":     list of {id, relation_type},
        "events":        list of {id, event_type, title},
        "metrics":       list of {id, name, value, unit},
        "tasks":         list of {id, title, due_date},
        "clarifications": list of str,
        "summary":       str,
        "applied_rules": list of str,
      }
    """
    # ── Date defaults ─────────────────────────────────────────────────────────
    _today = date_today or date.today().strftime("%Y-%m-%d")
    _tomorrow = date_tomorrow or (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    # ── Fetch relevant rules if not provided ──────────────────────────────────
    if rules is None:
        try:
            from bot.modules.memory_rules import get_relevant_memory
            rules = await get_relevant_memory(text, user_id, limit=10)
        except Exception as exc:
            logger.debug("ingest_business_text: rule fetch failed: %s", exc)
            rules = []

    # Extract definitions and preferences from rules
    _definitions = [r for r in rules if r.get("memory_type") == "definition"]
    _applied_rules: list[str] = []

    # ── Result accumulators ───────────────────────────────────────────────────
    entities: list[dict] = []
    relations: list[dict] = []
    events: list[dict] = []
    metrics_result: list[dict] = []
    tasks: list[dict] = []
    clarifications: list[str] = []

    # ── 1. Extract raw signals ────────────────────────────────────────────────
    client_name = _extract_client_name(text)
    campaign_count = _extract_campaign_count(text)
    creative_count = _extract_creative_count(text)
    has_negative_creative = bool(_NEGATIVE_CREATIVE_RE.search(text))
    raw_metrics = _extract_metrics(text)
    raw_tasks = _extract_tasks(text, _today, _tomorrow)

    # If no business signals found at all, bail out early
    if not (client_name or campaign_count or creative_count or raw_metrics or raw_tasks):
        return {
            "entities": [], "relations": [], "events": [], "metrics": [],
            "tasks": [], "clarifications": ["Не удалось распознать бизнес-данные"],
            "summary": "",
        }

    # ── 2. Client entity ──────────────────────────────────────────────────────
    client_id: Optional[int] = None
    if client_name:
        client_id = await create_or_update_entity(
            user_id=user_id,
            type="client",
            name=client_name,
            canonical_key=f"client-{client_name.lower()}",
            source_message_id=source_message_id,
            sync_google=sync_google,
        )
        entities.append({"id": client_id, "type": "client", "name": client_name})
    else:
        clarifications.append("Не распознан клиент — укажи имя клиента явно")

    # ── 3. Campaign entity ────────────────────────────────────────────────────
    campaign_id: Optional[int] = None
    if campaign_count > 0:
        camp_name = (
            f"Кампании {_today} для {client_name}" if client_name
            else f"Кампании {_today}"
        )
        camp_key = camp_name.lower().replace(" ", "-")
        campaign_id = await create_or_update_entity(
            user_id=user_id,
            type="campaign",
            name=camp_name,
            canonical_key=camp_key,
            data={"count": campaign_count, "client": client_name or ""},
            source_message_id=source_message_id,
            sync_google=sync_google,
        )
        entities.append({"id": campaign_id, "type": "campaign", "name": camp_name})

        # Campaign sync with dedicated Campaigns sheet handler
        if sync_google:
            await _sync_google("campaign", user_id, campaign_id, {
                "name": camp_name,
                "project_id": client_id or "",
                "status": "active",
                "notes": f"count={campaign_count}",
            })

        # Relation: client → campaign
        if client_id and campaign_id:
            rel_id = await create_or_update_relation(
                user_id=user_id,
                from_type="client",
                from_id=client_id,
                relation_type="has_campaign",
                to_type="campaign",
                to_id=campaign_id,
                source_message_id=source_message_id,
                sync_google=sync_google,
            )
            relations.append({"id": rel_id, "relation_type": "has_campaign"})

    # ── 4. Creative entities ──────────────────────────────────────────────────
    # Determine how many creatives were mentioned with negative vs positive signals
    neg_count = 0
    pos_count = 0

    if creative_count > 0:
        # Heuristic: if "не понравились N" + "один дал CTR", split by sentiment
        if has_negative_creative and raw_metrics:
            neg_count = max(creative_count - 1, 1)
            pos_count = 1
        elif has_negative_creative:
            neg_count = creative_count
        else:
            pos_count = creative_count

    # Negative creative(s)
    neg_creative_id: Optional[int] = None
    if neg_count > 0:
        neg_name = f"Kreativ {_today} негатив"
        neg_key = f"creative-neg-{_today}"
        neg_creative_id = await create_or_update_entity(
            user_id=user_id,
            type="creative",
            name=neg_name,
            canonical_key=neg_key,
            data={"count": neg_count, "sentiment": "negative"},
            source_message_id=source_message_id,
            sync_google=sync_google,
        )
        entities.append({"id": neg_creative_id, "type": "creative", "name": neg_name})

        # Sync to Creatives sheet
        if sync_google:
            await _sync_google("creative", user_id, neg_creative_id, {
                "campaign_id": campaign_id or "",
                "name": neg_name,
                "status": "rejected",
                "notes": f"negative, count={neg_count}",
            })

        # Feedback event
        ev_id = await record_event(
            user_id=user_id,
            event_type="feedback",
            entity_type="creative",
            entity_id=neg_creative_id,
            date=_today,
            title=f"Негативная оценка ({neg_count} креатив(а))",
            data={"sentiment": "negative", "count": neg_count},
            source_message_id=source_message_id,
            sync_google=sync_google,
        )
        events.append({"id": ev_id, "event_type": "feedback", "title": f"Негатив ({neg_count})"})

        # Relation: campaign → negative creative
        if campaign_id:
            rel_id = await create_or_update_relation(
                user_id=user_id,
                from_type="campaign",
                from_id=campaign_id,
                relation_type="has_creative",
                to_type="creative",
                to_id=neg_creative_id,
                source_message_id=source_message_id,
                sync_google=sync_google,
            )
            relations.append({"id": rel_id, "relation_type": "has_creative"})

    # Positive/metric creative(s)
    pos_creative_id: Optional[int] = None
    if pos_count > 0 or raw_metrics:
        pos_name = f"Kreativ {_today} CTR" if raw_metrics else f"Kreativ {_today}"
        pos_key = f"creative-pos-{_today}"
        pos_creative_id = await create_or_update_entity(
            user_id=user_id,
            type="creative",
            name=pos_name,
            canonical_key=pos_key,
            data={"sentiment": "positive"},
            source_message_id=source_message_id,
            sync_google=sync_google,
        )
        entities.append({"id": pos_creative_id, "type": "creative", "name": pos_name})

        if sync_google:
            await _sync_google("creative", user_id, pos_creative_id, {
                "campaign_id": campaign_id or "",
                "name": pos_name,
                "status": "active",
                "notes": "positive" + (f", {raw_metrics[0]['name']}={raw_metrics[0]['value']}{raw_metrics[0]['unit']}" if raw_metrics else ""),
            })

        # Relation: campaign → positive creative
        if campaign_id:
            rel_id = await create_or_update_relation(
                user_id=user_id,
                from_type="campaign",
                from_id=campaign_id,
                relation_type="has_creative",
                to_type="creative",
                to_id=pos_creative_id,
                source_message_id=source_message_id,
                sync_google=sync_google,
            )
            relations.append({"id": rel_id, "relation_type": "has_creative"})

    # ── 5. Metrics ────────────────────────────────────────────────────────────
    # Attach to pos_creative if available, otherwise to campaign, else to client
    metric_entity_type = "creative" if pos_creative_id else ("campaign" if campaign_id else "client")
    metric_entity_id = pos_creative_id or campaign_id or client_id

    for m in raw_metrics:
        if metric_entity_id is None:
            clarifications.append(f"Метрика {m['name']}={m['value']}{m['unit']} не привязана (нет сущности)")
            continue
        met_id = await record_metric(
            user_id=user_id,
            entity_type=metric_entity_type,
            entity_id=metric_entity_id,
            metric_name=m["name"],
            metric_value=m["value"],
            unit=m["unit"],
            date=_today,
            source=source,
            sync_google=sync_google,
        )
        metrics_result.append({"id": met_id, "name": m["name"], "value": m["value"], "unit": m["unit"]})

    # ── 6. Tasks ──────────────────────────────────────────────────────────────
    # Apply definitions BEFORE creating tasks (expands triggers like "плохие объявления")
    if _definitions:
        try:
            from bot.modules.memory_rules import apply_definitions_to_tasks
            raw_tasks = apply_definitions_to_tasks(raw_tasks, _definitions)
            for defn in _definitions:
                _applied_rules.append(f"definition: {defn.get('normalized_key', defn.get('text', ''))[:60]}")
        except Exception as exc:
            logger.debug("ingest_business_text: apply_definitions failed: %s", exc)

    for t in raw_tasks:
        # Create real task in tasks table
        try:
            task_id = await db.task_create(
                user_id=user_id,
                title=t["title"],
                due_date=t["due_date"],
                priority="normal",
            )
        except Exception as exc:
            logger.warning("ingest_business_text: task_create failed: %s", exc)
            task_id = None

        # Also record as event in the graph (entity-agnostic)
        event_data: dict = {"source": source, "task_id": task_id}
        # If definitions expanded this task, store extra context
        if t.get("target_type"):
            event_data["target_type"] = t["target_type"]
        if t.get("target_status"):
            event_data["target_status"] = t["target_status"]
        ev_id = await record_event(
            user_id=user_id,
            event_type="task",
            entity_type=None,
            entity_id=None,
            date=t["due_date"],
            title=t["title"],
            data=event_data,
            source_message_id=source_message_id,
            sync_google=sync_google,
        )
        tasks.append({"id": task_id, "title": t["title"], "due_date": t["due_date"],
                       **({"target_type": t["target_type"]} if t.get("target_type") else {}),
                       **({"target_status": t["target_status"]} if t.get("target_status") else {})})
        events.append({"id": ev_id, "event_type": "task", "title": t["title"]})

    # ── 7. Build summary ──────────────────────────────────────────────────────
    parts: list[str] = []
    if entities:
        e_summary = ", ".join(f"{e['type']} «{e['name']}»" for e in entities[:4])
        parts.append(f"Сущности: {e_summary}")
    if metrics_result:
        m_summary = ", ".join(f"{m['name']}={m['value']}{m['unit']}" for m in metrics_result)
        parts.append(f"Метрики: {m_summary}")
    if tasks:
        t_summary = ", ".join(f"«{t['title']}»" for t in tasks[:3])
        parts.append(f"Задачи: {t_summary}")
    if clarifications:
        parts.append(f"⚠️ Уточнить: {'; '.join(clarifications)}")

    summary = " | ".join(parts) if parts else ""

    return {
        "entities": entities,
        "relations": relations,
        "events": events,
        "metrics": metrics_result,
        "tasks": tasks,
        "clarifications": clarifications,
        "summary": summary,
        "applied_rules": _applied_rules,
    }
