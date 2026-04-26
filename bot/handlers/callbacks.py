import logging
from datetime import datetime, timedelta

import pytz
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import config
from bot.db.database import db
import bot.utils.scheduler as sched_module
from bot.modules.menu import main_menu_keyboard, build_tasks_menu, build_reminders_menu, build_sections_menu

router = Router()


def _snooze_keyboard(reminder_id: int, minutes: int = 60) -> InlineKeyboardMarkup:
    options = [10, 30, 60, 120]
    btns = [InlineKeyboardButton(text=f"⏰ {m} мин", callback_data=f"rem_snooze:{reminder_id}:{m}") for m in options]
    return InlineKeyboardMarkup(inline_keyboard=[btns[:2], btns[2:]])


# ===== REMINDER CALLBACKS =====

@router.callback_query(F.data.startswith("rem_done:"))
async def cb_reminder_done(callback: CallbackQuery):
    reminder_id = int(callback.data.split(":")[1])
    reminder = await db.reminder_cancel(callback.from_user.id, reminder_id)
    sched_module.cancel_reminder_job(reminder_id)
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Выполнено!"
    )
    await callback.answer("Отмечено как выполнено")


@router.callback_query(F.data.startswith("rem_snooze_pick:"))
async def cb_reminder_snooze_pick(callback: CallbackQuery):
    reminder_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=_snooze_keyboard(reminder_id))
    await callback.answer("Выбери время откладывания")


@router.callback_query(F.data.startswith("rem_snooze:"))
async def cb_reminder_snooze(callback: CallbackQuery):
    parts = callback.data.split(":")
    reminder_id = int(parts[1])
    minutes = int(parts[2]) if len(parts) > 2 else 10

    tz = pytz.timezone(config.TIMEZONE)
    new_time = datetime.now(tz) + timedelta(minutes=minutes)
    new_time_str = new_time.strftime("%Y-%m-%d %H:%M:%S")

    # Get original reminder
    reminders = await db.reminder_list(callback.from_user.id)
    reminder = next((r for r in reminders if r["id"] == reminder_id), None)
    if not reminder:
        await callback.answer("Напоминание не найдено")
        return

    # Cancel old, schedule new
    sched_module.cancel_reminder_job(reminder_id)
    await db._execute(
        "UPDATE reminders SET remind_at=? WHERE id=?",
        (new_time_str, reminder_id),
    )
    sched_module.add_reminder_job(
        reminder_id=reminder_id,
        user_id=callback.from_user.id,
        text=reminder["text"],
        remind_at_str=new_time_str,
    )

    new_time_human = new_time.strftime("%H:%M")
    await callback.message.edit_text(
        callback.message.text + f"\n\n⏰ Отложено до {new_time_human}"
    )
    await callback.answer(f"Отложено на {minutes} мин")


@router.callback_query(F.data.startswith("rem_cancel:"))
async def cb_reminder_cancel(callback: CallbackQuery):
    reminder_id = int(callback.data.split(":")[1])
    await db.reminder_cancel(callback.from_user.id, reminder_id)
    sched_module.cancel_reminder_job(reminder_id)
    await callback.message.edit_text(callback.message.text + "\n\n❌ Отменено")
    await callback.answer("Напоминание отменено")


# ===== MENU CALLBACKS =====

@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback: CallbackQuery):
    await callback.message.edit_text("📱 Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:tasks")
async def cb_menu_tasks(callback: CallbackQuery):
    kb, text = await build_tasks_menu(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "menu:reminders")
async def cb_menu_reminders(callback: CallbackQuery):
    kb, text = await build_reminders_menu(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "menu:sections")
async def cb_menu_sections(callback: CallbackQuery):
    kb, text = await build_sections_menu(callback.from_user.id)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("menu:section:"))
async def cb_menu_section_view(callback: CallbackQuery):
    section_name = callback.data.split(":", 2)[2]
    from bot.modules.dynamic import handle_query
    text = await handle_query(callback.from_user.id, {"section_name": section_name}, "")
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu:sections")
    ]])
    await callback.message.edit_text(text, reply_markup=back_kb)
    await callback.answer()


@router.callback_query(F.data == "menu:export")
async def cb_menu_export(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Задачи Excel", callback_data="export:tasks"),
            InlineKeyboardButton(text="💰 Расходы Excel", callback_data="export:expenses"),
        ],
        [InlineKeyboardButton(text="📄 Все данные TXT", callback_data="export:all_txt")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])
    await callback.message.edit_text("📊 Экспорт данных:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("export:"))
async def cb_export(callback: CallbackQuery):
    target = callback.data.split(":")[1]
    user_id = callback.from_user.id
    await callback.answer("Генерирую файл...")

    from bot.modules.exports import export_to_excel, export_to_txt
    from pathlib import Path
    from aiogram.types import FSInputFile

    try:
        if target == "all_txt":
            file_path = await export_to_txt(user_id, "all", "month")
        else:
            file_path = await export_to_excel(user_id, target, period="month")

        if file_path and Path(file_path).exists():
            await callback.message.answer_document(
                FSInputFile(file_path),
                caption=f"📊 Экспорт: {target}",
            )
        else:
            await callback.message.answer("❌ Нет данных для экспорта")
    except Exception as e:
        logging.error(f"Export callback error: {e}")
        await callback.message.answer("❌ Ошибка при экспорте")


@router.callback_query(F.data == "menu:backup")
async def cb_menu_backup(callback: CallbackQuery):
    await callback.answer("Создаю backup...")
    from bot.modules.backup import create_backup
    from pathlib import Path
    from aiogram.types import FSInputFile

    try:
        file_path = await create_backup(callback.from_user.id)
        if file_path and Path(file_path).exists():
            await callback.message.answer_document(
                FSInputFile(file_path),
                caption="💾 Backup создан",
            )
        else:
            await callback.message.answer("❌ Ошибка при создании backup")
    except Exception as e:
        logging.error(f"Backup callback error: {e}")
        await callback.message.answer("❌ Ошибка backup")


@router.callback_query(F.data.startswith("task_done:"))
async def cb_task_done(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    success = await db.task_complete(callback.from_user.id, task_id)
    if success:
        await callback.message.edit_text(callback.message.text + "\n\n✅ Выполнено!")
    await callback.answer("Задача отмечена выполненной" if success else "Задача не найдена")


@router.callback_query(F.data.startswith("task_delete:"))
async def cb_task_delete(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    success = await db.task_delete(callback.from_user.id, task_id)
    if success:
        try:
            await callback.message.edit_text(callback.message.text + "\n\n🗑 Удалено")
        except Exception:
            pass
    await callback.answer("Задача удалена" if success else "Задача не найдена")


@router.callback_query(F.data.startswith("task_remind:"))
async def cb_task_remind(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    await callback.answer("Напиши когда напомнить, например: «напомни задачу #" + str(task_id) + " завтра в 12:00»")


@router.callback_query(F.data.startswith("task_edit:"))
async def cb_task_edit(callback: CallbackQuery):
    task_id = int(callback.data.split(":")[1])
    await callback.answer(f"Напиши что изменить: «задача #{task_id} переименовать в ...»")


@router.callback_query(F.data == "task_add")
async def cb_task_add(callback: CallbackQuery):
    await callback.answer("Напиши задачу, например: «напомни купить молоко»")


@router.callback_query(F.data == "reminder_add")
async def cb_reminder_add(callback: CallbackQuery):
    await callback.answer("Напиши напоминание, например: «напомни завтра в 10:00 встреча»")


@router.callback_query(F.data.startswith("plan:"))
async def cb_plan(callback: CallbackQuery):
    action = callback.data.split(":")[1] if ":" in callback.data else ""
    user_id = callback.from_user.id

    if action == "table":
        # Show last plan as a simple formatted table
        try:
            from bot.db.database import db as _db
            state = await _db.conversation_state_get(user_id)
            if state and state.get("last_plan_json"):
                import json
                plan = json.loads(state["last_plan_json"])
                timed = plan.get("timed", [])
                flexible = plan.get("flexible", [])
                lines = ["```", "Время    | Событие", "---------|--------"]
                for b in timed:
                    t = b.get("time", "")
                    txt = b.get("text", "")[:35]
                    lines.append(f"{t:<8} | {txt}")
                if flexible:
                    lines.append("---------|--------")
                    for b in flexible:
                        lines.append(f"flex     | {b[:35]}")
                lines.append("```")
                await callback.message.answer("\n".join(lines), parse_mode="Markdown")
            else:
                await callback.message.answer("Нет сохранённого плана. Запроси «дай план на сегодня».")
        except Exception as e:
            logging.error(f"plan:table callback error: {e}")
            await callback.message.answer("❌ Ошибка при отображении таблицы")
        await callback.answer()

    elif action == "table":
        await callback.answer("Таблица уже отправлена")
    else:
        await callback.answer(f"Действие '{action}' пока не поддерживается")


@router.callback_query(F.data.startswith("analytics:"))
async def cb_analytics(callback: CallbackQuery):
    section_name = callback.data.split(":", 1)[1] if ":" in callback.data else ""
    await callback.answer(f"Напиши «аналитика {section_name}» для получения статистики")
