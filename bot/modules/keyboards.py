"""bot/modules/keyboards.py — Contextual inline keyboards for TUNTUN.

build_task_keyboard(task_id)    — кнопки для карточки задачи
build_plan_keyboard()           — кнопки для плана дня
build_finance_keyboard()        — кнопки для финансовой сводки
build_ideas_keyboard(idea_id)   — кнопки для идеи
build_reminder_keyboard(rem_id) — кнопки для напоминания
build_section_keyboard(name)    — кнопки для раздела
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Готово", callback_data=f"task_done:{task_id}"),
            InlineKeyboardButton(text="⏰ Напомнить", callback_data=f"task_remind:{task_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"task_edit:{task_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task_delete:{task_id}"),
        ],
    ])


def build_tasks_list_keyboard(tasks: list) -> InlineKeyboardMarkup:
    """Keyboard for task list — quick complete buttons."""
    rows = []
    for task in tasks[:5]:
        rows.append([InlineKeyboardButton(
            text=f"✅ #{task['id']}: {task['title'][:28]}",
            callback_data=f"task_done:{task['id']}",
        )])
    rows.append([
        InlineKeyboardButton(text="➕ Добавить", callback_data="task_add"),
        InlineKeyboardButton(text="📊 Excel", callback_data="export:tasks"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Таблица", callback_data="plan:table"),
            InlineKeyboardButton(text="📤 Excel", callback_data="export:plan"),
        ],
        [
            InlineKeyboardButton(text="➕ Задачу", callback_data="task_add"),
            InlineKeyboardButton(text="⏰ Напоминание", callback_data="reminder_add"),
        ],
    ])


def build_finance_keyboard(section_name: str = "finance") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Excel", callback_data=f"export:{section_name}"),
            InlineKeyboardButton(text="📈 Статистика", callback_data=f"analytics:{section_name}"),
        ],
        [
            InlineKeyboardButton(text="✏️ Исправить", callback_data=f"record_edit:{section_name}"),
            InlineKeyboardButton(text="📂 Все записи", callback_data=f"section_query:{section_name}"),
        ],
    ])


def build_expense_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Excel", callback_data="export:expenses"),
            InlineKeyboardButton(text="📈 За месяц", callback_data="analytics:expenses_month"),
        ],
        [
            InlineKeyboardButton(text="✏️ Исправить", callback_data="expense_edit"),
            InlineKeyboardButton(text="📋 Категории", callback_data="expense_categories"),
        ],
    ])


def build_ideas_keyboard(idea_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ В задачу", callback_data=f"idea_to_task:{idea_id}"),
            InlineKeyboardButton(text="📁 К проекту", callback_data=f"idea_link:{idea_id}"),
        ],
        [
            InlineKeyboardButton(text="📦 Архив", callback_data=f"idea_archive:{idea_id}"),
        ],
    ])


def build_ideas_list_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Новая идея", callback_data="idea_add"),
            InlineKeyboardButton(text="✅ В задачу", callback_data="idea_convert_latest"),
        ],
    ])


def build_reminder_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"rem_cancel:{reminder_id}"),
            InlineKeyboardButton(text="📋 Все", callback_data="reminders_list"),
        ],
    ])


def build_section_keyboard(section_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Excel", callback_data=f"export:{section_name}"),
            InlineKeyboardButton(text="➕ Запись", callback_data=f"record_add:{section_name}"),
        ],
        [
            InlineKeyboardButton(text="📋 Все записи", callback_data=f"section_query:{section_name}"),
            InlineKeyboardButton(text="➕ Поле", callback_data=f"section_add_field:{section_name}"),
        ],
    ])


def build_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Режим дня", callback_data="settings:schedule"),
            InlineKeyboardButton(text="💬 Стиль", callback_data="settings:style"),
        ],
        [
            InlineKeyboardButton(text="🔔 Напоминания", callback_data="settings:reminders"),
            InlineKeyboardButton(text="📊 Планы", callback_data="settings:plans"),
        ],
    ])
