"""Tests for Memory V2 Step 2: local-source wiring.

Each test calls the module function (memory/tasks/reminders/etc.) and verifies
that index_* was called with the correct arguments.

All indexer calls are mocked (replaced with a recording coroutine), so tests
do NOT need a real DB and do NOT call OpenAI.

Run: python -B -m pytest test_memory_v2_step2.py -v
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_db(path: str):
    from bot.db.database import Database
    return Database(path)


class _IndexCapture:
    """Captures calls to an async indexer function."""
    def __init__(self):
        self.calls = []

    def make_coro(self, name: str):
        capture = self.calls
        async def _func(*args, **kwargs):
            capture.append({"name": name, "args": args, "kwargs": kwargs})
            return 99
        return _func


# ══════════════════════════════════════════════════════════════════════════════
# 1. memory.py → index_explicit_memory
# ══════════════════════════════════════════════════════════════════════════════

def test_memory_handle_save_indexes(monkeypatch, tmp_path):
    """handle_save must call index_explicit_memory with the saved row data."""
    import bot.modules.memory as memory_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(memory_mod, "db", test_db)

    cap = _IndexCapture()

    tasks_created = []
    original_create_task = asyncio.create_task

    def fake_create_task(coro, **kw):
        tasks_created.append(coro)
        # schedule the coro so it runs in the event loop
        return original_create_task(coro, **kw)

    async def run():
        await test_db.init()
        # patch index function AFTER init so module-level import is in place
        monkeypatch.setattr(indexer_mod, "index_explicit_memory", cap.make_coro("index_explicit_memory"))

        import asyncio as _asyncio
        monkeypatch.setattr(_asyncio, "create_task", fake_create_task)

        result = await memory_mod.handle_save(
            user_id=1,
            params={"category": "health", "value": "не ем глютен"},
            ai_response="ok",
        )
        # allow tasks to run
        await asyncio.sleep(0)
        assert "Запомнил" in result
        assert len(cap.calls) == 1
        call = cap.calls[0]
        # index_explicit_memory is called with a dict as positional arg
        row = call["args"][0] if call["args"] else call["kwargs"]
        assert row.get("user_id") == 1
        assert row.get("value") == "не ем глютен"

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 2. tasks.py → index_task
# ══════════════════════════════════════════════════════════════════════════════

def test_tasks_handle_create_indexes(monkeypatch, tmp_path):
    """handle_create must call index_task with task_id and title."""
    import bot.modules.tasks as tasks_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(tasks_mod, "db", test_db)

    cap = _IndexCapture()

    async def run():
        await test_db.init()
        monkeypatch.setattr(indexer_mod, "index_task", cap.make_coro("index_task"))

        result = await tasks_mod.handle_create(
            user_id=1,
            params={"title": "Купить молоко", "priority": "normal"},
            ai_response="ok",
        )
        await asyncio.sleep(0)
        assert "Задача" in result
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert kw["title"] == "Купить молоко"
        assert kw["task_id"] is not None

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 3. reminders.py → index_reminder
# ══════════════════════════════════════════════════════════════════════════════

def test_reminders_handle_create_indexes(monkeypatch, tmp_path):
    """handle_create must call index_reminder with reminder_id and text."""
    import bot.modules.reminders as rem_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(rem_mod, "db", test_db)

    # Stub the scheduler so it doesn't need APScheduler
    import bot.utils.scheduler as sched_mod
    monkeypatch.setattr(sched_mod, "add_reminder_job", lambda **kw: "job-1")

    cap = _IndexCapture()

    async def run():
        await test_db.init()
        monkeypatch.setattr(indexer_mod, "index_reminder", cap.make_coro("index_reminder"))

        result = await rem_mod.handle_create(
            user_id=1,
            params={"text": "позвонить маме", "remind_at": "2025-12-01 10:00"},
            ai_response="ok",
        )
        await asyncio.sleep(0)
        assert "Напоминание" in result
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert kw["text"] == "позвонить маме"
        assert kw["reminder_id"] is not None

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 4. projects.py → index_finance_record
# ══════════════════════════════════════════════════════════════════════════════

def test_projects_expense_add_indexes(monkeypatch, tmp_path):
    """handle_expense_add must call index_finance_record."""
    import bot.modules.projects as proj_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(proj_mod, "db", test_db)

    cap = _IndexCapture()

    async def run():
        await test_db.init()
        monkeypatch.setattr(indexer_mod, "index_finance_record", cap.make_coro("index_finance_record"))

        result = await proj_mod.handle_expense_add(
            user_id=1,
            params={"amount": 50, "currency": "USD", "description": "Тест рекламы"},
            ai_response="ok",
        )
        await asyncio.sleep(0)
        assert "Расход" in result
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert kw["amount"] == 50.0
        assert kw["currency"] == "USD"

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 5. dynamic.py → index_dynamic_record
# ══════════════════════════════════════════════════════════════════════════════

def test_dynamic_record_add_indexes(monkeypatch, tmp_path):
    """handle_record_add must call index_dynamic_record after section_record_add."""
    import bot.modules.dynamic as dyn_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(dyn_mod, "db", test_db)

    cap = _IndexCapture()

    async def run():
        await test_db.init()
        # Create a section first
        await test_db.section_create(1, "реклама", "Реклама", ["date", "amount"])
        monkeypatch.setattr(indexer_mod, "index_dynamic_record", cap.make_coro("index_dynamic_record"))

        result = await dyn_mod.handle_record_add(
            user_id=1,
            params={"section_name": "реклама", "data": {"date": "2025-01-01", "amount": "100"}},
            ai_response="ok",
        )
        await asyncio.sleep(0)
        assert "Запись" in result
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert kw["record_id"] is not None
        assert "Реклама" in kw["section_name"]

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 6. ideas.py → index_memory_item (idea)
# ══════════════════════════════════════════════════════════════════════════════

def test_ideas_handle_save_indexes(monkeypatch, tmp_path):
    """handle_save must call index_memory_item with source_type='idea'."""
    import bot.modules.ideas as ideas_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(ideas_mod, "db", test_db)

    cap = _IndexCapture()

    async def run():
        await test_db.init()
        monkeypatch.setattr(indexer_mod, "index_memory_item", cap.make_coro("index_memory_item"))

        result = await ideas_mod.handle_save(
            user_id=1,
            params={"title": "Система лояльности", "description": "Даём баллы за покупки"},
            ai_response="ok",
        )
        await asyncio.sleep(0)
        assert "Идея" in result
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert kw["source_type"] == "idea"
        assert "Система лояльности" in kw["content"]

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 7. voice handler → index_voice_transcript
# ══════════════════════════════════════════════════════════════════════════════

def test_voice_handler_indexes_transcript(monkeypatch, tmp_path):
    """handle_voice in message.py must call index_voice_transcript after transcription."""
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)

    cap = _IndexCapture()

    # Stub transcription to return text without file I/O
    async def fake_transcribe(message):
        return "тест голосового сообщения", "/tmp/voice_test.ogg"

    monkeypatch.setattr("bot.handlers.voice.transcribe_and_save", fake_transcribe)

    # Stub _process_text to avoid full chat pipeline
    async def fake_process(message, text, state, scheduler, **kw):
        pass

    monkeypatch.setattr(msg_mod, "_process_text", fake_process)

    # Fake message object
    class FakeUser:
        id = 1

    class FakeMessage:
        from_user = FakeUser()
        voice = object()
        async def answer(self, text, **kw):
            pass

    async def run():
        await test_db.init()
        monkeypatch.setattr(indexer_mod, "index_voice_transcript", cap.make_coro("index_voice_transcript"))

        await msg_mod.handle_voice(FakeMessage(), state=None, scheduler=None)
        await asyncio.sleep(0)
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert kw["transcript"] == "тест голосового сообщения"

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 8. photo.py → index_vision_result (when vision is enabled)
# ══════════════════════════════════════════════════════════════════════════════

def test_photo_handler_indexes_vision_result(monkeypatch, tmp_path):
    """handle_photo must call index_vision_result when vision_result is present."""
    import bot.handlers.photo as photo_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(photo_mod, "db", test_db)

    cap = _IndexCapture()

    # Fake vision result
    _vision_data = {
        "photo_type": "receipt",
        "summary": "Чек из магазина на 150 USD",
        "extracted_text": "Total: 150 USD",
        "suggested_actions": [],
        "detected_entities": None,
    }

    async def fake_analyze_photo(**kw):
        return _vision_data

    async def fake_build_reply(vr, att_id, caption):
        return "Анализ фото"

    # Stub vision module
    fake_vision = types.ModuleType("bot.modules.vision")
    fake_vision.analyze_photo = fake_analyze_photo
    fake_vision.build_reply = lambda vr, att_id, caption: "Анализ фото"
    monkeypatch.setitem(sys.modules, "bot.modules.vision", fake_vision)

    # Enable vision (patch on photo_mod, which already has a local ref to is_vision_enabled)
    monkeypatch.setattr(photo_mod, "is_vision_enabled", lambda: True)

    # Fake message / bot objects
    class FakeBot:
        async def download(self, file, destination):
            destination.write_bytes(b"fakejpeg")

    class FakePhoto:
        file_id = "fid1"
        width = 100
        height = 100

    class FakeUser:
        id = 1

    class FakeMessage:
        from_user = FakeUser()
        photo = [FakePhoto()]
        caption = ""
        bot = FakeBot()

        async def answer(self, text, **kw):
            pass

    # Patch PHOTOS_DIR to tmp_path
    import config as cfg_mod
    from pathlib import Path
    monkeypatch.setattr(cfg_mod, "PHOTOS_DIR", Path(str(tmp_path)))

    async def run():
        await test_db.init()
        monkeypatch.setattr(indexer_mod, "index_vision_result", cap.make_coro("index_vision_result"))

        await photo_mod.handle_photo(FakeMessage(), scheduler=None)
        await asyncio.sleep(0)
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert "150 USD" in kw["summary"] or kw["summary"] == _vision_data["summary"]
        assert kw["photo_type"] == "receipt"

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 9. regime.py → index_memory_item (plan)
# ══════════════════════════════════════════════════════════════════════════════

def test_regime_plan_day_indexes(monkeypatch, tmp_path):
    """handle_plan_day in regime.py must call index_memory_item with source_type='plan'."""
    import bot.modules.regime as regime_mod
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(regime_mod, "db", test_db)

    cap = _IndexCapture()

    async def run():
        await test_db.init()
        monkeypatch.setattr(indexer_mod, "index_memory_item", cap.make_coro("index_memory_item"))

        # Stub user_settings to return defaults
        async def fake_get_settings(user_id):
            return {}
        monkeypatch.setattr(regime_mod, "_get_user_settings", fake_get_settings, raising=False)

        # Need to also stub db.task_list and db.schedule_get_day
        async def fake_task_list(uid, **kw):
            return [{"title": "Утренняя зарядка", "due_time": "07:00", "priority": "normal"}]
        async def fake_schedule_get_day(uid, d):
            return []
        monkeypatch.setattr(test_db, "task_list", fake_task_list)
        monkeypatch.setattr(test_db, "schedule_get_day", fake_schedule_get_day)

        result = await regime_mod.handle_day_plan(
            user_id=1,
            params={"date": "2025-01-15"},
            ai_response="ok",
        )
        await asyncio.sleep(0)
        assert "План" in result
        assert len(cap.calls) == 1
        kw = cap.calls[0]["kwargs"]
        assert kw["user_id"] == 1
        assert kw["source_type"] == "plan"
        assert kw["source_id"] == "2025-01-15"

    asyncio.run(run())
