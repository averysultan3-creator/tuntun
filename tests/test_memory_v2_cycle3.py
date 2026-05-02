"""Tests for Memory V2 Cycle 3: brain context in chat_assistant.

Tests verify:
- handle_chat_response calls retrieve_brain_context for memory queries
- brain context block is injected into the system prompt
- empty brain context does NOT cause errors
- prompt size stays bounded
- query "что я говорил про рекламу" retrieves relevant memory_items
- non-data-query does NOT inject brain context unnecessarily

Run: python -B -m pytest test_memory_v2_cycle3.py -v
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
    from bot.db.database import Database
    return Database(path)


# ══════════════════════════════════════════════════════════════════════════════
# helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_fake_openai_client(response_text: str = "ok"):
    """Returns an AsyncOpenAI-like fake that never calls the real API."""

    class FakeChoice:
        message = types.SimpleNamespace(content=response_text)

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        async def create(self, **kw):
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    return FakeClient()


# ══════════════════════════════════════════════════════════════════════════════
# 1. _is_memory_query detection
# ══════════════════════════════════════════════════════════════════════════════

def test_is_memory_query_positive():
    from bot.modules.chat_assistant import _is_memory_query
    assert _is_memory_query("что я говорил про рекламу?") is True
    assert _is_memory_query("что ты помнишь о моих расходах") is True
    assert _is_memory_query("что я тратил по рекламе") is True
    assert _is_memory_query("история по Facebook") is True


def test_is_memory_query_negative():
    from bot.modules.chat_assistant import _is_memory_query
    assert _is_memory_query("добавь задачу купить молоко") is False
    assert _is_memory_query("какая погода завтра") is False
    assert _is_memory_query("напомни в 10 утра") is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. retrieve_brain_context called on is_data_query
# ══════════════════════════════════════════════════════════════════════════════

def test_brain_context_called_on_data_query(monkeypatch, tmp_path):
    """handle_chat_response must call retrieve_brain_context when is_data_query=True."""
    import bot.modules.chat_assistant as ca_mod
    import bot.db.database as db_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)

    brain_called = []

    async def fake_brain(user_id, query, max_items=15, max_chars=2200):
        brain_called.append({"user_id": user_id, "query": query})
        return ""

    monkeypatch.setattr(ret_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "_get_client", lambda: _make_fake_openai_client("ok"))

    async def run():
        await test_db.init()
        await ca_mod.handle_chat_response(
            user_id=1,
            question="сколько я потратил в этом месяце?",
            is_data_query=True,
        )
        assert len(brain_called) == 1
        assert brain_called[0]["user_id"] == 1

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 3. retrieve_brain_context called on memory-type questions
# ══════════════════════════════════════════════════════════════════════════════

def test_brain_context_called_on_memory_query(monkeypatch, tmp_path):
    """handle_chat_response calls retrieve_brain_context for 'что я говорил...' queries."""
    import bot.modules.chat_assistant as ca_mod
    import bot.db.database as db_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)

    brain_called = []

    async def fake_brain(user_id, query, max_items=15, max_chars=2200):
        brain_called.append(query)
        return ""

    monkeypatch.setattr(ret_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "_get_client", lambda: _make_fake_openai_client())

    async def run():
        await test_db.init()
        await ca_mod.handle_chat_response(
            user_id=1,
            question="что я говорил про рекламу на фейсбук?",
            is_data_query=False,
            needs_retrieval=False,
        )
        assert len(brain_called) == 1

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 4. Empty brain context does not crash
# ══════════════════════════════════════════════════════════════════════════════

def test_empty_brain_context_no_crash(monkeypatch, tmp_path):
    """When retrieve_brain_context returns empty string, handle_chat_response succeeds."""
    import bot.modules.chat_assistant as ca_mod
    import bot.db.database as db_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)

    async def fake_brain(user_id, query, **kw):
        return ""

    monkeypatch.setattr(ret_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "_get_client", lambda: _make_fake_openai_client("ответ без контекста"))

    async def run():
        await test_db.init()
        result = await ca_mod.handle_chat_response(
            user_id=1,
            question="что я говорил про рекламу?",
            is_data_query=True,
        )
        # should return the fake AI response, not crash
        assert isinstance(result, str)
        assert len(result) > 0

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 5. Brain context exception does not crash the whole response
# ══════════════════════════════════════════════════════════════════════════════

def test_brain_context_exception_graceful(monkeypatch, tmp_path):
    """If retrieve_brain_context raises, handle_chat_response still succeeds."""
    import bot.modules.chat_assistant as ca_mod
    import bot.db.database as db_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)

    async def fake_brain_raises(user_id, query, **kw):
        raise RuntimeError("DB connection error")

    monkeypatch.setattr(ret_mod, "retrieve_brain_context", fake_brain_raises)
    monkeypatch.setattr(ca_mod, "retrieve_brain_context", fake_brain_raises)
    monkeypatch.setattr(ca_mod, "_get_client", lambda: _make_fake_openai_client("ok despite error"))

    async def run():
        await test_db.init()
        result = await ca_mod.handle_chat_response(
            user_id=1,
            question="что я говорил про учёбу?",
            is_data_query=True,
        )
        assert isinstance(result, str)
        # should not propagate the exception

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 6. Brain context injected into prompt when non-empty
# ══════════════════════════════════════════════════════════════════════════════

def test_brain_context_injected_in_prompt(monkeypatch, tmp_path):
    """When brain context is non-empty, it must appear in the messages sent to OpenAI."""
    import bot.modules.chat_assistant as ca_mod
    import bot.db.database as db_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)

    captured_messages = []

    async def fake_brain(user_id, query, **kw):
        return "[Brain context]\n  [finance, #1, 2025-01-10] 150 USD — реклама Facebook"

    monkeypatch.setattr(ret_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "retrieve_brain_context", fake_brain)

    class FakeChoice:
        message = types.SimpleNamespace(content="вот что я нашёл")

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        async def create(self, **kw):
            captured_messages.extend(kw.get("messages", []))
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(ca_mod, "_get_client", lambda: FakeClient())

    async def run():
        await test_db.init()
        await ca_mod.handle_chat_response(
            user_id=1,
            question="что я говорил про рекламу?",
            is_data_query=True,
        )
        # Brain context should appear somewhere in the system message
        system_msg = next(
            (m["content"] for m in captured_messages if m["role"] == "system"), ""
        )
        assert "Brain context" in system_msg or "150 USD" in system_msg

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 7. Brain context retrieves relevant memory_items for "реклама" query
# ══════════════════════════════════════════════════════════════════════════════

def test_brain_context_finds_relevant_items(monkeypatch, tmp_path):
    """retrieve_brain_context must find indexed memory items matching query."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr(ret_mod, "db", test_db)

    from bot.modules.memory_retriever import retrieve_brain_context

    async def run():
        await test_db.init()

        # Index two memory items: one about ads, one about food
        await test_db.memory_item_upsert(
            user_id=1,
            content="Потратил 200 USD на рекламу Facebook в январе",
            hash="h1",
            source_type="finance",
            source_id="1",
            summary="Реклама FB 200 USD",
            category="finance",
            importance=3,
        )
        await test_db.memory_item_upsert(
            user_id=1,
            content="Съел пиццу на обед",
            hash="h2",
            source_type="explicit_memory",
            source_id="2",
            summary="Пицца",
            category="health",
            importance=2,
        )

        result = await retrieve_brain_context(
            user_id=1,
            query="что я говорил про рекламу",
            max_items=10,
        )
        assert "реклам" in result.lower() or "facebook" in result.lower() or "200" in result
        # food item should ideally NOT dominate (it may or may not appear, but ads item must)
        assert "Brain context" in result

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 8. Prompt size is bounded
# ══════════════════════════════════════════════════════════════════════════════

def test_prompt_size_bounded(monkeypatch, tmp_path):
    """Brain context must be capped at max_chars=2200."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr(ret_mod, "db", test_db)

    from bot.modules.memory_retriever import retrieve_brain_context

    async def run():
        await test_db.init()

        # Insert many items with the same content to force many matches
        for i in range(50):
            await test_db.memory_item_upsert(
                user_id=1,
                content=f"реклама Facebook кампания {i}: " + "x" * 200,
                hash=f"h{i}",
                source_type="finance",
                source_id=str(i),
                summary=f"Реклама {i}",
                category="finance",
                importance=3,
            )

        result = await retrieve_brain_context(
            user_id=1,
            query="реклама",
            max_items=10,
            max_chars=2200,
        )
        assert len(result) <= 2200 + 50  # small buffer for ellipsis line

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 9. Non-data query does NOT call retrieve_brain_context
# ══════════════════════════════════════════════════════════════════════════════

def test_no_brain_context_for_simple_chat(monkeypatch, tmp_path):
    """For simple chat messages (not data queries), brain context is NOT requested."""
    import bot.modules.chat_assistant as ca_mod
    import bot.db.database as db_mod
    import bot.modules.memory_retriever as ret_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)

    brain_called = []

    async def fake_brain(user_id, query, **kw):
        brain_called.append(query)
        return ""

    monkeypatch.setattr(ret_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "retrieve_brain_context", fake_brain)
    monkeypatch.setattr(ca_mod, "_get_client", lambda: _make_fake_openai_client("привет!"))

    async def run():
        await test_db.init()
        await ca_mod.handle_chat_response(
            user_id=1,
            question="привет, как дела?",
            is_data_query=False,
            needs_retrieval=False,
            refers_to_previous=False,
            needs_reasoning=False,
        )
        # brain context should NOT be called for simple greeting
        assert len(brain_called) == 0

    asyncio.run(run())
