import logging
from aiogram.fsm.context import FSMContext

import config
from bot.ai.model_router import should_use_backend_only
from bot.modules import tasks, study, schedule, reminders, memory, projects, dynamic, regime, user_settings, ideas, onboarding

# ── Patterns that indicate a bad/empty router reply ────────────────────────────
_BAD_REPLY_PATTERNS = (
    "чем могу помочь",
    "нет записей",
    "нет данных",
    "по этой теме пока нет",
    "не смог найти",
    "не нашёл данных",
)


def _should_call_chat_response(
    ai_reply: str,
    needs_reasoning: bool,
    safety_level: str,
    confidence: float,
    is_data_query: bool,
    has_action_results: bool,
    has_chat_question: bool,
) -> bool:
    """Decide if we need to call handle_chat_response().

    Returns True only when the router's ai_reply is insufficient or we need
    deeper intelligence. Prevents unnecessary second model calls.

    Cases that ALWAYS call handle_chat_response:
      - needs_reasoning=True (plan day, complex analytics)
      - safety_level confirm/dangerous
      - confidence < 0.75 (ambiguous message)
      - is_data_query with no backend answer yet
      - actions executed + separate chat_question from user
      - ai_reply is empty or boilerplate

    Otherwise: use router's ai_reply directly (no second model call).
    """
    # Complex reasoning always needs full model
    if needs_reasoning:
        return True
    # Dangerous/confirm actions always need full context
    if safety_level in ("confirm", "dangerous"):
        return True
    # Low confidence = ambiguous → need reasoning
    if confidence < 0.75:
        return True
    # Data query where backend produced no answer → real query needed
    if is_data_query and not has_action_results:
        return True
    # Actions executed + user also asked a separate question → answer it
    if has_action_results and has_chat_question:
        return True
    # Check if router's reply is good enough to use directly
    reply = (ai_reply or "").strip()
    if len(reply) < 40:
        return True
    reply_lower = reply.lower()
    if any(p in reply_lower for p in _BAD_REPLY_PATTERNS):
        return True
    # Router gave a good, substantive reply — use it directly
    return False


async def _safe_delete(intent: str, params: dict, user_id: int) -> str | None:
    """Check if a delete/cancel would affect multiple objects.

    Returns:
        str  — if we should NOT proceed (show confirmation/list instead)
        None — if safe to proceed with normal handler
    """
    from bot.db.database import db

    if intent == "reminder_cancel":
        keyword = params.get("keyword") or params.get("text") or ""
        reminder_id = params.get("reminder_id")
        if reminder_id:
            return None  # explicit ID → safe

        if keyword:
            # Find matching reminders
            all_reminders = await db.reminder_list(user_id)
            keyword_lower = keyword.lower()
            matches = [
                r for r in all_reminders
                if keyword_lower in str(r.get("text", "")).lower()
                or keyword_lower in str(r.get("remind_at", "")).lower()
            ]
            if len(matches) == 1:
                # Patch params with the found ID so normal handler uses it
                params["reminder_id"] = matches[0]["id"]
                return None  # safe to proceed
            elif len(matches) > 1:
                lines = [f"Нашёл {len(matches)} напоминания по «{keyword}»:"]
                for i, r in enumerate(matches[:5], 1):
                    lines.append(f"  {i}. #{r['id']} — {r['text']} ({str(r['remind_at'])[:16]})")
                lines.append("Какое удалить? Напиши номер или ID.")
                return "\n".join(lines)
        return None  # let normal handler figure it out

    if intent == "task_delete":
        keyword = params.get("keyword") or params.get("title") or ""
        task_id = params.get("task_id")
        if task_id:
            return None  # explicit ID → safe

        if keyword:
            from bot.db.database import db as _db
            matches = await _db.task_find_by_title(user_id, keyword)
            if len(matches) == 1:
                params["task_id"] = matches[0]["id"]
                return None
            elif len(matches) > 1:
                lines = [f"Нашёл {len(matches)} задач по «{keyword}»:"]
                for i, t in enumerate(matches[:5], 1):
                    lines.append(f"  {i}. #{t['id']} — {t['title']}")
                lines.append("Какую удалить? Напиши номер или ID.")
                return "\n".join(lines)
        return None

    return None



_HANDLERS = {
    "task_create": tasks.handle_create,
    "task_list": tasks.handle_list,
    "task_complete": tasks.handle_complete,
    "task_update": tasks.handle_update,
    "task_delete": tasks.handle_delete,
    "study_add_subject": study.handle_add_subject,
    "study_add_record": study.handle_add_record,
    "study_list": study.handle_list,
    "schedule_view": schedule.handle_view,
    "schedule_add_event": schedule.handle_add_event,
    "schedule_plan_day": schedule.handle_plan_day,
    "reminder_create": reminders.handle_create,
    "reminder_list": reminders.handle_list,
    "reminder_cancel": reminders.handle_cancel,
    "memory_save": memory.handle_save,
    "memory_recall": memory.handle_recall,
    "project_create": projects.handle_create,
    "project_list": projects.handle_list,
    "expense_add": projects.handle_expense_add,
    "expense_stats": projects.handle_expense_stats,
    "section_create": dynamic.handle_create,
    "section_record_add": dynamic.handle_record_add,
    "section_query": dynamic.handle_query,
    "regime_sleep_calc": regime.handle_sleep_calc,
    "regime_day_plan": regime.handle_day_plan,
    "setting_save": user_settings.handle_save,
    "setting_get": user_settings.handle_get,
    # Ideas
    "idea_save": ideas.handle_save,
    "idea_list": ideas.handle_list,
    "idea_convert_to_task": ideas.handle_convert_to_task,
    # Dynamic section management
    "section_add_field": dynamic.handle_add_field,
    "section_rename": dynamic.handle_rename,
    "record_edit": dynamic.handle_edit,
    # Onboarding
    "start_onboarding": onboarding.handle_start,
}

# Lazy-load heavy modules to avoid circular imports at startup
_LAZY_HANDLERS = {
    "export_excel": ("bot.modules.exports", "handle_excel"),
    "export_txt": ("bot.modules.exports", "handle_txt"),
    "backup_create": ("bot.modules.backup", "handle_create"),
    "analytics_query": ("bot.modules.analytics", "handle_query"),
    "menu_show": ("bot.modules.menu", "handle_show"),
}


async def _call_lazy(module_path: str, func_name: str, **kwargs) -> str:
    import importlib
    mod = importlib.import_module(module_path)
    fn = getattr(mod, func_name)
    return await fn(**kwargs)


async def dispatch_actions(actions: list, user_id: int, ai_reply: str,
                           chat_response_needed: bool = False,
                           state: FSMContext = None, scheduler=None, bot=None,
                           message_text: str = None,
                           is_data_query: bool = False,
                           needs_retrieval: bool = False,
                           data_query_type: str = None,
                           safety_level: str = "safe",
                           contextual_followup: bool = False,
                           format_request: str = None,
                           needs_reasoning: bool = False,
                           refers_to_previous: bool = False,
                           chat_question: str = None,
                           confidence: float = 0.9) -> str:
    """Execute all actions with sufficient confidence and combine responses.

    Safe Actions rules:
    - safety_level="dangerous" → require explicit confirmation keyword
    - DESTRUCTIVE_INTENTS with confidence < 0.85 → require confirmation
    - Multiple affected objects → ask which one
    """
    results = []
    low_confidence_questions = []

    for action in actions:
        intent = action.get("intent", "unknown")
        params = action.get("params", {})
        confidence = float(action.get("confidence", 0.8))

        # Skip any residual chat/unknown intents that slipped through normalize
        if intent in ("chat", "unknown"):
            continue

        if confidence < config.MIN_CONFIDENCE:
            low_confidence_questions.append(
                f"❓ Не уверен: {intent} — {params}. Уточни, пожалуйста."
            )
            continue

        # ── Safe Actions Layer ────────────────────────────────────────────
        # 1. Explicit dangerous safety level from router → always confirm
        if safety_level == "dangerous":
            results.append(
                f"⚠️ Опасное действие: {intent}.\n"
                f"Напиши явно «подтверди» чтобы продолжить."
            )
            continue

        # 2. Known destructive intents with low confidence → confirm
        if intent in config.DESTRUCTIVE_INTENTS and confidence < 0.85:
            results.append(
                f"⚠️ Действие {intent} требует подтверждения (уверенность {confidence:.0%}).\n"
                f"Напиши «подтверди {intent}» для выполнения."
            )
            continue

        # 3. task_delete / reminder_cancel → try to find single target, else list
        if intent in ("task_delete", "reminder_cancel"):
            safe_result = await _safe_delete(
                intent=intent, params=params, user_id=user_id
            )
            if safe_result is not None:
                results.append(safe_result)
                continue
            # safe_result=None means "proceed with normal handler"


        try:
            handler = _HANDLERS.get(intent)
            if handler:
                result = await handler(
                    user_id=user_id, params=params, ai_response=ai_reply,
                    scheduler=scheduler, bot=bot,
                )
            elif intent in _LAZY_HANDLERS:
                module_path, func_name = _LAZY_HANDLERS[intent]
                result = await _call_lazy(
                    module_path, func_name,
                    user_id=user_id, params=params, ai_response=ai_reply,
                    scheduler=scheduler, bot=bot,
                )
            else:
                logging.warning(f"Unknown intent: {intent}")
                result = ai_reply or f"Не знаю как выполнить: {intent}"

            if result:
                results.append(result)

        except Exception as e:
            logging.error(f"dispatch_actions error for intent={intent} user={user_id}: {e}", exc_info=True)
            results.append(f"⚠️ Не смог выполнить «{intent}». Ошибка записана в лог.")

    results.extend(low_confidence_questions)

    # ── Determine the chat part of the response ───────────────────────────
    chat_answer = ai_reply or ""

    # ── Backend-only check ─────────────────────────────────────────────────
    _all_intents = [a.get("intent", "") for a in actions if a.get("intent") not in ("chat", "unknown")]
    _min_conf = min((float(a.get("confidence", 0.8)) for a in actions), default=confidence) if actions else confidence
    _backend_only = bool(results) and should_use_backend_only(_all_intents, _min_conf)
    if _backend_only:
        logging.debug(
            "model_router | purpose=backend_only intents=%s conf=%.2f -> skip model call",
            _all_intents, _min_conf,
        )

    # ── Decide whether to call handle_chat_response ───────────────────────
    # If backend_only and NO separate chat_question: skip entirely.
    # If backend_only but there IS a chat_question alongside actions: answer it.
    _has_chat_question = bool(chat_question and chat_question.strip())
    _need_chat = False

    if chat_response_needed:
        if _backend_only and not _has_chat_question:
            # Pure backend action, user asked no question → skip model call
            _need_chat = False
        elif _backend_only and _has_chat_question:
            # Mixed: action done + user asked a question → answer with CHAT (not reasoning)
            _need_chat = True
            needs_reasoning = False  # Force cheap CHAT model for follow-up
        else:
            _need_chat = _should_call_chat_response(
                ai_reply=ai_reply,
                needs_reasoning=needs_reasoning,
                safety_level=safety_level,
                confidence=_min_conf,
                is_data_query=is_data_query,
                has_action_results=bool(results),
                has_chat_question=_has_chat_question,
            )

    if _need_chat:
        try:
            from bot.modules.chat_assistant import handle_chat_response
            _question = chat_question or message_text or chat_answer or "Помоги"
            chat_answer = await handle_chat_response(
                user_id=user_id,
                question=_question,
                is_data_query=is_data_query,
                needs_retrieval=needs_retrieval,
                data_query_type=data_query_type,
                needs_reasoning=needs_reasoning,
                refers_to_previous=refers_to_previous,
                confidence=_min_conf,
                safety_level=safety_level,
                intents=_all_intents,
            )
        except Exception as e:
            logging.warning("dispatch_actions: handle_chat_response failed: %s", e)
            chat_answer = chat_answer or "Чем могу помочь?"
    elif not _need_chat and chat_response_needed and not results:
        # No actions, no model call needed — use router's reply as-is
        pass  # chat_answer already = ai_reply

    if results:
        if _need_chat and chat_answer:
            results.append(chat_answer)
        return "\n\n".join(results)

    if chat_response_needed:
        return chat_answer or "Чем могу помочь?"

    return ai_reply or "Чем могу помочь?"
