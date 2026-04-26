from datetime import datetime, timedelta, date
import json
from bot.db.database import db


async def handle_sleep_calc(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    bedtime = params.get("bedtime", "23:00")
    min_hours = int(params.get("min_hours") or 8)

    try:
        bt = datetime.strptime(bedtime, "%H:%M")
    except ValueError:
        return "❌ Неверный формат времени. Укажи в формате HH:MM (например: 23:30)"

    # Add 15 minutes to fall asleep
    sleep_start = bt + timedelta(minutes=15)

    lines = [
        f"🌙 Если ляжешь в {bedtime}:",
        "(учитывает ~15 мин на засыпание + 90-мин. циклы сна)\n",
    ]

    for cycles in range(1, 7):
        wake_time = sleep_start + timedelta(minutes=90 * cycles)
        total_hours = cycles * 1.5

        if total_hours < min_hours:
            continue

        wake_str = wake_time.strftime("%H:%M")
        if cycles == 1:
            cycle_word = "цикл"
        elif cycles in (2, 3, 4):
            cycle_word = "цикла"
        else:
            cycle_word = "циклов"

        recommended = " ← рекомендуется" if total_hours in (min_hours, min_hours + 1.5) else ""
        lines.append(f"  ⏰ {wake_str} — {total_hours:.1f}ч ({cycles} {cycle_word}){recommended}")

    return "\n".join(lines)


async def handle_day_plan(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    plan_date = params.get("date") or date.today().strftime("%Y-%m-%d")
    include_meals = params.get("include_meals", True)

    try:
        d = datetime.strptime(plan_date, "%Y-%m-%d")
        date_label = d.strftime("%d.%m.%Y")
    except ValueError:
        date_label = plan_date

    events = await db.schedule_get_day(user_id, plan_date)
    tasks = await db.task_list(user_id, filter_date=plan_date)

    # Read user wake/sleep settings
    wake_time_setting = await db.setting_get(user_id, "wake_time")
    sleep_time_setting = await db.setting_get(user_id, "sleep_time")
    wake_time = wake_time_setting or "08:00"
    sleep_time = sleep_time_setting or "23:00"
    has_custom_schedule = bool(wake_time_setting or sleep_time_setting)

    blocks = []

    # Wake up block (fact if set, suggestion otherwise)
    wake_label = "🌅 Подъём" if wake_time_setting else "🌅 Подъём (ориентировочно)"
    blocks.append({"time": wake_time, "text": wake_label, "type": "routine"})

    # Events with time — from real DB
    for e in events:
        if e.get("start_time"):
            end = f"–{e['end_time']}" if e.get("end_time") else ""
            blocks.append({"time": e["start_time"], "text": f"📅 {e['title']} {end}".strip(), "type": "event"})

    # Meals — show as suggestions, not facts (unless user added them to schedule)
    if include_meals:
        for meal_time, label in [("08:30", "🍳 Завтрак"), ("13:00", "🍽️ Обед"), ("19:00", "🥗 Ужин")]:
            if meal_time >= wake_time:
                meal_label = f"{label} (предложение)" if not has_custom_schedule else label
                blocks.append({"time": meal_time, "text": meal_label, "type": "meal"})

    # Tasks — from real DB
    for t in tasks:
        if t.get("due_time"):
            blocks.append({"time": t["due_time"], "text": f"✅ {t['title']}", "type": "task"})
        else:
            blocks.append({"time": "flexible", "text": f"✅ {t['title']}", "type": "task"})

    # Sleep block
    sleep_label = "🌙 Отход ко сну" if sleep_time_setting else "🌙 Отход ко сну (ориентировочно)"
    blocks.append({"time": sleep_time, "text": sleep_label, "type": "routine"})

    timed = sorted([b for b in blocks if b["time"] != "flexible"], key=lambda x: x["time"])
    flexible = [b for b in blocks if b["time"] == "flexible"]

    lines = [f"📋 План дня на {date_label}:", ""]

    for b in timed:
        lines.append(f"  {b['time']}  {b['text']}")

    if flexible:
        lines.append("\n📌 Без фиксированного времени:")
        for b in flexible:
            lines.append(f"  • {b['text']}")

    if not timed and not flexible:
        lines.append("Нет запланированных задач и событий.")
        lines.append("Добавь их через обычные сообщения.")

    plan_text = "\n".join(lines)

    # Save plan to daily_plans
    plan_data = {
        "timed": [{"time": b["time"], "text": b["text"]} for b in timed],
        "flexible": [b["text"] for b in flexible],
        "wake_time": wake_time,
        "sleep_time": sleep_time,
    }
    await db.plan_save(user_id, plan_date, plan_data)

    # Save plan in conversation_state for contextual follow-ups ("перенеси завтрак", "убери обед")
    await db.conversation_state_update(
        user_id,
        active_topic="plan",
        active_date=plan_date,
        last_plan_json=json.dumps(plan_data, ensure_ascii=False),
    )

    return plan_text
