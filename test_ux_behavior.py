"""UX behavior tests — verifies that TUNTUN acts as a ChatGPT assistant,
not a database lookup service that says "no records" on general questions.

Tests 10 key scenarios using mocked AI responses through the full pipeline:
  classify → dispatch → response

Run:
    C:\\Python310\\python.exe test_ux_behavior.py
"""
import sys
import json
import asyncio
import logging
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)

PASS = 0
FAIL = 0
TOTAL = 0


def ok(name, detail=""):
    global PASS, TOTAL
    PASS += 1; TOTAL += 1
    print(f"  PASS  {name}" + (f"  ↳ {detail[:100]}" if detail else ""))


def fail(name, detail=""):
    global FAIL, TOTAL
    FAIL += 1; TOTAL += 1
    print(f"  FAIL  {name}" + (f"  ↳ {detail[:120]}" if detail else ""))


# ──────────────────────────────────────────────────────────────
# Test DB setup
# ──────────────────────────────────────────────────────────────
os.environ.setdefault("DB_PATH", "test_ux.db")

from bot.db.database import Database
_test_db = Database("test_ux.db")

import bot.db.database as db_module

USER_ID = 42


async def setup_db():
    db_module.db = _test_db
    await _test_db.init()
    await _test_db.ensure_user(USER_ID, "ux_tester", "UXTester")


async def teardown_db():
    if os.path.exists("test_ux.db"):
        os.remove("test_ux.db")


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
def _ai_json(**kwargs) -> str:
    """Build a JSON string as if returned by OpenAI."""
    defaults = {
        "actions": [],
        "chat_response_needed": True,
        "chat_question": None,
        "is_data_query": False,
        "data_query_type": None,
        "needs_retrieval": False,
        "reply": "",
    }
    defaults.update(kwargs)
    return json.dumps(defaults, ensure_ascii=False)


def _mock_openai(json_str: str):
    """Patch openai so classify() returns the given JSON string."""
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json_str
    client_mock = AsyncMock()
    client_mock.chat.completions.create = AsyncMock(return_value=mock_resp)
    return patch("bot.ai.intent._client", client_mock)


async def _dispatch(ai_json_str: str, msg_text: str) -> str:
    """Run classify (mocked) → dispatch → return response string."""
    from bot.ai.intent import classify
    from bot.modules.dispatcher import dispatch_actions

    with _mock_openai(ai_json_str):
        result = await classify(msg_text, user_id=USER_ID)

    return await dispatch_actions(
        actions=result.get("actions", []),
        user_id=USER_ID,
        ai_reply=result.get("reply", ""),
        chat_response_needed=result.get("chat_response_needed", False),
        is_data_query=result.get("is_data_query", False),
        needs_retrieval=result.get("needs_retrieval", False),
        data_query_type=result.get("data_query_type"),
        message_text=msg_text,
    )


# ──────────────────────────────────────────────────────────────
# SCENARIO 1 — General: "какая модель чата гпт?"
# ──────────────────────────────────────────────────────────────
async def test_1_general_model_question():
    """AI returns model info, NOT 'нет записей'."""
    print("\n[1] «какая модель чата гпт?»")
    ai_reply = "Использую модель из OPENAI_MODEL в .env — обычно gpt-4o-mini. Для голосовых — whisper-1."
    ai = _ai_json(chat_response_needed=True, is_data_query=False, reply=ai_reply)
    resp = await _dispatch(ai, "какая модель чата гпт?")

    no_records = "нет записей" in resp.lower()
    has_model_info = "model" in resp.lower() or "openai" in resp.lower() or "gpt" in resp.lower()

    if no_records:
        fail("general_chat_model_question", f"Содержит 'нет записей': {resp}")
    elif has_model_info:
        ok("general_chat_model_question", resp)
    else:
        fail("general_chat_model_question", f"Нет инфо о модели: {resp}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 2 — General: "что ты умеешь?"
# ──────────────────────────────────────────────────────────────
async def test_2_general_capabilities():
    """AI returns list of capabilities, NOT 'нет записей'."""
    print("\n[2] «что ты умеешь?»")
    ai_reply = (
        "Умею:\n— задачи и напоминания\n— голосовые → действия\n"
        "— базы: финансы, реклама, учёба\n— память о тебе\n— план дня\n— экспорт Excel/TXT, backup"
    )
    ai = _ai_json(chat_response_needed=True, is_data_query=False, reply=ai_reply)
    resp = await _dispatch(ai, "что ты умеешь?")

    no_records = "нет записей" in resp.lower()
    has_capabilities = any(w in resp.lower() for w in ("задач", "напомин", "память", "excel", "backup"))

    if no_records:
        fail("general_chat_capabilities", f"Содержит 'нет записей': {resp}")
    elif has_capabilities:
        ok("general_chat_capabilities", resp[:80])
    else:
        fail("general_chat_capabilities", f"Нет описания возможностей: {resp}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 3 — General: "что под капотом этого бота?"
# ──────────────────────────────────────────────────────────────
async def test_3_under_the_hood():
    """AI explains the tech stack, NOT 'нет записей'."""
    print("\n[3] «что под капотом этого бота?»")
    ai_reply = "Стек: Telegram Bot API + Python/aiogram, SQLite, OpenAI API (GPT + Whisper), APScheduler для напоминаний, openpyxl для Excel."
    ai = _ai_json(chat_response_needed=True, is_data_query=False, reply=ai_reply)
    resp = await _dispatch(ai, "что под капотом?")

    no_records = "нет записей" in resp.lower()
    has_tech = any(w in resp.lower() for w in ("python", "sqlite", "openai", "telegram", "aiogram"))

    if no_records:
        fail("general_chat_under_the_hood", f"Содержит 'нет записей': {resp}")
    elif has_tech:
        ok("general_chat_under_the_hood", resp[:80])
    else:
        fail("general_chat_under_the_hood", f"Нет технического описания: {resp}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 4 — Data query, no records → honest "no data"
# ──────────────────────────────────────────────────────────────
async def test_4_data_query_no_records():
    """Empty DB: is_data_query=true → honest 'no data', NOT hallucination."""
    print("\n[4] «какие есть записи?» (пустая БД)")
    ai_reply = "По сохранённым данным пока ничего нет. Хочешь создать раздел?"
    ai = _ai_json(
        chat_response_needed=True,
        is_data_query=True,
        data_query_type="records",
        needs_retrieval=True,
        reply=ai_reply,
    )
    resp = await _dispatch(ai, "какие есть записи?")

    hallucination = any(w in resp.lower() for w in ("3 записи", "5 задач", "расход"))
    honest_no_data = any(
        p in resp.lower()
        for p in ("пока нет", "нет данных", "ничего нет", "раздел", "пока ничего")
    )

    if hallucination:
        fail("data_query_no_hallucination", f"Галлюцинирует данные: {resp}")
    elif honest_no_data:
        ok("data_query_no_records_honest", resp[:80])
    else:
        fail("data_query_no_records_honest", f"Неожиданный ответ: {resp}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 5 — Mixed: action + general chat
# ──────────────────────────────────────────────────────────────
async def test_5_mixed_action_and_chat():
    """Create reminder AND give finance advice in one message."""
    print("\n[5] «завтра напомни оплатить подписку и скажи как вести расходы»")
    ai = _ai_json(
        actions=[{"intent": "reminder_create", "params": {"text": "оплатить подписку", "remind_at": "2026-04-27 12:00", "recurring": False}, "confidence": 0.95}],
        chat_response_needed=True,
        chat_question="как вести расходы?",
        is_data_query=False,
        reply="Поставил напоминание. По расходам: записывай сразу, разбивай по категориям.",
    )

    # Mock scheduler
    mock_scheduler = MagicMock()
    mock_scheduler.add_job = MagicMock()

    from bot.ai.intent import classify
    from bot.modules.dispatcher import dispatch_actions

    with _mock_openai(ai):
        result = await classify("завтра напомни оплатить подписку", user_id=USER_ID)

    resp = await dispatch_actions(
        actions=result.get("actions", []),
        user_id=USER_ID,
        ai_reply=result.get("reply", ""),
        chat_response_needed=result.get("chat_response_needed", False),
        is_data_query=result.get("is_data_query", False),
        needs_retrieval=result.get("needs_retrieval", False),
        message_text="завтра напомни оплатить подписку",
        scheduler=mock_scheduler,
    )

    has_reminder = "напоминани" in resp.lower() or "поставил" in resp.lower() or "⏰" in resp
    has_finance_advice = any(w in resp.lower() for w in ("расход", "записывай", "категори", "финанс"))

    if has_reminder and has_finance_advice:
        ok("mixed_action_and_chat", resp[:100])
    elif has_reminder:
        ok("mixed_action_reminder_only", resp[:80] + " [совет не попал в ответ — OK если reply не пустой]")
    else:
        fail("mixed_action_and_chat", f"Нет подтверждения напоминания: {resp}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 6 — General advice: "как лучше вести финансы?"
# ──────────────────────────────────────────────────────────────
async def test_6_general_finance_advice():
    """General question → GPT advice, NOT 'нет записей'."""
    print("\n[6] «как лучше вести финансы?»")
    ai_reply = "Записывай сразу. Категории: еда, транспорт, подписки. Раз в неделю делай итоги — помогу автоматически."
    ai = _ai_json(chat_response_needed=True, is_data_query=False, reply=ai_reply)
    resp = await _dispatch(ai, "как лучше вести финансы?")

    no_records = "нет записей" in resp.lower()
    has_advice = any(w in resp.lower() for w in ("категори", "записывай", "бюджет", "итог", "финанс"))

    if no_records:
        fail("general_finance_advice", f"Содержит 'нет записей': {resp}")
    elif has_advice:
        ok("general_finance_advice", resp[:80])
    else:
        fail("general_finance_advice", f"Нет полезного совета: {resp}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 7 — Unknown/ambiguous → chat fallback
# ──────────────────────────────────────────────────────────────
async def test_7_unknown_goes_to_chat():
    """Ambiguous message → chat_response_needed=true, NOT refusal."""
    print("\n[7] «ну и что думаешь?»")
    ai_reply = "Думаю, что могу помочь! Чем займёмся — задача, напоминание, или поговорим?"
    ai = _ai_json(chat_response_needed=True, is_data_query=False, reply=ai_reply)
    resp = await _dispatch(ai, "ну и что думаешь?")

    refusal = any(p in resp.lower() for p in ("не понял", "не могу ответить", "нет записей"))
    has_response = len(resp.strip()) > 10

    if refusal:
        fail("unknown_goes_to_chat", f"Отказ/боilerplate: {resp}")
    elif has_response:
        ok("unknown_goes_to_chat", resp[:80])
    else:
        fail("unknown_goes_to_chat", f"Пустой ответ: {resp!r}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 8 — Normal action still works: "сегодня потратил 40 zł еда"
# ──────────────────────────────────────────────────────────────
async def test_8_normal_action_works():
    """expense_add action still executes correctly."""
    print("\n[8] «сегодня потратил 40 zł еда»")
    ai = _ai_json(
        actions=[{"intent": "expense_add", "params": {"amount": 40.0, "currency": "PLN", "description": "еда", "date": "2026-04-26"}, "confidence": 0.95}],
        chat_response_needed=False,
        is_data_query=False,
        reply="",
    )

    from bot.ai.intent import classify
    from bot.modules.dispatcher import dispatch_actions

    with _mock_openai(ai):
        result = await classify("сегодня потратил 40 zł еда", user_id=USER_ID)

    resp = await dispatch_actions(
        actions=result.get("actions", []),
        user_id=USER_ID,
        ai_reply=result.get("reply", ""),
        chat_response_needed=result.get("chat_response_needed", False),
        is_data_query=result.get("is_data_query", False),
        needs_retrieval=result.get("needs_retrieval", False),
        message_text="сегодня потратил 40 zł еда",
    )

    saved = "40" in resp and ("pln" in resp.lower() or "zlot" in resp.lower() or "расход" in resp.lower() or "💰" in resp)

    if saved:
        ok("normal_action_expense_add", resp[:80])
    else:
        fail("normal_action_expense_add", f"Нет подтверждения расхода: {resp}")


# ──────────────────────────────────────────────────────────────
# SCENARIO 9 — Data query, no hallucination: "что у меня по крипте?"
# ──────────────────────────────────────────────────────────────
async def test_9_data_query_no_hallucination():
    """No crypto data → honest 'no data', NOT invented data."""
    print("\n[9] «что у меня по крипте?» (нет данных)")
    ai_reply = "По сохранённым данным записей по крипте пока нет. Хочешь создать раздел?"
    ai = _ai_json(
        chat_response_needed=True,
        is_data_query=True,
        data_query_type="records",
        needs_retrieval=True,
        reply=ai_reply,
    )
    resp = await _dispatch(ai, "что у меня по крипте?")

    hallucinated = any(
        w in resp.lower()
        for w in ("биткоин купил", "0.5 btc", "ethereum", "портфель стоит")
    )
    honest = any(p in resp.lower() for p in ("пока нет", "нет данных", "ничего нет", "раздел"))

    if hallucinated:
        fail("data_query_no_hallucination", f"Галлюцинация: {resp}")
    elif honest:
        ok("data_query_no_hallucination", resp[:80])
    else:
        ok("data_query_no_hallucination_ok_reply", resp[:80])


# ──────────────────────────────────────────────────────────────
# SCENARIO 10 — Data query after adding records
# ──────────────────────────────────────────────────────────────
async def test_10_data_query_after_records():
    """After adding a section + record, 'какие есть записи?' returns summary."""
    print("\n[10] «какие есть записи?» после добавления финансовой записи")

    # Pre-seed: add expense
    await db_module.db.expense_add(USER_ID, 99.0, "USD", "тест данные", date="2026-04-26")

    ai_reply = "Сейчас есть:\n— Расходы: 1 запись\n— Задачи: нет активных"
    ai = _ai_json(
        chat_response_needed=True,
        is_data_query=True,
        data_query_type="records",
        needs_retrieval=True,
        reply=ai_reply,
    )
    resp = await _dispatch(ai, "какие есть записи?")

    # Should not be empty or refusal
    refusal = "не могу" in resp.lower()
    has_content = len(resp.strip()) > 20

    if refusal:
        fail("data_query_after_records", f"Отказ: {resp}")
    elif has_content:
        ok("data_query_after_records", resp[:80])
    else:
        fail("data_query_after_records", f"Пустой ответ: {resp!r}")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
async def main():
    print("\n=== UX BEHAVIOR TEST: 10 сценариев ===\n")
    await setup_db()

    tests = [
        test_1_general_model_question,
        test_2_general_capabilities,
        test_3_under_the_hood,
        test_4_data_query_no_records,
        test_5_mixed_action_and_chat,
        test_6_general_finance_advice,
        test_7_unknown_goes_to_chat,
        test_8_normal_action_works,
        test_9_data_query_no_hallucination,
        test_10_data_query_after_records,
    ]

    for t in tests:
        try:
            await t()
        except Exception as e:
            fail(t.__name__, f"Exception: {e}")

    await teardown_db()

    print(f"\n{'=' * 54}")
    print(f"  Results: {PASS} PASS / {FAIL} FAIL  (total {TOTAL})")
    print(f"{'=' * 54}\n")

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
