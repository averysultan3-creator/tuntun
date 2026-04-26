from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.db.database import db
from bot.utils.formatters import format_reminders
import bot.utils.scheduler as sched_module


def reminder_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Сделано", callback_data=f"rem_done:{reminder_id}"),
            InlineKeyboardButton(text="⏰ Отложить", callback_data=f"rem_snooze_pick:{reminder_id}"),
        ],
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"rem_cancel:{reminder_id}"),
        ],
    ])


async def handle_create(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    text = params.get("text", "Напоминание").strip()
    remind_at = params.get("remind_at", "")
    recurring = bool(params.get("recurring", False))
    interval_minutes = params.get("interval_minutes")

    if not remind_at:
        return "❌ Укажи время напоминания (например: напомни завтра в 12:00)"

    remind_at_clean = remind_at.replace("T", " ")
    if len(remind_at_clean) == 16:
        remind_at_clean += ":00"

    rid = await db.reminder_create(
        user_id=user_id, text=text, remind_at=remind_at_clean,
        recurring=recurring,
        interval_minutes=int(interval_minutes) if interval_minutes else None,
    )

    job_id = sched_module.add_reminder_job(
        reminder_id=rid, user_id=user_id, text=text,
        remind_at_str=remind_at_clean, recurring=recurring,
        interval_minutes=int(interval_minutes) if interval_minutes else None,
    )
    await db.reminder_update_job_id(rid, job_id)

    try:
        from datetime import datetime
        dt = datetime.fromisoformat(remind_at_clean)
        dt_str = dt.strftime("%d.%m.%Y в %H:%M")
    except Exception:
        dt_str = remind_at_clean

    recurring_str = " (повторяющееся)" if recurring else ""

    # Save active object for contextual follow-ups ("отмени это")
    await db.conversation_state_update(
        user_id,
        active_topic="reminder",
        active_object_type="reminder",
        active_object_id=rid,
        last_discussed_reminder_ids=str(rid),
    )

    return f"⏰ Напоминание #{rid} на {dt_str}{recurring_str}:\n{text}"


async def handle_list(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    reminders = await db.reminder_list(user_id)
    return format_reminders(reminders)


async def handle_cancel(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    reminder_id = params.get("reminder_id")
    keyword = params.get("keyword", "")

    if reminder_id:
        reminder = await db.reminder_cancel(user_id, int(reminder_id))
        if reminder:
            sched_module.cancel_reminder_job(int(reminder_id))
            return f"✅ Напоминание #{reminder_id} отменено"
        return f"❌ Напоминание #{reminder_id} не найдено"

    if keyword:
        rem_list = await db.reminder_list(user_id)
        found = [r for r in rem_list if keyword.lower() in r["text"].lower()]
        if not found:
            return f"❌ Напоминание по «{keyword}» не найдено"
        if len(found) == 1:
            r = found[0]
            await db.reminder_cancel(user_id, r["id"])
            sched_module.cancel_reminder_job(r["id"])
            return f"✅ Напоминание #{r['id']} отменено: {r['text']}"
        lines = [f"Найдено несколько по «{keyword}»:"]
        for r in found:
            lines.append(f"  #{r['id']}: {r['text']}")
        lines.append("\nНапиши: отмени напоминание #N")
        return "\n".join(lines)

    return "Укажи номер или текст напоминания"
