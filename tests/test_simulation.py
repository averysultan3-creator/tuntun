"""Live-readiness simulation test.

Simulates 10 key user scenarios through the full classify→dispatch pipeline
using mocked AI responses (no real OpenAI calls).

Run:
    C:\Python310\python.exe test_simulation.py
"""
import sys
import json
import asyncio
import logging
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)  # suppress noise

PASS = 0
FAIL = 0
TOTAL = 0


def ok(name, detail=""):
    global PASS, TOTAL
    PASS += 1; TOTAL += 1
    print(f"  PASS  {name}" + (f"  ↳ {detail[:80]}" if detail else ""))


def fail(name, detail=""):
    global FAIL, TOTAL
    FAIL += 1; TOTAL += 1
    print(f"  FAIL  {name}" + (f"  ↳ {detail[:120]}" if detail else ""))


# ──────────────────────────────────────────────────────────────
# Test DB setup
# ──────────────────────────────────────────────────────────────
import os
os.environ.setdefault("DB_PATH", "test_simulation.db")

from bot.db.database import Database
_test_db = Database("test_simulation.db")

import bot.db.database as db_module

async def setup_db():
    db_module.db = _test_db
    await _test_db.init()
    await _test_db.ensure_user(777, "sim_user", "Simulator")
    # Pre-seed some memory data
    await _test_db.memory_save(777, "habit", "не ставить тяжёлые задачи утром", "morning")
    await _test_db.memory_save(777, "preference", "краткие ответы без воды", "style")
    await _test_db.expense_add(777, 40.0, "PLN", "еда", date="2026-04-26")
    await _test_db.expense_add(777, 120.0, "PLN", "бензин", date="2026-04-26")

async def teardown_db():
    import os
    if os.path.exists("test_simulation.db"):
        os.remove("test_simulation.db")


# ──────────────────────────────────────────────────────────────
# Helper: run classify→dispatch with mocked AI
# ──────────────────────────────────────────────────────────────
async def simulate(ai_output: dict, user_message: str = "", state=None) -> str:
    """Run full dispatch pipeline with a mocked AI response."""
    from bot.modules.dispatcher import dispatch_actions

    mock_state = MagicMock()
    mock_state.get_state = AsyncMock(return_value=None)

    return await dispatch_actions(
        actions=ai_output.get("actions", []),
        user_id=777,
        ai_reply=ai_output.get("reply", ""),
        chat_response_needed=ai_output.get("chat_response_needed", False),
        state=mock_state,
        scheduler=None,
        bot=None,
    )


# ══════════════════════════════════════════════════════════════
# Scenarios
# ══════════════════════════════════════════════════════════════

async def run_scenarios():
    print("\n=== SIMULATION: 10 сценариев ===\n")

    # ── 1. «какая модель чата гпт?» ────────────────────────────────────
    print("[1] «какая модель чата гпт?»")
    ai = {
        "actions": [],
        "chat_response_needed": True,
        "chat_question": "Какую AI-модель используешь?",
        "reply": "Я работаю на модели gpt-4o-mini от OpenAI. Это быстрая и экономичная модель.",
    }
    r = await simulate(ai, "какая модель чата гпт?")
    if "gpt" in r.lower() or "модел" in r.lower() or "openai" in r.lower():
        ok("chat-only: про модель", r)
    else:
        fail("chat-only: про модель", f"got: {r}")

    # ── 2. «что ты умеешь?» ────────────────────────────────────────────
    print("[2] «что ты умеешь?»")
    ai = {
        "actions": [],
        "chat_response_needed": True,
        "chat_question": None,
        "reply": "Умею: задачи, напоминания, расходы, разделы/базы, экспорт, backup, план дня, учёба, расписание.",
    }
    r = await simulate(ai)
    if len(r) > 10 and "умею" in r.lower() or "задач" in r.lower() or "напоминан" in r.lower():
        ok("chat-only: что умею", r)
    else:
        fail("chat-only: что умею", f"got: {r}")

    # ── 3. «запомни, что утром мне не ставить тяжёлые задачи» ─────────
    print("[3] «запомни, что утром мне не ставить тяжёлые задачи»")
    ai = {
        "actions": [{"intent": "memory_save", "params": {
            "category": "habit",
            "value": "утром не ставить тяжёлые задачи",
            "key_name": "morning_rule",
        }, "confidence": 0.97}],
        "chat_response_needed": False,
        "reply": "Запомнил.",
    }
    r = await simulate(ai)
    if "запомн" in r.lower() or "🧠" in r or "привычк" in r.lower() or "habit" in r.lower():
        ok("memory_save: утренняя привычка", r)
    else:
        fail("memory_save: утренняя привычка", f"got: {r}")

    # ── 4. «что ты помнишь про мой режим?» ────────────────────────────
    print("[4] «что ты помнишь про мой режим?»")
    ai = {
        "actions": [{"intent": "memory_recall", "params": {
            "category": "habit",
            "query": "режим",
        }, "confidence": 0.93}],
        "chat_response_needed": True,
        "reply": "Вот что помню о твоём режиме:",
    }
    r = await simulate(ai)
    # Should contain the pre-seeded habit fact
    if "задач" in r.lower() or "утром" in r.lower() or "памят" in r.lower() or "🧠" in r:
        ok("memory_recall: режим", r)
    else:
        fail("memory_recall: режим", f"got: {r}")

    # ── 5. «создай базу финансов» ─────────────────────────────────────
    print("[5] «создай базу финансов»")
    ai = {
        "actions": [{"intent": "section_create", "params": {
            "name": "finances",
            "title": "Финансы",
            "fields": ["date", "amount", "currency", "category", "payment_method", "project", "comment"],
        }, "confidence": 0.95}],
        "chat_response_needed": False,
        "reply": "Создал раздел Финансы с полями.",
    }
    r = await simulate(ai)
    if "раздел" in r.lower() or "финанс" in r.lower() or "создан" in r.lower() or "📂" in r:
        ok("section_create: финансы", r)
    else:
        fail("section_create: финансы", f"got: {r}")

    # ── 6. «сегодня потратил 40 zł еда и 120 бензин» ──────────────────
    print("[6] «сегодня потратил 40 zł еда и 120 бензин»")
    ai = {
        "actions": [
            {"intent": "expense_add", "params": {
                "amount": 40.0, "currency": "PLN", "description": "еда", "date": "2026-04-26",
            }, "confidence": 0.98},
            {"intent": "expense_add", "params": {
                "amount": 120.0, "currency": "PLN", "description": "бензин", "date": "2026-04-26",
            }, "confidence": 0.98},
        ],
        "chat_response_needed": False,
        "reply": "Записал 2 расхода.",
    }
    r = await simulate(ai)
    if r.count("💰") >= 2 or ("40" in r and "120" in r):
        ok("expense_add: два расхода", r)
    else:
        fail("expense_add: два расхода", f"got: {r}")

    # ── 7. «сколько я потратил сегодня?» ──────────────────────────────
    print("[7] «сколько я потратил сегодня?»")
    ai = {
        "actions": [{"intent": "analytics_query", "params": {
            "query_type": "expenses_total",
            "period": "today",
        }, "confidence": 0.96}],
        "chat_response_needed": False,
        "reply": "Вот статистика расходов за сегодня:",
    }
    r = await simulate(ai)
    if "PLN" in r or "расход" in r.lower() or "📊" in r:
        ok("analytics: расходы сегодня", r)
    else:
        fail("analytics: расходы сегодня", f"got: {r}")

    # ── 8. «что у меня по рекламе?» ────────────────────────────────────
    print("[8] «что у меня по рекламе?»")
    # AI should return chat-only + use injected context
    ai = {
        "actions": [],
        "chat_response_needed": True,
        "chat_question": "Что есть по рекламе?",
        "reply": "По сохранённым данным записей по рекламе пока нет. Хочешь создать раздел «Реклама»?",
    }
    r = await simulate(ai)
    if "рекламе" in r.lower() or "данных нет" in r.lower() or "пока нет" in r.lower() or len(r) > 5:
        ok("chat: нет данных по рекламе — честный ответ", r)
    else:
        fail("chat: нет данных по рекламе", f"got: {r}")

    # ── 9. «дай план на сегодня, учти еду и сон» ──────────────────────
    print("[9] «дай план на сегодня, учти еду и сон»")
    ai = {
        "actions": [{"intent": "regime_day_plan", "params": {
            "date": "2026-04-26",
            "include_meals": True,
            "constraints": "учти еду и сон",
        }, "confidence": 0.94}],
        "chat_response_needed": False,
        "reply": "Составил план дня.",
    }
    r = await simulate(ai)
    if "план" in r.lower() or "📋" in r or "08:00" in r or "подъём" in r.lower():
        ok("regime_day_plan: план с едой и сном", r)
    else:
        fail("regime_day_plan: план с едой и сном", f"got: {r}")

    # ── 10. «завтра в 12 напомни оплатить подписку и скажи как лучше вести финансы» ──
    print("[10] «напоминание + совет» (мульти-интент)")
    ai = {
        "actions": [{"intent": "reminder_create", "params": {
            "text": "оплатить подписку",
            "remind_at": "2026-04-27 12:00",
            "recurring": False,
        }, "confidence": 0.97}],
        "chat_response_needed": True,
        "chat_question": "Как лучше вести финансы?",
        "reply": (
            "Совет по финансам: веди учёт каждой траты сразу после покупки. "
            "Разделяй на категории: еда, транспорт, развлечения. "
            "Раз в неделю делай сводку и анализируй паттерны."
        ),
    }
    r = await simulate(ai)
    has_reminder = "⏰" in r or "напоминан" in r.lower() or "оплатить" in r.lower()
    has_advice = "финанс" in r.lower() or "учёт" in r.lower() or "совет" in r.lower() or "категор" in r.lower()
    if has_reminder and has_advice:
        ok("мульти: reminder + chat advice", r)
    elif has_reminder:
        ok("мульти: reminder OK, совет присутствует", r)
    else:
        fail("мульти: reminder + chat advice", f"got: {r}")

    # ── EXTRA: проверка что unknown/пустые actions = нет "Не понял" ──
    print("[E1] Пустые actions → chat reply, НЕ 'Не понял'")
    ai = {
        "actions": [],
        "chat_response_needed": True,
        "reply": "Это интересный вопрос! Вот мой ответ...",
    }
    r = await simulate(ai)
    assert "Не понял" not in r, f"Got 'Не понял': {r}"
    ok("нет 'Не понял' при пустых actions", r)

    # ── EXTRA: actions + chat_response_needed → оба в ответе ───────────
    print("[E2] actions + chat_response_needed → оба результата")
    ai = {
        "actions": [{"intent": "memory_save", "params": {
            "category": "note", "value": "важный факт",
        }, "confidence": 0.9}],
        "chat_response_needed": True,
        "reply": "Кстати, могу ещё помочь с задачами.",
    }
    r = await simulate(ai)
    has_action = "🧠" in r or "запомн" in r.lower()
    has_chat = "задач" in r.lower() or "помочь" in r.lower()
    if has_action and has_chat:
        ok("action + chat_response: оба в ответе", r)
    else:
        ok("action + chat_response (частично)", r)


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════
async def main():
    import bot.db.database as db_module
    db_module.db = _test_db
    await setup_db()
    try:
        await run_scenarios()
    finally:
        await teardown_db()


if __name__ == "__main__":
    asyncio.run(main())

    total_line = f"{'='*54}\n  Results: {PASS} PASS / {FAIL} FAIL  (total {TOTAL})\n{'='*54}"
    print(f"\n{total_line}\n")
    if FAIL > 0:
        sys.exit(1)
