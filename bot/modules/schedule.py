from datetime import date, timedelta, datetime
from bot.db.database import db
from bot.utils.formatters import format_schedule


async def handle_view(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    period = params.get("period", "today")
    filter_date = params.get("date")
    today = date.today()

    if not filter_date:
        if period == "today":
            filter_date = today.strftime("%Y-%m-%d")
        elif period == "tomorrow":
            filter_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")

    if filter_date:
        events = await db.schedule_get_day(user_id, filter_date)
        try:
            d = datetime.strptime(filter_date, "%Y-%m-%d")
            title = f"Расписание на {d.strftime('%d.%m.%Y')}"
        except ValueError:
            title = "Расписание"
        return format_schedule(events, title)

    # Range view (week/month/year)
    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        label = "эту неделю"
    elif period == "month":
        start = today.replace(day=1)
        next_month = (start.replace(month=start.month % 12 + 1, day=1)
                      if start.month < 12 else start.replace(year=start.year + 1, month=1, day=1))
        end = next_month - timedelta(days=1)
        label = "этот месяц"
    else:
        start = today
        end = today + timedelta(days=365)
        label = "год"

    events = await db.schedule_get_range(
        user_id, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
    )
    return format_schedule(events, f"Расписание на {label}")


async def handle_add_event(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    title = params.get("title", "").strip()
    if not title:
        return "❌ Укажи название события"

    event_date = params.get("date")
    start_time = params.get("start_time")
    end_time = params.get("end_time")
    recurring = bool(params.get("recurring", False))

    eid = await db.schedule_add_event(
        user_id, title, event_date, start_time, end_time, recurring
    )

    date_str = f" {event_date}" if event_date else ""
    time_str = ""
    if start_time:
        time_str = f" в {start_time}"
        if end_time:
            time_str += f"–{end_time}"
    recurring_str = " (повторяется)" if recurring else ""

    return f"📅 Событие добавлено: {title}{date_str}{time_str}{recurring_str} #{eid}"


async def handle_plan_day(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    plan_date = params.get("date") or date.today().strftime("%Y-%m-%d")
    try:
        d = datetime.strptime(plan_date, "%Y-%m-%d")
        date_label = d.strftime("%d.%m.%Y")
    except ValueError:
        date_label = plan_date

    events = await db.schedule_get_day(user_id, plan_date)
    tasks = await db.task_list(user_id, filter_date=plan_date)

    lines = [f"📋 План на {date_label}:", ""]

    if events:
        lines.append("📅 События:")
        for e in events:
            time_str = f" {e['start_time']}" if e.get("start_time") else ""
            if e.get("end_time"):
                time_str += f"–{e['end_time']}"
            lines.append(f"  • {e['title']}{time_str}")
        lines.append("")

    if tasks:
        lines.append("✅ Задачи:")
        for t in tasks:
            time_str = f" в {t['due_time']}" if t.get("due_time") else ""
            lines.append(f"  • {t['title']}{time_str}")
        lines.append("")

    if not events and not tasks:
        lines.append("Записей нет. Добавь задачи и события через обычные сообщения.")

    constraints = params.get("constraints")
    if constraints:
        lines.append(f"ℹ️ Условия: {constraints}")

    return "\n".join(lines)
