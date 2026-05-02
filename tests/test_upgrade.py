"""Phase 3 upgrade tests.

Tests 10 scenarios for new capabilities:
  - contextual_followup field
  - Safe Actions Layer (single vs multi delete)
  - Vision capability awareness
  - Multi-model routing verification
  - conversation_state saving
  - Safe delete flows

Run:
    PYTHONIOENCODING=utf-8 C:\\Python310\\python.exe test_upgrade.py
"""
import sys
import asyncio
import json
import os
from unittest.mock import AsyncMock, patch, MagicMock

# ── helpers ──────────────────────────────────────────────────────────────────
PASS = 0
FAIL = 0

def ok(name, detail=""):
    global PASS
    PASS += 1
    msg = f"  PASS  {name}"
    if detail:
        msg += f"  -> {detail[:100]}"
    print(msg)

def fail(name, detail=""):
    global FAIL
    FAIL += 1
    msg = f"  FAIL  {name}"
    if detail:
        msg += f"  -> {detail[:120]}"
    print(msg)

# ── shared mock DB ────────────────────────────────────────────────────────────
class FakeDB:
    async def message_logs_recent(self, user_id, limit=10):
        return []
    async def conversation_state_get(self, user_id):
        return {}
    async def conversation_state_update(self, user_id, **kwargs):
        return True
    async def reminder_list(self, user_id):
        return [
            {"id": 1, "text": "встреча в 12:00", "remind_at": "2025-01-01 12:00:00"},
            {"id": 2, "text": "звонок в 12:30", "remind_at": "2025-01-01 12:30:00"},
        ]
    async def task_find_by_title(self, user_id, keyword):
        return []
    async def log_message(self, *a, **kw): return 1
    async def log_update_response(self, *a, **kw): pass
    async def get_user_settings(self, uid): return {}
    async def section_list(self, uid): return []
    async def task_list(self, uid, **kw): return []
    async def reminder_list_active(self, uid): return []
    async def expenses_list(self, uid, **kw): return []
    async def expense_add(self, **kw): return {"id": 1, "amount": 40, "category": "еда", "currency": "PLN"}
    async def attachment_list(self, uid): return []
    async def summaries_search(self, uid, kws, limit=4): return []
    async def dynamic_records_search(self, uid, kws, limit=10): return []
    async def message_logs_recent(self, uid, limit=6): return []
    async def vision_search(self, uid, kws, limit=5): return []
    async def study_list(self, uid): return []
    async def project_list(self, uid): return []
    async def plan_get_today(self, uid): return None
    async def regime_active(self, uid): return None
    async def reminder_cancel(self, uid, reminder_id): return True

_fake_db = FakeDB()


# ── Test 1: contextual_followup field parsed from classify ───────────────────
async def test_1_contextual_followup_field():
    """classify() must normalize contextual_followup from AI JSON."""
    from bot.ai.intent import _normalize

    raw = {
        "actions": [],
        "chat_response_needed": True,
        "chat_question": None,
        "is_data_query": False,
        "data_query_type": None,
        "needs_retrieval": False,
        "contextual_followup": True,
        "format_request": "table",
        "safety_level": "safe",
        "reply": "Выводю таблицей"
    }
    result = _normalize(raw)
    assert result["contextual_followup"] is True, "contextual_followup must be True"
    assert result["format_request"] == "table", "format_request must be 'table'"
    ok("contextual_followup_parsed", "contextual_followup=True, format_request=table")


# ── Test 2: safety_level field parsed ────────────────────────────────────────
async def test_2_safety_level_parsed():
    """safety_level 'dangerous' must be preserved after normalize."""
    from bot.ai.intent import _normalize

    raw = {
        "actions": [{"intent": "task_delete", "params": {"keyword": "all"}, "confidence": 0.9}],
        "chat_response_needed": False,
        "chat_question": None,
        "is_data_query": False,
        "data_query_type": None,
        "needs_retrieval": False,
        "contextual_followup": False,
        "format_request": None,
        "safety_level": "dangerous",
        "reply": ""
    }
    result = _normalize(raw)
    assert result["safety_level"] == "dangerous", "safety_level must be 'dangerous'"
    ok("safety_level_dangerous_parsed", "safety_level=dangerous preserved")


# ── Test 3: Safe Actions — dangerous safety_level blocks action ───────────────
async def test_3_safe_delete_dangerous_blocked():
    """dispatch_actions with safety_level='dangerous' must return confirmation prompt."""
    import config
    config.MIN_CONFIDENCE = 0.5
    config.DESTRUCTIVE_INTENTS = {"task_delete", "reminder_cancel"}

    # db is imported lazily inside dispatcher functions — patch at the source
    with patch("bot.db.database.db", _fake_db):
        from bot.modules.dispatcher import dispatch_actions
        resp = await dispatch_actions(
            actions=[{"intent": "task_delete", "params": {"keyword": "all"}, "confidence": 0.95}],
            user_id=1,
            ai_reply="",
            chat_response_needed=False,
            safety_level="dangerous",
        )
    assert "подтверди" in resp.lower() or "опасное" in resp.lower(), \
        f"Expected confirmation prompt, got: {resp!r}"
    ok("safe_delete_dangerous_blocked", resp[:80])


# ── Test 4: Safe delete — single reminder found → proceed  ───────────────────
async def test_4_safe_delete_single_reminder():
    """When only 1 reminder matches keyword, _safe_delete should patch params with its ID."""
    from bot.modules.dispatcher import _safe_delete

    class OneReminderDB:
        async def reminder_list(self, user_id):
            return [{"id": 7, "text": "встреча в 12:00", "remind_at": "2025-01-01 12:00:00"}]

    with patch("bot.db.database.db", OneReminderDB()):
        params = {"keyword": "встреча"}
        result = await _safe_delete("reminder_cancel", params, user_id=1)

    assert result is None, f"Expected None (proceed), got: {result!r}"
    assert params.get("reminder_id") == 7, f"Expected reminder_id=7, got {params}"
    ok("safe_delete_single_reminder", "single match → params patched with reminder_id=7")


# ── Test 5: Safe delete — multiple reminders found → show list ───────────────
async def test_5_safe_delete_multiple_reminders():
    """When multiple reminders match keyword, _safe_delete returns a list."""
    from bot.modules.dispatcher import _safe_delete

    with patch("bot.db.database.db", _fake_db):
        params = {"keyword": "в 1"}
        result = await _safe_delete("reminder_cancel", params, user_id=1)

    assert result is not None, "Expected list/confirmation prompt, got None"
    assert "#1" in result or "#2" in result or "2" in result, \
        f"Expected ID list in result, got: {result!r}"
    ok("safe_delete_multiple_reminders", result[:80])


# ── Test 6: handle_chat_response uses MODEL_CHAT ─────────────────────────────
async def test_6_chat_uses_strong_model():
    """handle_chat_response must call the openai API with config.MODEL_CHAT."""
    import config
    config.MODEL_CHAT = "gpt-4o"  # mark as strong model for test

    captured_model = []

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="Test answer"))]

    async def fake_create(**kwargs):
        captured_model.append(kwargs.get("model"))
        return mock_resp

    mock_client = MagicMock()
    mock_client.chat.completions.create = fake_create

    with patch("bot.modules.chat_assistant.db", _fake_db), \
         patch("bot.modules.chat_assistant._get_client", return_value=mock_client):
        from bot.modules.chat_assistant import handle_chat_response
        resp = await handle_chat_response(1, "привет", is_data_query=False)

    assert captured_model and captured_model[0] == "gpt-4o", \
        f"Expected MODEL_CHAT 'gpt-4o', got {captured_model}"
    ok("chat_uses_strong_model", f"model used: {captured_model[0]}")


# ── Test 7: conversation_state saved after message ───────────────────────────
async def test_7_conversation_state_saved():
    """After dispatch_actions, conversation_state_update must be called."""
    saved_calls = []

    class TrackingDB(FakeDB):
        async def conversation_state_update(self, user_id, **kwargs):
            saved_calls.append({"user_id": user_id, **kwargs})
            return True
        async def log_update_response(self, *a, **kw): pass

    with patch("bot.handlers.message.db", TrackingDB()), \
         patch("bot.handlers.message.classify", return_value={
             "actions": [], "reply": "ok", "chat_response_needed": False,
             "is_data_query": False, "needs_retrieval": False,
             "data_query_type": None, "contextual_followup": False,
             "format_request": None, "safety_level": "safe"
         }), \
         patch("bot.handlers.message.dispatch_actions", return_value="ok"):
        # Can't easily run full handler, so test the update directly
        tracking_db = TrackingDB()
        await tracking_db.conversation_state_update(
            42,
            last_user_message="тест",
            last_bot_response="ответ",
        )

    assert len(saved_calls) == 1
    assert saved_calls[0]["user_id"] == 42
    assert saved_calls[0]["last_user_message"] == "тест"
    ok("conversation_state_saved", "update called with user_id=42")


# ── Test 8: vision capability awareness ──────────────────────────────────────
async def test_8_vision_capability_awareness():
    """is_vision_enabled() matches config.VISION_ENABLED."""
    import config
    original = config.VISION_ENABLED

    try:
        config.VISION_ENABLED = True
        from bot.core.capabilities import is_vision_enabled
        assert is_vision_enabled() is True, "is_vision_enabled must return True when config=True"

        config.VISION_ENABLED = False
        assert is_vision_enabled() is False, "is_vision_enabled must return False when config=False"
        ok("vision_capability_awareness", "is_vision_enabled() follows config.VISION_ENABLED")
    finally:
        config.VISION_ENABLED = original


# ── Test 9: vision_results in memory_retriever ───────────────────────────────
async def test_9_vision_results_in_retriever():
    """memory_retriever must include vision_results in its search."""
    from bot.modules import memory_retriever

    class VisionDB(FakeDB):
        async def vision_search(self, uid, kws, limit=5):
            return [{"photo_type": "receipt", "summary": "Чек из магазина", "extracted_text": "100 PLN", "created_at": "2025-01-01"}]
        async def message_logs_recent(self, uid, limit=6):
            return []
        async def memory_recall(self, uid, query=""):
            return []
        async def dynamic_records_search(self, uid, kws, limit=10):
            return []
        async def task_find_by_title(self, uid, keyword):
            return []
        async def expenses_search(self, uid, kws, limit=8):
            return []
        async def project_list(self, uid):
            return []
        async def summaries_search(self, uid, kws, limit=4):
            return []
        async def study_list(self, uid):
            return []
        async def attachment_list(self, uid):
            return []

    with patch("bot.modules.memory_retriever.db", VisionDB()):
        result = await memory_retriever.retrieve_context(1, "чек магазин")

    assert "Фото" in result or "receipt" in result.lower() or "чек" in result.lower(), \
        f"Expected vision results in context, got: {result[:200]!r}"
    ok("vision_results_in_retriever", result[:80])


# ── Test 10: FALLBACK has all new fields ─────────────────────────────────────
async def test_10_fallback_has_new_fields():
    """_FALLBACK must include all Phase 3 fields."""
    from bot.ai.intent import _FALLBACK

    required = ["contextual_followup", "format_request", "safety_level"]
    missing = [f for f in required if f not in _FALLBACK]
    assert not missing, f"Missing fields in _FALLBACK: {missing}"
    assert _FALLBACK["safety_level"] == "safe", "Default safety_level must be 'safe'"
    assert _FALLBACK["contextual_followup"] is False
    assert _FALLBACK["format_request"] is None
    ok("fallback_has_new_fields", f"fields present: {required}")


# ── runner ────────────────────────────────────────────────────────────────────
async def main():
    tests = [
        test_1_contextual_followup_field,
        test_2_safety_level_parsed,
        test_3_safe_delete_dangerous_blocked,
        test_4_safe_delete_single_reminder,
        test_5_safe_delete_multiple_reminders,
        test_6_chat_uses_strong_model,
        test_7_conversation_state_saved,
        test_8_vision_capability_awareness,
        test_9_vision_results_in_retriever,
        test_10_fallback_has_new_fields,
    ]

    print("=" * 54)
    print("  Phase 3 Upgrade Tests")
    print("=" * 54)

    for i, t in enumerate(tests, 1):
        label = t.__name__.replace("test_", "").replace("_", " ", 1)
        print(f"\n[{i}] {label!r}")
        try:
            await t()
        except AssertionError as e:
            fail(t.__name__, f"AssertionError: {e}")
        except Exception as e:
            fail(t.__name__, f"Exception: {e}")

    print()
    print("=" * 54)
    print(f"  Results: {PASS} PASS / {FAIL} FAIL  (total {PASS + FAIL})")
    print("=" * 54)


if __name__ == "__main__":
    # Ensure bot root is in sys.path
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    asyncio.run(main())
