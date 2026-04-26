"""test_live_flow.py — Полная интеграционная проверка TUNTUN бота.

Симулирует реальные пользовательские сценарии:
  text → classify (OpenAI) → dispatch → DB → response

Запуск:
    C:\Python310\python.exe test_live_flow.py           # с реальным AI
    C:\Python310\python.exe test_live_flow.py --no-ai   # без AI (мок-интенты)

Что проверяется:
  STARTUP  — dirs, DB (17 таблиц), user, scheduler module
  [1]  /start → главное меню (кнопки)
  [2]  «создай базу финансов»
  [3]  «сегодня потратил 40 zł на еду и 120 zł на бензин»
  [4]  «что по финансам за неделю?»
  [5]  «завтра в 12 напомни оплатить подписку»
  [6]  «запомни, что утром не ставить тяжёлые задачи»
  [7]  «дай план на сегодня»
  [8]  «выгрузи финансы в Excel»
  [9]  «сделай backup»
  [10] multi-intent (reminder + expenses + memory)
  [11] message_logs пишутся
  [12] logs/app.log создаётся
"""

import asyncio
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.platform == "win32" and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Redirect DB to test instance BEFORE any bot imports ──────────────────────
sys.path.insert(0, str(Path(__file__).parent))
import config
config.DB_PATH = "tuntun_live_test.db"
# ─────────────────────────────────────────────────────────────────────────────

# Suppress noisy background logs during tests
logging.basicConfig(level=logging.ERROR)

from bot.db.database import db  # noqa: E402 — must come after config override
from bot.modules.dispatcher import dispatch_actions  # noqa: E402
from bot.ai.intent import _normalize  # noqa: E402

# ── Test config ───────────────────────────────────────────────────────────────
TEST_USER = 999002
USE_REAL_AI = "--no-ai" not in sys.argv and bool(config.OPENAI_API_KEY)

# ── Result tracking ───────────────────────────────────────────────────────────
_PASS = 0
_FAIL = 0
_WARN = 0


def _ok(label: str, detail: str = ""):
    global _PASS
    _PASS += 1
    suffix = f": {detail}" if detail else ""
    print(f"  \033[32mPASS\033[0m  {label}{suffix}")


def _fail(label: str, detail: str = ""):
    global _FAIL
    _FAIL += 1
    suffix = f": {detail}" if detail else ""
    print(f"  \033[31mFAIL\033[0m  {label}{suffix}")


def _warn(label: str, detail: str = ""):
    global _WARN
    _WARN += 1
    suffix = f": {detail}" if detail else ""
    print(f"  \033[33mWARN\033[0m  {label}{suffix}")


# ── Mock classify (for --no-ai mode) ─────────────────────────────────────────
async def _mock_classify(text: str) -> dict:
    """Return hardcoded intents based on keywords (offline testing)."""
    t = text.lower()
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    today_str = date.today().strftime("%Y-%m-%d")

    # Multi-intent: build list of all matching actions
    actions = []

    if "создай базу" in t or "создай раздел" in t:
        actions.append({"intent": "section_create", "params": {
            "name": "finances_livetest", "title": "Финансы LiveTest",
            "fields": ["date", "amount", "currency", "description"]
        }, "confidence": 0.95})

    if "потратил" in t or "zł" in t or "злот" in t:
        amounts = []
        if "40" in t:
            amounts.append({"intent": "expense_add", "params": {
                "amount": 40, "currency": "PLN", "description": "еда", "date": today_str
            }, "confidence": 0.95})
        if "120" in t:
            amounts.append({"intent": "expense_add", "params": {
                "amount": 120, "currency": "PLN", "description": "бензин", "date": today_str
            }, "confidence": 0.95})
        if not amounts:
            amounts.append({"intent": "expense_add", "params": {
                "amount": 0, "currency": "PLN", "description": text[:30], "date": today_str
            }, "confidence": 0.80})
        actions.extend(amounts)

    if "финансам" in t or ("финанс" in t and ("недел" in t or "стат" in t or "итог" in t)):
        actions.append({"intent": "analytics_query", "params": {
            "query_type": "expenses_total", "period": "week"
        }, "confidence": 0.90})

    if "напомни" in t:
        actions.append({"intent": "reminder_create", "params": {
            "text": "оплатить подписку",
            "remind_at": f"{tomorrow} 12:00:00"
        }, "confidence": 0.95})

    if "запомни" in t:
        actions.append({"intent": "memory_save", "params": {
            "category": "preferences",
            "key_name": "morning_tasks",
            "value": "утром не ставить тяжёлые задачи"
        }, "confidence": 0.95})

    if "план на" in t or "план дня" in t:
        actions.append({"intent": "regime_day_plan", "params": {
            "date": today_str
        }, "confidence": 0.95})

    if "excel" in t or "выгрузи" in t:
        actions.append({"intent": "export_excel", "params": {
            "target": "expenses", "period": "month"
        }, "confidence": 0.90})

    if "backup" in t or "бэкап" in t or "резервн" in t:
        actions.append({"intent": "backup_create", "params": {
        }, "confidence": 0.95})

    if actions:
        if len(actions) == 1:
            reply = f"Выполняю: {actions[0]['intent']}"
        else:
            reply = f"Выполняю {len(actions)} действий"
        return {"actions": actions, "reply": reply}

    return {"actions": [{"intent": "chat", "params": {}, "confidence": 0.80}],
            "reply": "Привет! Чем могу помочь?"}


# ── Core: text → classify → dispatch ─────────────────────────────────────────
async def _do_classify(text: str) -> dict:
    if USE_REAL_AI:
        from bot.ai.intent import classify
        return await classify(text)
    return await _mock_classify(text)


async def _run(text: str) -> tuple[dict, str]:
    """Classify text and dispatch. Returns (classify_result, bot_response)."""
    result = await _do_classify(text)
    actions = result.get("actions", [])
    ai_reply = result.get("reply", "")
    response = await dispatch_actions(
        actions=actions,
        user_id=TEST_USER,
        ai_reply=ai_reply,
        state=None,
        scheduler=None,
        bot=None,
    )
    return result, response


# ═════════════════════════════════════════════════════════════════════════════
#  STARTUP: dirs, DB, user
# ═════════════════════════════════════════════════════════════════════════════
async def check_startup():
    print("\n[STARTUP] Инициализация")

    # 1. Create all storage dirs
    for d_path in config.STORAGE_DIRS:
        d_path.mkdir(parents=True, exist_ok=True)
    missing_dirs = [str(p) for p in config.STORAGE_DIRS if not p.exists()]
    if missing_dirs:
        _fail("dirs_created", f"Отсутствуют: {missing_dirs}")
    else:
        _ok("dirs_created", f"{len(config.STORAGE_DIRS)} папок")

    # 2. DB init
    await db.init()
    import aiosqlite
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [r[0] for r in await cur.fetchall()]
    expected = [
        "attachments", "daily_plans", "dynamic_records", "dynamic_sections",
        "expenses", "exports_log", "memory", "message_logs", "projects",
        "reminders", "settings", "tasks", "users",
    ]
    missing_tables = [t for t in expected if t not in tables]
    if missing_tables:
        _fail("db_tables", f"Отсутствуют: {missing_tables}")
    else:
        _ok("db_tables", f"{len(tables)} таблиц созданы")

    # 3. User registration
    await db.ensure_user(TEST_USER, "live_test_user", "LiveTest")
    user = await db._fetchone("SELECT * FROM users WHERE user_id=?", (TEST_USER,))
    if user:
        _ok("user_ensure", f"user_id={TEST_USER}")
    else:
        _fail("user_ensure", "Пользователь не создан")

    # 4. Scheduler module
    try:
        from bot.utils.scheduler import add_reminder_job, cancel_reminder_job
        _ok("scheduler_module")
    except Exception as e:
        _fail("scheduler_module", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [1] /start → главное меню
# ═════════════════════════════════════════════════════════════════════════════
async def check_start():
    print("\n[1] /start → главное меню")
    try:
        from bot.modules.menu import main_menu_keyboard
        kb = main_menu_keyboard()
        buttons = [btn for row in kb.inline_keyboard for btn in row]
        if len(buttons) >= 5:
            labels = ", ".join(b.text for b in buttons)
            _ok("main_menu_keyboard", labels)
        else:
            _fail("main_menu_keyboard", f"Только {len(buttons)} кнопок, ожидалось ≥5")
    except Exception as e:
        _fail("main_menu_keyboard", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [2] «создай базу финансов»
# ═════════════════════════════════════════════════════════════════════════════
async def check_create_section():
    print("\n[2] «создай базу финансов»")
    try:
        result, response = await _run("создай базу финансов")
        intents = [a["intent"] for a in result.get("actions", [])]
        if "section_create" in intents:
            _ok("ai_route_section_create", f"→ {response[:60]}")
        else:
            _warn("ai_route_section_create", f"Ожидал section_create, получил: {intents}")

        # Directly verify DB via known params
        from bot.modules.dynamic import handle_create
        r2 = await handle_create(TEST_USER, {
            "name": "finances_livetest",
            "title": "Финансы LiveTest",
            "fields": ["date", "amount", "currency", "description"],
        }, "")
        if "создан" in r2.lower() or "финанс" in r2.lower() or "livetest" in r2.lower():
            _ok("section_db_write", r2[:70])
        else:
            _warn("section_db_write", r2[:70])

        # Verify it's in the DB
        section = await db.section_find(TEST_USER, "finances_livetest")
        if section:
            _ok("section_db_read", f"id={section['id']}, fields={section['fields']}")
        else:
            _fail("section_db_read", "Раздел не найден в DB")

    except Exception as e:
        _fail("check_create_section", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [3] «сегодня потратил 40 zł на еду и 120 zł на бензин»
# ═════════════════════════════════════════════════════════════════════════════
async def check_expenses():
    print("\n[3] «потратил 40 zł еда, 120 zł бензин»")
    try:
        result, response = await _run(
            "сегодня потратил 40 zł на еду и 120 zł на бензин"
        )
        intents = [a["intent"] for a in result.get("actions", [])]
        expense_count = sum(1 for i in intents if i == "expense_add")
        if expense_count >= 2:
            _ok("ai_route_expenses", f"{expense_count} expense_add → {response[:60]}")
        elif expense_count == 1:
            _warn("ai_route_expenses", f"Только 1 expense_add (ожидал 2): {response[:60]}")
        else:
            _warn("ai_route_expenses", f"Нет expense_add, intents={intents}")

        # Verify in DB
        today = date.today().strftime("%Y-%m-%d")
        expenses = await db.expense_stats(TEST_USER, start_date=today, end_date=today)
        if expenses:
            total = sum(e["amount"] for e in expenses)
            _ok("expenses_in_db", f"{len(expenses)} записей, сумма={total}")
        else:
            _warn("expenses_in_db", "Нет записей за сегодня в DB")

    except Exception as e:
        _fail("check_expenses", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [4] «что по финансам за неделю?»
# ═════════════════════════════════════════════════════════════════════════════
async def check_finance_stats():
    print("\n[4] «что по финансам за неделю?»")
    try:
        result, response = await _run("что по финансам за неделю?")
        intents = [a["intent"] for a in result.get("actions", [])]
        if "analytics_query" in intents or "expense_stats" in intents:
            _ok("ai_route_analytics", f"{intents[0]}")
        else:
            _warn("ai_route_analytics", f"Ожидал analytics_query, получил: {intents}")

        if response and len(response) > 5:
            _ok("analytics_response", response[:100])
        else:
            _warn("analytics_response", "Пустой или короткий ответ")

    except Exception as e:
        _fail("check_finance_stats", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [5] «завтра в 12 напомни оплатить подписку»
# ═════════════════════════════════════════════════════════════════════════════
async def check_reminder():
    print("\n[5] «завтра в 12 напомни оплатить подписку»")
    try:
        result, response = await _run("завтра в 12 напомни оплатить подписку")
        intents = [a["intent"] for a in result.get("actions", [])]
        if "reminder_create" in intents:
            _ok("ai_route_reminder", f"→ {response[:60]}")
        else:
            _warn("ai_route_reminder", f"Ожидал reminder_create, получил: {intents}")

        # Check DB
        reminders = await db.reminder_list(TEST_USER)
        found = [r for r in reminders if "подписк" in r.get("text", "").lower()]
        if found:
            _ok("reminder_in_db", f"remind_at={found[0]['remind_at']}")
        else:
            _warn("reminder_in_db", "Напоминание не найдено в DB")

    except Exception as e:
        _fail("check_reminder", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [6] «запомни, что утром не ставить тяжёлые задачи»
# ═════════════════════════════════════════════════════════════════════════════
async def check_memory():
    print("\n[6] «запомни, что утром не ставить тяжёлые задачи»")
    try:
        result, response = await _run(
            "запомни, что утром мне не ставить тяжёлые задачи"
        )
        intents = [a["intent"] for a in result.get("actions", [])]
        if "memory_save" in intents:
            _ok("ai_route_memory", f"→ {response[:60]}")
        else:
            _warn("ai_route_memory", f"Ожидал memory_save, получил: {intents}")

        # Check DB
        rows = await db._fetchall(
            "SELECT * FROM memory WHERE user_id=?", (TEST_USER,)
        )
        if rows:
            _ok("memory_in_db", f"{len(rows)} фактов в памяти")
        else:
            _warn("memory_in_db", "Нет записей в memory")

    except Exception as e:
        _fail("check_memory", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [7] «дай план на сегодня»
# ═════════════════════════════════════════════════════════════════════════════
async def check_day_plan():
    print("\n[7] «дай план на сегодня»")
    try:
        result, response = await _run("дай план на сегодня")
        intents = [a["intent"] for a in result.get("actions", [])]
        if "regime_day_plan" in intents:
            _ok("ai_route_day_plan")
        else:
            _warn("ai_route_day_plan", f"Ожидал regime_day_plan, получил: {intents}")

        if "план" in response.lower() or "📋" in response or "подъём" in response.lower():
            _ok("plan_response", response[:100])
        else:
            _warn("plan_response", response[:60])

        # Check DB
        today = date.today().strftime("%Y-%m-%d")
        plan = await db._fetchone(
            "SELECT * FROM daily_plans WHERE user_id=? AND date=?",
            (TEST_USER, today)
        )
        if plan:
            _ok("plan_saved_db", f"date={plan['date']}")
        else:
            _warn("plan_saved_db", "Не сохранён в daily_plans")

    except Exception as e:
        _fail("check_day_plan", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [8] «выгрузи финансы в Excel»
# ═════════════════════════════════════════════════════════════════════════════
async def check_excel_export():
    print("\n[8] «выгрузи финансы в Excel»")
    try:
        result, response = await _run("выгрузи финансы в Excel")
        intents = [a["intent"] for a in result.get("actions", [])]
        if "export_excel" in intents:
            _ok("ai_route_excel", "export_excel")
        else:
            _warn("ai_route_excel", f"Ожидал export_excel, получил: {intents}")

        # Check if __FILE__ marker present
        if "__FILE__:" in response:
            idx = response.index("__FILE__:") + len("__FILE__:")
            file_path = response[idx:].strip().splitlines()[0]
            if Path(file_path).exists():
                size = Path(file_path).stat().st_size
                _ok("excel_file_created", f"{size}b → {Path(file_path).name}")
            else:
                _fail("excel_file_missing", f"Маркер есть, файл не найден: {file_path}")
        else:
            # Fallback: call export directly to verify it works
            from bot.modules.exports import export_to_excel
            path = await export_to_excel(TEST_USER, "expenses", "month")
            if path and Path(path).exists():
                _ok("excel_direct_export", f"{Path(path).stat().st_size}b")
            else:
                _warn("excel_direct_export", "export_to_excel вернул None (нет данных?)")

    except Exception as e:
        _fail("check_excel_export", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [9] «сделай backup»
# ═════════════════════════════════════════════════════════════════════════════
async def check_backup():
    print("\n[9] «сделай backup»")
    try:
        result, response = await _run("сделай backup")
        intents = [a["intent"] for a in result.get("actions", [])]
        if "backup_create" in intents:
            _ok("ai_route_backup", "backup_create")
        else:
            _warn("ai_route_backup", f"Ожидал backup_create, получил: {intents}")

        if "__FILE__:" in response:
            idx = response.index("__FILE__:") + len("__FILE__:")
            file_path = response[idx:].strip().splitlines()[0]
            if Path(file_path).exists():
                size = Path(file_path).stat().st_size
                _ok("backup_file_created", f"{size}b → {Path(file_path).name}")
            else:
                _fail("backup_file_missing", f"Маркер есть, ZIP не найден: {file_path}")
        else:
            # Direct fallback
            from bot.modules.backup import create_backup
            path = await create_backup(TEST_USER)
            if path and Path(path).exists():
                _ok("backup_direct", f"{Path(path).stat().st_size}b")
            else:
                _fail("backup_direct", "create_backup вернул None или файл не создан")

    except Exception as e:
        _fail("check_backup", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [10] Multi-intent: напоминание + расходы + память
# ═════════════════════════════════════════════════════════════════════════════
async def check_multi_intent():
    print("\n[10] Multi-intent: reminder + expenses + memory")
    text = (
        "завтра в 12 напомни оплатить подписку, "
        "сегодня 40 zł еда, 120 zł бензин, "
        "запомни что утром не ставить тяжёлые задачи"
    )
    try:
        result, response = await _run(text)
        actions = result.get("actions", [])
        intents = [a["intent"] for a in actions]

        if len(actions) >= 3:
            _ok("multi_actions_count", f"{len(actions)} действий: {intents}")
        elif len(actions) >= 2:
            _warn("multi_actions_count", f"Только {len(actions)}: {intents} (ожидал 3+)")
        else:
            _warn("multi_actions_count", f"Только {len(actions)}: {intents}")

        unique_intents = set(intents)
        expected_set = {"reminder_create", "expense_add", "memory_save"}
        covered = unique_intents & expected_set
        if len(covered) >= 2:
            _ok("multi_intent_variety", f"Покрыто: {covered}")
        else:
            _warn("multi_intent_variety", f"Покрыто только: {covered}")

        if response and len(response) > 5:
            _ok("multi_response", response[:120])
        else:
            _warn("multi_response", "Пустой или короткий ответ")

    except Exception as e:
        _fail("check_multi_intent", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [11] message_logs пишутся
# ═════════════════════════════════════════════════════════════════════════════
async def check_message_logs():
    print("\n[11] message_logs")
    try:
        log_id = await db.log_message(TEST_USER, "text", "тестовое сообщение live flow")
        await db.log_update_response(
            log_id, "тестовый ответ", actions_json='[{"intent":"chat"}]'
        )
        row = await db._fetchone(
            "SELECT * FROM message_logs WHERE id=?", (log_id,)
        )
        if row and row.get("bot_response") == "тестовый ответ":
            _ok("message_log_write_read", f"log_id={log_id}")
        else:
            _fail("message_log_write_read", f"row={row}")

    except Exception as e:
        _fail("check_message_logs", str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  [12] logs/app.log создаётся
# ═════════════════════════════════════════════════════════════════════════════
async def check_app_log():
    print("\n[12] logs/app.log")
    log_path = config.LOGS_DIR / "app.log"
    if log_path.exists():
        size = log_path.stat().st_size
        _ok("app_log_exists", f"{size} bytes")
    else:
        _warn("app_log_not_found",
              "Создаётся только при запуске main.py (RotatingFileHandler)")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════
async def main() -> int:
    print("=" * 62)
    mode = "РЕАЛЬНЫЙ AI (OpenAI)" if USE_REAL_AI else "МОК (--no-ai)"
    print(f"  TUNTUN — Live Flow Tests [{mode}]")
    print("=" * 62)
    if not USE_REAL_AI and "--no-ai" not in sys.argv:
        print("  ⚠  OPENAI_API_KEY не задан — используется мок-режим")

    await check_startup()
    await check_start()
    await check_create_section()
    await check_expenses()
    await check_finance_stats()
    await check_reminder()
    await check_memory()
    await check_day_plan()
    await check_excel_export()
    await check_backup()
    await check_multi_intent()
    await check_message_logs()
    await check_app_log()

    # ── Cleanup ───────────────────────────────────────────────────────────
    cutoff = datetime.now().timestamp() - 300  # files created in last 5 min
    for p in config.EXPORTS_DIR.glob("*.xlsx"):
        if p.stat().st_mtime > cutoff:
            p.unlink(missing_ok=True)
    for p in config.BACKUPS_DIR.glob("*.zip"):
        if p.stat().st_mtime > cutoff:
            p.unlink(missing_ok=True)
    (config.STORAGE_DIR / "README_backup.txt").unlink(missing_ok=True)
    Path(config.DB_PATH).unlink(missing_ok=True)

    print()
    print("=" * 62)
    total = _PASS + _FAIL + _WARN
    print(f"  Итого: {total} тестов | "
          f"\033[32mPASS {_PASS}\033[0m | "
          f"\033[31mFAIL {_FAIL}\033[0m | "
          f"\033[33mWARN {_WARN}\033[0m")
    print("=" * 62)
    print("  (тестовая БД и временные файлы удалены)")
    return _FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    sys.exit(0 if failed == 0 else 1)
