"""bot/modules/settings_manager.py — Conversational settings for TUNTUN.

Detects and applies setting changes from natural language messages.
Manages reply_style, default_view, and other user preferences.

Usage:
    # Apply reply_style to a generated response:
    from bot.modules.settings_manager import apply_reply_style
    response = await apply_reply_style(response_text, user_id)

    # Get all settings as a dict:
    settings = await get_user_settings(user_id)

    # Auto-save setting from AI classified intent:
    await apply_settings_update(user_id, classify_result)
"""
from bot.db.database import db

# ──────────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────────

DEFAULTS = {
    "reply_style": "normal",
    "default_view": "text",
    "style_mode": "standard",
    "proactive_enabled": "true",
    "planning_style": "flexible",
    "reminder_style": "normal",
    "voice_enabled": "false",
}

# ──────────────────────────────────────────────────────────────
# Reply style application
# ──────────────────────────────────────────────────────────────

_SHORT_MAX_CHARS = 300
_DETAILED_MIN_CHARS = 400


def shorten_response(text: str) -> str:
    """Truncate response for 'short' reply_style — keep first ~2-3 sentences."""
    if len(text) <= _SHORT_MAX_CHARS:
        return text

    sentences = text.split(". ")
    result = ""
    for sentence in sentences:
        if len(result) + len(sentence) + 2 > _SHORT_MAX_CHARS:
            break
        result += sentence + ". "

    result = result.strip()
    if not result:
        result = text[:_SHORT_MAX_CHARS] + "…"
    elif len(result) < len(text) - 10:
        result = result.rstrip(". ") + "."

    return result


async def apply_reply_style(response: str, user_id: int) -> str:
    """Adjust response length based on user's reply_style setting."""
    style = await db.setting_get(user_id, "reply_style") or DEFAULTS["reply_style"]

    if style == "short":
        return shorten_response(response)
    # "normal" and "detailed" — return as-is (detailed adds context in prompts)
    return response


# ──────────────────────────────────────────────────────────────
# Get all user settings
# ──────────────────────────────────────────────────────────────

async def get_user_settings(user_id: int) -> dict:
    """Return all user settings with defaults filled in."""
    rows = await db._fetchall(
        "SELECT key, value FROM settings WHERE user_id=?", (user_id,)
    )
    settings = dict(DEFAULTS)
    for row in rows:
        settings[row["key"]] = row["value"]
    return settings


# ──────────────────────────────────────────────────────────────
# Auto-save settings from classified AI result
# ──────────────────────────────────────────────────────────────

async def apply_settings_update(user_id: int, classify_result: dict) -> bool:
    """If AI flagged settings_update_needed, save reply_style and related keys.

    Returns True if any setting was saved.
    """
    if not classify_result.get("settings_update_needed"):
        return False

    saved = False

    # reply_style can come either from top-level or from actions[].params
    reply_style = classify_result.get("reply_style")
    if reply_style and reply_style in ("short", "normal", "detailed"):
        await db.setting_set(user_id, "reply_style", reply_style)
        saved = True

    # Also scan actions for setting_save intents
    for action in classify_result.get("actions", []):
        if action.get("intent") == "setting_save":
            params = action.get("params", {})
            key = params.get("key", "")
            value = params.get("value", "")
            if key and value:
                await db.setting_set(user_id, key, value)
                saved = True

    return saved


# ──────────────────────────────────────────────────────────────
# Context injection for prompts
# ──────────────────────────────────────────────────────────────

async def get_style_context(user_id: int) -> str:
    """Return short style hint for injection into AI system prompt."""
    settings = await get_user_settings(user_id)
    parts = []

    style = settings.get("reply_style", "normal")
    if style == "short":
        parts.append("Отвечай кратко — 1-3 предложения.")
    elif style == "detailed":
        parts.append("Отвечай развёрнуто — давай подробные объяснения.")

    view = settings.get("default_view", "text")
    if view == "table":
        parts.append("Планы и списки показывай в виде таблиц.")

    mode = settings.get("style_mode", "standard")
    if mode == "student":
        parts.append("Используй студенческий стиль — дружелюбно, по-простому.")
    elif mode == "business":
        parts.append("Используй деловой стиль — чётко, без лишних слов.")
    elif mode == "minimal":
        parts.append("Минималистичный стиль — только самое важное.")

    planning = settings.get("planning_style", "flexible")
    if planning == "strict":
        parts.append("Планирование строгое — конкретное время для каждой задачи.")
    elif planning == "student":
        parts.append("Планирование в студенческом стиле — с учётом пар и дедлайнов.")

    return " ".join(parts) if parts else ""
