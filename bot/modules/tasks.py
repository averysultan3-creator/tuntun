from datetime import date, timedelta, datetime
from bot.db.database import db
from bot.utils.formatters import format_tasks


async def handle_create(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    title = params.get("title", "").strip()
    if not title:
        return "❌ Укажи название задачи"

    task_id = await db.task_create(
        user_id=user_id,
        title=title,
        description=params.get("description"),
        priority=params.get("priority", "normal"),
        due_date=params.get("due_date"),
        due_time=params.get("due_time"),
    )

    due_str = ""
    if params.get("due_date"):
        try:
            d = datetime.strptime(params["due_date"], "%Y-%m-%d")
            due_str = f" на {d.strftime('%d.%m')}"
        except ValueError:
            due_str = f" на {params['due_date']}"
    if params.get("due_time"):
        due_str += f" в {params['due_time']}"

    priority_icons = {"high": "🔴", "normal": "🟡", "low": "🟢"}
    icon = priority_icons.get(params.get("priority", "normal"), "🟡")

    return f"✅ {icon} Задача #{task_id} записана: {title}{due_str}"


async def handle_list(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    period = params.get("period")  # None = all pending, "today"/"tomorrow" = filtered
    filter_date = params.get("filter_date") or params.get("date")

    if not filter_date and period:
        today = date.today()
        if period == "today":
            filter_date = today.strftime("%Y-%m-%d")
        elif period == "tomorrow":
            filter_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")

    tasks = await db.task_list(user_id, filter_date=filter_date)
    return format_tasks(tasks, filter_date)


async def handle_complete(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    task_id = params.get("task_id")
    keyword = params.get("keyword", "")

    if task_id:
        success = await db.task_complete(user_id, int(task_id))
        return f"✅ Задача #{task_id} выполнена!" if success else f"❌ Задача #{task_id} не найдена"

    if keyword:
        found = await db.task_find_by_title(user_id, keyword)
        if not found:
            return f"❌ Задача по запросу «{keyword}» не найдена"
        if len(found) == 1:
            await db.task_complete(user_id, found[0]["id"])
            return f"✅ Выполнено: {found[0]['title']}"
        lines = [f"Найдено несколько задач по «{keyword}»:"]
        for t in found:
            lines.append(f"  #{t['id']}: {t['title']}")
        lines.append("\nНапиши номер задачи: выполнил #N")
        return "\n".join(lines)

    return "Укажи номер или название задачи"


async def handle_update(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    task_id = params.get("task_id")
    keyword = params.get("keyword", "")

    if not task_id and keyword:
        found = await db.task_find_by_title(user_id, keyword)
        if found:
            task_id = found[0]["id"]

    if not task_id:
        return "❌ Задача не найдена"

    await db.task_update(
        user_id, int(task_id),
        due_date=params.get("due_date"),
        priority=params.get("priority"),
        title=params.get("new_title"),
    )
    return f"✏️ Задача #{task_id} обновлена"


async def handle_delete(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    task_id = params.get("task_id")
    keyword = params.get("keyword", "")

    if not task_id and keyword:
        found = await db.task_find_by_title(user_id, keyword)
        if found:
            task_id = found[0]["id"]

    if not task_id:
        return "❌ Задача не найдена"

    await db.task_update(user_id, int(task_id), status="deleted")
    return f"🗑️ Задача #{task_id} удалена"
