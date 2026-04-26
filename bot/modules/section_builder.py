from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.db.database import db


class SectionBuilderStates(StatesGroup):
    waiting_for_fields = State()
    waiting_for_confirmation = State()


async def handle_fsm_input(message: Message, state: FSMContext) -> bool:
    """Returns True if this message was handled by section builder FSM, False otherwise."""
    current_state = await state.get_state()

    if current_state == SectionBuilderStates.waiting_for_fields.state:
        await _process_fields_input(message, state)
        return True

    if current_state == SectionBuilderStates.waiting_for_confirmation.state:
        await _process_confirmation(message, state)
        return True

    return False


async def _process_fields_input(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    section_name = data.get("section_name", "")
    section_title = data.get("section_title", section_name)
    suggested_fields = data.get("suggested_fields", [])

    text = message.text.strip()

    # If user says "да" — use suggested fields
    if text.lower() in ("да", "yes", "y", "ок", "ok", "+") and suggested_fields:
        fields = suggested_fields
    else:
        # Parse fields: "дата, сумма, категория" or "дата; сумма; категория" or newlines
        import re
        fields_raw = re.split(r"[,;\n]+", text)
        fields = [f.strip().lower() for f in fields_raw if f.strip()]

    if not fields:
        await message.answer("❌ Не могу распознать поля. Напиши через запятую: дата, сумма, категория")
        return

    await state.update_data(fields=fields)
    await state.set_state(SectionBuilderStates.waiting_for_confirmation.state)

    fields_str = ", ".join(fields)
    await message.answer(
        f"📂 Создаю раздел *{section_title}* с полями: *{fields_str}*\n\n"
        f"Подтверждаешь? (да/нет)",
        parse_mode="Markdown"
    )


async def _process_confirmation(message: Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text.strip().lower()

    if text in ("да", "yes", "y", "ок", "ok", "+", "создай", "создавай"):
        data = await state.get_data()
        section_name = data.get("section_name", "")
        section_title = data.get("section_title", section_name)
        fields = data.get("fields", [])

        await db.section_create(user_id, section_name, section_title, fields)
        await state.clear()
        await message.answer(
            f"✅ Раздел *{section_title}* создан!\n"
            f"Поля: {', '.join(fields)}\n\n"
            f"Теперь можешь добавлять записи: «добавь в {section_title}: поле1=значение1, поле2=значение2»",
            parse_mode="Markdown"
        )
    elif text in ("нет", "no", "n", "отмена", "cancel", "-"):
        await state.clear()
        await message.answer("❌ Создание раздела отменено")
    else:
        await message.answer("Напиши *да* для создания или *нет* для отмены", parse_mode="Markdown")


async def start_section_builder(message: Message, state: FSMContext,
                                section_name: str, section_title: str,
                                suggested_fields: list = None):
    """Start the conversational section builder FSM."""
    await state.set_state(SectionBuilderStates.waiting_for_fields.state)
    await state.update_data(section_name=section_name, section_title=section_title)

    if suggested_fields:
        fields_str = ", ".join(f"`{f}`" for f in suggested_fields)
        await message.answer(
            f"📂 Создаём раздел *{section_title}*.\n\n"
            f"Предлагаю поля: {fields_str}\n\n"
            f"Напиши *да* чтобы принять, или перечисли свои поля через запятую:",
            parse_mode="Markdown"
        )
        # Store suggestions so user can just say "да"
        await state.update_data(suggested_fields=suggested_fields)
    else:
        await message.answer(
            f"📂 Создаём раздел *{section_title}*.\n"
            f"Напиши поля через запятую, например:\n"
            f"`дата, сумма, категория, описание`",
            parse_mode="Markdown"
        )
