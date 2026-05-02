"""Tests for Jarvis Memory — Conversation Episodes system.

Covers:
  - DB: conversation_episodes CRUD
  - DB: message_logs episode_id migration
  - auto_summarizer: _build_messages_text
  - auto_summarizer: _call_ai_extractor (mocked)
  - auto_summarizer: maybe_summarize_conversation (mocked AI)
  - auto_summarizer: get_episode_context
  - auto_summarizer: recall_episodes
  - auto_summarizer: _upsert_person_entity
  - sync.py: sync_episode row format
  - sheets.py: ConversationEpisodes headers present
"""
import asyncio
import json
import os
import tempfile
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Temporary isolated Database instance."""
    from bot.db.database import Database
    db_file = str(tmp_path / "test_jarvis.db")
    return Database(db_path=db_file)


@pytest.fixture
async def ready_db(tmp_db):
    """Initialized Database with schema."""
    await tmp_db.init()
    await tmp_db.ensure_user(1001, "tester", "Test")
    return tmp_db


# ── 1. DB: conversation_episodes table exists ────────────────────────────────

async def test_episode_create_and_get(ready_db):
    """Create an episode, then retrieve it by ID."""
    ep_id = await ready_db.episode_create(
        user_id=1001,
        date="2024-01-15",
        title="Обсуждение проекта TUNTUN",
        summary="Обсудили архитектуру бота и план задач на неделю.",
        key_points=["Использовать aiosqlite", "Добавить эпизоды"],
        decisions=["Реализовать Jarvis Memory в первую очередь"],
        people=[{"name": "Дарья", "role": "дизайнер", "notes": "обсуждает UI"}],
        projects=["TUNTUN"],
        entities=["aiogram", "OpenAI"],
        tasks=["Написать auto_summarizer.py"],
        rules=["Всегда отвечать кратко по умолчанию"],
    )
    assert isinstance(ep_id, int)
    assert ep_id > 0

    ep = await ready_db.episode_get(ep_id)
    assert ep is not None
    assert ep["title"] == "Обсуждение проекта TUNTUN"
    assert ep["summary"] == "Обсудили архитектуру бота и план задач на неделю."
    assert "Использовать aiosqlite" in ep["key_points"]
    assert "Реализовать Jarvis Memory в первую очередь" in ep["decisions"]
    assert ep["projects"] == ["TUNTUN"]
    assert ep["tasks"] == ["Написать auto_summarizer.py"]
    assert ep["rules"] == ["Всегда отвечать кратко по умолчанию"]


async def test_episode_get_recent(ready_db):
    """episode_get_recent returns most recent episodes."""
    for i in range(3):
        await ready_db.episode_create(
            user_id=1001,
            date=f"2024-01-{10+i:02d}",
            title=f"Разговор {i+1}",
            summary=f"Краткое содержание разговора {i+1}",
        )
    episodes = await ready_db.episode_get_recent(1001, limit=5)
    assert len(episodes) == 3
    # Most recent first
    assert episodes[0]["title"] == "Разговор 3"


async def test_episode_search_by_keyword(ready_db):
    """episode_search finds episodes by title/summary keywords."""
    await ready_db.episode_create(
        user_id=1001,
        date="2024-01-20",
        title="Реклама на Facebook",
        summary="Обсуждали кампании и бюджет.",
    )
    await ready_db.episode_create(
        user_id=1001,
        date="2024-01-21",
        title="Задачи на неделю",
        summary="Планирование задач и напоминаний.",
    )
    results = await ready_db.episode_search(1001, ["реклама", "facebook"], limit=5)
    assert len(results) == 1
    assert "Facebook" in results[0]["title"]


async def test_message_logs_unsummarized(ready_db):
    """message_logs_unsummarized returns only messages without episode_id."""
    # Insert some messages without episode_id
    for i in range(4):
        await ready_db.log_message(1001, "text", f"Сообщение {i+1}")
    
    unsummarized = await ready_db.message_logs_unsummarized(1001, limit=10)
    assert len(unsummarized) == 4
    assert all(m["original_text"].startswith("Сообщение") for m in unsummarized)


async def test_message_logs_mark_episode(ready_db):
    """mark_episode links messages to an episode, unsummarized count drops."""
    ids = []
    for i in range(5):
        lid = await ready_db.log_message(1001, "text", f"Msg {i+1}")
        ids.append(lid)

    ep_id = await ready_db.episode_create(
        user_id=1001, date="2024-01-20",
        title="Test Episode", summary="Test summary",
    )
    await ready_db.message_logs_mark_episode(ids[:3], ep_id)

    unsummarized = await ready_db.message_logs_unsummarized(1001, limit=10)
    assert len(unsummarized) == 2  # only 2 remain without episode_id


async def test_episode_update_doc_url(ready_db):
    """episode_update_doc_url saves the Google Doc URL."""
    ep_id = await ready_db.episode_create(
        user_id=1001, date="2024-01-20",
        title="Episode", summary="Summary",
    )
    await ready_db.episode_update_doc_url(ep_id, "https://docs.google.com/document/d/abc123")
    ep = await ready_db.episode_get(ep_id)
    assert ep["google_doc_url"] == "https://docs.google.com/document/d/abc123"


# ── 2. auto_summarizer helpers ───────────────────────────────────────────────

def test_build_messages_text():
    """_build_messages_text formats conversation correctly."""
    from bot.modules.auto_summarizer import _build_messages_text

    messages = [
        {"created_at": "2024-01-15 10:00:00", "original_text": "Привет! Что делаем?",
         "bot_response": "Привет! Расскажи что нужно сделать."},
        {"created_at": "2024-01-15 10:01:00", "original_text": "Добавь задачу: встреча с Дарьей",
         "bot_response": "Задача добавлена: встреча с Дарьей"},
    ]
    text = _build_messages_text(messages)
    assert "Пользователь: Привет!" in text
    assert "Бот: Привет!" in text
    assert "Дарьей" in text
    assert "2024-01-15 10:00" in text


def test_build_messages_text_empty():
    """_build_messages_text handles empty list."""
    from bot.modules.auto_summarizer import _build_messages_text
    assert _build_messages_text([]) == ""


# ── 3. auto_summarizer.maybe_summarize_conversation (mocked AI) ──────────────

async def test_maybe_summarize_not_enough_messages(ready_db):
    """maybe_summarize_conversation returns None with < 6 messages."""
    # Insert only 3 messages
    for i in range(3):
        await ready_db.log_message(1001, "text", f"Сообщение {i+1}")

    # Patch db singleton used by auto_summarizer
    with patch("bot.modules.auto_summarizer.db", ready_db):
        from bot.modules.auto_summarizer import maybe_summarize_conversation
        result = await maybe_summarize_conversation(1001)
    assert result is None


async def test_maybe_summarize_creates_episode(ready_db):
    """maybe_summarize_conversation creates an episode when ≥ 6 messages."""
    # Insert 7 messages
    for i in range(7):
        await ready_db.log_message(1001, "text", f"Обсуждаем TUNTUN проект, сообщение {i+1}")
        await ready_db.log_update_response(i+1, f"Ответ бота {i+1}")

    fake_extracted = {
        "title": "Обсуждение TUNTUN",
        "summary": "Обсудили архитектуру и план задач.",
        "key_points": ["Использовать SQLite"],
        "decisions": ["Реализовать эпизоды"],
        "people": [{"name": "Дарья", "role": "дизайнер", "notes": ""}],
        "projects": ["TUNTUN"],
        "entities": ["aiogram"],
        "tasks": ["Написать тесты"],
        "rules": [],
    }

    with patch("bot.modules.auto_summarizer.db", ready_db), \
         patch("bot.modules.auto_summarizer._call_ai_extractor",
               new=AsyncMock(return_value=fake_extracted)), \
         patch("bot.modules.auto_summarizer._index_episode_to_memory",
               new=AsyncMock(return_value=None)), \
         patch("bot.modules.auto_summarizer._create_google_doc_for_episode",
               new=AsyncMock(return_value=None)), \
         patch("bot.modules.auto_summarizer._sync_episode_to_sheets",
               new=AsyncMock(return_value=None)):

        from bot.modules import auto_summarizer
        # Reload to pick up patched db
        result = await auto_summarizer.maybe_summarize_conversation(1001)

    assert result is not None
    assert result["title"] == "Обсуждение TUNTUN"
    assert result["summary"] == "Обсудили архитектуру и план задач."


async def test_maybe_summarize_marks_messages(ready_db):
    """After summarization, messages are linked to the episode."""
    for i in range(6):
        await ready_db.log_message(1001, "text", f"Msg {i+1} about TUNTUN")

    fake_extracted = {
        "title": "Test Episode",
        "summary": "Test summary",
        "key_points": [], "decisions": [], "people": [],
        "projects": [], "entities": [], "tasks": [], "rules": [],
    }

    with patch("bot.modules.auto_summarizer.db", ready_db), \
         patch("bot.modules.auto_summarizer._call_ai_extractor",
               new=AsyncMock(return_value=fake_extracted)), \
         patch("bot.modules.auto_summarizer._index_episode_to_memory",
               new=AsyncMock(return_value=None)), \
         patch("bot.modules.auto_summarizer._create_google_doc_for_episode",
               new=AsyncMock(return_value=None)), \
         patch("bot.modules.auto_summarizer._sync_episode_to_sheets",
               new=AsyncMock(return_value=None)):

        from bot.modules import auto_summarizer
        await auto_summarizer.maybe_summarize_conversation(1001)

    # All messages should now be linked to an episode
    remaining = await ready_db.message_logs_unsummarized(1001, limit=20)
    assert len(remaining) == 0


async def test_maybe_summarize_returns_none_on_ai_failure(ready_db):
    """maybe_summarize_conversation returns None gracefully when AI fails."""
    for i in range(8):
        await ready_db.log_message(1001, "text", f"Msg {i+1}")

    with patch("bot.modules.auto_summarizer.db", ready_db), \
         patch("bot.modules.auto_summarizer._call_ai_extractor",
               new=AsyncMock(return_value=None)):
        from bot.modules import auto_summarizer
        result = await auto_summarizer.maybe_summarize_conversation(1001)

    assert result is None


# ── 4. auto_summarizer.get_episode_context ───────────────────────────────────

async def test_get_episode_context_empty_db(ready_db):
    """get_episode_context returns empty string when no episodes exist."""
    with patch("bot.modules.auto_summarizer.db", ready_db):
        from bot.modules.auto_summarizer import get_episode_context
        ctx = await get_episode_context(1001, "TUNTUN")
    assert ctx == ""


async def test_get_episode_context_with_data(ready_db):
    """get_episode_context returns formatted string with episode data."""
    await ready_db.episode_create(
        user_id=1001,
        date="2024-01-15",
        title="TUNTUN разработка",
        summary="Обсудили архитектуру и эпизоды.",
        decisions=["Реализовать Jarvis Memory"],
        people=[{"name": "Дарья", "role": "дизайнер", "notes": ""}],
    )

    with patch("bot.modules.auto_summarizer.db", ready_db):
        from bot.modules.auto_summarizer import get_episode_context
        ctx = await get_episode_context(1001, "TUNTUN архитектура")

    assert "TUNTUN разработка" in ctx
    assert "Обсудили" in ctx


# ── 5. auto_summarizer.recall_episodes ───────────────────────────────────────

async def test_recall_episodes_by_person(ready_db):
    """recall_episodes finds episodes by people_json content."""
    ep_id = await ready_db.episode_create(
        user_id=1001,
        date="2024-01-15",
        title="Встреча",
        summary="Обсудили с Дарьей дизайн.",
        people=[{"name": "Дарья", "role": "дизайнер", "notes": ""}],
    )

    with patch("bot.modules.auto_summarizer.db", ready_db):
        from bot.modules.auto_summarizer import recall_episodes
        results = await recall_episodes(1001, "найди где обсуждали Дарья")

    assert len(results) >= 1
    found_ids = [r["id"] for r in results]
    assert ep_id in found_ids


# ── 6. Person entity upsert ──────────────────────────────────────────────────

async def test_upsert_person_entity(ready_db):
    """_upsert_person_entity stores a person in entities table."""
    with patch("bot.modules.auto_summarizer.db", ready_db):
        from bot.modules.auto_summarizer import _upsert_person_entity
        await _upsert_person_entity(1001, {
            "name": "Дарья",
            "role": "дизайнер",
            "notes": "работает над UI",
        })

    entities = await ready_db._fetchall(
        "SELECT * FROM entities WHERE user_id=? AND type='person'", (1001,)
    )
    assert len(entities) == 1
    assert entities[0]["name"] == "Дарья"
    data = json.loads(entities[0]["data_json"])
    assert data["role"] == "дизайнер"


async def test_upsert_person_entity_upsert_on_repeat(ready_db):
    """_upsert_person_entity updates existing person without duplicating."""
    with patch("bot.modules.auto_summarizer.db", ready_db):
        from bot.modules.auto_summarizer import _upsert_person_entity
        await _upsert_person_entity(1001, {"name": "Дарья", "role": "дизайнер", "notes": ""})
        await _upsert_person_entity(1001, {"name": "Дарья", "role": "тимлид", "notes": "новая роль"})

    entities = await ready_db._fetchall(
        "SELECT * FROM entities WHERE user_id=? AND type='person' AND name='Дарья'", (1001,)
    )
    assert len(entities) == 1  # No duplicates


# ── 7. sync_episode row format ───────────────────────────────────────────────

def test_sync_episode_row_format():
    """sync_episode builds a 9-column row for ConversationEpisodes sheet."""
    from bot.integrations.google.sheets import _SHEET_HEADERS
    assert "ConversationEpisodes" in _SHEET_HEADERS
    headers = _SHEET_HEADERS["ConversationEpisodes"]
    assert len(headers) == 9
    assert "title" in headers
    assert "summary" in headers
    assert "decisions" in headers
    assert "people" in headers
    assert "google_doc_url" in headers


def test_sync_handlers_include_episode():
    """_SYNC_HANDLERS includes 'episode' handler."""
    # Import without running async code
    import importlib
    import sys

    # Mock google deps to avoid credential errors at import time
    with patch.dict("sys.modules", {
        "googleapiclient": MagicMock(),
        "googleapiclient.discovery": MagicMock(),
        "google.oauth2": MagicMock(),
        "google.oauth2.service_account": MagicMock(),
    }):
        from bot.integrations.google import sync as sync_mod
        assert "episode" in sync_mod._SYNC_HANDLERS
        assert sync_mod._SYNC_HANDLERS["episode"] is sync_mod.sync_episode


# ── 8. _call_ai_extractor JSON parsing ───────────────────────────────────────

async def test_call_ai_extractor_strips_markdown():
    """_call_ai_extractor correctly parses JSON wrapped in markdown fences."""
    mock_content = '```json\n{"title": "Тест", "summary": "Тестовый разговор", "key_points": [], "decisions": [], "people": [], "projects": [], "entities": [], "tasks": [], "rules": []}\n```'

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = mock_content

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("bot.modules.auto_summarizer.AsyncOpenAI", return_value=mock_client), \
         patch("bot.modules.auto_summarizer.config") as mock_cfg:
        mock_cfg.OPENAI_API_KEY = "test-key"
        with patch("bot.modules.auto_summarizer.get_model", return_value="gpt-4o-mini"):
            from bot.modules.auto_summarizer import _call_ai_extractor
            result = await _call_ai_extractor("test dialogue", "2024-01-15")

    assert result is not None
    assert result["title"] == "Тест"
    assert result["summary"] == "Тестовый разговор"
