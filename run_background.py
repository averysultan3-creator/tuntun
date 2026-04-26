"""
run_background.py — TUNTUN process manager helper.

Usage:
    python run_background.py start   — start bot, write PID to bot.pid
    python run_background.py stop    — stop bot by PID from bot.pid
    python run_background.py status  — check if bot is running
    python run_background.py pid     — print current PID or 0

Called from start.bat / stop.bat automatically.
"""
import sys
import os
import subprocess
import signal
from pathlib import Path

BASE_DIR = Path(__file__).parent
PID_FILE = BASE_DIR / "bot.pid"
LOG_FILE = BASE_DIR / "logs" / "runtime.log"


def _read_pid() -> int:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return 0


def _is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # On Windows, os.kill(pid, 0) sends CTRL_C_EVENT to the whole console
        # group — DO NOT use it for process existence checks.
        # Use OpenProcess (Win32 API) instead: it returns 0 only if the PID
        # does not exist or we have no permission to open it.
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def cmd_start():
    pid = _read_pid()
    if _is_running(pid):
        print(f"[WARN] TUNTUN already running (PID {pid}). Not starting again.")
        sys.exit(0)

    # Ensure logs dir exists
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Find python executable (prefer .venv)
    venv_python = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    log_handle = open(LOG_FILE, "a", encoding="utf-8", buffering=1)

    # Launch main.py as a detached background process
    proc = subprocess.Popen(
        [python_exe, str(BASE_DIR / "main.py")],
        stdout=log_handle,
        stderr=log_handle,
        cwd=str(BASE_DIR),
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        if sys.platform == "win32" else 0,
    )

    PID_FILE.write_text(str(proc.pid))
    print(f"[OK] TUNTUN started (PID {proc.pid}). Log: {LOG_FILE}")
    sys.exit(0)


def cmd_stop():
    pid = _read_pid()
    if not _is_running(pid):
        print(f"[INFO] TUNTUN is not running (PID file: {pid or 'none'}).")
        if PID_FILE.exists():
            PID_FILE.unlink()
        sys.exit(0)

    print(f"[*] Stopping TUNTUN (PID {pid})...")
    try:
        if sys.platform == "win32":
            subprocess.call(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print(f"[WARN] Could not stop PID {pid}: {e}")

    PID_FILE.unlink(missing_ok=True)
    print(f"[OK] Stopped.")
    sys.exit(0)


def cmd_status():
    pid = _read_pid()
    if _is_running(pid):
        print(f"running")
        print(f"PID: {pid}")
        sys.exit(0)
    else:
        print(f"stopped")
        if pid:
            print(f"stale PID: {pid}")
        sys.exit(1)


def cmd_pid():
    pid = _read_pid()
    if _is_running(pid):
        print(pid)
    else:
        print(0)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    elif cmd == "pid":
        cmd_pid()
    else:
        print(f"Usage: python run_background.py start|stop|status|pid")
        sys.exit(1)
