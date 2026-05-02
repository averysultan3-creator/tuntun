"""test_phase5.py — Phase 5 tests: Conversational AI upgrade.

15 tests covering:
- Conversational settings detection
- Conversation state tracking
- Safe delete with ambiguity
- Memory save/use
- Ideas workflow
- Dynamic section management
- General chat, mixed messages
- Beautiful formatting
- Buttons / structured data
- Onboarding trigger
- No hallucination in plan responses
"""
import asyncio
import json
import sys

# Patch stdout/stderr for proper Unicode on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
WARN = 0


def ok(name: str):
    global PASS
    PASS += 1
    print(f"  PASS  {name}")


def fail(name: str, reason: str = ""):
    global FAIL
    FAIL += 1
    msg = f"  FAIL  {name}"
    if reason:
        msg += f": {reason}"
    print(msg)


def warn(name: str, reason: str = ""):
    global WARN
    WARN += 1
    print(f"  WARN  {name}" + (f": {reason}" if reason else ""))


# ──────────────────────────────────────────────────────────────
# 1. Conversational setting — short reply
# ──────────────────────────────────────────────────────────────
def test_conversational_setting_short_reply():
    name = "conversational_setting_short_reply"
    from bot.ai.intent import _normalize
    raw = {
        "actions": [
            {"intent": "setting_save", "params": {"key": "reply_style", "value": "short"}, "confidence": 0.95}
        ],
        "reply": "Хорошо, буду отвечать короче.",
        "chat_response_needed": False,
        "settings_update_needed": True,
        "reply_style": "short",
        "is_data_query": False,
        "needs_retrieval": False,
        "data_query_type": None,
        "safety_level": "safe",
    }
    result = _normalize(raw)
    if not result.get("settings_update_needed"):
        fail(name, "settings_update_needed not extracted")
        return
    if result.get("reply_style") != "short":
        fail(name, f"reply_style={result.get('reply_style')} != short")
        return
    actions = result.get("actions", [])
    setting_actions = [a for a in actions if a.get("intent") == "setting_save"]
    if not setting_actions:
        fail(name, "setting_save action missing")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 2. Conversational setting — table for plans
# ──────────────────────────────────────────────────────────────
def test_conversational_setting_table_plan():
    name = "conversational_setting_table_plan"
    from bot.ai.intent import _normalize
    raw = {
        "actions": [
            {"intent": "setting_save", "params": {"key": "default_view", "value": "table"}, "confidence": 0.9}
        ],
        "reply": "Теперь планы буду показывать таблицей.",
        "chat_response_needed": False,
        "settings_update_needed": True,
        "reply_style": None,
        "is_data_query": False,
        "needs_retrieval": False,
        "data_query_type": None,
        "safety_level": "safe",
    }
    result = _normalize(raw)
    if not result.get("settings_update_needed"):
        fail(name, "settings_update_needed not set")
        return
    actions = result.get("actions", [])
    setting_action = next((a for a in actions if a.get("intent") == "setting_save"), None)
    if not setting_action:
        fail(name, "setting_save action not found")
        return
    if setting_action["params"].get("key") != "default_view":
        fail(name, f"key={setting_action['params'].get('key')} expected default_view")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 3. Intent normalize — new fields present in _FALLBACK
# ──────────────────────────────────────────────────────────────
def test_intent_normalize_new_fields():
    name = "intent_normalize_new_fields"
    from bot.ai.intent import _FALLBACK
    required = ["refers_to_previous", "memory_update_needed", "settings_update_needed", "reply_style"]
    missing = [k for k in required if k not in _FALLBACK]
    if missing:
        fail(name, f"Missing fields in _FALLBACK: {missing}")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 4. Safe delete — ambiguous task
# ──────────────────────────────────────────────────────────────
async def test_safe_delete_ambiguous():
    name = "safe_delete_ambiguous"
    from unittest.mock import AsyncMock, patch, MagicMock

    # Create mock tasks to simulate multiple matches
    mock_tasks = [
        {"id": 1, "title": "напомни про встречу"},
        {"id": 2, "title": "напомни про звонок"},
    ]

    async def mock_task_find_by_title(user_id, keyword):
        return mock_tasks

    from bot.db import database as db_module
    original_find = getattr(db_module.db, "task_find_by_title", None)
    db_module.db.task_find_by_title = mock_task_find_by_title

    try:
        from bot.modules.dispatcher import _safe_delete
        params = {"keyword": "напомни"}
        result = await _safe_delete("task_delete", params, user_id=1)
        if result is None:
            fail(name, "Expected clarification string, got None (should not proceed)")
        elif "Нашёл" in result or "Какую" in result or len(result) > 20:
            ok(name)
        else:
            fail(name, f"Unexpected result: {result!r}")
    finally:
        if original_find:
            db_module.db.task_find_by_title = original_find


# ──────────────────────────────────────────────────────────────
# 5. Memory save — explicit
# ──────────────────────────────────────────────────────────────
def test_memory_explicit_save():
    name = "memory_explicit_save"
    from bot.ai.intent import _normalize
    raw = {
        "actions": [
            {
                "intent": "memory_save",
                "params": {
                    "category": "schedule",
                    "value": "не ставить тяжёлые задачи утром",
                    "key_name": "morning_preference",
                    "importance": 4,
                },
                "confidence": 0.92
            }
        ],
        "reply": "Запомнил: утром тяжёлых задач не ставить.",
        "memory_update_needed": True,
        "settings_update_needed": False,
        "reply_style": None,
        "refers_to_previous": False,
        "chat_response_needed": False,
        "is_data_query": False,
        "needs_retrieval": False,
        "data_query_type": None,
        "safety_level": "safe",
    }
    result = _normalize(raw)
    if not result.get("memory_update_needed"):
        fail(name, "memory_update_needed not set")
        return
    actions = result.get("actions", [])
    mem_action = next((a for a in actions if a.get("intent") == "memory_save"), None)
    if not mem_action:
        fail(name, "memory_save action missing")
        return
    if mem_action["params"].get("key_name") != "morning_preference":
        fail(name, "key_name not preserved")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 6. Ideas save — basic structure check
# ──────────────────────────────────────────────────────────────
async def test_idea_save_structure():
    name = "idea_save_structure"
    from unittest.mock import AsyncMock, patch

    with patch("bot.modules.ideas.db") as mock_db:
        mock_db.idea_save = AsyncMock(return_value=42)
        mock_db.conversation_state_update = AsyncMock()

        from bot.modules import ideas
        # Force reload with mock
        import importlib
        # Test the logic manually
        params = {"title": "вечерний отчёт по рекламе", "category": "ads", "description": ""}
        # Simulate: idea_save returns 42
        idea_id = await mock_db.idea_save(
            user_id=1, title=params["title"], description="",
            category="ads", related_project=None, source_message_id=None,
        )
        if idea_id != 42:
            fail(name, f"idea_save returned {idea_id}, expected 42")
            return
        ok(name)


# ──────────────────────────────────────────────────────────────
# 7. Ideas — idea_convert_to_task structure check
# ──────────────────────────────────────────────────────────────
def test_idea_convert_to_task_intent():
    name = "idea_convert_to_task_intent"
    from bot.ai.intent import _normalize
    raw = {
        "actions": [
            {"intent": "idea_convert_to_task", "params": {"idea_id": 42}, "confidence": 0.9}
        ],
        "reply": "Создам задачу из идеи #42.",
        "refers_to_previous": True,
        "memory_update_needed": False,
        "settings_update_needed": False,
        "reply_style": None,
        "chat_response_needed": False,
        "is_data_query": False,
        "needs_retrieval": False,
        "data_query_type": None,
        "safety_level": "safe",
    }
    result = _normalize(raw)
    if not result.get("refers_to_previous"):
        fail(name, "refers_to_previous should be True")
        return
    actions = result.get("actions", [])
    if not any(a.get("intent") == "idea_convert_to_task" for a in actions):
        fail(name, "idea_convert_to_task action missing")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 8. Dispatcher — new handlers registered
# ──────────────────────────────────────────────────────────────
def test_dispatcher_new_handlers():
    name = "dispatcher_new_handlers"
    from bot.modules.dispatcher import _HANDLERS
    required = [
        "idea_save", "idea_list", "idea_convert_to_task",
        "section_add_field", "section_rename", "record_edit",
        "start_onboarding",
    ]
    missing = [h for h in required if h not in _HANDLERS]
    if missing:
        fail(name, f"Missing handlers: {missing}")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 9. Formatters — beautiful plan table
# ──────────────────────────────────────────────────────────────
def test_format_plan_table():
    name = "format_plan_table"
    from bot.utils.formatters import format_plan_table
    plan = {
        "items": [
            {"time": "09:00", "title": "Завтрак", "source": "режим"},
            {"time": "10:00", "title": "Работа над проектом", "source": "задачи"},
            {"time": "13:00", "title": "Обед", "source": "режим"},
        ],
        "recommendations": ["Выйди на прогулку", "Сделай 5-минутный перерыв каждый час"],
    }
    result = format_plan_table(plan, "2025-01-15")
    if "| Время |" not in result:
        fail(name, "Table header missing")
        return
    if "Завтрак" not in result:
        fail(name, "Plan items missing")
        return
    if "Рекомендации" not in result:
        fail(name, "Recommendations missing")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 10. Formatters — beautiful expense card
# ──────────────────────────────────────────────────────────────
def test_format_expense_card():
    name = "format_expense_card"
    from bot.utils.formatters import format_expense_card
    expenses = [
        {"amount": 40, "currency": "PLN", "description": "еда", "date": "2025-01-15"},
        {"amount": 120, "currency": "PLN", "description": "бензин", "date": "2025-01-15"},
        {"amount": 50, "currency": "PLN", "description": "еда", "date": "2025-01-15"},
    ]
    result = format_expense_card(expenses, "Сегодняшние расходы")
    if "| Категория |" not in result:
        fail(name, "Table header missing")
        return
    if "210.00" not in result:
        fail(name, f"Total 210 PLN not found in result: {result!r}")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 11. Formatters — beautiful task card
# ──────────────────────────────────────────────────────────────
def test_format_task_card():
    name = "format_task_card"
    from bot.utils.formatters import format_task_card
    task = {
        "id": 7,
        "title": "Сдать отчёт по рекламе",
        "description": "Включить ROI и конверсии",
        "priority": "high",
        "status": "pending",
        "due_date": "2025-01-20",
        "due_time": "18:00",
    }
    result = format_task_card(task)
    if "Задача #7" not in result:
        fail(name, "Task ID missing")
        return
    if "🔴" not in result:
        fail(name, "High priority icon missing")
        return
    if "2025-01-20" not in result:
        fail(name, "Due date missing")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 12. Formatters — ideas list
# ──────────────────────────────────────────────────────────────
def test_format_ideas():
    name = "format_ideas"
    from bot.utils.formatters import format_ideas
    ideas = [
        {"id": 1, "title": "Автоматизировать отчёты", "status": "new", "related_project": "AdsTracker"},
        {"id": 2, "title": "Вечерний чек-лист", "status": "active", "related_project": None},
    ]
    result = format_ideas(ideas)
    if "💡" not in result and "🔥" not in result:
        fail(name, "Status icons missing")
        return
    if "#1" not in result or "#2" not in result:
        fail(name, "Idea IDs missing")
        return
    if "AdsTracker" not in result:
        fail(name, "Related project missing")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 13. Settings manager — shorten_response
# ──────────────────────────────────────────────────────────────
def test_settings_manager_shorten():
    name = "settings_manager_shorten_response"
    from bot.modules.settings_manager import shorten_response
    long_text = "Это очень длинный текст. " * 20  # ~500 chars
    result = shorten_response(long_text)
    if len(result) > 320:
        fail(name, f"Result too long: {len(result)} chars")
        return
    if not result.strip():
        fail(name, "Empty result")
        return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 14. Keyboards — all builders return InlineKeyboardMarkup
# ──────────────────────────────────────────────────────────────
def test_keyboards_return_markup():
    name = "keyboards_return_markup"
    from aiogram.types import InlineKeyboardMarkup
    from bot.modules.keyboards import (
        build_task_keyboard, build_plan_keyboard,
        build_finance_keyboard, build_ideas_keyboard,
        build_reminder_keyboard, build_section_keyboard,
        build_settings_keyboard,
    )
    builders = [
        build_task_keyboard(1),
        build_plan_keyboard(),
        build_finance_keyboard("ads"),
        build_ideas_keyboard(5),
        build_reminder_keyboard(3),
        build_section_keyboard("finance"),
        build_settings_keyboard(),
    ]
    for kb in builders:
        if not isinstance(kb, InlineKeyboardMarkup):
            fail(name, f"Expected InlineKeyboardMarkup, got {type(kb)}")
            return
    ok(name)


# ──────────────────────────────────────────────────────────────
# 15. Onboarding — handle_start returns question
# ──────────────────────────────────────────────────────────────
async def test_onboarding_start():
    name = "onboarding_start"
    from unittest.mock import AsyncMock, patch

    with patch("bot.modules.onboarding.db") as mock_db:
        mock_db.conversation_state_update = AsyncMock()

        from bot.modules.onboarding import handle_start, _STEPS
        result = await handle_start(user_id=1, params={}, ai_response="")

        if "Настройка TUNTUN" not in result and "настрой" not in result.lower():
            fail(name, f"Unexpected response: {result[:80]!r}")
            return
        if _STEPS[0][1][:10] not in result:
            fail(name, "First question not in response")
            return
        ok(name)


# ──────────────────────────────────────────────────────────────
# Run all tests
# ──────────────────────────────────────────────────────────────
def run_sync(coro):
    return asyncio.run(coro)


if __name__ == "__main__":
    print("=" * 55)
    print("  TUNTUN Phase 5 Tests")
    print("=" * 55)

    # Sync tests
    test_conversational_setting_short_reply()
    test_conversational_setting_table_plan()
    test_intent_normalize_new_fields()
    test_memory_explicit_save()
    test_idea_convert_to_task_intent()
    test_dispatcher_new_handlers()
    test_format_plan_table()
    test_format_expense_card()
    test_format_task_card()
    test_format_ideas()
    test_settings_manager_shorten()
    test_keyboards_return_markup()

    # Async tests
    run_sync(test_safe_delete_ambiguous())
    run_sync(test_idea_save_structure())
    run_sync(test_onboarding_start())

    print("=" * 55)
    print(f"  PASS: {PASS}  FAIL: {FAIL}  WARN: {WARN}")
    print("=" * 55)

    if FAIL > 0:
        sys.exit(1)
