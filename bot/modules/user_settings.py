from bot.db.database import db

_SETTING_LABELS = {
    # Schedule
    "wake_time": "время подъёма",
    "sleep_time": "время отхода ко сну",
    "timezone": "часовой пояс",
    "language": "язык",
    "work_start": "начало рабочего дня",
    "work_end": "конец рабочего дня",
    "lunch_time": "обеденное время",
    # Communication style
    "reply_style": "стиль ответов (short/normal/detailed)",
    "default_view": "вид планов (text/table/card)",
    "style_mode": "режим стиля (standard/student/business/minimal)",
    "voice_enabled": "голосовые ответы",
    "vision_enabled": "анализ фото",
    # Proactivity
    "proactive_enabled": "проактивные подсказки",
    "morning_plan_time": "время утреннего плана",
    "evening_review_time": "время вечернего обзора",
    # Planning
    "planning_style": "стиль планирования (strict/flexible/student/work)",
    "reminder_style": "стиль напоминаний (soft/normal/strict)",
}


async def handle_save(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    key = params.get("key", "").strip()
    value = params.get("value", "").strip()

    if not key or not value:
        return "❌ Укажи что и какое значение сохранить"

    await db.setting_set(user_id, key, value)

    label = _SETTING_LABELS.get(key, key)
    return f"⚙️ Сохранено: {label} = {value}"


async def handle_get(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    key = params.get("key", "").strip()

    if key:
        value = await db.setting_get(user_id, key)
        label = _SETTING_LABELS.get(key, key)
        if value:
            return f"⚙️ {label}: {value}"
        return f"⚙️ Настройка «{label}» не задана"

    # Return all settings
    rows = await db._fetchall(
        "SELECT key, value FROM settings WHERE user_id=? ORDER BY key", (user_id,)
    )
    if not rows:
        return "⚙️ Настройки не заданы"

    lines = ["⚙️ Твои настройки:"]
    for r in rows:
        label = _SETTING_LABELS.get(r["key"], r["key"])
        lines.append(f"  • {label}: {r['value']}")
    return "\n".join(lines)
