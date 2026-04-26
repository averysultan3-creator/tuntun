from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.db.database import db
from bot.utils.formatters import format_tasks, format_reminders


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Задачи", callback_data="menu:tasks"),
            InlineKeyboardButton(text="⏰ Напоминания", callback_data="menu:reminders"),
        ],
        [
            InlineKeyboardButton(text="📂 Разделы", callback_data="menu:sections"),
            InlineKeyboardButton(text="📊 Экспорт", callback_data="menu:export"),
        ],
        [
            InlineKeyboardButton(text="💾 Backup", callback_data="menu:backup"),
        ],
    ])


async def build_tasks_menu(user_id: int) -> tuple[InlineKeyboardMarkup, str]:
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    tasks = await db.task_list(user_id, filter_date=today)
    text = format_tasks(tasks, today)

    rows = []
    for task in tasks[:5]:
        rows.append([InlineKeyboardButton(
            text=f"✅ #{task['id']}: {task['title'][:30]}",
            callback_data=f"task_done:{task['id']}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows), text


async def build_reminders_menu(user_id: int) -> tuple[InlineKeyboardMarkup, str]:
    reminders = await db.reminder_list(user_id)
    text = format_reminders(reminders)
    rows = []
    for r in reminders[:5]:
        rows.append([InlineKeyboardButton(
            text=f"❌ #{r['id']}: {r['text'][:30]}",
            callback_data=f"rem_cancel:{r['id']}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows), text


async def build_sections_menu(user_id: int) -> tuple[InlineKeyboardMarkup, str]:
    sections = await db.section_list(user_id)
    if not sections:
        text = "📂 Разделов нет. Напиши: «создай раздел Финансы с полями: дата, сумма, категория»"
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")]
        ]), text

    text = "📂 Мои разделы:"
    rows = []
    for s in sections:
        rows.append([InlineKeyboardButton(
            text=f"📂 {s['title']}",
            callback_data=f"menu:section:{s['name']}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows), text


async def handle_show(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    """Called via dispatcher when intent=menu_show"""
    return "📱 Используй кнопку /menu или нажми на меню ниже"
