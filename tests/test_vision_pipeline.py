"""Tests for Vision pipeline, JSON parser, confirm/cancel matchers, and pending actions flow.

Run: python -B -m pytest test_vision_pipeline.py -v
"""
import asyncio
import json
import os
import sys
import types
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_PATH", ":memory:")

# ── config stub (scoped so other test modules aren't polluted) ─────────────────
_ORIG_CONFIG = sys.modules.get("config")

def _make_fake_config():
    m = types.ModuleType("config")
    m.OPENAI_API_KEY = "sk-test"
    m.VISION_ENABLED = True
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


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    """Inject fake config for every test; restore original afterwards."""
    fake = _make_fake_config()
    monkeypatch.setitem(sys.modules, "config", fake)
    yield fake


# ── Import the modules under test (after first fixture run sets the stub) ─────
# We import lazily inside tests that need it, or use the fixture to ensure
# the stub is installed before any import happens at module level.
# Vision helpers are pure-python, safe to import once here:
sys.modules["config"] = _make_fake_config()  # needed for module-level import below
from bot.modules.vision import _parse_vision_json, _fallback_vision_result, _normalise


# ═════════════════════════════════════════════════════════════════════════════
# 1-4. JSON parser tests
# ═════════════════════════════════════════════════════════════════════════════

def test_vision_json_parser_clean_json():
    raw = json.dumps({
        "photo_type": "receipt",
        "summary": "Чек на 42 PLN",
        "extracted_text": "BIEDRONKA 42.00 PLN",
        "detected_entities": {"amount": 42.0, "currency": "PLN"},
        "suggested_actions": [{"intent": "expense_add", "params": {"amount": 42.0, "currency": "PLN"}}],
        "needs_confirmation": True,
    })
    result = _parse_vision_json(raw)
    assert result["photo_type"] == "receipt"
    assert result["detected_entities"]["amount"] == 42.0
    assert len(result["suggested_actions"]) == 1


def test_vision_json_parser_markdown_fence():
    raw = """Here is the analysis:

```json
{
  "photo_type": "study_task",
  "summary": "Задание по математике",
  "extracted_text": "Решить задачу 5",
  "detected_entities": {},
  "suggested_actions": [],
  "needs_confirmation": true
}
```"""
    result = _parse_vision_json(raw)
    assert result["photo_type"] == "study_task"
    assert result["summary"] == "Задание по математике"


def test_vision_json_parser_extra_text():
    raw = """Это изображение показывает чек из супермаркета.

{"photo_type": "receipt", "summary": "Чек Biedronka", "extracted_text": "42 PLN", "detected_entities": {"amount": 42}, "suggested_actions": [], "needs_confirmation": true}

Если нужно я могу помочь."""
    result = _parse_vision_json(raw)
    assert result["photo_type"] == "receipt"
    assert "Biedronka" in result["summary"]


def test_vision_json_parser_invalid_fallback():
    raw = "Это не JSON вообще, просто текст от модели."
    result = _parse_vision_json(raw)
    assert result["photo_type"] == "unknown"
    assert "suggested_actions" in result
    assert isinstance(result["suggested_actions"], list)
    assert result.get("error_text") or result["summary"]


def test_vision_json_parser_empty_string():
    result = _parse_vision_json("")
    assert result["photo_type"] == "unknown"
    assert result["error_text"] == "empty response"


def test_vision_json_parser_normalise_defaults():
    """_normalise fills in missing keys with safe defaults."""
    partial = {"photo_type": "object", "summary": "Холодильник"}
    result = _normalise(partial)
    assert result["extracted_text"] == ""
    assert result["suggested_actions"] == []
    assert result["detected_entities"] == {}
    assert result["needs_confirmation"] is True


# ═════════════════════════════════════════════════════════════════════════════
# 5-6. Photo pipeline mock tests
# ═════════════════════════════════════════════════════════════════════════════

class _AsyncDB:
    """Minimal async DB mock for pipeline tests."""
    def __init__(self):
        self.attachments = {}
        self.vision_results = {}
        self.conversation_states = {}
        self._att_id = 0
        self._vis_id = 0

    async def attachment_save(self, user_id, file_type, file_id, local_path=None,
                               caption=None, section_name=None, record_id=None):
        self._att_id += 1
        self.attachments[self._att_id] = {
            "id": self._att_id, "user_id": user_id, "file_type": file_type,
            "file_id": file_id, "local_path": local_path, "caption": caption,
        }
        return self._att_id

    async def vision_save(self, user_id, attachment_id, photo_type, summary,
                          extracted_text=None, detected_entities=None, suggested_actions=None):
        self._vis_id += 1
        self.vision_results[self._vis_id] = {
            "attachment_id": attachment_id, "photo_type": photo_type, "summary": summary,
        }
        return self._vis_id

    async def attachment_update_vision(self, attachment_id, vision_summary):
        if attachment_id in self.attachments:
            self.attachments[attachment_id]["vision_summary"] = vision_summary

    async def conversation_state_update(self, user_id, **fields):
        state = self.conversation_states.get(user_id, {})
        state.update(fields)
        self.conversation_states[user_id] = state

    async def conversation_state_get(self, user_id):
        return self.conversation_states.get(user_id, {})


def test_photo_pipeline_saves_attachment_mock():
    """Verify attachment_save is called with correct file_type."""
    mock_db = _AsyncDB()

    async def run():
        att_id = await mock_db.attachment_save(
            user_id=1,
            file_type="photo",
            file_id="AgACx",
            local_path="/tmp/photo_1.jpg",
            caption="тест",
        )
        return att_id, mock_db.attachments[att_id]

    att_id, att = asyncio.run(run())
    assert att_id == 1
    assert att["file_type"] == "photo"
    assert att["local_path"] == "/tmp/photo_1.jpg"
    assert att["caption"] == "тест"


def test_photo_pipeline_saves_vision_result_mock():
    """Verify vision_save is called and summary is written back to attachment."""
    mock_db = _AsyncDB()

    vision_result = {
        "photo_type": "receipt",
        "summary": "Чек на 42 PLN",
        "extracted_text": "42 PLN",
        "detected_entities": {"amount": 42},
        "suggested_actions": [{"intent": "expense_add", "params": {"amount": 42, "currency": "PLN"}}],
    }

    async def run():
        att_id = await mock_db.attachment_save(1, "photo", "AgAC", "/tmp/p.jpg")
        await mock_db.vision_save(
            user_id=1,
            attachment_id=att_id,
            photo_type=vision_result["photo_type"],
            summary=vision_result["summary"],
        )
        await mock_db.attachment_update_vision(att_id, vision_result["summary"])
        await mock_db.conversation_state_update(
            1,
            active_topic="photo",
            last_photo_id=att_id,
            pending_vision_actions_json=json.dumps(vision_result["suggested_actions"]),
        )
        return att_id

    att_id = asyncio.run(run())
    assert mock_db.attachments[att_id]["vision_summary"] == "Чек на 42 PLN"
    state = mock_db.conversation_states[1]
    assert state["active_topic"] == "photo"
    pending = json.loads(state["pending_vision_actions_json"])
    assert pending[0]["intent"] == "expense_add"


# ═════════════════════════════════════════════════════════════════════════════
# 7-8. Pending vision action confirm / cancel
# ═════════════════════════════════════════════════════════════════════════════

def test_pending_vision_action_confirm_yes():
    """'да' should dispatch actions and clear pending state."""
    from bot.handlers.message import is_vision_action_confirm, is_vision_action_cancel

    assert is_vision_action_confirm("да") is True
    assert is_vision_action_confirm("сохрани") is True
    assert is_vision_action_cancel("да") is False  # confirm word is not a cancel

    mock_db = _AsyncDB()
    actions = [{"intent": "expense_add", "params": {"amount": 42, "currency": "PLN"}, "confidence": 0.95}]
    dispatched = []

    async def run():
        await mock_db.conversation_state_update(
            1,
            active_topic="photo",
            pending_vision_actions_json=json.dumps(actions),
        )
        state = await mock_db.conversation_state_get(1)
        assert state["active_topic"] == "photo"

        pending = json.loads(state["pending_vision_actions_json"])
        dispatched.extend(pending)

        # Simulate clearing
        await mock_db.conversation_state_update(1, pending_vision_actions_json=None, active_topic=None)

    asyncio.run(run())
    assert len(dispatched) == 1
    assert dispatched[0]["intent"] == "expense_add"
    final = asyncio.run(mock_db.conversation_state_get(1))
    assert final.get("pending_vision_actions_json") is None
    assert final.get("active_topic") is None


def test_pending_vision_action_cancel():
    """'нет' should clear pending state without dispatching."""
    from bot.handlers.message import is_vision_action_cancel, _CANCEL_EXACT

    assert is_vision_action_cancel("нет") is True
    assert is_vision_action_cancel("отмена") is True
    assert "нет" in _CANCEL_EXACT

    mock_db = _AsyncDB()
    actions = [{"intent": "expense_add", "params": {}}]

    async def run():
        await mock_db.conversation_state_update(
            1,
            active_topic="photo",
            pending_vision_actions_json=json.dumps(actions),
        )
        # simulate cancel: clear without dispatching
        await mock_db.conversation_state_update(1, pending_vision_actions_json=None, active_topic=None)
        return await mock_db.conversation_state_get(1)

    final = asyncio.run(run())
    assert final.get("pending_vision_actions_json") is None
    assert final.get("active_topic") is None


# ═════════════════════════════════════════════════════════════════════════════
# 9. DB health migration test
# ═════════════════════════════════════════════════════════════════════════════

def test_db_health_creates_google_tables():
    """db_health_migrate must create google_sync_queue and google_links."""
    import tempfile
    import aiosqlite

    async def run():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            from bot.db.database import Database, _CREATE_SQL
            test_db = Database(db_path)
            report = await test_db.db_health_migrate()

            # Verify tables exist
            async with aiosqlite.connect(db_path) as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = {row[0] for row in await cursor.fetchall()}

            assert "google_sync_queue" in tables, f"google_sync_queue missing. Tables: {tables}"
            assert "google_links" in tables, f"google_links missing. Tables: {tables}"
            assert "attachments" in tables
            assert "vision_results" in tables
            return tables
        finally:
            os.unlink(db_path)

    tables = asyncio.run(run())
    assert len(tables) >= 10  # all main tables present


# ═════════════════════════════════════════════════════════════════════════════
# 10-19. Safe confirm/cancel matcher tests  (spec §6, items 1-8)
# ═════════════════════════════════════════════════════════════════════════════

def test_vision_confirm_exact_yes():
    """'да' is an unambiguous confirmation."""
    from bot.handlers.message import is_vision_action_confirm
    assert is_vision_action_confirm("да") is True


def test_vision_confirm_exact_yes_with_punctuation():
    """'да.' and 'да!' are also confirmations."""
    from bot.handlers.message import is_vision_action_confirm
    assert is_vision_action_confirm("да.") is True
    assert is_vision_action_confirm("да!") is True


def test_vision_confirm_yes_save():
    """'да, сохрани' is a confirmation."""
    from bot.handlers.message import is_vision_action_confirm
    assert is_vision_action_confirm("да, сохрани") is True


def test_vision_confirm_save_finance():
    """Explicit action phrase 'запиши в финансы' is a confirmation."""
    from bot.handlers.message import is_vision_action_confirm
    assert is_vision_action_confirm("запиши в финансы") is True
    assert is_vision_action_confirm("добавь в финансы") is True


def test_vision_confirm_not_dai():
    """'дай план на сегодня' must NOT trigger confirmation."""
    from bot.handlers.message import is_vision_action_confirm
    assert is_vision_action_confirm("дай план на сегодня") is False


def test_vision_confirm_not_dannye():
    """'данные по рекламе' must NOT trigger confirmation."""
    from bot.handlers.message import is_vision_action_confirm
    assert is_vision_action_confirm("данные по рекламе") is False


def test_vision_confirm_not_davai():
    """'давай посмотрим' must NOT trigger confirmation."""
    from bot.handlers.message import is_vision_action_confirm
    assert is_vision_action_confirm("давай посмотрим") is False


def test_vision_confirm_not_neutral_phrases():
    """Other neutral phrases must not be mistaken for confirmation."""
    from bot.handlers.message import is_vision_action_confirm
    for phrase in ["дальше", "доброе утро", "дай мне план", "добавь задачу купить хлеб"]:
        assert is_vision_action_confirm(phrase) is False, f"Should NOT confirm: {phrase!r}"


def test_vision_cancel_phrases():
    """Cancel matcher covers the required phrases."""
    from bot.handlers.message import is_vision_action_cancel
    for phrase in ["нет", "не надо", "отмена", "отмени", "не сохраняй", "не записывай"]:
        assert is_vision_action_cancel(phrase) is True, f"Should cancel: {phrase!r}"


def test_vision_cancel_not_triggered_by_neutral():
    """Neutral phrases are not cancels."""
    from bot.handlers.message import is_vision_action_cancel
    for phrase in ["не уверен", "нет времени", "не могу сейчас"]:
        assert is_vision_action_cancel(phrase) is False, f"Should NOT cancel: {phrase!r}"


def test_pending_vision_dai_plan_goes_to_normal_flow():
    """With pending actions, 'дай план на сегодня' should return False from the matcher."""
    from bot.handlers.message import is_vision_action_confirm, is_vision_action_cancel
    # If both matchers return False, _check_pending_vision_actions returns False
    # meaning the message falls through to normal classify/dispatcher.
    text = "дай план на сегодня"
    assert is_vision_action_confirm(text) is False
    assert is_vision_action_cancel(text) is False


def test_pending_vision_yes_executes_actions():
    """'да' triggers confirm path: actions should be dispatched and state cleared."""
    from bot.handlers.message import is_vision_action_confirm, is_vision_action_cancel
    mock_db = _AsyncDB()
    actions = [{"intent": "expense_add", "params": {"amount": 42}}]

    assert is_vision_action_confirm("да") is True
    assert is_vision_action_cancel("да") is False

    async def run():
        await mock_db.conversation_state_update(
            2, active_topic="photo",
            pending_vision_actions_json=json.dumps(actions),
        )
        # Simulate what _check_pending_vision_actions does on confirm
        state = await mock_db.conversation_state_get(2)
        pending = json.loads(state["pending_vision_actions_json"])
        await mock_db.conversation_state_update(2, pending_vision_actions_json=None, active_topic=None)
        return pending

    executed = asyncio.run(run())
    assert executed[0]["intent"] == "expense_add"
    final = asyncio.run(mock_db.conversation_state_get(2))
    assert final.get("pending_vision_actions_json") is None
    assert final.get("active_topic") is None


# ═════════════════════════════════════════════════════════════════════════════
# Integration tests for _check_pending_vision_actions with real function
# ═════════════════════════════════════════════════════════════════════════════

class _FakeMessage:
    """Minimal aiogram Message stub for integration tests."""
    def __init__(self, text, user_id=99):
        self.text = text
        self.from_user = type("U", (), {"id": user_id})()
        self.bot = None
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


def _make_state_db(state_dict: dict) -> _AsyncDB:
    """Create a mock DB pre-seeded with one conversation state row."""
    mock = _AsyncDB()
    mock.conversation_states[99] = dict(state_dict)
    return mock


def test_pending_vision_confirm_before_expiry_executes(monkeypatch):
    """Confirm 'да' before expires_at → dispatch executed, state cleared."""
    from datetime import datetime as dt, timedelta as td
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod

    expires = (dt.now() + td(minutes=30)).isoformat(sep=" ", timespec="seconds")
    actions = [{"intent": "expense_add", "params": {"amount": 100}, "confidence": 0.95}]

    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": json.dumps(actions),
        "pending_vision_expires_at": expires,
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []

    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "\u2705 \u0420\u0430\u0441\u0445\u043e\u0434 \u0437\u0430\u043f\u0438\u0441\u0430\u043d"

    import sys
    fake_dispatcher = types.ModuleType("bot.modules.dispatcher")
    fake_dispatcher.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fake_dispatcher)

    message = _FakeMessage("\u0434\u0430", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(message, scheduler=None))

    assert result is True, "Should have handled the confirm"
    assert len(dispatched) == 1
    assert dispatched[0]["intent"] == "expense_add"
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None
    assert final.get("pending_vision_expires_at") is None
    assert final.get("active_topic") is None


def test_pending_vision_confirm_after_expiry_does_not_execute(monkeypatch):
    """Confirm 'да' after expires_at → action NOT executed, expired message sent."""
    from datetime import datetime as dt, timedelta as td
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod

    # Expired 1 minute ago
    expires = (dt.now() - td(minutes=1)).isoformat(sep=" ", timespec="seconds")
    actions = [{"intent": "expense_add", "params": {"amount": 100}}]

    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": json.dumps(actions),
        "pending_vision_expires_at": expires,
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []

    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "should not reach"

    import sys
    fake_dispatcher = types.ModuleType("bot.modules.dispatcher")
    fake_dispatcher.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fake_dispatcher)

    message = _FakeMessage("\u0434\u0430", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(message, scheduler=None))

    assert len(dispatched) == 0, "Expired action must not be dispatched"
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None
    assert final.get("pending_vision_expires_at") is None
    # Expiry message was sent to user
    assert any("\u0443\u0441\u0442\u0430\u0440\u0435\u043b\u043e" in a or "\u0435\u0449\u0451 \u0440\u0430\u0437" in a for a in message.answers), \
        f"Expected expiry message, got: {message.answers}"


def test_pending_vision_normal_message_does_not_extend_ttl(monkeypatch):
    """'дай план на сегодня' must NOT execute actions and must NOT touch expires_at."""
    from datetime import datetime as dt, timedelta as td
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod

    fixed_expires = (dt.now() + td(minutes=25)).isoformat(sep=" ", timespec="seconds")
    actions = [{"intent": "expense_add", "params": {}}]

    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": json.dumps(actions),
        "pending_vision_expires_at": fixed_expires,
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    message = _FakeMessage("\u0434\u0430\u0439 \u043f\u043b\u0430\u043d \u043d\u0430 \u0441\u0435\u0433\u043e\u0434\u043d\u044f", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(message, scheduler=None))

    assert result is False, "Neutral message must not be intercepted"
    # expires_at must be unchanged
    state_after = asyncio.run(mock_db.conversation_state_get(99))
    assert state_after.get("pending_vision_expires_at") == fixed_expires
    assert state_after.get("pending_vision_actions_json") == json.dumps(actions)


def test_pending_vision_legacy_no_expires_at_treated_as_expired(monkeypatch):
    """Legacy pending without expires_at → treated as expired (safety-first), not dispatched."""
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod

    actions = [{"intent": "task_add", "params": {"title": "legacy task"}}]
    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": json.dumps(actions),
        # No pending_vision_expires_at — legacy record
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []

    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "should not reach"

    import sys
    fake_dispatcher = types.ModuleType("bot.modules.dispatcher")
    fake_dispatcher.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fake_dispatcher)

    message = _FakeMessage("\u0434\u0430", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(message, scheduler=None))

    assert len(dispatched) == 0, "Legacy pending without expires_at must not be dispatched"
    # Returns True: consumed, NOT passed to classify/dispatcher
    assert result is True, "Legacy pending must be consumed (return True), not fall through"
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None


def test_expired_pending_consumes_yes(monkeypatch):
    """Expired pending + 'да' -> returns True (consumed), no dispatch, pending cleared."""
    from datetime import datetime as dt, timedelta as td
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod

    expires = (dt.now() - td(minutes=5)).isoformat(sep=" ", timespec="seconds")
    actions = [{"intent": "expense_add", "params": {"amount": 77}}]
    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": json.dumps(actions),
        "pending_vision_expires_at": expires,
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []
    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "should not reach"
    import sys
    fd = types.ModuleType("bot.modules.dispatcher")
    fd.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fd)

    msg = _FakeMessage("да", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(msg, scheduler=None))

    assert result is True
    assert len(dispatched) == 0
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None
    assert final.get("pending_vision_expires_at") is None


def test_legacy_pending_without_expires_consumes_yes(monkeypatch):
    """Legacy pending (no expires_at) + 'да' -> returns True, no dispatch, cleared."""
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod

    actions = [{"intent": "task_add", "params": {"title": "old task"}}]
    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": json.dumps(actions),
        # No expires_at
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []
    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "nope"
    import sys
    fd = types.ModuleType("bot.modules.dispatcher")
    fd.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fd)

    msg = _FakeMessage("да", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(msg, scheduler=None))

    assert result is True
    assert len(dispatched) == 0
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None


def test_malformed_expires_consumes_yes(monkeypatch):
    """Malformed expires_at + 'да' -> returns True, no dispatch, pending cleared, warning logged."""
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod

    actions = [{"intent": "reminder_add", "params": {"text": "malformed test"}}]
    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": json.dumps(actions),
        "pending_vision_expires_at": "bad-date-xyz",
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []
    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "nope"
    import sys
    fd = types.ModuleType("bot.modules.dispatcher")
    fd.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fd)

    msg = _FakeMessage("да", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(msg, scheduler=None))

    assert result is True
    assert len(dispatched) == 0
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None
    assert final.get("pending_vision_expires_at") is None


def test_new_photo_clears_old_pending_if_vision_fails():
    """New photo arrival must clear old pending even if vision returns no actions."""
    mock_db = _AsyncDB()
    old_actions = [{"intent": "expense_add", "params": {"amount": 50}}]
    from datetime import datetime as dt, timedelta as td
    old_expires = (dt.now() + td(minutes=20)).isoformat(sep=" ", timespec="seconds")

    async def run():
        # Seed old pending state
        await mock_db.conversation_state_update(
            10,
            active_topic="photo",
            last_photo_id=1,
            pending_vision_actions_json=json.dumps(old_actions),
            pending_vision_expires_at=old_expires,
        )
        # Simulate new photo arrival: clear old pending
        await mock_db.conversation_state_update(
            10,
            active_topic="photo",
            last_photo_id=2,
            pending_vision_actions_json=None,
            pending_vision_expires_at=None,
        )
        # Vision fails / no actions: don't set new pending
        return await mock_db.conversation_state_get(10)

    final = asyncio.run(run())
    assert final.get("pending_vision_actions_json") is None
    assert final.get("pending_vision_expires_at") is None
    assert final.get("last_photo_id") == 2


def test_new_photo_sets_new_pending_only_for_new_actions():
    """New photo with vision result replaces old pending with new one."""
    mock_db = _AsyncDB()
    old_actions = [{"intent": "expense_add", "params": {"amount": 50}}]
    new_actions = [{"intent": "task_add", "params": {"title": "Fix the roof"}}]
    from datetime import datetime as dt, timedelta as td
    old_expires = (dt.now() + td(minutes=20)).isoformat(sep=" ", timespec="seconds")
    new_expires = (dt.now() + td(minutes=30)).isoformat(sep=" ", timespec="seconds")

    async def run():
        # Seed old pending state
        await mock_db.conversation_state_update(
            11,
            active_topic="photo",
            last_photo_id=3,
            pending_vision_actions_json=json.dumps(old_actions),
            pending_vision_expires_at=old_expires,
        )
        # New photo: first clear old pending
        await mock_db.conversation_state_update(
            11,
            active_topic="photo",
            last_photo_id=4,
            pending_vision_actions_json=None,
            pending_vision_expires_at=None,
        )
        # Vision succeeded: write new pending
        await mock_db.conversation_state_update(
            11,
            pending_vision_actions_json=json.dumps(new_actions),
            pending_vision_expires_at=new_expires,
        )
        return await mock_db.conversation_state_get(11)

    final = asyncio.run(run())
    stored = json.loads(final["pending_vision_actions_json"])
    assert stored[0]["intent"] == "task_add", "Should have new action, not old"
    assert final.get("last_photo_id") == 4


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])


# ═════════════════════════════════════════════════════════════════════════════
# Phase 1 micro-fix tests: active_object context + corrupted pending JSON
# ═════════════════════════════════════════════════════════════════════════════

def test_new_photo_sets_active_attachment_context():
    """After new photo, conversation state must reflect new attachment as active object."""
    mock_db = _AsyncDB()
    old_actions = [{"intent": "expense_add", "params": {"amount": 10}}]
    from datetime import datetime as dt, timedelta as td
    old_expires = (dt.now() + td(minutes=20)).isoformat(sep=" ", timespec="seconds")

    async def run():
        # Seed: old active context (e.g. task)
        await mock_db.conversation_state_update(
            5,
            active_topic="task",
            active_object_type="task",
            active_object_id=42,
            last_photo_id=7,
            pending_vision_actions_json=json.dumps(old_actions),
            pending_vision_expires_at=old_expires,
        )
        # New photo: simulate what photo.py does after attachment_save
        new_att_id = await mock_db.attachment_save(5, "photo", "AgNEW", "/tmp/new.jpg")
        await mock_db.conversation_state_update(
            5,
            active_topic="photo",
            active_object_type="attachment",
            active_object_id=new_att_id,
            last_photo_id=new_att_id,
            last_user_message="[фото]",
            pending_vision_actions_json=None,
            pending_vision_expires_at=None,
        )
        return await mock_db.conversation_state_get(5), new_att_id

    state, new_att_id = asyncio.run(run())
    assert state["active_topic"] == "photo"
    assert state["active_object_type"] == "attachment"
    assert state["active_object_id"] == new_att_id
    assert state["last_photo_id"] == new_att_id
    assert state.get("pending_vision_actions_json") is None
    assert state.get("pending_vision_expires_at") is None


def test_corrupted_pending_json_consumes_yes(monkeypatch):
    """Corrupted JSON in pending + 'да' -> consumed (True), no dispatch, pending cleared."""
    from datetime import datetime as dt, timedelta as td
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod
    import sys

    expires = (dt.now() + td(minutes=20)).isoformat(sep=" ", timespec="seconds")
    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": "{bad json!!!",
        "pending_vision_expires_at": expires,
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []

    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "nope"

    fd = types.ModuleType("bot.modules.dispatcher")
    fd.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fd)

    msg = _FakeMessage("да", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(msg, scheduler=None))

    assert result is True, "Corrupted JSON must be consumed"
    assert len(dispatched) == 0
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None
    assert final.get("pending_vision_expires_at") is None


def test_empty_pending_actions_consumes_yes(monkeypatch):
    """Empty list [] in pending + 'да' -> consumed (True), not sent to classify."""
    from datetime import datetime as dt, timedelta as td
    import bot.handlers.message as msg_mod
    import bot.db.database as db_mod
    import sys

    expires = (dt.now() + td(minutes=20)).isoformat(sep=" ", timespec="seconds")
    mock_db = _make_state_db({
        "active_topic": "photo",
        "pending_vision_actions_json": "[]",
        "pending_vision_expires_at": expires,
    })
    monkeypatch.setattr(db_mod, "db", mock_db)
    monkeypatch.setattr(msg_mod, "db", mock_db)

    dispatched = []

    async def _fake_dispatch(actions, user_id, ai_reply, scheduler, bot, confidence):
        dispatched.extend(actions)
        return "nope"

    fd = types.ModuleType("bot.modules.dispatcher")
    fd.dispatch_actions = _fake_dispatch
    monkeypatch.setitem(sys.modules, "bot.modules.dispatcher", fd)

    msg = _FakeMessage("да", user_id=99)
    result = asyncio.run(msg_mod._check_pending_vision_actions(msg, scheduler=None))

    assert result is True, "Empty pending list must be consumed"
    assert len(dispatched) == 0
    final = asyncio.run(mock_db.conversation_state_get(99))
    assert final.get("pending_vision_actions_json") is None

