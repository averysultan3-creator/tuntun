import json
import logging
import re
from datetime import datetime, timedelta

import pytz
from openai import AsyncOpenAI

import config
from bot.ai.prompts import SYSTEM_PROMPT
from bot.ai.model_router import get_model, choose_model

_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
_WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

# ──────────────────────────────────────────────────────────────
# Lightweight context for the router (no heavy DB queries)
# ──────────────────────────────────────────────────────────────

async def _get_lightweight_router_context(user_id: int) -> str:
    """Build minimal context for intent classification.

    Only reads conversation_state — fast, cheap, no retrieval.
    Full user data is loaded in chat_assistant.py when actually answering.
    """
    try:
        from bot.db.database import db
        state = await db.conversation_state_get(user_id)
        if not state:
            return ""
        parts = []
        if state.get("active_topic"):
            parts.append(f"active_topic: {state['active_topic']}")
        if state.get("active_section"):
            parts.append(f"active_section: {state['active_section']}")
        if state.get("active_object_type") and state.get("active_object_id"):
            parts.append(
                f"active_object: {state['active_object_type']} #{state['active_object_id']}"
            )
        if state.get("active_date"):
            parts.append(f"active_date: {state['active_date']}")
        if state.get("last_discussed_task_ids"):
            parts.append(f"last_task_ids: {state['last_discussed_task_ids']}")
        if state.get("last_discussed_reminder_ids"):
            parts.append(f"last_reminder_ids: {state['last_discussed_reminder_ids']}")
        if state.get("last_plan_json"):
            parts.append("last_plan: exists")
        if state.get("last_table_json"):
            parts.append("last_table: exists")
        return ", ".join(parts) if parts else ""
    except Exception:
        return ""


async def _get_recent_router_messages(
    user_id: int,
    current_message: str,
    limit: int = 6,
) -> list[dict]:
    """Return recent dialogue for the router without heavy user-data retrieval."""
    try:
        from bot.db.database import db

        rows = await db.message_logs_recent(user_id, limit=limit + 1)
        messages = []
        skipped_current = False
        for row in reversed(rows):
            user_text = str(row.get("original_text") or "").strip()
            bot_text = str(row.get("bot_response") or "").strip()

            # _process_text logs the current user message before classify().
            # Skip that open row so the final current message is not duplicated.
            if (
                not skipped_current
                and not bot_text
                and user_text == current_message.strip()
            ):
                skipped_current = True
                continue

            if user_text:
                messages.append({"role": "user", "content": user_text[:600]})
            if bot_text:
                messages.append({"role": "assistant", "content": bot_text[:600]})

        return messages[-limit * 2:]
    except Exception:
        return []

_FALLBACK = {
    "actions": [],
    "chat_response_needed": True,
    "chat_question": None,
    "is_data_query": False,
    "data_query_type": None,
    "needs_retrieval": False,
    "contextual_followup": False,
    "refers_to_previous": False,
    "format_request": None,
    "safety_level": "safe",
    "memory_update_needed": False,
    "settings_update_needed": False,
    "reply_style": None,
    "needs_reasoning": False,
    "reply": "Чем могу помочь?",
}

# Replies that indicate the AI misclassified a general question as a data query
_BAD_REPLY_PATTERNS = (
    "по этой теме пока нет записей",
    "нет записей",
    "записей пока нет",
    "не могу ответить",
    "не нашёл данных",
)


def _extract_json(text: str) -> dict | None:
    """Try to extract JSON from a string that may contain extra text."""
    text = text.strip()
    # Remove markdown code fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()
    text = text.rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find first { ... } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _normalize(result: dict) -> dict:
    """Normalize AI response to have actions[], chat_response_needed, chat_question, reply
    plus new fields: is_data_query, needs_retrieval, data_query_type.
    """
    if result is None:
        return dict(_FALLBACK)

    # Extract chat / routing fields
    chat_response_needed = bool(result.get("chat_response_needed", False))
    chat_question = result.get("chat_question", None)
    reply = result.get("reply", "")
    is_data_query = bool(result.get("is_data_query", False))
    needs_retrieval = bool(result.get("needs_retrieval", False))
    data_query_type = result.get("data_query_type", None)
    contextual_followup = bool(result.get("contextual_followup", False))
    refers_to_previous = bool(result.get("refers_to_previous", False))
    format_request = result.get("format_request", None)
    safety_level = result.get("safety_level", "safe")
    memory_update_needed = bool(result.get("memory_update_needed", False))
    settings_update_needed = bool(result.get("settings_update_needed", False))
    reply_style = result.get("reply_style", None)
    needs_reasoning = bool(result.get("needs_reasoning", False))

    # Safety: if reply looks like a "no records" boilerplate on a general question,
    # mark chat_response_needed so dispatcher can try a proper chat call.
    if not is_data_query and reply:
        reply_lower = reply.lower()
        if any(p in reply_lower for p in _BAD_REPLY_PATTERNS):
            chat_response_needed = True
            reply = ""  # force dispatcher to call handle_chat_response

    if "actions" in result:
        if not isinstance(result["actions"], list):
            result["actions"] = []
        # Ensure each action has required fields, strip chat/unknown intents
        cleaned = []
        for a in result["actions"]:
            if isinstance(a, dict) and "intent" in a:
                intent = a.get("intent", "")
                if intent in ("chat", "unknown"):
                    continue  # discard these
                cleaned.append({
                    "intent": intent,
                    "params": a.get("params", {}),
                    "confidence": float(a.get("confidence", 0.8)),
                })
        # If no real actions, mark as chat
        if not cleaned:
            chat_response_needed = True
        return {
            "actions": cleaned,
            "chat_response_needed": chat_response_needed,
            "chat_question": chat_question,
            "is_data_query": is_data_query,
            "data_query_type": data_query_type,
            "needs_retrieval": needs_retrieval,
            "contextual_followup": contextual_followup,
            "refers_to_previous": refers_to_previous,
            "format_request": format_request,
            "safety_level": safety_level,
            "memory_update_needed": memory_update_needed,
            "settings_update_needed": settings_update_needed,
            "reply_style": reply_style,
            "needs_reasoning": needs_reasoning,
            "reply": reply,
        }

    # Legacy single-intent format fallback
    if "intent" in result:
        intent = result["intent"]
        if intent in ("chat", "unknown"):
            return {
                "actions": [],
                "chat_response_needed": True,
                "chat_question": None,
                "is_data_query": False,
                "data_query_type": None,
                "needs_retrieval": False,
                "reply": reply or "Чем могу помочь?",
            }
        return {
            "actions": [{
                "intent": intent,
                "params": result.get("params", {}),
                "confidence": 0.85,
            }],
            "chat_response_needed": chat_response_needed,
            "chat_question": chat_question,
            "is_data_query": is_data_query,
            "data_query_type": data_query_type,
            "needs_retrieval": needs_retrieval,
            "reply": result.get("response", reply),
        }

    return dict(_FALLBACK)


async def classify(user_message: str, user_id: int = None) -> dict:
    """Classify user message into actions + optional chat response."""
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    dt_str = f"{now.strftime('%Y-%m-%d %H:%M')} ({_WEEKDAYS_RU[now.weekday()]})"

    # Lightweight context for router: only conversation_state (no heavy DB queries).
    # Full retrieval happens in chat_assistant.py when actually answering.
    user_context_block = ""
    if user_id:
        try:
            ctx = await _get_lightweight_router_context(user_id)
            if ctx:
                user_context_block = (
                    "\n===========================\n"
                    "КОНТЕКСТ ДИАЛОГА\n"
                    "===========================\n"
                    f"{ctx}\n"
                )
        except Exception as ctx_err:
            logging.warning(f"classify: context load error: {ctx_err}")

    # Build capabilities block for the prompt
    capabilities_block = ""
    try:
        from bot.core.capabilities import CAPABILITIES_SHORT, MODEL_INFO
        capabilities_block = f"Умеешь: {CAPABILITIES_SHORT}\nМодели: {MODEL_INFO}"
    except Exception:
        pass

    system = SYSTEM_PROMPT.format(
        datetime=dt_str,
        timezone=config.TIMEZONE,
        today=today,
        tomorrow=tomorrow,
        user_context_block=user_context_block,
        capabilities_block=capabilities_block,
    )

    try:
        router_messages = []
        if user_id:
            router_messages = await _get_recent_router_messages(user_id, user_message)

        messages = [{"role": "system", "content": system}]
        messages.extend(router_messages)
        messages.append({"role": "user", "content": user_message})

        response = await _client.chat.completions.create(
            model=get_model("router"),  # always cheap router for classification
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_completion_tokens=1500,
        )
        content = response.choices[0].message.content
        raw = _extract_json(content)
        if raw is None:
            logging.warning(f"classify: could not extract JSON from: {content[:200]}")
            return dict(_FALLBACK)
        return _normalize(raw)

    except Exception as e:
        err_type = type(e).__name__
        err_str = str(e)
        logging.error(f"classify error user={user_id}: {err_type}: {err_str}")
        # Map known OpenAI error types to helpful messages
        err_lower = err_str.lower()
        if "authentication" in err_lower or "invalid_api_key" in err_lower or "incorrect api key" in err_lower:
            msg = "❌ Неверный OpenAI API ключ. Проверь OPENAI_API_KEY в .env"
        elif "model_not_found" in err_lower or "does not exist" in err_lower or "invalid model" in err_lower:
            from bot.ai.model_router import get_model as _gm
            msg = f"❌ Модель не найдена: {_gm('router')}. Проверь OPENAI_MODEL_ROUTER в .env"
        elif "insufficient_quota" in err_lower or "quota" in err_lower or "billing" in err_lower:
            msg = "❌ Закончились кредиты OpenAI. Проверь баланс на platform.openai.com"
        elif "rate_limit" in err_lower or "rate limit" in err_lower:
            msg = "⏳ Превышен лимит запросов OpenAI. Подожди немного."
        elif "connection" in err_lower or "timeout" in err_lower or "network" in err_lower:
            msg = "🌐 Нет соединения с OpenAI. Проверь интернет на сервере."
        else:
            msg = f"❌ Ошибка AI ({err_type}): {err_str[:120]}"
        return {
            "actions": [],
            "chat_response_needed": True,
            "chat_question": None,
            "reply": msg,
        }
