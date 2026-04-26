"""User context loader + chat response handler for TUNTUN AI assistant.

get_user_context(user_id, query=None) builds a rich context string
that is injected into the AI system-prompt so the bot can answer
questions about the user's real data (tasks, reminders, projects,
sections, memory, recent history, etc.).

handle_chat_response(user_id, question, is_data_query, needs_retrieval)
is a dedicated GPT call for chat answers — used as a safety net when
the classify() reply is empty or contains "no records" boilerplate.

Structure of the returned block:
  BASE CONTEXT   — always present: today's tasks, reminders,
                   active projects, known sections, settings.
  QUERY CONTEXT  — only when query is given: memory facts, section
                   records, expenses and recent messages that match
                   the user's query keywords (via memory_retriever).
"""
import logging
from datetime import date

from openai import AsyncOpenAI

import config
from bot.ai.model_router import get_model, choose_model, should_use_reasoning
from bot.db.database import db
from bot.modules.memory_retriever import retrieve_context


def _build_capabilities_text() -> str:
    """Build capabilities text dynamically from the capabilities module."""
    try:
        from bot.core.capabilities import get_capabilities_text, MODEL_INFO
        return (
            "Твои возможности:\n" + get_capabilities_text() + "\n\n"
            "Модели: " + MODEL_INFO
        )
    except Exception:
        return (
            "Умеешь: задачи, напоминания, голос→действия, базы данных, финансы, "
            "память, план дня, экспорт Excel/TXT, backup, учёба, аналитика, ChatGPT-режим."
        )


_IDENTITY = """Ты — TUNTUN, персональный AI-ассистент пользователя в Telegram.
Ты работаешь как личная операционная система:
память, задачи, напоминания, базы данных, финансы, учёба, проекты, расписание,
планирование, голос, фото, Excel, backup, аналитика.

Ты не просто отвечаешь на вопросы.
Ты помогаешь пользователю организовывать жизнь, задачи, данные и проекты.

Твоя задача: понять сообщение → найти нужные данные → ответить как умный ассистент
→ предложить следующий полезный шаг → не фантазировать → не удалять без уверенности.

Отвечаешь только на русском. Коротко, конкретно, без воды."""

_chat_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _chat_client
    if _chat_client is None:
        _chat_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _chat_client


async def _get_recent_conversation(user_id: int, limit: int = 10) -> list[dict]:
    """Fetch recent message log as OpenAI messages format."""
    try:
        rows = await db.message_logs_recent(user_id, limit=limit)
        messages = []
        for row in reversed(rows):  # oldest first
            user_text = str(row.get("original_text") or "").strip()
            bot_text  = str(row.get("bot_response") or "").strip()
            if user_text:
                messages.append({"role": "user", "content": user_text})
            if bot_text:
                messages.append({"role": "assistant", "content": bot_text[:400]})
        return messages
    except Exception:
        return []


async def _get_conversation_state_block(user_id: int) -> str:
    """Build a brief active-context block for the system prompt."""
    try:
        state = await db.conversation_state_get(user_id)
        if not state:
            return ""
        parts = []
        if state.get("active_topic"):
            parts.append(f"Активная тема: {state['active_topic']}")
        if state.get("active_section"):
            parts.append(f"Активный раздел: {state['active_section']}")
        if state.get("active_object_type") and state.get("active_object_id"):
            parts.append(f"Последний объект: {state['active_object_type']} #{state['active_object_id']}")
        if state.get("active_date"):
            parts.append(f"Обсуждаемая дата: {state['active_date']}")
        if state.get("last_plan_json"):
            parts.append("Последний план дня: [в памяти — пользователь может спросить «выведи таблицей»]")
        return "\n".join(parts) if parts else ""
    except Exception:
        return ""


async def handle_chat_response(
    user_id: int,
    question: str,
    is_data_query: bool = False,
    needs_retrieval: bool = False,
    data_query_type: str | None = None,
    confidence: float = 0.9,
    safety_level: str = "safe",
    refers_to_previous: bool = False,
    intents: list | None = None,
    needs_reasoning: bool = False,
) -> str:
    """GPT call using CHAT or REASONING model based on context.

    Model selection:
      - choose_model() picks REASONING when: plan day, complex analytics,
        ambiguous/dangerous actions, low confidence, or router flagged it.
      - Otherwise uses CHAT (cheap, gpt-5.4-mini).
    """
    # ── 1. Build system prompt ────────────────────────────────────────────
    caps_text = _build_capabilities_text()
    context_state = await _get_conversation_state_block(user_id)

    system_parts = [_IDENTITY, "", caps_text]

    if context_state:
        system_parts.append("\n--- Активный контекст ---\n" + context_state)

    # ── 2. User data context ──────────────────────────────────────────────
    context_parts: list[str] = []
    try:
        base_ctx = await get_user_context(
            user_id,
            query=question if needs_retrieval else None,
        )
        if base_ctx:
            context_parts.append(base_ctx)
    except Exception as e:
        logging.warning("handle_chat_response: context error: %s", e)

    if context_parts:
        system_parts.append("\n--- Данные пользователя ---\n" + "\n".join(context_parts))

    # If data query but no context → honest reply
    if is_data_query and not context_parts:
        type_labels = {
            "finance": "по финансам",
            "ads": "по рекламе",
            "tasks": "по задачам",
            "reminders": "по напоминаниям",
            "study": "по учёбе",
            "memory": "в памяти",
            "records": "в разделах",
            "analytics": "для аналитики",
        }
        label = type_labels.get(data_query_type or "", "по этой теме")
        return (
            f"По сохранённым данным {label} пока ничего нет. "
            "Хочешь создать раздел или добавить запись?"
        )

    system = "\n".join(system_parts)

    # ── 3. Conversation history ───────────────────────────────────────────
    history = await _get_recent_conversation(user_id, limit=10)

    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    # Don't re-add current question if it's already the last user message
    if not history or history[-1].get("content") != question:
        messages.append({"role": "user", "content": question})

    try:
        model = choose_model(
            "chat",
            confidence=confidence,
            safety_level=safety_level,
            refers_to_previous=refers_to_previous,
            intents=intents,
            needs_reasoning=needs_reasoning,
        )
        resp = await _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
            max_tokens=800,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error("handle_chat_response GPT error: %s", e)
        return "Не смог ответить. Попробуй ещё раз."



async def get_user_context(user_id: int, query: str = None) -> str:
    """Return a formatted context string for the given user.

    Args:
        user_id: Telegram user id.
        query:   The raw user message.  When supplied, a keyword search
                 across all data sources is performed and the relevant
                 snippets are appended to the base context.

    Returns:
        Multi-line string (may be empty if no data exists yet).
    """
    parts = []
    try:
        today_str = date.today().strftime("%Y-%m-%d")

        # ── 1. Tasks ──────────────────────────────────────────────────────
        today_tasks = await db.task_list(user_id, filter_date=today_str)
        all_tasks   = await db.task_list(user_id)
        if today_tasks:
            titles = ", ".join('"{}"'.format(t["title"]) for t in today_tasks[:6])
            extra  = " и ещё {}".format(len(today_tasks) - 6) if len(today_tasks) > 6 else ""
            parts.append("Задачи на сегодня ({}): {}{}".format(len(today_tasks), titles, extra))
        elif all_tasks:
            titles = ", ".join('"{}"'.format(t["title"]) for t in all_tasks[:4])
            parts.append("Задач на сегодня нет. В работе ({}): {}".format(len(all_tasks), titles))

        # ── 2. Active reminders ───────────────────────────────────────────
        reminders = await db.reminder_list(user_id)
        if reminders:
            r_items = "; ".join(
                '"{}" — {}'.format(r["text"], str(r["remind_at"])[:16])
                for r in reminders[:4]
            )
            parts.append("Напоминания: " + r_items)

        # ── 3. Projects ───────────────────────────────────────────────────
        projects = await db.project_list(user_id)
        if projects:
            p_items = ", ".join(
                "{} ({})".format(p["name"], p.get("title") or p["name"])
                for p in projects[:8]
            )
            parts.append("Проекты: " + p_items)

        # ── 4. Dynamic sections the user has created ──────────────────────
        sections = await db.section_list(user_id)
        if sections:
            s_items = ", ".join(
                "{} ({})".format(s["name"], s.get("title") or s["name"])
                for s in sections[:10]
            )
            parts.append("Разделы/базы: " + s_items)

        # ── 5. Settings ───────────────────────────────────────────────────
        settings = await db._fetchall(
            "SELECT key, value FROM settings WHERE user_id=? ORDER BY key",
            (user_id,),
        )
        if settings:
            s_str = ", ".join("{}={}".format(s["key"], s["value"]) for s in settings)
            parts.append("Настройки: " + s_str)

        # ── 6. Query-driven retrieval ─────────────────────────────────────
        if query:
            relevant = await retrieve_context(user_id, query, max_chars=1600)
            if relevant:
                parts.append("--- Релевантный контекст по запросу ---")
                parts.append(relevant)

    except Exception as e:
        logging.warning("get_user_context error (user=%s): %s", user_id, e)

    return "\n".join(parts)
