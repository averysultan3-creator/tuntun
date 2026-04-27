from bot.db.database import db
from bot.utils.formatters import format_memory


async def handle_save(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    category = params.get("category", "general").strip()
    value = params.get("value", "").strip()
    key_name = params.get("key_name")

    if not value:
        return "❌ Нечего запоминать"

    mid = await db.memory_save(user_id, category, value, key_name)
    cat_str = f" в категорию «{category}»" if category != "general" else ""

    # Memory V2 index (non-blocking)
    import asyncio as _asyncio
    from bot.modules.memory_indexer import index_explicit_memory as _idx_mem
    _asyncio.create_task(_idx_mem({
        "id": mid, "user_id": user_id, "value": value,
        "category": category, "key_name": key_name,
    }))

    # Google Sheets sync (non-blocking)
    import asyncio
    import config as _cfg
    if _cfg.GOOGLE_ENABLED:
        from bot.integrations.google.sync import sync_object_to_google
        asyncio.create_task(sync_object_to_google(
            user_id=user_id,
            object_type="memory",
            object_id=mid,
            payload={"category": category, "key_name": key_name or "", "value": value},
        ))

    return f"🧠 Запомнил{cat_str}: {value} #{mid}"


async def handle_recall(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    category = params.get("category")
    query = params.get("query")

    memories = await db.memory_recall(user_id, category=category, query=query)

    if category:
        title = f"Память — {category}"
    elif query:
        title = f"Память — поиск: {query}"
    else:
        title = "Всё из памяти"

    return format_memory(memories, title)
