"""bot/modules/ideas.py — Идеи пользователя.

Позволяет сохранять, просматривать и конвертировать идеи в задачи.
Доступно через обычный разговор:
  "идея: сделать вечерний отчёт"
  "покажи мои идеи по продуктивности"
  "сделай эту идею задачей"
"""
from bot.db.database import db


_STATUS_ICONS = {
    "new": "💡",
    "active": "🔥",
    "done": "✅",
    "archived": "📦",
}

_CATEGORY_ICONS = {
    "general": "💡",
    "project": "📁",
    "ads": "📣",
    "study": "📚",
    "health": "❤️",
    "finance": "💸",
}


def _format_idea(idea: dict) -> str:
    icon = _STATUS_ICONS.get(idea.get("status", "new"), "💡")
    cat_icon = _CATEGORY_ICONS.get(idea.get("category", "general"), "💡")
    title = idea.get("title", "")
    desc = idea.get("description", "")
    project = idea.get("related_project", "")
    lines = [f"{icon} *Идея #{idea['id']}* {cat_icon}"]
    lines.append(f"*{title}*")
    if desc:
        lines.append(desc)
    if project:
        lines.append(f"📁 Проект: {project}")
    lines.append(f"📅 {str(idea.get('created_at', ''))[:10]}")
    return "\n".join(lines)


async def handle_save(user_id: int, params: dict, ai_response: str,
                      source_message_id: int = None, **kwargs) -> str:
    title = params.get("title", "").strip()
    if not title:
        return "❌ Укажи название идеи"

    description = params.get("description", "")
    category = params.get("category", "general")
    related_project = params.get("related_project")

    idea_id = await db.idea_save(
        user_id=user_id,
        title=title,
        description=description,
        category=category,
        related_project=related_project,
        source_message_id=source_message_id,
    )

    # Save in conversation state for "сделай это задачей" follow-up
    await db.conversation_state_update(
        user_id,
        active_topic="idea",
        active_object_type="idea",
        active_object_id=idea_id,
        last_discussed_idea_ids=str(idea_id),
    )

    icon = _CATEGORY_ICONS.get(category, "💡")
    project_note = f"\n📁 Привязана к: {related_project}" if related_project else ""
    return (
        f"💡 Идея #{idea_id} сохранена {icon}\n"
        f"*{title}*{project_note}\n\n"
        f"Напиши «сделай это задачей» чтобы добавить в задачи."
    )


async def handle_list(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    category = params.get("category")
    status = params.get("status")

    ideas = await db.idea_list(user_id, category=category, status=status, limit=15)

    if not ideas:
        label = f" по теме «{category}»" if category else ""
        return f"💡 Идей{label} пока нет.\n\nНапиши «идея: ...» чтобы сохранить."

    title_parts = ["💡 *Мои идеи*"]
    if category:
        title_parts.append(f"по теме «{category}»")

    lines = [" ".join(title_parts), ""]
    for idea in ideas:
        icon = _STATUS_ICONS.get(idea.get("status", "new"), "💡")
        project = f" [{idea['related_project']}]" if idea.get("related_project") else ""
        lines.append(f"{icon} #{idea['id']}: {idea['title']}{project}")

    # Update conversation state with discussed idea IDs
    idea_ids = ",".join(str(i["id"]) for i in ideas)
    await db.conversation_state_update(
        user_id,
        active_topic="ideas",
        last_discussed_idea_ids=idea_ids,
    )

    return "\n".join(lines)


async def handle_convert_to_task(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    idea_id = params.get("idea_id")
    title_override = params.get("title")
    due_date = params.get("due_date")

    # If no idea_id — look in conversation state
    if not idea_id:
        state = await db.conversation_state_get(user_id)
        if state.get("active_object_type") == "idea" and state.get("active_object_id"):
            idea_id = state["active_object_id"]
        elif state.get("last_discussed_idea_ids"):
            ids = [x.strip() for x in str(state["last_discussed_idea_ids"]).split(",") if x.strip()]
            if ids:
                idea_id = int(ids[0])

    if not idea_id:
        return "❌ Не понял, какую идею конвертировать. Укажи ID: «сделай задачей идею #5»"

    idea = await db.idea_get(user_id, idea_id)
    if not idea:
        return f"❌ Идея #{idea_id} не найдена"

    task_title = title_override or idea["title"]
    task_id = await db.task_create(
        user_id=user_id,
        title=task_title,
        description=idea.get("description"),
        due_date=due_date,
    )

    # Mark idea as active (converted)
    await db.idea_update_status(user_id, idea_id, "active")

    # Update conversation state
    await db.conversation_state_update(
        user_id,
        active_topic="task",
        active_object_type="task",
        active_object_id=task_id,
    )

    return (
        f"✅ Задача #{task_id} создана из идеи!\n"
        f"*{task_title}*"
        + (f"\n📅 Дедлайн: {due_date}" if due_date else "")
        + f"\n\n_Идея #{idea_id} помечена как активная._"
    )
