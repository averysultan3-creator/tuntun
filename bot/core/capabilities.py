"""TUNTUN capabilities registry.

Single source of truth for what the bot can do.
Used in:
  - chat_assistant.py  → injected into system prompt
  - prompts.py        → tells router about vision availability
  - photo.py          → checks if vision is enabled before calling OpenAI

Usage:
    from bot.core.capabilities import CAPABILITIES_TEXT, is_vision_enabled
"""
import config

# ──────────────────────────────────────────────────────────────
# Capabilities list (human-readable, injected into prompts)
# ──────────────────────────────────────────────────────────────
_CAPS_ALWAYS = [
    "📝 Задачи — создавать, выполнять, искать, удалять",
    "⏰ Напоминания — одноразовые и повторяющиеся",
    "🎙️ Голос — транскрипция через Whisper → действия",
    "📂 Динамические базы/разделы — финансы, реклама, учёба, любые",
    "🧠 Память — факты о пользователе, привычки, настройки",
    "💰 Расходы — трекинг, аналитика по периодам",
    "📊 Аналитика — суммы, статистика задач, разделов",
    "📅 Расписание — события, план дня с едой и сном",
    "🌙 Режим — расчёт времени подъёма, план дня",
    "📤 Экспорт — Excel (openpyxl), TXT",
    "💾 Backup — полная резервная копия базы",
    "📚 Учёба — предметы, долги, задания",
    "🔍 Умный retrieval — поиск по всей базе данных",
    "💬 ChatGPT-режим — советы, планирование, объяснения",
    "🔄 Мульти-действия — несколько команд в одном сообщении",
    "💡 Идеи — сохранять, просматривать, конвертировать в задачи",
    "⚙️ Настройки через диалог — стиль, режим, планирование, напоминания",
]

_CAPS_VISION = [
    "📸 Анализ фото — скриншоты, чеки, документы, расписания, задания",
    "🧾 Чеки → расходы — автоматическое извлечение суммы, категории",
    "📋 Фото задания → study record + помощь с решением",
    "🖼️ Сохранение фото с привязкой к разделу и поиском по ним",
]


def is_vision_enabled() -> bool:
    """True if OPENAI_MODEL_VISION is set in .env."""
    return config.VISION_ENABLED


def get_capabilities_list() -> list[str]:
    """Return list of capability strings depending on current config."""
    caps = list(_CAPS_ALWAYS)
    if is_vision_enabled():
        caps.extend(_CAPS_VISION)
    else:
        caps.append("📸 Фото — сохранение (анализ доступен при настройке OPENAI_MODEL_VISION)")
    return caps


def get_capabilities_text() -> str:
    """Human-readable multiline capabilities block for system prompts."""
    return "\n".join(get_capabilities_list())


# Short version for router prompt (keeps token count low)
CAPABILITIES_SHORT = (
    "Умеешь: задачи, напоминания, голос→действия, базы данных, финансы, память, "
    "план дня, экспорт Excel/TXT, backup, учёба, аналитика, ChatGPT-режим"
    + (", анализ фото/чеков/документов" if is_vision_enabled() else "")
    + "."
)

# Model info block for "какая модель?" questions
MODEL_INFO = (
    f"Router: {config.MODEL_ROUTER} | "
    f"Chat: {config.MODEL_CHAT} | "
    f"Vision: {config.MODEL_VISION} | "
    f"Transcribe: {config.WHISPER_MODEL}"
)
