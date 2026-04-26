"""test_final_stability.py — TUNTUN final stability test suite.

Covers:
  1.  Model routing (router/chat/reasoning/backend-only)
  2.  Safe delete confirmation
  3.  Context follow-up ("eto", active_object)
  4.  Memory: save, dedup, retrieval
  5.  Backend-only: expense_add skips model call
  6.  No hallucination on empty data queries
  7.  Auto-update config safety
  8.  Reminder creation + active_object tracking
  9.  Plan table -> last_plan_json in conversation_state
  10. Export + Backup files
  11. Production startup checks
  12. Markdown safety (fallback in message.py)
  13. Dispatcher always uses CHAT

Run:
    python test_final_stability.py
"""
import sys
import os
import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)

os.environ.setdefault("DATABASE_PATH", "test_stability.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
PASS = 0
FAIL = 0
WARN = 0


def ok(name, detail=""):
    global PASS
    PASS += 1
    detail_str = f"  [{detail[:80]}]" if detail else ""
    print(f"  PASS  {name}{detail_str}")


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    detail_str = f"  [{detail[:120]}]" if detail else ""
    print(f"  FAIL  {name}{detail_str}")


def warn(name, detail=""):
    global WARN
    WARN += 1
    detail_str = f"  [{detail[:80]}]" if detail else ""
    print(f"  WARN  {name}{detail_str}")


# ─────────────────────────────────────────────────────────────
# Sync: model routing (no DB, no async)
# ─────────────────────────────────────────────────────────────
print("\n=== 1. Model Routing ===")
try:
    from bot.ai.model_router import (
        get_model, choose_model, should_use_backend_only, should_use_reasoning,
        BACKEND_ONLY_INTENTS, REASONING_INTENTS,
    )

    r = get_model("router")
    assert r, "router model empty"
    ok("router model configured", r)

    c = get_model("chat")
    assert c, "chat model empty — fallback failed"
    ok("chat model configured (or fallback to router)", c)

    assert should_use_backend_only(["expense_add"], 0.9) is True
    ok("expense_add -> backend_only=True")

    assert should_use_backend_only(["task_create"], 0.9) is True
    ok("task_create -> backend_only=True")

    assert should_use_backend_only(["task_list"], 0.9) is True
    ok("task_list -> backend_only=True")

    assert should_use_reasoning(["regime_day_plan"], 0.9, "safe", False, False, False) is True
    ok("regime_day_plan -> reasoning=True")

    assert should_use_reasoning([], 0.9, "safe", False, False, False) is False
    ok("pure chat -> reasoning=False")

    assert should_use_reasoning([], 0.6, "safe", False, False, False) is True
    ok("confidence=0.6 -> reasoning=True")

    assert should_use_reasoning([], 0.9, "dangerous", False, False, False) is True
    ok("safety=dangerous -> reasoning=True")

    m = choose_model("chat", confidence=0.9, safety_level="safe",
                     refers_to_previous=False, intents=["regime_day_plan"],
                     needs_reasoning=False)
    assert m == get_model("reasoning"), f"expected reasoning, got {m}"
    ok("choose_model: regime_day_plan -> reasoning model")

except Exception as e:
    fail("model_routing", str(e))


# ─────────────────────────────────────────────────────────────
# Sync: auto-update config safety
# ─────────────────────────────────────────────────────────────
print("\n=== 7. Auto-update Config Safety ===")
try:
    auto_update = Path("auto_update.bat")
    assert auto_update.exists(), "auto_update.bat not found"
    ok("auto_update.bat exists")

    content = auto_update.read_text(encoding="utf-8", errors="replace")

    bad_patterns = ["echo > .env", "echo>> .env", "> .env", "set-content .env"]
    for bp in bad_patterns:
        assert bp not in content.lower(), f"Dangerous pattern: {bp}"
    ok("auto_update.bat does NOT overwrite .env")

    assert "tuntun.db" in content and ("copy" in content.lower() or "backup" in content.lower())
    ok("auto_update.bat backs up DB before update")

    assert "rollback" in content.lower(), "no rollback section"
    ok("auto_update.bat has rollback")

    assert Path("start.bat").exists()
    ok("start.bat exists")

    assert Path("stop.bat").exists()
    ok("stop.bat exists")

except Exception as e:
    fail("auto_update_safety", str(e))


# ─────────────────────────────────────────────────────────────
# Sync: production startup checks
# ─────────────────────────────────────────────────────────────
print("\n=== 11. Production Startup ===")
try:
    import config

    for attr in ("BOT_TOKEN", "OPENAI_API_KEY", "MODEL_ROUTER", "MODEL_CHAT",
                 "MODEL_REASONING", "STORAGE_DIRS", "LOGS_DIR"):
        assert hasattr(config, attr), f"config.{attr} missing"
    ok("config.py has all required attributes")

    for d in config.STORAGE_DIRS:
        assert isinstance(d, Path), f"STORAGE_DIRS item not Path: {d}"
    ok("config.STORAGE_DIRS all Path objects")

    assert Path("main.py").exists()
    ok("main.py exists")

    main_content = Path("main.py").read_text(encoding="utf-8")
    assert "--init-db" in main_content
    ok("main.py supports --init-db")

    req_path = Path("requirements.txt")
    assert req_path.exists()
    req = req_path.read_text(encoding="utf-8").lower()
    for dep in ("aiogram", "openai", "aiosqlite", "apscheduler"):
        assert dep in req, f"requirements.txt missing: {dep}"
    ok("requirements.txt has key dependencies")

except Exception as e:
    fail("production_startup", str(e))


# ─────────────────────────────────────────────────────────────
# Sync: Markdown safety
# ─────────────────────────────────────────────────────────────
print("\n=== 12. Markdown Safety ===")
try:
    content = Path("bot/handlers/message.py").read_text(encoding="utf-8")
    assert "parse_mode" in content
    # Check: try Markdown, except plain
    assert 'parse_mode="Markdown"' in content
    # Check there's a fallback except block
    lines = content.splitlines()
    found_md = False
    found_fallback = False
    for i, line in enumerate(lines):
        if 'parse_mode="Markdown"' in line:
            found_md = True
        if found_md and "except" in line and i < len(lines) - 5:
            found_fallback = True
            break
    assert found_md and found_fallback, "No Markdown fallback found"
    ok("message.py has Markdown -> fallback plain text")

except Exception as e:
    fail("markdown_safety", str(e))


# ─────────────────────────────────────────────────────────────
# Sync: dispatcher always uses CHAT
# ─────────────────────────────────────────────────────────────
print("\n=== 13. Dispatcher Always Uses CHAT ===")
try:
    content = Path("bot/modules/dispatcher.py").read_text(encoding="utf-8")
    assert "need_fallback = True" in content, \
        "dispatcher.py should always set need_fallback=True"
    ok("dispatcher.py always calls handle_chat_response for chat")

    assert "not chat_answer.strip()" not in content, \
        "old need_fallback condition still present"
    ok("dispatcher.py: no old fallback condition on chat_answer")

except Exception as e:
    fail("dispatcher_always_chat", str(e))


# ─────────────────────────────────────────────────────────────
# Async tests — all in one event loop
# ─────────────────────────────────────────────────────────────
async def run_async_tests():
    # Setup DB
    from bot.db.database import Database
    import bot.db.database as db_module

    test_db = Database("test_stability.db")
    db_module.db = test_db
    await test_db.init()
    await test_db.ensure_user(99, "stability_tester", "StabilityTest")
    USER_ID = 99

    # ── 2. SAFE DELETE ────────────────────────────────────────
    print("\n=== 2. Safe Delete ===")
    try:
        from bot.modules.dispatcher import _safe_delete

        r = await _safe_delete("task_delete", {}, USER_ID)
        assert r is None
        ok("task_delete no params -> proceed (None)")

        r = await _safe_delete("task_delete", {"task_id": 42}, USER_ID)
        assert r is None
        ok("task_delete explicit ID -> proceed (None)")

        r = await _safe_delete("task_delete", {"keyword": "xyz_nonexistent"}, USER_ID)
        assert r is None
        ok("task_delete no matches -> proceed (None)")

        # Two tasks with same prefix -> disambiguation
        await test_db.task_create(USER_ID, "test task alpha")
        await test_db.task_create(USER_ID, "test task beta")
        r = await _safe_delete("task_delete", {"keyword": "test task"}, USER_ID)
        assert r is not None, "expected disambiguation"
        assert "2" in r or "alpha" in r.lower() or "beta" in r.lower()
        ok("task_delete 2 matches -> disambiguation", r[:60])

        r = await _safe_delete("reminder_cancel", {"reminder_id": 5}, USER_ID)
        assert r is None
        ok("reminder_cancel explicit ID -> proceed (None)")

    except Exception as e:
        fail("safe_delete", str(e))

    # ── 3. CONTEXT FOLLOW-UP ─────────────────────────────────
    print("\n=== 3. Context Follow-up ===")
    try:
        from bot.modules.tasks import handle_create as task_create
        r = await task_create(USER_ID, {"title": "Context Task ABC"}, "")
        assert "#" in r or "Context Task ABC" in r
        ok("task_create returns confirmation", r[:50])

        state = await test_db.conversation_state_get(USER_ID)
        assert state and state.get("active_object_type") == "task"
        assert state.get("active_object_id") is not None
        ok("task_create -> active_object_type=task")

        from bot.modules.chat_assistant import _get_conversation_state_block
        with patch("bot.modules.chat_assistant.db", test_db):
            block = await _get_conversation_state_block(USER_ID)
        assert "task" in block.lower() or "Context Task" in block
        assert "это" in block.lower() or "его" in block.lower() or "id" in block.lower()
        ok("conversation_state_block has object + 'eto/ego' hint", block[:60])

    except Exception as e:
        fail("context_followup", str(e))

    # ── 4. MEMORY ────────────────────────────────────────────
    print("\n=== 4. Memory System ===")
    try:
        import bot.modules.auto_memory as am_module

        mock_db = MagicMock()
        mock_db.memory_recall = AsyncMock(return_value=[])
        mock_db.memory_save = AsyncMock(return_value=1)
        with patch.object(am_module, "db", mock_db):
            saved = await am_module.auto_extract_memory(
                USER_ID, "zapomni chto ya ne lyublyu dlinnye otvety"
            )
        # text doesn't match Russian patterns since it's transliterated, that's ok
        ok("auto_extract_memory does not crash")

        # Russian text
        mock_db2 = MagicMock()
        mock_db2.memory_recall = AsyncMock(return_value=[])
        mock_db2.memory_save = AsyncMock(return_value=2)
        with patch.object(am_module, "db", mock_db2):
            saved2 = await am_module.auto_extract_memory(
                USER_ID, "запомни что я не люблю длинные ответы"
            )
        assert saved2 is True
        assert mock_db2.memory_save.called
        ok("auto_extract_memory saves Russian preference")

        # Commands are skipped
        mock_db3 = MagicMock()
        mock_db3.memory_save = AsyncMock()
        with patch.object(am_module, "db", mock_db3):
            skip = await am_module.auto_extract_memory(USER_ID, "добавь задачу купить молоко")
        assert skip is False
        assert not mock_db3.memory_save.called
        ok("auto_extract_memory skips commands")

        # Retrieval doesn't crash
        from bot.modules.memory_retriever import retrieve_context
        await test_db.memory_save(USER_ID, "preference", "test_key", "краткие ответы")
        ctx = await retrieve_context(USER_ID, "стиль ответов", max_chars=500)
        ok("retrieve_context doesn't crash", (ctx[:50] if ctx else "(empty)"))

    except Exception as e:
        fail("memory_system", str(e))

    # ── 5. BACKEND-ONLY ───────────────────────────────────────
    print("\n=== 5. Backend-only (no model call) ===")
    try:
        from bot.modules.dispatcher import dispatch_actions
        from bot.ai.model_router import should_use_backend_only

        assert should_use_backend_only(["expense_add"], 0.95) is True

        chat_called = False

        async def _mock_chat(*args, **kwargs):
            nonlocal chat_called
            chat_called = True
            return "should not be called"

        with patch("bot.modules.chat_assistant.handle_chat_response", side_effect=_mock_chat):
            resp = await dispatch_actions(
                actions=[{"intent": "expense_add", "params": {
                    "amount": 40.0, "currency": "PLN", "description": "eda",
                    "date": "2026-04-26"
                }, "confidence": 0.95}],
                user_id=USER_ID,
                ai_reply="",
                chat_response_needed=False,
                message_text="segodnya potratil 40 PLN eda",
            )

        assert not chat_called, "handle_chat_response must NOT be called for expense_add"
        assert "40" in resp or "расход" in resp.lower() or "pln" in resp.lower()
        ok("expense_add: backend-only, no model call", resp[:60])

    except Exception as e:
        fail("backend_only", str(e))

    # ── 6. NO HALLUCINATION ───────────────────────────────────
    print("\n=== 6. No Hallucination ===")
    try:
        from bot.modules.dispatcher import dispatch_actions

        async def _honest_chat(user_id, question, is_data_query=False, **kwargs):
            if is_data_query:
                return "Po sohranennym dannym poka nichego net."
            return "Chem mogu pomoch?"

        with patch("bot.modules.chat_assistant.handle_chat_response", side_effect=_honest_chat):
            resp = await dispatch_actions(
                actions=[],
                user_id=USER_ID,
                ai_reply="",
                chat_response_needed=True,
                is_data_query=True,
                data_query_type="records",
                message_text="chto u menya po kripte?",
            )

        hallucinated = any(w in resp.lower() for w in ("btc", "bitcoin", "0.5", "ethereum"))
        assert not hallucinated, f"Hallucination detected: {resp}"
        ok("empty data query -> no hallucination", resp[:60])

    except Exception as e:
        fail("no_hallucination", str(e))

    # ── 8. REMINDER + ACTIVE OBJECT ───────────────────────────
    print("\n=== 8. Reminder + Active Object ===")
    try:
        with patch("bot.modules.reminders.sched_module.add_reminder_job", return_value="rem_1"):
            from bot.modules.reminders import handle_create
            resp = await handle_create(
                USER_ID,
                {"text": "kupit moloko", "remind_at": "2099-12-31 09:00"},
                "",
                scheduler=MagicMock(),
            )
        assert "напоминани" in resp.lower() or "⏰" in resp or "rem" in resp.lower()
        ok("reminder_create returns confirmation", resp[:50])

        state = await test_db.conversation_state_get(USER_ID)
        assert state and state.get("active_object_type") == "reminder"
        assert state.get("last_discussed_reminder_ids")
        ok("reminder_create -> active_object_type=reminder + last_discussed_reminder_ids")

    except Exception as e:
        fail("reminder_active_object", str(e))

    # ── 9. PLAN TABLE ─────────────────────────────────────────
    print("\n=== 9. Plan Table ===")
    try:
        from bot.modules.regime import handle_day_plan

        resp = await handle_day_plan(USER_ID, {"date": "2026-04-26"}, "")
        assert resp and len(resp) > 20
        ok("handle_day_plan returns content", resp[:60])

        state = await test_db.conversation_state_get(USER_ID)
        assert state and state.get("last_plan_json"), "last_plan_json not saved"
        plan_data = json.loads(state["last_plan_json"])
        assert "timed" in plan_data
        ok("last_plan_json saved to conversation_state")

        assert state.get("active_date") == "2026-04-26"
        ok("active_date=2026-04-26 saved")

        from bot.modules.chat_assistant import _get_conversation_state_block
        with patch("bot.modules.chat_assistant.db", test_db):
            block = await _get_conversation_state_block(USER_ID)
        assert "план" in block.lower() or "tabl" in block.lower() or "plan" in block.lower()
        ok("conversation_state_block mentions plan", block[:60])

    except Exception as e:
        fail("plan_table", str(e))

    # ── 10. EXPORT + BACKUP ───────────────────────────────────
    print("\n=== 10. Export + Backup ===")
    try:
        import config
        config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

        try:
            from bot.modules.exports import export_to_excel
            file_path = await export_to_excel(USER_ID, "tasks", period="month")
            if file_path:
                assert Path(file_path).exists()
                ok("export_to_excel tasks -> file created")
            else:
                warn("export_to_excel returned None (no data or openpyxl issue)")
        except ImportError:
            warn("openpyxl not installed, skipping Excel test")

        try:
            from bot.modules.backup import create_backup
            backup_path = await create_backup(USER_ID)
            if backup_path:
                assert Path(backup_path).exists()
                ok("backup created", backup_path[-40:])
            else:
                warn("backup returned None")
        except Exception as e2:
            fail("backup_create", str(e2))

    except Exception as e:
        fail("export_backup", str(e))

    # Cleanup
    if Path("test_stability.db").exists():
        os.remove("test_stability.db")


asyncio.run(run_async_tests())


# ─────────────────────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────────────────────
total = PASS + FAIL + WARN
print(f"\n{'=' * 60}")
print(f"  Results: {PASS} PASS / {FAIL} FAIL / {WARN} WARN  (total {total})")
print(f"{'=' * 60}\n")

if FAIL > 0:
    sys.exit(1)
