import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Accept both TELEGRAM_BOT_TOKEN (preferred) and legacy BOT_TOKEN
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ALLOWED_USER_IDS: list = [
    int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()
]
TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Warsaw")
DB_PATH: str = os.getenv("DATABASE_PATH") or os.getenv("DB_PATH", "tuntun.db")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# Transcription: OPENAI_MODEL_TRANSCRIBE preferred, OPENAI_TRANSCRIBE_MODEL legacy fallback
WHISPER_MODEL: str = (
    os.getenv("OPENAI_MODEL_TRANSCRIBE")
    or os.getenv("OPENAI_TRANSCRIBE_MODEL")
    or "whisper-1"
)

# Multi-model routing
# IMPORTANT: CHAT / REASONING / VISION are stored as raw env values (may be empty).
# bot/ai/model_router.py applies the fallback chain:
#   REASONING → CHAT → OPENAI_MODEL → ROUTER
#   VISION    → CHAT → ROUTER
#   CHAT      → OPENAI_MODEL → ROUTER

# ROUTER — cheap, fast: intent classification only (always has a value)
MODEL_ROUTER: str      = os.getenv("OPENAI_MODEL_ROUTER") or "gpt-4o-mini"

# CHAT — smart: conversations, advice, explanations
# Fallback: OPENAI_MODEL_CHAT -> OPENAI_MODEL -> MODEL_ROUTER
MODEL_CHAT: str        = (
    os.getenv("OPENAI_MODEL_CHAT")
    or OPENAI_MODEL
    or "gpt-4o"
)

# REASONING — strongest: planning, analytics, ambiguous/destructive
# Fallback: OPENAI_MODEL_REASONING -> MODEL_CHAT -> MODEL_ROUTER
MODEL_REASONING: str   = (
    os.getenv("OPENAI_MODEL_REASONING")
    or MODEL_CHAT
    or MODEL_ROUTER
)

# VISION — multimodal: photos, receipts (empty = Vision disabled)
MODEL_VISION: str      = os.getenv("OPENAI_MODEL_VISION", "")

# EMBEDDINGS — reserved for V2 semantic search (not used yet)
MODEL_EMBEDDINGS: str  = os.getenv("OPENAI_MODEL_EMBEDDINGS", "text-embedding-3-small")

# Feature flags
VISION_ENABLED: bool = bool(os.getenv("OPENAI_MODEL_VISION"))  # True only if explicitly set

BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
PHOTOS_DIR = STORAGE_DIR / "photos"
VOICE_DIR = STORAGE_DIR / "voice"
DOCUMENTS_DIR = STORAGE_DIR / "documents"
EXPORTS_DIR = STORAGE_DIR / "exports"
BACKUPS_DIR = STORAGE_DIR / "backups"
LOGS_DIR = BASE_DIR / "logs"

STORAGE_DIRS = [STORAGE_DIR, PHOTOS_DIR, VOICE_DIR, DOCUMENTS_DIR, EXPORTS_DIR, BACKUPS_DIR, LOGS_DIR]

MIN_CONFIDENCE: float = 0.65

# ── Google Integration (optional) ────────────────────────────────────────────
GOOGLE_ENABLED: bool = os.getenv("GOOGLE_ENABLED", "false").lower() == "true"
GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/google_service_account.json"
)
GOOGLE_SPREADSHEET_ID: str = os.getenv("GOOGLE_SPREADSHEET_ID", "")
GOOGLE_DRIVE_ROOT_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
GOOGLE_SYNC_MODE: str = os.getenv("GOOGLE_SYNC_MODE", "local_first")
DESTRUCTIVE_INTENTS: set = {"task_delete", "section_delete", "memory_clear"}
