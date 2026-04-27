"""Tests for Vision pipeline, JSON parser, and pending actions flow.

Run: python -m pytest test_vision_pipeline.py -v
"""
import asyncio
import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_PATH", ":memory:")

# ── Stubs so we can import without real .env ──────────────────────────────────
import types

_fake_config = types.ModuleType("config")
_fake_config.OPENAI_API_KEY = "sk-test"
_fake_config.VISION_ENABLED = True
_fake_config.GOOGLE_ENABLED = False
_fake_config.ALLOWED_USER_IDS = []
_fake_config.DB_PATH = ":memory:"
_fake_config.MODEL_ROUTER = "gpt-4o-mini"
_fake_config.MODEL_CHAT = "gpt-4o-mini"
_fake_config.MODEL_REASONING = "gpt-4o"
_fake_config.MODEL_VISION = "gpt-4o-mini"
_fake_config.WHISPER_MODEL = "whisper-1"
_fake_config.MODEL_EMBEDDINGS = "text-embedding-3-small"
_fake_config.TIMEZONE = "Europe/Warsaw"
_fake_config.MIN_CONFIDENCE = 0.65
_fake_config.PHOTOS_DIR = "/tmp"
sys.modules["config"] = _fake_config

# ── Import the modules under test ─────────────────────────────────────────────
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
    from bot.handlers.message import _CONFIRM_WORDS, _CANCEL_WORDS

    assert "да" in _CONFIRM_WORDS
    assert "сохрани" in _CONFIRM_WORDS

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
    from bot.handlers.message import _CANCEL_WORDS

    assert "нет" in _CANCEL_WORDS
    assert "отмена" in _CANCEL_WORDS

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


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
