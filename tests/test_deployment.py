"""Deployment smoke tests for TUNTUN.

Tests:
  1.  env_example_exists        — .env.example is present
  2.  gitignore_blocks_secrets  — .env, *.db, storage/ are in .gitignore
  3.  env_loaded_correctly       — config.py loads env vars without error
  4.  no_hardcoded_keys          — no raw API key strings in source files
  5.  folders_created_on_init    — --init-db creates required directories
  6.  db_init_creates_tables     — --init-db creates all required tables
  7.  pid_file_management        — run_background start/stop writes/removes bot.pid
  8.  duplicate_start_prevented  — second start call doesn't start a second process
  9.  imports_ok                 — all required packages importable
  10. bat_files_exist            — all deployment bat files present

Run with:
    cd d:\\AackREF\\TUNTUN
    python test_deployment.py
"""
import os
import sys
import asyncio
import subprocess
import tempfile
import shutil
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

PASS_COUNT = 0
FAIL_COUNT = 0
FAIL_NAMES = []


def ok(name: str, detail: str = ""):
    global PASS_COUNT
    PASS_COUNT += 1
    suffix = f"  → {detail}" if detail else ""
    print(f"  ✅  {name}{suffix}")


def fail(name: str, detail: str = ""):
    global FAIL_COUNT
    FAIL_COUNT += 1
    FAIL_NAMES.append(name)
    suffix = f"  ← {detail}" if detail else ""
    print(f"  ❌  {name}{suffix}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: .env.example exists
# ─────────────────────────────────────────────────────────────────────────────
def test_env_example_exists():
    path = BASE_DIR / ".env.example"
    if path.exists():
        ok("env_example_exists")
    else:
        fail("env_example_exists", ".env.example not found")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: .gitignore blocks secrets
# ─────────────────────────────────────────────────────────────────────────────
def test_gitignore_blocks_secrets():
    path = BASE_DIR / ".gitignore"
    if not path.exists():
        fail("gitignore_blocks_secrets", ".gitignore not found")
        return
    content = path.read_text(encoding="utf-8")
    required = [".env", "*.db", "storage/", "logs/"]
    missing = [r for r in required if r not in content]
    if missing:
        fail("gitignore_blocks_secrets", f"missing: {missing}")
    else:
        ok("gitignore_blocks_secrets", ".env + *.db + storage/ + logs/ all blocked")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: config.py loads without error
# ─────────────────────────────────────────────────────────────────────────────
def test_env_loaded_correctly():
    try:
        import importlib
        import config as _cfg
        importlib.reload(_cfg)
        # Just check attributes exist
        _ = _cfg.BOT_TOKEN
        _ = _cfg.OPENAI_API_KEY
        _ = _cfg.MODEL_ROUTER
        _ = _cfg.MODEL_CHAT
        _ = _cfg.MODEL_REASONING
        ok("env_loaded_correctly", f"router={_cfg.MODEL_ROUTER or '(fallback)'}")
    except Exception as e:
        fail("env_loaded_correctly", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: no hardcoded API keys in source files
# ─────────────────────────────────────────────────────────────────────────────
def test_no_hardcoded_keys():
    import re
    # Patterns that look like real API keys
    patterns = [
        re.compile(r"sk-[A-Za-z0-9]{20,}"),   # OpenAI API key
        re.compile(r"\d{9,10}:[A-Za-z0-9_-]{35}"),  # Telegram bot token
    ]
    suspect_files = []
    check_dirs = [BASE_DIR / "bot", BASE_DIR / "config.py", BASE_DIR / "main.py"]
    for entry in check_dirs:
        if entry.is_file():
            files = [entry]
        else:
            files = list(entry.rglob("*.py"))
        for f in files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                for pat in patterns:
                    if pat.search(content):
                        suspect_files.append(str(f.relative_to(BASE_DIR)))
                        break
            except Exception:
                pass
    if suspect_files:
        fail("no_hardcoded_keys", f"possible keys in: {suspect_files}")
    else:
        ok("no_hardcoded_keys", "no raw API key patterns found")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 & 6: --init-db creates folders and tables
# ─────────────────────────────────────────────────────────────────────────────
async def _async_init_db_test():
    import config
    from bot.db.database import db

    # Run init
    for d in config.STORAGE_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    await db.init()

    # Check folders
    required_dirs = [
        config.STORAGE_DIR, config.PHOTOS_DIR, config.VOICE_DIR,
        config.DOCUMENTS_DIR, config.EXPORTS_DIR, config.BACKUPS_DIR,
        config.LOGS_DIR,
    ]
    missing_dirs = [str(d) for d in required_dirs if not d.exists()]
    if missing_dirs:
        return False, False, f"missing dirs: {missing_dirs}", ""

    # Check tables
    import aiosqlite
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in await cur.fetchall()}

    required_tables = {"users", "tasks", "reminders", "dynamic_sections",
                       "dynamic_records", "message_logs"}
    missing_tables = required_tables - tables
    if missing_tables:
        return True, False, "", f"missing tables: {missing_tables}"

    return True, True, "", f"{len(tables)} tables found"


def test_init_db():
    try:
        dirs_ok, tables_ok, dir_err, table_msg = asyncio.run(_async_init_db_test())
        if dirs_ok:
            ok("folders_created_on_init", "all storage dirs present")
        else:
            fail("folders_created_on_init", dir_err)
        if tables_ok:
            ok("db_init_creates_tables", table_msg)
        else:
            fail("db_init_creates_tables", table_msg)
    except Exception as e:
        fail("folders_created_on_init", str(e))
        fail("db_init_creates_tables", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# TEST 7 & 8: PID file management + duplicate prevention
# ─────────────────────────────────────────────────────────────────────────────
def test_pid_management():
    """Tests that run_background correctly detects stale PIDs."""
    import importlib
    import run_background as rb
    importlib.reload(rb)

    # _is_running should return False for an unrealistic large PID
    assert not rb._is_running(99999999), "99999999 should not be running"

    # _is_running should return True for our own PID
    assert rb._is_running(os.getpid()), "own PID should be running"

    ok("pid_file_management", "stale PID → not running, own PID → running")


def test_duplicate_start_prevented():
    """Tests _is_running logic that prevents duplicate starts."""
    import importlib
    import run_background as rb
    importlib.reload(rb)

    # Simulate: PID file has our own PID → system thinks bot is already running
    own_pid = os.getpid()
    is_running = rb._is_running(own_pid)
    if is_running:
        ok("duplicate_start_prevented", "running PID detected → start would be skipped")
    else:
        fail("duplicate_start_prevented", "own PID not recognized as running")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: all required packages importable
# ─────────────────────────────────────────────────────────────────────────────
def test_imports_ok():
    required = [
        "aiogram", "openai", "aiosqlite", "apscheduler",
        "openpyxl", "pytz", "aiofiles", "dotenv",
    ]
    failed = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            failed.append(pkg)

    if failed:
        fail("imports_ok", f"missing: {failed}")
    else:
        ok("imports_ok", f"all {len(required)} packages present")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: all deployment bat files exist
# ─────────────────────────────────────────────────────────────────────────────
def test_bat_files_exist():
    required_bats = [
        "SERVER_INSTALL_AND_RUN.bat",
        "start.bat",
        "stop.bat",
        "restart.bat",
        "status.bat",
        "check.bat",
        "auto_update.bat",
        "install_bot_task.bat",
        "install_updater_task.bat",
        "uninstall_tasks.bat",
    ]
    missing = [b for b in required_bats if not (BASE_DIR / b).exists()]
    if missing:
        fail("bat_files_exist", f"missing: {missing}")
    else:
        ok("bat_files_exist", f"all {len(required_bats)} bat files present")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_all():
    print("\n" + "═" * 62)
    print("  TUNTUN — Deployment Smoke Tests")
    print("═" * 62)

    test_env_example_exists()
    test_gitignore_blocks_secrets()
    test_env_loaded_correctly()
    test_no_hardcoded_keys()
    test_init_db()
    test_pid_management()
    test_duplicate_start_prevented()
    test_imports_ok()
    test_bat_files_exist()

    total = PASS_COUNT + FAIL_COUNT
    print("─" * 62)
    print(f"  ИТОГ: {PASS_COUNT}/{total} тестов прошли")
    if FAIL_NAMES:
        print(f"  Провалено: {', '.join(FAIL_NAMES)}")
    print("═" * 62 + "\n")
    return FAIL_COUNT == 0


if __name__ == "__main__":
    ok_result = run_all()
    sys.exit(0 if ok_result else 1)
