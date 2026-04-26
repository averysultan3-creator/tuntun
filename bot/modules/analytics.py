from datetime import date, timedelta
from bot.db.database import db
from bot.utils.date_parser import parse_date_range


def _resolve_period(period: str):
    """Convert period string to (start, end, label).

    Handles standard keywords AND free-form text via date_parser.
    """
    today = date.today()
    _KEYWORDS = {
        "today":   (today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), "сегодня"),
        "week":    ((today - timedelta(days=7)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), "за 7 дней"),
        "month":   (today.replace(day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), f"за {today.strftime('%B').lower()}"),
        "year":    (today.replace(month=1, day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"), f"за {today.year}"),
        "all":     (None, None, "за всё время"),
    }
    if period in _KEYWORDS:
        return _KEYWORDS[period]

    # Fallback: try to parse as free-form date expression
    d_from, d_to = parse_date_range(period or "")
    if d_from:
        label = f"{d_from} — {d_to}" if d_from != d_to else d_from
        return d_from, d_to, label

    return None, None, "за всё время"


async def handle_query(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    query_type = params.get("query_type", "overview")
    period = params.get("period", "month")

    # Normalise aliases from AI prompt (expenses_total → expenses, tasks_stats → tasks, section_stats → sections)
    _ALIASES = {
        "expenses_total": "expenses",
        "tasks_stats": "tasks",
        "section_stats": "sections",
    }
    query_type = _ALIASES.get(query_type, query_type)

    start, end, period_label = _resolve_period(period)

    lines = [f"📊 Аналитика {period_label}:", ""]

    if query_type in ("overview", "tasks", "all"):
        stats = await db.tasks_stats(user_id, start_date=start, end_date=end)
        total = stats.get("total", 0)
        done = stats.get("done", 0)
        pending = stats.get("pending", 0)
        pct = round(done / total * 100) if total else 0
        lines.append(f"✅ Задачи: {done}/{total} выполнено ({pct}%)")
        if pending:
            lines.append(f"   В ожидании: {pending}")

        overdue = stats.get("overdue", 0)
        if overdue:
            lines.append(f"   🔴 Просрочено: {overdue}")
        lines.append("")

    if query_type in ("overview", "expenses", "all"):
        totals = await db.expenses_total(user_id, start_date=start, end_date=end)
        if totals:
            lines.append("💰 Расходы:")
            for t in totals:
                lines.append(f"   {t['currency']}: {t['total']:.2f} ({t['count']} операций)")
        else:
            lines.append("💰 Расходы: нет данных за период")
        lines.append("")

    if query_type in ("overview", "sections", "all"):
        sections = await db.section_list(user_id)
        if sections:
            lines.append(f"📂 Разделы: {len(sections)} шт.")
            for s in sections[:5]:
                records = await db.section_records_all(user_id, s["name"])
                lines.append(f"   • {s['title']}: {len(records)} записей")
        lines.append("")

    if query_type in ("overview", "reminders", "all"):
        reminders = await db.reminder_list(user_id)
        if reminders:
            lines.append(f"⏰ Активных напоминаний: {len(reminders)}")
        lines.append("")

    return "\n".join(lines).rstrip()
