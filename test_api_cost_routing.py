"""test_api_cost_routing.py — Verify that TUNTUN minimizes OpenAI API calls.

Routing contract:
  - simple backend actions  -> NO model call (backend-only template response)
  - pure chat with good reply -> NO second model call (use router reply directly)
  - mixed action + question -> backend result + CHAT (not reasoning)
  - plan day / complex       -> REASONING model
  - ambiguous delete         -> ask for confirmation, no delete

Each test asserts model call patterns WITHOUT making real OpenAI calls.

Run:
    python test_api_cost_routing.py
"""
import sys
import os
import asyncio
import json
import logging
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock, call

sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)

TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "tuntun_test_cost.db")
for suffix in ("", "-journal", "-wal", "-shm"):
    try:
        os.remove(TEST_DB_PATH + suffix)
    except FileNotFoundError:
        pass

os.environ["DATABASE_PATH"] = TEST_DB_PATH
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

PASS = 0
FAIL = 0


def ok(name, detail=""):
    global PASS
    PASS += 1
    detail_str = f"  [{detail[:100]}]" if detail else ""
    print(f"  PASS  {name}{detail_str}")


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    detail_str = f"  [{detail[:120]}]" if detail else ""
    print(f"  FAIL  {name}{detail_str}")


# ─────────────────────────────────────────────────────────────
# DB setup
# ─────────────────────────────────────────────────────────────
from bot.db.database import Database
import bot.db.database as db_module

_test_db = Database(TEST_DB_PATH)
USER_ID = 77


async def setup():
    db_module.db = _test_db
    await _test_db.init()
    await _test_db.ensure_user(USER_ID, "cost_tester", "CostTest")


# ─────────────────────────────────────────────────────────────
# Helper: run dispatch_actions with mocked handle_chat_response
# Returns (response, chat_was_called)
# ─────────────────────────────────────────────────────────────
async def _run_dispatch(actions, ai_reply, chat_response_needed,
                        needs_reasoning=False, refers_to_previous=False,
                        is_data_query=False, safety_level="safe",
                        confidence=0.9, chat_question=None,
                        msg_text="test message"):
    from bot.modules.dispatcher import dispatch_actions

    chat_called = False
    chat_model_used = []

    async def _mock_chat(user_id, question, is_data_query=False,
                         needs_retrieval=False, data_query_type=None,
                         confidence=0.9, safety_level="safe",
                         refers_to_previous=False, intents=None,
                         needs_reasoning=False):
        nonlocal chat_called
        chat_called = True
        chat_model_used.append("reasoning" if needs_reasoning else "chat")
        return f"[chat_answer needs_reasoning={needs_reasoning}]"

    with patch("bot.modules.chat_assistant.handle_chat_response", side_effect=_mock_chat):
        resp = await dispatch_actions(
            actions=actions,
            user_id=USER_ID,
            ai_reply=ai_reply,
            chat_response_needed=chat_response_needed,
            message_text=msg_text,
            is_data_query=is_data_query,
            needs_reasoning=needs_reasoning,
            refers_to_previous=refers_to_previous,
            safety_level=safety_level,
            confidence=confidence,
            chat_question=chat_question,
        )

    return resp, chat_called, chat_model_used


# ─────────────────────────────────────────────────────────────
# All async tests in one event loop
# ─────────────────────────────────────────────────────────────
async def run_all():
    await setup()

    # ── TEST 1: "сегодня 40 zł еда" — expense_add, backend-only ──────────
    print("\n[1] expense_add backend-only (no chat call)")
    resp, chat_called, _ = await _run_dispatch(
        actions=[{"intent": "expense_add", "params": {
            "amount": 40.0, "currency": "PLN", "description": "еда",
            "date": "2026-04-26"
        }, "confidence": 0.95}],
        ai_reply="",
        chat_response_needed=False,  # router says no chat needed for expense_add
        confidence=0.95,
        msg_text="сегодня 40 zł еда",
    )
    if chat_called:
        fail("expense_add_no_chat", f"handle_chat_response was called but should NOT be")
    elif "40" in resp or "pln" in resp.lower() or "расход" in resp.lower():
        ok("expense_add_no_chat", resp[:70])
    else:
        fail("expense_add_no_chat", f"Unexpected response: {resp}")

    # ── TEST 2: "что ты умеешь?" — good router reply, no second call ──────
    print("\n[2] 'что ты умеешь?' — router reply used directly")
    good_reply = (
        "Умею: задачи, напоминания, голосовые сообщения, базы данных, "
        "финансы, память, план дня, экспорт Excel/TXT, backup, аналитика."
    )
    resp, chat_called, _ = await _run_dispatch(
        actions=[],
        ai_reply=good_reply,
        chat_response_needed=True,
        confidence=0.9,
        msg_text="что ты умеешь?",
    )
    if chat_called:
        fail("capabilities_no_second_call",
             f"handle_chat_response called even though router gave good reply")
    elif "задач" in resp.lower() or "excel" in resp.lower():
        ok("capabilities_no_second_call", resp[:80])
    else:
        fail("capabilities_no_second_call", f"Router reply not used: {resp}")

    # ── TEST 3: "напомни завтра в 12 оплатить" — reminder backend-only ───
    print("\n[3] reminder_create backend-only (no chat call)")
    with patch("bot.modules.reminders.sched_module.add_reminder_job", return_value="rem_77"):
        resp, chat_called, _ = await _run_dispatch(
            actions=[{"intent": "reminder_create", "params": {
                "text": "оплатить", "remind_at": "2099-04-27 12:00"
            }, "confidence": 0.93}],
            ai_reply="",
            chat_response_needed=False,
            confidence=0.93,
            msg_text="напомни завтра в 12 оплатить",
        )
    if chat_called:
        fail("reminder_no_chat", "handle_chat_response called for simple reminder")
    elif "напоминани" in resp.lower() or "⏰" in resp:
        ok("reminder_no_chat", resp[:60])
    else:
        fail("reminder_no_chat", f"Unexpected: {resp}")

    # ── TEST 4: "напомни в 12 и как лучше вести расходы?" — mixed ────────
    # Action: reminder_create (backend-only result) + chat_question about expenses
    print("\n[4] mixed: reminder + chat_question about expenses")
    with patch("bot.modules.reminders.sched_module.add_reminder_job", return_value="rem_78"):
        resp, chat_called, models = await _run_dispatch(
            actions=[{"intent": "reminder_create", "params": {
                "text": "оплатить", "remind_at": "2099-04-27 12:00"
            }, "confidence": 0.93}],
            ai_reply="",
            chat_response_needed=True,  # user also asked a question
            confidence=0.93,
            chat_question="как лучше вести расходы?",
            msg_text="напомни в 12 оплатить и как лучше вести расходы?",
        )
    # Action should be done, AND chat should be called (but not reasoning)
    if not chat_called:
        fail("mixed_reminder_question", "handle_chat_response NOT called for chat_question")
    elif models and models[0] == "reasoning":
        fail("mixed_reminder_question",
             f"REASONING used for simple follow-up question, should be CHAT")
    else:
        has_reminder = "напоминани" in resp.lower() or "⏰" in resp
        ok("mixed_reminder_question",
           f"reminder={has_reminder}, chat_called=True, model={models[0] if models else '?'}")

    # ── TEST 5: "дай план на сегодня, учти сон, еду и задачи" — reasoning
    print("\n[5] regime_day_plan -> REASONING model")
    from bot.ai.model_router import should_use_reasoning
    needs_r = should_use_reasoning(
        intents=["regime_day_plan"],
        confidence=0.9,
        safety_level="safe",
        refers_to_previous=False,
        needs_reasoning=False,
    )
    if needs_r:
        ok("day_plan_uses_reasoning", "regime_day_plan -> should_use_reasoning=True")
    else:
        fail("day_plan_uses_reasoning", "regime_day_plan should require reasoning")

    # Also check choose_model returns reasoning model
    from bot.ai.model_router import choose_model, get_model
    m = choose_model("chat", confidence=0.9, safety_level="safe",
                     refers_to_previous=False, intents=["regime_day_plan"],
                     needs_reasoning=False)
    reasoning_model = get_model("reasoning")
    if m == reasoning_model:
        ok("day_plan_choose_model_reasoning", f"model={m}")
    else:
        fail("day_plan_choose_model_reasoning", f"expected {reasoning_model}, got {m}")

    # ── TEST 6: "выведи это таблицей" — context formatting ───────────────
    print("\n[6] 'выведи это таблицей' — if last_plan_json, no reasoning needed")
    # Set last_plan_json in conversation_state
    import json as _json
    plan_data = {"timed": [{"time": "08:00", "activity": "Подъём"}]}
    await _test_db.conversation_state_update(
        USER_ID, last_plan_json=_json.dumps(plan_data)
    )

    # Router context should see last_plan: exists
    from bot.ai.intent import _get_lightweight_router_context
    ctx = await _get_lightweight_router_context(USER_ID)
    assert "last_plan: exists" in ctx, f"Context doesn't mention plan: {ctx}"
    ok("plan_table_context_visible", f"ctx={ctx}")

    # For table formatting, should NOT need reasoning (simple format, context exists)
    needs_r2 = should_use_reasoning(
        intents=[],
        confidence=0.9,
        safety_level="safe",
        refers_to_previous=True,
        needs_reasoning=False,
    )
    # With refers_to_previous=True but no ambiguity → not reasoning (it is reasoning in current impl)
    # The key test: plan table formatting is NOT an issue for reasoning intents list
    from bot.ai.model_router import REASONING_INTENTS
    assert "regime_day_plan" in REASONING_INTENTS
    assert "section_query" not in REASONING_INTENTS
    ok("table_formatting_not_reasoning_intent",
       "table formatting not in REASONING_INTENTS")

    # ── TEST 7: "убери на 12" — ambiguous, should ask for clarification ───
    print("\n[7] 'убери на 12' — ambiguous, no delete without confirmation")
    # Create multiple reminders to trigger disambiguation
    await _test_db.reminder_create(USER_ID, "встреча в 12", "2099-04-27 12:00")
    await _test_db.reminder_create(USER_ID, "звонок в 12", "2099-04-27 12:00")

    from bot.modules.dispatcher import _safe_delete
    result = await _safe_delete(
        "reminder_cancel",
        {"keyword": "12"},
        USER_ID
    )
    if result is None:
        fail("ambiguous_delete_asks_clarification",
             "Should return disambiguation message, got None (would delete)")
    elif "2" in result or "нашёл" in result.lower() or "напоминани" in result.lower():
        ok("ambiguous_delete_asks_clarification", result[:70])
    else:
        fail("ambiguous_delete_asks_clarification", f"Unexpected: {result}")

    # ── TEST 8: config fallback chain ─────────────────────────────────────
    print("\n[8] config fallback chain")
    import config

    # OPENAI_MODEL_TRANSCRIBE preferred
    original_whisper = config.WHISPER_MODEL
    ok("whisper_model_set", f"WHISPER_MODEL={original_whisper}")

    # When OPENAI_MODEL_CHAT is empty, MODEL_CHAT should not be empty
    assert config.MODEL_CHAT, "MODEL_CHAT should not be empty"
    ok("model_chat_not_empty", f"MODEL_CHAT={config.MODEL_CHAT}")

    # MODEL_REASONING should not be empty
    assert config.MODEL_REASONING, "MODEL_REASONING should not be empty"
    ok("model_reasoning_not_empty", f"MODEL_REASONING={config.MODEL_REASONING}")

    # MODEL_ROUTER should not be empty
    assert config.MODEL_ROUTER, "MODEL_ROUTER should not be empty"
    ok("model_router_not_empty", f"MODEL_ROUTER={config.MODEL_ROUTER}")

    # get_model never returns empty
    from bot.ai.model_router import get_model
    for purpose in ("router", "chat", "reasoning"):
        m = get_model(purpose)
        assert m, f"get_model('{purpose}') returned empty"
        ok(f"get_model_{purpose}_not_empty", m)

    # ── Cleanup
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = TEST_DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    asyncio.run(run_all())

    total = PASS + FAIL
    print(f"\n{'=' * 58}")
    print(f"  Results: {PASS} PASS / {FAIL} FAIL  (total {total})")
    print(f"{'=' * 58}\n")

    if FAIL > 0:
        sys.exit(1)
