"""bot/modules/onboarding.py — Онбординг через диалог.

Позволяет настроить бота под пользователя через обычный разговор.

Триггеры:
  "настрой себя под меня"
  "настрой меня"
  "с чего начать?"
  "как настроить тебя?"

Последовательность вопросов сохраняется через conversation_state.onboarding_step.
После завершения — сохраняет настройки и возвращает итог.
"""
from bot.db.database import db


_STEPS = [
    # (key, question, setting_key, description)
    (1, "Во сколько ты обычно встаёшь? Напиши время (например: 09:00)", "wake_time", "Время подъёма"),
    (2, "Во сколько ложишься спать? (например: 23:30)", "sleep_time", "Время сна"),
    (3, "Как ты предпочитаешь получать ответы?\n[1] Коротко\n[2] Нормально\n[3] Подробно", "reply_style", "Стиль ответов"),
    (4, "Как показывать планы?\n[1] Текстом\n[2] Таблицей", "default_view", "Вид планов"),
    (5, "Нужны ли вечерние отчёты? Во сколько? (или напиши «нет»)", "evening_review_time", "Вечерний отчёт"),
    (6, "Нужны ли напоминания пожёстче?\n[1] Мягко\n[2] Обычно\n[3] Жёстко", "reminder_style", "Стиль напоминаний"),
]

_STYLE_MAP = {
    "1": "short", "коротко": "short", "кратко": "short",
    "2": "normal", "нормально": "normal", "обычно": "normal",
    "3": "detailed", "подробно": "detailed", "развёрнуто": "detailed",
}

_VIEW_MAP = {
    "1": "text", "текстом": "text", "текст": "text",
    "2": "table", "таблицей": "table", "таблица": "table",
}

_REMINDER_MAP = {
    "1": "soft", "мягко": "soft",
    "2": "normal", "обычно": "normal",
    "3": "strict", "жёстко": "strict",
}


def _normalize_answer(key: str, answer: str) -> str:
    """Convert user answer to normalized setting value."""
    answer = answer.strip().lower()
    if key == "reply_style":
        return _STYLE_MAP.get(answer, "normal")
    if key == "default_view":
        return _VIEW_MAP.get(answer, "text")
    if key == "reminder_style":
        return _REMINDER_MAP.get(answer, "normal")
    if key in ("wake_time", "sleep_time", "evening_review_time"):
        if answer in ("нет", "no", "-", "не нужно"):
            return ""
        # Try to extract HH:MM
        import re
        m = re.search(r"(\d{1,2})[:\.](\d{2})", answer)
        if m:
            return f"{int(m.group(1)):02d}:{m.group(2)}"
        return answer
    return answer


async def handle_start(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    """Start the onboarding flow."""
    await db.conversation_state_update(user_id, onboarding_step=1, active_topic="onboarding")
    step_key, question, _, _ = _STEPS[0]
    return (
        "🎉 *Настройка TUNTUN под тебя*\n\n"
        "Отвечу на несколько вопросов, чтобы лучше работать с тобой.\n"
        "Можно пропустить любой вопрос — напиши «пропустить» или «нет».\n\n"
        f"**Вопрос 1/{len(_STEPS)}:**\n{question}"
    )


async def handle_onboarding_answer(user_id: int, text: str) -> tuple[str, bool]:
    """Process answer to current onboarding question.

    Returns (response_text, is_done).
    """
    state = await db.conversation_state_get(user_id)
    step = state.get("onboarding_step", 0)

    if step == 0 or step > len(_STEPS):
        return "", False  # not in onboarding

    # Find current step
    step_idx = step - 1
    if step_idx >= len(_STEPS):
        await db.conversation_state_update(user_id, onboarding_step=0, active_topic=None)
        return "", True

    _, _, setting_key, label = _STEPS[step_idx]

    answer = text.strip().lower()
    skip = answer in ("пропустить", "skip", "-", "далее", "следующий")

    if not skip:
        value = _normalize_answer(setting_key, text)
        if value:
            await db.setting_set(user_id, setting_key, value)

    # Move to next step
    next_step = step + 1
    if next_step > len(_STEPS):
        # Done!
        await db.conversation_state_update(user_id, onboarding_step=0, active_topic=None)
        return await _build_summary(user_id), True

    await db.conversation_state_update(user_id, onboarding_step=next_step)
    _, next_question, _, _ = _STEPS[next_step - 1]
    skip_note = " (пропущено)" if skip else ""
    return (
        f"✅ Сохранено{skip_note}.\n\n"
        f"**Вопрос {next_step}/{len(_STEPS)}:**\n{next_question}"
    ), False


async def _build_summary(user_id: int) -> str:
    """Build onboarding completion summary."""
    lines = ["🎉 *Настройка завершена!*\n\nВот что я запомнил:"]
    setting_labels = {
        "wake_time": "⏰ Подъём",
        "sleep_time": "🌙 Сон",
        "reply_style": "💬 Стиль ответов",
        "default_view": "📊 Вид планов",
        "evening_review_time": "📋 Вечерний отчёт",
        "reminder_style": "🔔 Напоминания",
    }
    for key, label in setting_labels.items():
        val = await db.setting_get(user_id, key)
        if val:
            lines.append(f"• {label}: {val}")

    lines.append("\nВсё можно изменить в любой момент — просто напиши, например:")
    lines.append("«отвечай короче», «планы таблицей», «утром план в 9»")
    return "\n".join(lines)


async def is_in_onboarding(user_id: int) -> bool:
    """Check if user is currently in onboarding flow."""
    state = await db.conversation_state_get(user_id)
    step = state.get("onboarding_step", 0)
    topic = state.get("active_topic", "")
    return step > 0 and topic == "onboarding"
