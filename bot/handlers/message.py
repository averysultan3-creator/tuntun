import json
import logging

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import config
from bot.ai.intent import classify
from bot.db.database import db
from bot.modules.dispatcher import dispatch_actions
from bot.modules.menu import main_menu_keyboard

router = Router()


def _is_allowed(user_id: int) -> bool:
    return not config.ALLOWED_USER_IDS or user_id in config.ALLOWED_USER_IDS


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if not _is_allowed(message.from_user.id):
        return
    await state.clear()
    await db.ensure_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "👋 Привет! Я *TUNTUN* — твой личный AI-ассистент.\n\n"
        "Пиши мне что угодно на русском — задачи, расписание, напоминания, учёба, расходы, планы.\n"
        "Можешь отправить голосовое, фото или документ.\n\n"
        "*Примеры:*\n"
        "• «завтра в 12 напомни оплатить подписку»\n"
        "• «создай базу финансов: дата, сумма, категория»\n"
        "• «потратил 40 zł еда и 120 zł бензин»\n"
        "• «выгрузи задачи в Excel»\n"
        "• «сделай backup всех данных»",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not _is_allowed(message.from_user.id):
        return
    await message.answer(
        "📖 *Что я умею:*\n\n"
        "✅ Задачи — «запиши задачу X на завтра», «что у меня сегодня?»\n"
        "📚 Учёба — «у меня новый предмет Математика», «запиши долг по PRI»\n"
        "📅 Расписание — «дай расписание на неделю», «добавь пары в 10:00»\n"
        "⏰ Напоминания — «напомни в 15:00», «напоминай каждый день в 9:00»\n"
        "🧠 Память — «запомни, что я не люблю помидоры», «что помнишь о рекламе?»\n"
        "💰 Расходы — «потратил $20 на рекламу», «статистика за месяц»\n"
        "📂 Разделы — «создай раздел Реклама с полями: бюджет, аккаунты»\n"
        "🌙 Режим — «если лягу в 00:30, когда встать?», «составь план дня»\n"
        "📊 Экспорт — «выгрузи задачи в Excel», «экспортируй раздел Реклама»\n"
        "💾 Backup — «сделай backup всех данных»\n"
        "🎙️ Голос — просто отправь голосовое\n\n"
        "Одним сообщением можно сделать несколько действий сразу!",
        parse_mode="Markdown",
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    if not _is_allowed(message.from_user.id):
        return
    await message.answer("📱 Главное меню:", reply_markup=main_menu_keyboard())


@router.message(Command("debug"))
async def cmd_debug(message: Message):
    """Show config + test OpenAI connectivity — admin only."""
    if not _is_allowed(message.from_user.id):
        return
    from bot.ai.model_router import get_model
    key = config.OPENAI_API_KEY
    key_hint = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else ("(пусто)" if not key else key)
    token = config.BOT_TOKEN
    token_hint = f"{token[:10]}..." if token else "(пусто)"
    lines = [
        "🔧 *Debug info*",
        f"`BOT_TOKEN   :` `{token_hint}`",
        f"`API_KEY     :` `{key_hint}`",
        f"`MODEL_ROUTER:` `{get_model('router')}`",
        f"`MODEL_CHAT  :` `{get_model('chat')}`",
        f"`MODEL_REASON:` `{get_model('reasoning')}`",
        f"`TIMEZONE    :` `{config.TIMEZONE}`",
        "",
        "🔌 Тестирую соединение с OpenAI...",
    ]
    await message.answer("\n".join(lines), parse_mode="Markdown")
    # Live test
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=get_model("router"),
            messages=[{"role": "user", "content": "ping"}],
            max_completion_tokens=5,
        )
        await message.answer(f"✅ OpenAI OK — модель `{get_model('router')}` отвечает", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ OpenAI ОШИБКА:\n`{type(e).__name__}: {str(e)[:300]}`", parse_mode="Markdown")


@router.message(F.voice)
async def handle_voice(message: Message, state: FSMContext, scheduler=None):
    if not _is_allowed(message.from_user.id):
        return
    from bot.handlers.voice import transcribe_and_save

    await message.answer("🎙️ Распознаю...")
    text, local_path = await transcribe_and_save(message)

    if not text:
        await message.answer("❌ Не смог распознать. Попробуй ещё раз.")
        return

    await _process_text(message, text, state, scheduler, message_type="voice",
                        transcription=text)


@router.message(F.text)
async def handle_text(message: Message, state: FSMContext, scheduler=None):
    if not _is_allowed(message.from_user.id):
        return

    # Check if user is in onboarding flow first
    from bot.modules.onboarding import is_in_onboarding, handle_onboarding_answer
    if await is_in_onboarding(message.from_user.id):
        response, is_done = await handle_onboarding_answer(message.from_user.id, message.text)
        if response:
            try:
                await message.answer(response, parse_mode="Markdown")
            except Exception:
                await message.answer(response)
        return

    # ── Pending vision actions (after photo analysis) ───────────────────
    handled = await _check_pending_vision_actions(message, scheduler)
    if handled:
        return

    # Check FSM state (section builder, etc.)
    current_state = await state.get_state()
    if current_state:
        from bot.modules.section_builder import handle_fsm_input
        handled = await handle_fsm_input(message, state)
        if handled:
            return

    await _process_text(message, message.text, state, scheduler, message_type="text")


_CONFIRM_WORDS = frozenset({
    "да", "ок", "окей", "ладно", "давай", "сохрани", "запиши", "добавь",
    "запиши в финансы", "сделай задачей", "добавь в учёбу", "выполни",
    "подтверди", "yes", "ok", "sure",
})
_CANCEL_WORDS = frozenset({
    "нет", "не надо", "отмена", "отменить", "cancel", "стоп", "stop",
    "не сохраняй", "не добавляй",
})


async def _check_pending_vision_actions(message: Message, scheduler) -> bool:
    """Check if user is responding to a pending vision suggestion.

    Returns True if the message was handled (caller should return).
    """
    import json as _json
    user_id = message.from_user.id
    text = (message.text or "").strip().lower()

    # Fast exit: only intercept short confirmation/cancellation phrases
    is_confirm = text in _CONFIRM_WORDS or any(text.startswith(w) for w in _CONFIRM_WORDS)
    is_cancel = text in _CANCEL_WORDS

    if not (is_confirm or is_cancel):
        return False

    try:
        state = await db.conversation_state_get(user_id)
        if state.get("active_topic") != "photo":
            return False

        pending_json = state.get("pending_vision_actions_json")
        if not pending_json:
            return False

        actions = _json.loads(pending_json)
        if not actions:
            return False

    except Exception:
        return False

    # Clear pending actions regardless of confirm/cancel
    await db.conversation_state_update(
        user_id,
        pending_vision_actions_json=None,
        active_topic=None,
    )

    if is_cancel:
        try:
            await message.answer("Ок, не сохраняю.")
        except Exception:
            pass
        return True

    # Confirm → dispatch actions
    try:
        from bot.modules.dispatcher import dispatch_actions
        response = await dispatch_actions(
            actions=actions,
            user_id=user_id,
            ai_reply="",
            scheduler=scheduler,
            bot=message.bot,
            confidence=0.9,
        )
        if response:
            try:
                await message.answer(response, parse_mode="Markdown")
            except Exception:
                await message.answer(response)
        else:
            await message.answer("✅ Готово.")
    except Exception as e:
        logging.error("pending_vision_actions dispatch error: %s", e, exc_info=True)
        await message.answer("⚠️ Не удалось выполнить действие.")

    return True


async def _process_text(message: Message, text: str, state: FSMContext,
                        scheduler, message_type: str = "text", transcription: str = None):
    """Core: classify → dispatch → log → reply."""
    user_id = message.from_user.id
    log_id = await db.log_message(
        user_id, message_type, text, transcription=transcription
    )

    try:
        result = await classify(text, user_id=user_id)
        actions = result.get("actions", [])
        ai_reply = result.get("reply", "")
        chat_response_needed = result.get("chat_response_needed", False)
        chat_question = result.get("chat_question", None)
        is_data_query = result.get("is_data_query", False)
        needs_retrieval = result.get("needs_retrieval", False)
        data_query_type = result.get("data_query_type", None)
        contextual_followup = result.get("contextual_followup", False)
        format_request = result.get("format_request", None)
        safety_level = result.get("safety_level", "safe")
        memory_update_needed = result.get("memory_update_needed", False)
        settings_update_needed = result.get("settings_update_needed", False)
        reply_style = result.get("reply_style", None)
        needs_reasoning = result.get("needs_reasoning", False)
        refers_to_previous = result.get("refers_to_previous", False)
        # Overall confidence: min across actions, or 0.9 for pure chat
        _action_confs = [float(a.get("confidence", 0.9)) for a in actions if a.get("intent") not in ("chat", "unknown")]
        confidence = min(_action_confs) if _action_confs else 0.9

        # Auto-save settings if AI detected a change in conversational style
        if settings_update_needed or reply_style:
            from bot.modules.settings_manager import apply_settings_update
            await apply_settings_update(user_id, result)

        response = await dispatch_actions(
            actions=actions,
            user_id=user_id,
            ai_reply=ai_reply,
            chat_response_needed=chat_response_needed,
            state=state,
            scheduler=scheduler,
            bot=message.bot,
            message_text=text,
            is_data_query=is_data_query,
            needs_retrieval=needs_retrieval,
            data_query_type=data_query_type,
            safety_level=safety_level,
            contextual_followup=contextual_followup,
            format_request=format_request,
            needs_reasoning=needs_reasoning,
            refers_to_previous=refers_to_previous,
            chat_question=chat_question,
            confidence=confidence,
        )

        # Save conversation state after each message exchange
        try:
            await db.conversation_state_update(
                user_id,
                last_user_message=text[:300],
                last_bot_response=response[:300] if response else "",
            )
        except Exception:
            pass

        await db.log_update_response(
            log_id, response,
            actions_json=json.dumps(actions, ensure_ascii=False),
        )

        # Handle special markers from dispatcher
        # Support format: "summary text\n__FILE__:path" or plain "__FILE__:path"
        file_marker = "__FILE__:"
        if file_marker in response:
            from aiogram.types import FSInputFile
            from pathlib import Path
            idx = response.index(file_marker)
            summary_text = response[:idx].strip()
            file_path = response[idx + len(file_marker):].strip()
            if summary_text:
                try:
                    await message.answer(summary_text, parse_mode="Markdown")
                except Exception:
                    await message.answer(summary_text)
            if Path(file_path).exists():
                await message.answer_document(FSInputFile(file_path))
            else:
                await message.answer("❌ Файл не найден")

        elif response.startswith("__SECTION_BUILDER__:"):
            # Format: __SECTION_BUILDER__:name:title:field1,field2,...
            parts = response[len("__SECTION_BUILDER__:"):].split(":", 2)
            section_name = parts[0] if len(parts) > 0 else "section"
            section_title = parts[1] if len(parts) > 1 else section_name
            suggested = parts[2].split(",") if len(parts) > 2 else []
            from bot.modules.section_builder import start_section_builder
            await start_section_builder(message, state, section_name, section_title, suggested)

        else:
            # Apply reply_style if user has it set
            try:
                from bot.modules.settings_manager import apply_reply_style
                response = await apply_reply_style(response, user_id)
            except Exception:
                pass

            # Attach contextual inline keyboard based on last action
            reply_markup = None
            try:
                from bot.modules.keyboards import (
                    build_task_keyboard, build_plan_keyboard,
                    build_ideas_keyboard, build_expense_keyboard,
                )
                if actions:
                    top_intent = actions[0].get("intent", "")
                    top_params = actions[0].get("params", {})
                    if top_intent in ("task_create", "task_update") and top_params.get("task_id"):
                        reply_markup = build_task_keyboard(top_params["task_id"])
                    elif top_intent in ("schedule_plan_day", "regime_day_plan"):
                        reply_markup = build_plan_keyboard()
                    elif top_intent == "idea_save" and top_params.get("idea_id"):
                        reply_markup = build_ideas_keyboard(top_params["idea_id"])
                    elif top_intent in ("expense_add",):
                        reply_markup = build_expense_keyboard()
            except Exception:
                reply_markup = None

            # Try Markdown first, fall back to plain text
            try:
                await message.answer(response, parse_mode="Markdown",
                                     reply_markup=reply_markup)
            except Exception:
                await message.answer(response, reply_markup=reply_markup)

    except Exception:
        logging.exception("Error in _process_text")
        await db.log_update_response(log_id, "⚠️ Ошибка обработки")
        await message.answer("⚠️ Произошла ошибка. Попробуй ещё раз.")
        return

    # Auto-extract personal facts from the message (fire-and-forget, no await blocking)
    try:
        from bot.modules.auto_memory import auto_extract_memory
        await auto_extract_memory(user_id, text, log_id=log_id)
    except Exception:
        pass  # never block the main flow
