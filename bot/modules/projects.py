from datetime import date, timedelta
from bot.db.database import db
from bot.utils.date_parser import parse_date_range
from bot.utils.formatters import format_expenses


async def handle_create(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    name = params.get("name", "").strip()
    if not name:
        return "❌ Укажи название проекта"

    title = params.get("title") or name
    description = params.get("description")

    # Check if already exists
    existing = await db.project_find(user_id, name)
    if existing:
        return f"📁 Проект уже существует: {existing['title'] or existing['name']} #{existing['id']}"

    pid = await db.project_create(user_id, name, title, description)
    return f"📁 Проект создан: {title} #{pid}"


async def handle_list(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    projects = await db.project_list(user_id)
    if not projects:
        return "📁 Проектов нет. Создай первый: «создай проект Реклама»"

    lines = ["📁 Мои проекты:"]
    for p in projects:
        lines.append(f"  #{p['id']}: {p['title'] or p['name']}")
    return "\n".join(lines)


async def handle_expense_add(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    amount = params.get("amount")
    if not amount:
        return "❌ Укажи сумму расхода"

    currency = params.get("currency", "USD").upper()
    description = params.get("description", "")
    project_name = params.get("project_name")
    expense_date = params.get("date")

    eid = await db.expense_add(
        user_id=user_id,
        amount=float(amount),
        currency=currency,
        description=description,
        project_name=project_name,
        date=expense_date,
    )

    project_str = f" [{project_name}]" if project_name else ""
    desc_str = f" — {description}" if description else ""
    return f"💰 Расход #{eid} записан: {amount} {currency}{project_str}{desc_str}"


async def handle_expense_stats(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    project_name = params.get("project_name")
    period = params.get("period", "week")
    today = date.today()

    start_date = None
    end_date = None
    _PERIOD_MAP = {
        "today":  (today.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")),
        "week":   ((today - timedelta(days=7)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")),
        "month":  (today.replace(day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")),
        "year":   (today.replace(month=1, day=1).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")),
    }
    if period in _PERIOD_MAP:
        start_date, end_date = _PERIOD_MAP[period]
    elif period not in (None, "all", ""):
        # Free-form: "за март", "за 2025", etc.
        start_date, end_date = parse_date_range(period)

    expenses = await db.expense_stats(user_id, project_name=project_name, start_date=start_date)

    _LABELS = {"today": "сегодня", "week": "неделю", "month": "месяц", "year": "год", "all": "всё время"}
    period_str = _LABELS.get(period) or (f"{start_date} — {end_date}" if start_date else "всё время")
    title = f"Расходы за {period_str}"
    if project_name:
        title += f" [{project_name}]"

    return format_expenses(expenses, title)
