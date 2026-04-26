from datetime import datetime

_PRIORITY_ICONS = {"high": "🔴", "normal": "🟡", "low": "🟢"}
_TYPE_ICONS = {"debt": "📌", "absence": "❌", "task": "📝", "note": "💡"}
_STATUS_ICONS = {"new": "💡", "active": "🔥", "done": "✅", "archived": "📦"}


# ──────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────

def format_tasks(tasks: list, filter_date: str = None) -> str:
    if not tasks:
        label = ""
        if filter_date:
            try:
                d = datetime.strptime(filter_date, "%Y-%m-%d")
                label = f" на {d.strftime('%d.%m.%Y')}"
            except ValueError:
                pass
        return f"📭 Задач нет{label}"

    header = "📋 Задачи"
    if filter_date:
        try:
            d = datetime.strptime(filter_date, "%Y-%m-%d")
            header += f" на {d.strftime('%d.%m.%Y')}"
        except ValueError:
            pass

    lines = [header]
    for t in tasks:
        icon = _PRIORITY_ICONS.get(t.get("priority", "normal"), "🟡")
        time_str = f" в {t['due_time']}" if t.get("due_time") else ""
        date_str = f" ({t['due_date']})" if t.get("due_date") and not filter_date else ""
        lines.append(f"{icon} #{t['id']}: {t['title']}{time_str}{date_str}")

    return "\n".join(lines)


def format_task_card(task: dict) -> str:
    """Beautiful single-task card."""
    icon = _PRIORITY_ICONS.get(task.get("priority", "normal"), "🟡")
    status = "🔄 активная" if task.get("status") == "pending" else "✅ выполнена"
    lines = [f"✅ *Задача #{task['id']}*", f"*{task['title']}*"]
    if task.get("description"):
        lines.append(task["description"])
    lines.append(f"{icon} Приоритет: {task.get('priority', 'normal')}")
    if task.get("due_date"):
        due = task["due_date"]
        if task.get("due_time"):
            due += f" в {task['due_time']}"
        lines.append(f"📅 Дедлайн: {due}")
    lines.append(f"Статус: {status}")
    return "\n".join(lines)


def format_tasks_table(tasks: list, title: str = "Задачи") -> str:
    """Markdown table for tasks."""
    if not tasks:
        return "📭 Задач нет"
    lines = [f"📋 *{title}*\n"]
    lines.append("| # | Задача | Приоритет | Дедлайн |")
    lines.append("|---|--------|-----------|---------|")
    for t in tasks:
        pri = _PRIORITY_ICONS.get(t.get("priority", "normal"), "🟡")
        due = t.get("due_date", "—")
        if t.get("due_time"):
            due += f" {t['due_time']}"
        title_short = str(t.get("title", ""))[:35]
        lines.append(f"| #{t['id']} | {title_short} | {pri} | {due} |")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Study
# ──────────────────────────────────────────────────────────────

def format_study_records(records: list, title: str = "Учёба") -> str:
    if not records:
        return f"📚 {title}: записей нет"

    lines = [f"📚 {title}:"]
    for r in records:
        icon = _TYPE_ICONS.get(r.get("type", "note"), "📝")
        subject = f"[{r['subject_name']}] " if r.get("subject_name") else ""
        due = f" (до {r['due_date']})" if r.get("due_date") else ""
        lines.append(f"{icon} {subject}{r['content']}{due}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Schedule
# ──────────────────────────────────────────────────────────────

def format_schedule(events: list, title: str = "Расписание") -> str:
    if not events:
        return f"📅 {title}: событий нет"

    lines = [f"📅 {title}:"]
    for e in events:
        time_str = ""
        if e.get("start_time"):
            time_str = f" {e['start_time']}"
            if e.get("end_time"):
                time_str += f"–{e['end_time']}"
        date_str = f" ({e['date']})" if e.get("date") else ""
        recurring = " 🔄" if e.get("recurring") else ""
        lines.append(f"• {e['title']}{date_str}{time_str}{recurring}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Reminders
# ──────────────────────────────────────────────────────────────

def format_reminders(reminders: list) -> str:
    if not reminders:
        return "⏰ Активных напоминаний нет"

    lines = ["⏰ Активные напоминания:"]
    for r in reminders:
        try:
            dt = datetime.fromisoformat(r["remind_at"])
            dt_str = dt.strftime("%d.%m %H:%M")
        except Exception:
            dt_str = r["remind_at"]
        recurring = " 🔄" if r.get("recurring") else ""
        lines.append(f"  #{r['id']}: {r['text']} — {dt_str}{recurring}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Expenses / Finance
# ──────────────────────────────────────────────────────────────

def format_expenses(expenses: list, title: str = "Расходы") -> str:
    if not expenses:
        return f"💰 {title}: расходов нет"

    lines = [f"💰 {title}:"]
    totals: dict = {}
    for e in expenses:
        currency = e.get("currency", "USD")
        project = f" [{e['project_name']}]" if e.get("project_name") else ""
        desc = f" — {e['description']}" if e.get("description") else ""
        date_str = f" ({e['date']})" if e.get("date") else ""
        lines.append(f"  {e['amount']} {currency}{project}{desc}{date_str}")
        totals[currency] = totals.get(currency, 0) + float(e["amount"])

    lines.append("")
    for currency, total in totals.items():
        lines.append(f"Итого {currency}: {total:.2f}")

    return "\n".join(lines)


def format_expense_card(expenses: list, title: str = "Расходы сегодня") -> str:
    """Finance card with table + total."""
    if not expenses:
        return f"💸 {title}: расходов нет"

    totals: dict = {}
    rows_by_cat: dict = {}

    for e in expenses:
        currency = e.get("currency", "USD")
        cat = e.get("description") or e.get("project_name") or "Разное"
        amount = float(e.get("amount", 0))
        key = f"{cat}|{currency}"
        rows_by_cat[key] = rows_by_cat.get(key, 0) + amount
        totals[currency] = totals.get(currency, 0) + amount

    lines = [f"💸 *{title}*\n"]
    lines.append("| Категория | Сумма |")
    lines.append("|-----------|-------|")
    for key, amt in rows_by_cat.items():
        cat, cur = key.split("|", 1)
        lines.append(f"| {cat} | {amt:.2f} {cur} |")

    lines.append("")
    for currency, total in totals.items():
        lines.append(f"**Итого {currency}: {total:.2f}**")

    return "\n".join(lines)


def format_expense_table(expenses: list, title: str = "Расходы") -> str:
    """Full expense table."""
    if not expenses:
        return f"💸 {title}: расходов нет"

    lines = [f"💸 *{title}*\n"]
    lines.append("| Дата | Категория | Сумма | Валюта |")
    lines.append("|------|-----------|-------|--------|")
    for e in expenses:
        date = str(e.get("date", ""))[:10]
        cat = e.get("description") or e.get("project_name") or "—"
        amt = f"{float(e.get('amount', 0)):.2f}"
        cur = e.get("currency", "USD")
        lines.append(f"| {date} | {cat} | {amt} | {cur} |")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Memory
# ──────────────────────────────────────────────────────────────

def format_memory(memories: list, title: str = "Память") -> str:
    if not memories:
        return f"🧠 {title}: ничего не найдено"

    lines = [f"🧠 {title}:"]
    for m in memories:
        cat = m.get("category", "general")
        key = f" [{m['key_name']}]" if m.get("key_name") else ""
        lines.append(f"  ({cat}){key}: {m['value']}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Dynamic sections
# ──────────────────────────────────────────────────────────────

def format_dynamic_records(records: list, section_title: str = "Раздел") -> str:
    if not records:
        return f"📂 {section_title}: записей нет"

    lines = [f"📂 {section_title}:"]
    for r in records:
        data = r.get("data", {})
        date_str = r.get("created_at", "")[:10]
        data_str = ", ".join(f"{k}: {v}" for k, v in data.items() if v is not None)
        lines.append(f"  [{date_str}] {data_str}")

    return "\n".join(lines)


def format_dynamic_records_table(records: list, section_title: str = "Раздел") -> str:
    """Render dynamic section records as a Markdown table."""
    if not records:
        return f"📂 *{section_title}*: записей нет"

    # Collect all unique keys across records
    all_keys: list = []
    seen: set = set()
    for r in records:
        data = r.get("data", {})
        for k in data.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    if not all_keys:
        return format_dynamic_records(records, section_title)

    lines = [f"📂 *{section_title}*\n"]
    header = "| " + " | ".join(all_keys) + " |"
    sep = "|" + "|".join("---" for _ in all_keys) + "|"
    lines.append(header)
    lines.append(sep)

    for r in records:
        data = r.get("data", {})
        row = "| " + " | ".join(str(data.get(k, "—"))[:30] for k in all_keys) + " |"
        lines.append(row)

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Ideas
# ──────────────────────────────────────────────────────────────

def format_ideas(ideas: list, title: str = "Идеи") -> str:
    if not ideas:
        return f"💡 {title}: идей нет"

    lines = [f"💡 *{title}:*"]
    for idea in ideas:
        icon = _STATUS_ICONS.get(idea.get("status", "new"), "💡")
        project = f" [{idea['related_project']}]" if idea.get("related_project") else ""
        lines.append(f"{icon} #{idea['id']}: {idea['title']}{project}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Plan
# ──────────────────────────────────────────────────────────────

def format_plan_table(plan: dict, date: str = "") -> str:
    """Format day plan as Markdown table."""
    if not plan:
        return "📅 План пуст"

    date_str = ""
    if date:
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            date_str = f" — {d.strftime('%d.%m.%Y')}"
        except Exception:
            date_str = f" — {date}"

    lines = [f"📅 *План дня{date_str}*\n"]

    items = plan.get("items") or plan.get("schedule") or []
    if isinstance(items, list) and items:
        lines.append("| Время | Дело | Источник |")
        lines.append("|-------|------|----------|")
        for item in items:
            if isinstance(item, dict):
                time = item.get("time", "—")
                title = str(item.get("title", item.get("task", item.get("event", "—"))))[:35]
                source = item.get("source", "")
                lines.append(f"| {time} | {title} | {source} |")

    recommendations = plan.get("recommendations", [])
    if recommendations:
        lines.append("\n💡 *Рекомендации:*")
        for rec in recommendations[:3]:
            lines.append(f"— {rec}")

    return "\n".join(lines)


def format_plan_text(plan: dict, date: str = "") -> str:
    """Format day plan as text list."""
    if not plan:
        return "📅 План пуст"

    date_str = ""
    if date:
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            date_str = f" на {d.strftime('%d.%m.%Y')}"
        except Exception:
            date_str = f" на {date}"

    lines = [f"📅 *План дня{date_str}*\n"]
    lines.append("*Запланировано:*")

    items = plan.get("items") or plan.get("schedule") or []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                time = item.get("time", "")
                title = str(item.get("title", item.get("task", item.get("event", ""))))
                time_prefix = f"🕐 {time} — " if time else "• "
                lines.append(f"{time_prefix}{title}")
    else:
        lines.append("Нет запланированных событий")

    recommendations = plan.get("recommendations", [])
    if recommendations:
        lines.append("\n💡 *Рекомендации:*")
        for rec in recommendations[:3]:
            lines.append(f"— {rec}")

    return "\n".join(lines)
