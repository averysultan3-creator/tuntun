"""Tests for Memory V2: memory_items schema, indexer, backfill, and brain retrieval.

Run: python -B -m pytest test_memory_v2.py -v

Design notes:
  - Every test that writes data uses `tmp_path` (a real file) so aiosqlite
    connections share state between calls.
  - `await test_db.init()` is ALWAYS the first statement inside the coroutine
    passed to `asyncio.run()`.
  - monkeypatch.setattr happens synchronously BEFORE asyncio.run().
"""
import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── config stub ────────────────────────────────────────────────────────────────
def _make_fake_config():
    m = types.ModuleType("config")
    m.OPENAI_API_KEY = "sk-test"
    m.VISION_ENABLED = False
    m.GOOGLE_ENABLED = False
    m.ALLOWED_USER_IDS = []
    m.DB_PATH = ":memory:"
    m.MODEL_ROUTER = "gpt-4o-mini"
    m.MODEL_CHAT = "gpt-4o-mini"
    m.MODEL_REASONING = "gpt-4o"
    m.MODEL_VISION = "gpt-4o-mini"
    m.WHISPER_MODEL = "whisper-1"
    m.MODEL_EMBEDDINGS = "text-embedding-3-small"
    m.TIMEZONE = "Europe/Warsaw"
    m.MIN_CONFIDENCE = 0.65
    m.PHOTOS_DIR = "/tmp"
    return m


sys.modules["config"] = _make_fake_config()


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    fake = _make_fake_config()
    monkeypatch.setitem(sys.modules, "config", fake)
    yield fake


def _make_db(path: str):
    """Return an uninitialised Database backed by a real file at `path`.

    Usage inside a test:
        test_db = _make_db(str(tmp_path / "t.db"))
        monkeypatch.setattr(db_mod, "db", test_db)
        async def run():
            await test_db.init()   # FIRST
            ...
        asyncio.run(run())
    """
    from bot.db.database import Database
    return Database(path)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Schema: memory_items table + columns
# ══════════════════════════════════════════════════════════════════════════════

def test_memory_items_schema_created(tmp_path):
    """memory_items table must exist after db init."""
    import aiosqlite

    async def run():
        from bot.db.database import Database
        test_db = Database(str(tmp_path / "t.db"))
        await test_db.init()
        async with aiosqlite.connect(str(tmp_path / "t.db")) as conn:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            return {row[0] for row in await cursor.fetchall()}

    tables = asyncio.run(run())
    assert "memory_items" in tables, f"memory_items missing. Got: {tables}"


def test_memory_items_columns(tmp_path):
    """memory_items must have all required columns."""
    import aiosqlite

    async def run():
        from bot.db.database import Database
        test_db = Database(str(tmp_path / "t.db"))
        await test_db.init()
        async with aiosqlite.connect(str(tmp_path / "t.db")) as conn:
            cursor = await conn.execute("PRAGMA table_info(memory_items)")
            return {row[1] for row in await cursor.fetchall()}

    cols = asyncio.run(run())
    required = {
        "id", "user_id", "content", "summary", "category", "tags_json",
        "importance", "source_type", "source_id", "source_url", "source_title",
        "source_date", "embedding_model", "embedding_json", "hash",
        "created_at", "updated_at", "last_accessed_at",
    }
    missing = required - cols
    assert not missing, f"Missing columns: {missing}"


# ══════════════════════════════════════════════════════════════════════════════
# 2. index_memory_item creates a row
# ══════════════════════════════════════════════════════════════════════════════

def test_index_memory_item_creates_row(monkeypatch, tmp_path):
    """index_memory_item must persist a row and return a valid id > 0."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import index_memory_item

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        row_id = await index_memory_item(
            user_id=1,
            content="Купил бензин 200 PLN",
            source_type="finance",
            source_id="exp_42",
            importance=4,
            source_date="2026-04-20",
        )
        count = await test_db.memory_items_count(1)
        return row_id, count

    row_id, count = asyncio.run(run())
    assert row_id > 0, "Should return a positive row id"
    assert count == 1, "Should have exactly one row"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Duplicate same source_type+source_id does NOT duplicate
# ══════════════════════════════════════════════════════════════════════════════

def test_index_duplicate_source_no_dup(monkeypatch, tmp_path):
    """Two calls with the same source_type+source_id must upsert, not insert twice."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import index_memory_item

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        id1 = await index_memory_item(
            user_id=1, content="Старый текст", source_type="task", source_id="task_7"
        )
        id2 = await index_memory_item(
            user_id=1, content="Обновлённый текст", source_type="task", source_id="task_7"
        )
        count = await test_db.memory_items_count(1)
        rows = await test_db.memory_items_by_source(1, "task", "task_7")
        return id1, id2, count, rows[0]["content"]

    id1, id2, count, content = asyncio.run(run())
    assert id1 == id2, "Upsert should return same id"
    assert count == 1, "Should still be one row"
    assert "Обновлённый" in content, "Updated content must be stored"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Duplicate same content hash does NOT duplicate (no source_id)
# ══════════════════════════════════════════════════════════════════════════════

def test_index_duplicate_hash_no_dup(monkeypatch, tmp_path):
    """Two calls with identical content (same hash) but no source_id should not duplicate."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import index_memory_item

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        id1 = await index_memory_item(
            user_id=2, content="Точно такой же текст", source_type="explicit_memory"
        )
        id2 = await index_memory_item(
            user_id=2, content="Точно такой же текст", source_type="explicit_memory"
        )
        count = await test_db.memory_items_count(2)
        return id1, id2, count

    id1, id2, count = asyncio.run(run())
    assert id1 == id2, "Same hash should upsert to same row"
    assert count == 1, "Should be one row"


# ══════════════════════════════════════════════════════════════════════════════
# 5. backfill_old_memory_to_items imports old memory rows
# ══════════════════════════════════════════════════════════════════════════════

def test_backfill_old_memory(monkeypatch, tmp_path):
    """backfill_old_memory_to_items must transfer rows from `memory` table."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import backfill_old_memory_to_items

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        await test_db.memory_save(5, "general", "Люблю путешествия", key_name="travel")
        await test_db.memory_save(5, "health", "Тренировка 3 раза в неделю", key_name="workout")
        await test_db.memory_save(5, "finance", "Бюджет на еду 1500 PLN")
        report = await backfill_old_memory_to_items(user_id=5)
        count = await test_db.memory_items_count(5)
        return report, count

    report, count = asyncio.run(run())
    assert report["imported"] == 3, f"Expected 3 imported, got {report}"
    assert count == 3, f"Expected 3 items in memory_items, got {count}"


def test_backfill_is_idempotent(monkeypatch, tmp_path):
    """Running backfill twice must not duplicate rows."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import backfill_old_memory_to_items

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        await test_db.memory_save(6, "general", "Текст для дубля", key_name="dup_key")
        await backfill_old_memory_to_items(user_id=6)
        await backfill_old_memory_to_items(user_id=6)
        return await test_db.memory_items_count(6)

    count = asyncio.run(run())
    assert count == 1, f"Expected 1 row after double backfill, got {count}"


# ══════════════════════════════════════════════════════════════════════════════
# 6. retrieve_brain_context finds exact keyword
# ══════════════════════════════════════════════════════════════════════════════

def test_retrieve_brain_context_finds_keyword(monkeypatch, tmp_path):
    """retrieve_brain_context must return a block containing the seeded item."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.modules.memory_retriever as retriever_mod
    from bot.modules.memory_indexer import index_memory_item
    from bot.modules.memory_retriever import retrieve_brain_context

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr(retriever_mod, "db", test_db)

    async def run():
        await test_db.init()
        await index_memory_item(
            user_id=10,
            content="Потратил 500 PLN на бензин для машины",
            source_type="finance",
            source_id="exp_1",
            importance=4,
        )
        await index_memory_item(
            user_id=10,
            content="Завтра лекция по математике",
            source_type="study",
            source_id="study_1",
        )
        return await retrieve_brain_context(10, "расходы на машину")

    result = asyncio.run(run())
    assert result, "Should return non-empty context"
    assert "бензин" in result or "машин" in result or "PLN" in result, (
        f"Expected car/fuel content, got: {result!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7. retrieve_brain_context finds synonym / paraphrase
# ══════════════════════════════════════════════════════════════════════════════

def test_retrieve_brain_context_finds_synonym(monkeypatch, tmp_path):
    """Querying 'финансы' should surface items tagged with synonym 'расходы'."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.modules.memory_retriever as retriever_mod
    from bot.modules.memory_indexer import index_memory_item
    from bot.modules.memory_retriever import retrieve_brain_context

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr(retriever_mod, "db", test_db)

    async def run():
        await test_db.init()
        await index_memory_item(
            user_id=11,
            content="Расходы на еду за апрель составили 1200 PLN",
            source_type="finance",
            source_id="fin_5",
            category="finance",
            importance=3,
        )
        return await retrieve_brain_context(11, "финансы")

    result = asyncio.run(run())
    assert result, "Should find via synonym expansion"
    assert "1200" in result or "PLN" in result or "расход" in result.lower(), (
        f"Expected finance content, got: {result!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 8. retrieve_brain_context respects date range filter
# ══════════════════════════════════════════════════════════════════════════════

def test_retrieve_brain_context_date_range(monkeypatch, tmp_path):
    """April item (source_date in April) should be present when querying 'за апрель'."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.modules.memory_retriever as retriever_mod
    from bot.modules.memory_indexer import index_memory_item
    from bot.modules.memory_retriever import retrieve_brain_context

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr(retriever_mod, "db", test_db)

    async def run():
        await test_db.init()
        await index_memory_item(
            user_id=12,
            content="Потратил 200 PLN на одежду в январе",
            source_type="finance",
            source_id="fin_jan",
            importance=3,
            source_date="2026-01-15",
        )
        await index_memory_item(
            user_id=12,
            content="Потратил 150 PLN на продукты в апреле",
            source_type="finance",
            source_id="fin_apr",
            importance=3,
            source_date="2026-04-10",
        )
        return await retrieve_brain_context(12, "расходы за апрель")

    result = asyncio.run(run())
    assert result, "Should return non-empty result"
    assert "150" in result or "продукты" in result or "апрел" in result.lower(), (
        f"Expected April item in result, got: {result!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 9. source metadata is present in retrieve_brain_context output
# ══════════════════════════════════════════════════════════════════════════════

def test_retrieve_brain_context_source_metadata(monkeypatch, tmp_path):
    """Result block must include source_type and score metadata."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.modules.memory_retriever as retriever_mod
    from bot.modules.memory_indexer import index_memory_item
    from bot.modules.memory_retriever import retrieve_brain_context

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr(retriever_mod, "db", test_db)

    async def run():
        await test_db.init()
        await index_memory_item(
            user_id=13,
            content="Задача: купить корм для кота",
            source_type="task",
            source_id="task_99",
            importance=3,
            source_date="2026-04-25",
        )
        return await retrieve_brain_context(13, "задача кот")

    result = asyncio.run(run())
    assert result, "Should return non-empty result"
    assert "task" in result, f"source_type 'task' not in result: {result!r}"
    assert "score=" in result, f"score metadata not in result: {result!r}"


# ══════════════════════════════════════════════════════════════════════════════
# 10. No OpenAI / embedding call during indexing
# ══════════════════════════════════════════════════════════════════════════════

def test_no_openai_call_during_indexing(monkeypatch, tmp_path):
    """index_memory_item must not import or call openai."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import index_memory_item

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    called = []
    fake_openai = types.ModuleType("openai")

    class _FakeClient:
        def __getattr__(self, name):
            called.append(f"openai.{name}")
            raise AssertionError(f"openai.{name} was called during indexing!")

    fake_openai.OpenAI = _FakeClient
    fake_openai.AsyncOpenAI = _FakeClient
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    async def run():
        await test_db.init()
        return await index_memory_item(
            user_id=20,
            content="Тестовый текст без API",
            source_type="explicit_memory",
            source_id="test_no_api",
        )

    row_id = asyncio.run(run())
    assert row_id > 0, "Should create row"
    assert not called, f"openai was called: {called}"


# ══════════════════════════════════════════════════════════════════════════════
# 11. guess_category helper
# ══════════════════════════════════════════════════════════════════════════════

def test_guess_category_finance():
    from bot.modules.memory_indexer import guess_category
    assert guess_category("купил бензин за 200 PLN", "finance") == "finance"
    assert guess_category("потратил деньги на еду") == "finance"


def test_guess_category_source_type_hint():
    from bot.modules.memory_indexer import guess_category
    assert guess_category("любой текст", "voice") == "voice"
    assert guess_category("любой текст", "task") == "task"
    assert guess_category("любой текст", "reminder") == "reminder"


def test_guess_category_fallback():
    from bot.modules.memory_indexer import guess_category
    assert guess_category("непонятный текст без ключевых слов") == "general"


# ══════════════════════════════════════════════════════════════════════════════
# 12. compact_summary helper
# ══════════════════════════════════════════════════════════════════════════════

def test_compact_summary_short_text():
    from bot.modules.memory_indexer import compact_summary
    assert compact_summary("Короткий текст") == "Короткий текст"


def test_compact_summary_truncates():
    from bot.modules.memory_indexer import compact_summary
    result = compact_summary("А" * 600, max_len=400)
    assert len(result) <= 401


def test_compact_summary_empty():
    from bot.modules.memory_indexer import compact_summary
    assert compact_summary("") == ""


# ══════════════════════════════════════════════════════════════════════════════
# 13. make_memory_hash is stable and user-scoped
# ══════════════════════════════════════════════════════════════════════════════

def test_make_memory_hash_stable():
    from bot.modules.memory_indexer import make_memory_hash
    h1 = make_memory_hash(1, "finance", "42", "Купил бензин")
    h2 = make_memory_hash(1, "finance", "42", "Купил бензин")
    assert h1 == h2, "Hash must be deterministic"


def test_make_memory_hash_different_users():
    from bot.modules.memory_indexer import make_memory_hash
    h1 = make_memory_hash(1, "finance", "42", "Купил бензин")
    h2 = make_memory_hash(2, "finance", "42", "Купил бензин")
    assert h1 != h2, "Hashes must differ across users"


# ══════════════════════════════════════════════════════════════════════════════
# 14. memory_items_count
# ══════════════════════════════════════════════════════════════════════════════

def test_memory_items_count(monkeypatch, tmp_path):
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import index_memory_item

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        assert await test_db.memory_items_count(99) == 0
        await index_memory_item(99, "Первая заметка", "explicit_memory", source_id="m1")
        await index_memory_item(99, "Вторая заметка", "explicit_memory", source_id="m2")
        return await test_db.memory_items_count(99)

    count = asyncio.run(run())
    assert count == 2


# ══════════════════════════════════════════════════════════════════════════════
# 15. memory_item_touch_accessed updates last_accessed_at
# ══════════════════════════════════════════════════════════════════════════════

def test_touch_accessed(monkeypatch, tmp_path):
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    from bot.modules.memory_indexer import index_memory_item

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        row_id = await index_memory_item(
            100, "Запись для теста touch", "explicit_memory", source_id="touch_1"
        )
        rows_before = await test_db.memory_items_by_source(100, "explicit_memory", "touch_1")
        before = rows_before[0]["last_accessed_at"]
        await test_db.memory_item_touch_accessed([row_id])
        rows_after = await test_db.memory_items_by_source(100, "explicit_memory", "touch_1")
        after = rows_after[0]["last_accessed_at"]
        return before, after

    before, after = asyncio.run(run())
    assert before is None, "last_accessed_at should initially be None"
    assert after is not None, "last_accessed_at should be set after touch"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
