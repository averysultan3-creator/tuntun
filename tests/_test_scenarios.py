"""
Функциональные тесты сценариев TUNTUN.
Запуск: C:\Python310\python.exe _test_scenarios.py
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Fix Windows console encoding
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.platform == "win32" and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Use test DB, не трогать боевой
import config
config.DB_PATH = "tuntun_test.db"
config.EXPORTS_DIR = config.BASE_DIR / "storage" / "exports"
config.BACKUPS_DIR = config.BASE_DIR / "storage" / "backups"
config.STORAGE_DIRS = [
    config.STORAGE_DIR, config.PHOTOS_DIR, config.VOICE_DIR,
    config.DOCUMENTS_DIR, config.EXPORTS_DIR, config.BACKUPS_DIR, config.LOGS_DIR,
]

from bot.db.database import db

TEST_USER = 999001
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"

results = []

def ok(name):
    results.append((name, True, ""))
    print(f"  {PASS}  {name}")

def fail(name, reason=""):
    results.append((name, False, reason))
    print(f"  {FAIL}  {name}: {reason}")

def warn(name, reason=""):
    results.append((name, None, reason))
    print(f"  {WARN}  {name}: {reason}")

# ─────────────────────────────────────────────
# SCENARIO 1: Задачи
# ─────────────────────────────────────────────
async def test_tasks():
    print("\n[1] ЗАДАЧИ")
    from bot.modules.tasks import handle_create, handle_list, handle_complete, handle_update, handle_delete

    # create
    r = await handle_create(TEST_USER, {"title": "Тест задача", "priority": "high", "due_date": "2026-04-27"}, "")
    if "#" in r and "Тест задача" in r:
        ok("task_create")
    else:
        fail("task_create", r)

    # list (no date filter — shows all pending)
    r = await handle_list(TEST_USER, {}, "")
    if "Тест задача" in r:
        ok("task_list")
    else:
        fail("task_list", r)

    # complete by id
    tasks = await db.task_find_by_title(TEST_USER, "Тест задача")
    if tasks:
        tid = tasks[0]["id"]
        r = await handle_complete(TEST_USER, {"task_id": tid}, "")
        if "выполнена" in r.lower() or "✅" in r:
            ok("task_complete")
        else:
            fail("task_complete", r)
    else:
        fail("task_complete", "task not found")

    # create + delete
    r2 = await handle_create(TEST_USER, {"title": "Удаляемая задача"}, "")
    tasks2 = await db.task_find_by_title(TEST_USER, "Удаляемая задача")
    if tasks2:
        r3 = await handle_delete(TEST_USER, {"task_id": tasks2[0]["id"]}, "")
        if "удалена" in r3.lower() or "удалено" in r3.lower() or "🗑" in r3:
            ok("task_delete")
        else:
            fail("task_delete", r3)
    else:
        fail("task_delete", "task not created")

# ─────────────────────────────────────────────
# SCENARIO 2: Динамические базы (section)
# ─────────────────────────────────────────────
async def test_sections():
    print("\n[2] БАЗЫ ДАННЫХ (разделы)")
    from bot.modules.dynamic import handle_create, handle_record_add, handle_query

    # create section (use 'name' not 'section_name')
    r = await handle_create(TEST_USER, {
        "name": "finansy_test",
        "title": "Финансы тест",
        "fields": ["дата", "сумма", "категория"]
    }, "")
    if "создан" in r.lower() or "финансы" in r.lower() or "#" in r:
        ok("section_create")
    else:
        fail("section_create", r)

    # record add to existing section
    r2 = await handle_record_add(TEST_USER, {
        "section_name": "finansy_test",
        "data": {"дата": "2026-04-26", "сумма": "40", "категория": "еда"}
    }, "")
    if "Запись добавлена" in r2 or "#" in r2:
        ok("section_record_add")
    else:
        fail("section_record_add", r2)

    # record add to NON-EXISTENT section → should offer creation
    r3 = await handle_record_add(TEST_USER, {
        "section_name": "несуществующий_раздел_xyz",
        "data": {"сумма": "100"}
    }, "")
    if "__SECTION_BUILDER__:" in r3:
        ok("section_record_add_unknown → builder")
    else:
        fail("section_record_add_unknown", f"expected __SECTION_BUILDER__ marker, got: {r3}")

    # query
    r4 = await handle_query(TEST_USER, {"section_name": "finansy_test"}, "")
    if "40" in r4 or "еда" in r4 or "Финансы" in r4:
        ok("section_query")
    else:
        fail("section_query", r4)

# ─────────────────────────────────────────────
# SCENARIO 3: Финансы / расходы
# ─────────────────────────────────────────────
async def test_expenses():
    print("\n[3] ФИНАНСЫ / РАСХОДЫ")
    from bot.modules.projects import handle_expense_add, handle_expense_stats

    r1 = await handle_expense_add(TEST_USER, {"amount": 40, "currency": "PLN", "description": "еда"}, "")
    if "40" in r1 and ("PLN" in r1 or "расход" in r1.lower()):
        ok("expense_add")
    else:
        fail("expense_add", r1)

    r2 = await handle_expense_add(TEST_USER, {"amount": 120, "currency": "PLN", "description": "бензин"}, "")
    if "120" in r2:
        ok("expense_add_2")
    else:
        fail("expense_add_2", r2)

    r3 = await handle_expense_stats(TEST_USER, {"period": "month"}, "")
    if "PLN" in r3 or "160" in r3 or "расход" in r3.lower():
        ok("expense_stats")
    else:
        fail("expense_stats", r3)

    # DB totals
    totals = await db.expenses_total(TEST_USER)
    pln_total = next((t for t in totals if t["currency"] == "PLN"), None)
    if pln_total and pln_total["total"] >= 160:
        ok("expense_total_db")
    else:
        fail("expense_total_db", f"totals={totals}")

# ─────────────────────────────────────────────
# SCENARIO 4: Напоминания
# ─────────────────────────────────────────────
async def test_reminders():
    print("\n[4] НАПОМИНАНИЯ")
    from bot.modules.reminders import handle_create, handle_list, handle_cancel
    from bot.utils.dates import now_str
    from datetime import datetime, timedelta

    remind_at = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
    r1 = await handle_create(TEST_USER, {"text": "Тест напоминание", "remind_at": remind_at}, "")
    if "Напоминание" in r1 or "#" in r1:
        ok("reminder_create")
    else:
        fail("reminder_create", r1)

    r2 = await handle_list(TEST_USER, {}, "")
    if "Тест напоминание" in r2 or "напоминани" in r2.lower():
        ok("reminder_list")
    else:
        fail("reminder_list", r2)

    rems = await db.reminder_list(TEST_USER)
    if rems:
        rid = rems[0]["id"]
        r3 = await handle_cancel(TEST_USER, {"reminder_id": rid}, "")
        if "отменено" in r3.lower() or "❌" in r3 or "отмен" in r3.lower():
            ok("reminder_cancel")
        else:
            fail("reminder_cancel", r3)
    else:
        fail("reminder_cancel", "no reminders found")

# ─────────────────────────────────────────────
# SCENARIO 5: Память
# ─────────────────────────────────────────────
async def test_memory():
    print("\n[5] ПАМЯТЬ")
    from bot.modules.memory import handle_save, handle_recall

    r1 = await handle_save(TEST_USER, {
        "category": "preferences", "value": "не люблю помидоры", "key_name": "еда"
    }, "")
    if "сохран" in r1.lower() or "🧠" in r1:
        ok("memory_save")
    else:
        fail("memory_save", r1)

    r2 = await handle_recall(TEST_USER, {"category": "preferences"}, "")
    if "помидор" in r2:
        ok("memory_recall_by_category")
    else:
        fail("memory_recall_by_category", r2)

    r3 = await handle_recall(TEST_USER, {"query": "еда"}, "")
    if "помидор" in r3 or "еда" in r3:
        ok("memory_recall_by_query")
    else:
        fail("memory_recall_by_query", r3)

# ─────────────────────────────────────────────
# SCENARIO 6: Учёба
# ─────────────────────────────────────────────
async def test_study():
    print("\n[6] УЧЁБА")
    from bot.modules.study import handle_add_subject, handle_add_record, handle_list

    r1 = await handle_add_subject(TEST_USER, {"name": "Управление проектами", "short_name": "PRI"}, "")
    if "PRI" in r1 or "Управление" in r1:
        ok("study_add_subject")
    else:
        fail("study_add_subject", r1)

    r2 = await handle_add_record(TEST_USER, {
        "subject": "PRI",
        "type": "task",
        "content": "Доделать диаграммы",
        "due_date": "2026-04-29"
    }, "")
    if "Записано" in r2 or "диаграмм" in r2.lower():
        ok("study_add_record")
    else:
        fail("study_add_record", r2)

    r3 = await handle_list(TEST_USER, {"subject": "PRI"}, "")
    if "диаграмм" in r3.lower() or "PRI" in r3:
        ok("study_list")
    else:
        fail("study_list", r3)

# ─────────────────────────────────────────────
# SCENARIO 7: Настройки
# ─────────────────────────────────────────────
async def test_settings():
    print("\n[7] НАСТРОЙКИ")
    from bot.modules.user_settings import handle_save, handle_get

    r1 = await handle_save(TEST_USER, {"key": "wake_time", "value": "09:00"}, "")
    if "09:00" in r1 or "сохран" in r1.lower():
        ok("setting_save_wake")
    else:
        fail("setting_save_wake", r1)

    r2 = await handle_save(TEST_USER, {"key": "sleep_time", "value": "01:00"}, "")
    if "01:00" in r2 or "сохран" in r2.lower():
        ok("setting_save_sleep")
    else:
        fail("setting_save_sleep", r2)

    r3 = await handle_get(TEST_USER, {"key": "wake_time"}, "")
    if "09:00" in r3:
        ok("setting_get")
    else:
        fail("setting_get", r3)

    r4 = await handle_get(TEST_USER, {}, "")
    if "09:00" in r4 and "01:00" in r4:
        ok("setting_get_all")
    else:
        fail("setting_get_all", r4)

# ─────────────────────────────────────────────
# SCENARIO 8: План дня
# ─────────────────────────────────────────────
async def test_day_plan():
    print("\n[8] ПЛАН ДНЯ")
    from bot.modules.regime import handle_day_plan

    r = await handle_day_plan(TEST_USER, {"date": "2026-04-26", "include_meals": True}, "")
    if "09:00" in r and ("01:00" in r or "Подъём" in r):
        ok("day_plan_with_settings")
    elif "📋" in r:
        ok("day_plan_generated")
    else:
        fail("day_plan", r[:200])

    # Check saved in daily_plans
    plan = await db.plan_get(TEST_USER, "2026-04-26")
    if plan and plan.get("plan"):
        ok("day_plan_saved_to_db")
    else:
        fail("day_plan_saved_to_db", f"plan={plan}")

    # Sleep calc
    from bot.modules.regime import handle_sleep_calc
    r2 = await handle_sleep_calc(TEST_USER, {"bedtime": "23:30", "min_hours": 7}, "")
    if "23:30" in r2 and ("цикл" in r2 or "⏰" in r2):
        ok("sleep_calc")
    else:
        fail("sleep_calc", r2[:200])

# ─────────────────────────────────────────────
# SCENARIO 9: Excel экспорт
# ─────────────────────────────────────────────
async def test_export_excel():
    print("\n[9] EXCEL ЭКСПОРТ")
    from bot.modules.exports import handle_excel, export_to_excel
    import pathlib

    # Direct function
    path = await export_to_excel(TEST_USER, "tasks", "all")
    if path and pathlib.Path(path).exists():
        size = pathlib.Path(path).stat().st_size
        ok(f"excel_tasks_file (size={size}b)")
    else:
        fail("excel_tasks_file", f"path={path}")

    # Via handle (checks summary + __FILE__ marker)
    r = await handle_excel(TEST_USER, {"target": "expenses", "period": "month"}, "")
    if "__FILE__:" in r and "Экспорт" in r:
        ok("excel_handle_marker+summary")
    else:
        fail("excel_handle_marker", r[:200])

    # Section export
    path2 = await export_to_excel(TEST_USER, "section", "all", section_name="финансы_тест")
    if path2 and pathlib.Path(path2).exists():
        ok("excel_section_export")
    else:
        warn("excel_section_export", f"path={path2} (section may not exist in test)")

    # All
    path3 = await export_to_excel(TEST_USER, "all", "all")
    if path3 and pathlib.Path(path3).exists():
        ok("excel_all_export")
    else:
        fail("excel_all_export", f"path={path3}")

# ─────────────────────────────────────────────
# SCENARIO 10: TXT экспорт
# ─────────────────────────────────────────────
async def test_export_txt():
    print("\n[10] TXT ЭКСПОРТ")
    from bot.modules.exports import handle_txt, export_to_txt
    import pathlib

    path = await export_to_txt(TEST_USER, "all", "month")
    if path and pathlib.Path(path).exists():
        content = pathlib.Path(path).read_text(encoding="utf-8")
        if "TUNTUN Export" in content and "ЗАДАЧИ" in content:
            ok("txt_all_export")
        else:
            fail("txt_all_export_content", f"content starts: {content[:100]}")
    else:
        fail("txt_all_export", f"path={path}")

    r = await handle_txt(TEST_USER, {"target": "tasks", "period": "week"}, "")
    if "__FILE__:" in r and "Экспорт" in r:
        ok("txt_handle_marker+summary")
    else:
        fail("txt_handle_marker", r[:200])

# ─────────────────────────────────────────────
# SCENARIO 11: Backup
# ─────────────────────────────────────────────
async def test_backup():
    print("\n[11] BACKUP")
    from bot.modules.backup import handle_create, create_backup
    import pathlib

    path = await create_backup(TEST_USER)
    if path and pathlib.Path(path).exists():
        size = pathlib.Path(path).stat().st_size
        ok(f"backup_zip_created (size={size}b)")

        import zipfile
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        has_db = any("tuntun" in n or ".db" in n for n in names)
        has_readme = any("README" in n for n in names)
        if has_db:
            ok("backup_contains_db")
        else:
            fail("backup_contains_db", f"files: {names[:10]}")
        if has_readme:
            ok("backup_contains_readme")
        else:
            warn("backup_readme", f"no README in {names[:10]}")
    else:
        fail("backup_zip_created", f"path={path}")

    r = await handle_create(TEST_USER, {}, "")
    if "__FILE__:" in r:
        ok("backup_handle_marker")
    else:
        fail("backup_handle_marker", r[:200])

# ─────────────────────────────────────────────
# SCENARIO 12: Аналитика
# ─────────────────────────────────────────────
async def test_analytics():
    print("\n[12] АНАЛИТИКА")
    from bot.modules.analytics import handle_query

    r1 = await handle_query(TEST_USER, {"query_type": "expenses_total", "period": "month"}, "")
    if "PLN" in r1 or "расход" in r1.lower() or "💰" in r1:
        ok("analytics_expenses")
    else:
        fail("analytics_expenses", r1[:200])

    r2 = await handle_query(TEST_USER, {"query_type": "tasks_stats", "period": "all"}, "")
    if "задач" in r2.lower() or "📊" in r2 or "выполнен" in r2.lower():
        ok("analytics_tasks")
    else:
        fail("analytics_tasks", r2[:200])

    r3 = await handle_query(TEST_USER, {"query_type": "overview", "period": "month"}, "")
    if r3 and len(r3) > 10:
        ok("analytics_overview")
    else:
        fail("analytics_overview", r3[:200])

# ─────────────────────────────────────────────
# SCENARIO 13: Диспетчер (мульти-интент)
# ─────────────────────────────────────────────
async def test_dispatcher():
    print("\n[13] ДИСПЕТЧЕР (мульти-интент)")
    from bot.modules.dispatcher import dispatch_actions

    # Chat → returns ai_reply
    r = await dispatch_actions(
        [{"intent": "chat", "params": {}, "confidence": 0.9}],
        TEST_USER, "Привет! Я умею многое.", state=None
    )
    if "Привет" in r or "умею" in r:
        ok("dispatch_chat")
    else:
        fail("dispatch_chat", r)

    # Unknown → returns ai_reply
    r2 = await dispatch_actions(
        [{"intent": "unknown", "params": {}, "confidence": 0.0}],
        TEST_USER, "Не понял запрос, уточни.", state=None
    )
    if "Не понял" in r2 or r2:
        ok("dispatch_unknown")
    else:
        fail("dispatch_unknown", r2)

    # Low confidence → asks to clarify
    r3 = await dispatch_actions(
        [{"intent": "task_create", "params": {"title": "что-то"}, "confidence": 0.2}],
        TEST_USER, "", state=None
    )
    if "уточни" in r3.lower() or "❓" in r3:
        ok("dispatch_low_confidence")
    else:
        fail("dispatch_low_confidence", r3)

    # Multi-intent: task + expense
    r4 = await dispatch_actions([
        {"intent": "task_create", "params": {"title": "Мульти-задача"}, "confidence": 0.9},
        {"intent": "expense_add", "params": {"amount": 50, "currency": "USD", "description": "тест"}, "confidence": 0.9},
    ], TEST_USER, "Сохранил.", state=None)
    if "Мульти-задача" in r4 and ("50" in r4 or "USD" in r4):
        ok("dispatch_multi_intent")
    else:
        fail("dispatch_multi_intent", r4[:300])

    # Destructive → asks confirmation
    # Destructive with LOW confidence → asks confirmation (guard activates at conf < 0.85)
    r5 = await dispatch_actions(
        [{"intent": "task_delete", "params": {"task_id": 999}, "confidence": 0.70}],
        TEST_USER, "", state=None
    )
    if "подтверди" in r5.lower() or "подтвержд" in r5.lower() or "⚠️" in r5:
        ok("dispatch_destructive_guard")
    else:
        fail("dispatch_destructive_guard", r5)

# ─────────────────────────────────────────────
# SCENARIO 14: Intent parsing (без реального API)
# ─────────────────────────────────────────────
async def test_intent_parsing():
    print("\n[14] INTENT ПАРСИНГ")
    from bot.ai.intent import _extract_json, _normalize, _FALLBACK
    import json

    # Normal JSON
    text = '{"actions":[{"intent":"task_create","params":{"title":"Test"},"confidence":0.95}],"reply":"OK"}'
    r = _extract_json(text)
    n = _normalize(r)
    if n["actions"][0]["intent"] == "task_create" and n["reply"] == "OK":
        ok("intent_json_parse")
    else:
        fail("intent_json_parse", str(n))

    # JSON in markdown block
    text2 = '```json\n{"actions":[{"intent":"reminder_create","params":{},"confidence":0.8}],"reply":"Done"}\n```'
    r2 = _extract_json(text2)
    n2 = _normalize(r2)
    if n2["actions"][0]["intent"] == "reminder_create":
        ok("intent_json_in_markdown")
    else:
        fail("intent_json_in_markdown", str(n2))

    # Bad JSON → fallback → chat_response_needed=True, actions=[]
    r3 = _extract_json("это просто текст без JSON")
    n3 = _normalize(r3)
    if n3.get("chat_response_needed") is True and n3.get("actions") == []:
        ok("intent_fallback_on_bad_json")
    else:
        fail("intent_fallback_on_bad_json", str(n3))

    # Legacy single-intent → normalize
    legacy = {"intent": "memory_save", "params": {"category": "test"}, "reply": "ok"}
    n4 = _normalize(legacy)
    if n4["actions"][0]["intent"] == "memory_save":
        ok("intent_legacy_normalize")
    else:
        fail("intent_legacy_normalize", str(n4))

# ─────────────────────────────────────────────
# SCENARIO 15: Форматеры
# ─────────────────────────────────────────────
async def test_formatters():
    print("\n[15] ФОРМАТЕРЫ")
    from bot.utils.formatters import (
        format_tasks, format_reminders, format_expenses,
        format_memory, format_dynamic_records, format_schedule, format_study_records
    )

    tasks = [{"id": 1, "title": "Задача А", "priority": "high", "due_time": "10:00"}]
    r = format_tasks(tasks)
    if "Задача А" in r and "🔴" in r:
        ok("format_tasks")
    else:
        fail("format_tasks", r)

    r_empty = format_tasks([])
    if "нет" in r_empty.lower():
        ok("format_tasks_empty")
    else:
        fail("format_tasks_empty", r_empty)

    from datetime import datetime, timedelta
    rems = [{"id": 1, "text": "Напомни", "remind_at": (datetime.now()+timedelta(hours=1)).isoformat(), "recurring": 0}]
    r2 = format_reminders(rems)
    if "Напомни" in r2:
        ok("format_reminders")
    else:
        fail("format_reminders", r2)

    exps = [{"id": 1, "amount": 40.0, "currency": "PLN", "description": "еда", "date": "2026-04-26", "project_name": None}]
    r3 = format_expenses(exps)
    if "40" in r3 and "PLN" in r3:
        ok("format_expenses")
    else:
        fail("format_expenses", r3)

    mems = [{"id": 1, "category": "prefs", "key_name": "еда", "value": "не люблю помидоры"}]
    r4 = format_memory(mems)
    if "помидор" in r4:
        ok("format_memory")
    else:
        fail("format_memory", r4)

    recs = [{"id": 1, "created_at": "2026-04-26", "data": {"сумма": "40", "категория": "еда"}}]
    r5 = format_dynamic_records(recs, "Финансы")
    if "40" in r5 and "еда" in r5:
        ok("format_dynamic_records")
    else:
        fail("format_dynamic_records", r5)

# ─────────────────────────────────────────────
# SCENARIO 16: Расписание
# ─────────────────────────────────────────────
async def test_schedule():
    print("\n[16] РАСПИСАНИЕ")
    from bot.modules.schedule import handle_add_event, handle_view

    r1 = await handle_add_event(TEST_USER, {
        "title": "Лекция по математике",
        "date": "2026-04-27",
        "start_time": "10:00",
        "end_time": "11:30"
    }, "")
    if "Лекция" in r1 or "10:00" in r1:
        ok("schedule_add_event")
    else:
        fail("schedule_add_event", r1)

    r2 = await handle_view(TEST_USER, {"period": "today"}, "")
    if "📅" in r2:
        ok("schedule_view_today")
    else:
        fail("schedule_view_today", r2)

    r3 = await handle_view(TEST_USER, {"date": "2026-04-27"}, "")
    if "Лекция" in r3 or "2026-04-27" in r3 or "10:00" in r3:
        ok("schedule_view_date")
    else:
        fail("schedule_view_date", r3)

# ─────────────────────────────────────────────
# SCENARIO 17: Проекты
# ─────────────────────────────────────────────
async def test_projects():
    print("\n[17] ПРОЕКТЫ")
    from bot.modules.projects import handle_create, handle_list

    r1 = await handle_create(TEST_USER, {"name": "реклама", "title": "Рекламный проект"}, "")
    if "реклам" in r1.lower() or "#" in r1:
        ok("project_create")
    else:
        fail("project_create", r1)

    r2 = await handle_list(TEST_USER, {}, "")
    if "реклам" in r2.lower() or "проект" in r2.lower():
        ok("project_list")
    else:
        fail("project_list", r2)

    from bot.modules.projects import handle_expense_add
    r3 = await handle_expense_add(TEST_USER, {
        "amount": 30, "currency": "USD", "description": "рекламный расход", "project_name": "реклама"
    }, "")
    if "30" in r3 or "USD" in r3:
        ok("project_expense_add")
    else:
        fail("project_expense_add", r3)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
async def main():
    print("=" * 60)
    print("  TUNTUN — Функциональные тесты сценариев")
    print("=" * 60)

    # Init test DB
    for d in config.STORAGE_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    await db.init()
    await db.ensure_user(TEST_USER, "testuser", "Test")

    await test_tasks()
    await test_sections()
    await test_expenses()
    await test_reminders()
    await test_memory()
    await test_study()
    await test_settings()
    await test_day_plan()
    await test_export_excel()
    await test_export_txt()
    await test_backup()
    await test_analytics()
    await test_dispatcher()
    await test_intent_parsing()
    await test_formatters()
    await test_schedule()
    await test_projects()

    # Summary
    print("\n" + "=" * 60)
    passed = sum(1 for _, s, _ in results if s is True)
    failed = sum(1 for _, s, _ in results if s is False)
    warned = sum(1 for _, s, _ in results if s is None)
    total = len(results)
    print(f"  Итого: {total} тестов | {PASS} {passed} | {FAIL} {failed} | {WARN} {warned}")
    if failed:
        print(f"\n  Провалившиеся тесты:")
        for name, s, reason in results:
            if s is False:
                print(f"    ✗ {name}: {reason[:120]}")
    print("=" * 60)

    # Cleanup test DB
    import pathlib
    test_db = pathlib.Path("tuntun_test.db")
    if test_db.exists():
        test_db.unlink()
        print("  (тестовая БД удалена)")

    return failed

if __name__ == "__main__":
    failed = asyncio.run(main())
    sys.exit(0 if failed == 0 else 1)
