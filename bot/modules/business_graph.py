"""Business Graph helpers for TUNTUN.

This is the normalized layer for objects that need relations and metrics:
project -> campaign -> creative -> spend -> orders -> result.

The module is deliberately small and local-first:
1. write to SQLite;
2. index to memory_items;
3. optionally enqueue/sync to Google Sheets.
"""
import asyncio
import json
import logging
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
