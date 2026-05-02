"""Auto-memory extraction for TUNTUN bot.

After each user message, auto_extract_memory() checks whether the message
contains a long-term personal fact worth saving to the memory table.

Rules:
  - Save: preferences, habits, personal settings, rules, facts about
    the user's life, projects, routines.
  - Skip: one-off questions, commands that result in a task/reminder/expense
    (those are already stored), very short messages (<4 words).
  - Dedup: if a very similar memory already exists (same category + similar
    value), update it instead of inserting a duplicate.

Extraction:
  - Pattern-based (fast, no AI call) — covers common phrases.
  - AI-based fallback via auto_extract_memory_ai() — called when the router
    flagged memory_update_needed=True but regex found nothing.
"""
import re
import logging
from bot.db.database import db

# Patterns that strongly suggest a personal preference / habit / rule
_SAVE_PATTERNS = [
    # explicit save requests
    (r"запомни[,\s]+(.+)", "preference"),
    (r"важно\s+помни[,\s]+(.+)", "preference"),
    (r"всегда\s+((?:напоминай|говори|отвечай).+)", "preference"),
    # personal habits
    (r"я\s+обычно\s+(.+)", "habit"),
    (r"мой\s+режим\s+(.+)", "habit"),
    (r"по\s+утрам\s+(.+)", "habit"),
    (r"по\s+вечерам\s+(.+)", "habit"),
    # preferences
    (r"я\s+не\s+люблю\s+(.+)", "dislike"),
    (r"мне\s+не\s+нравится\s+(.+)", "dislike"),
    (r"я\s+люблю\s+(.+)", "like"),
    (r"мне\s+нравится\s+(.+)", "like"),
    (r"предпочитаю\s+(.+)", "preference"),
    (r"мне\s+лучше\s+(.+)", "preference"),
    # rules for the bot
    (r"отвечай\s+((?:короче|подробнее|кратко|развернуто).+)", "bot_style"),
    (r"(?:не|без)\s+воды[,\s].+", "bot_style"),
    # personal facts — extended
    (r"мой\s+проект\s+([\w\s]+)", "project"),
    (r"я\s+живу\s+в\s+(.+)", "location"),
    (r"я\s+из\s+(.+)", "location"),
    (r"мой\s+часовой\s+пояс\s+(.+)", "timezone"),
    (r"встаю\s+в\s+([\d:]+)", "wake_time"),
    (r"ложусь\s+в\s+([\d:]+)", "sleep_time"),
    # work / occupation
    (r"я\s+работаю\s+(?:в|на|как)\s+(.+)", "work"),
    (r"моя\s+профессия\s+(.+)", "work"),
    (r"я\s+(?:программист|дизайнер|менеджер|маркетолог|фрилансер|студент|врач|учитель)\b.*", "work"),
    # relationships / personal info
    (r"меня\s+зовут\s+(.+)", "name"),
    (r"мое\s+имя\s+(.+)", "name"),
    (r"моё\s+имя\s+(.+)", "name"),
    (r"у\s+меня\s+есть\s+([\w\s]+)", "personal_info"),
    (r"мой\s+партнер\s+(.+)", "relationship"),
    (r"моя\s+девушка\s+(.+)", "relationship"),
    (r"мой\s+парень\s+(.+)", "relationship"),
    (r"моя\s+жена\s+(.+)", "relationship"),
    (r"мой\s+муж\s+(.+)", "relationship"),
    # goals / focus
    (r"моя\s+цель\s+(.+)", "goal"),
    (r"хочу\s+достичь\s+(.+)", "goal"),
    (r"я\s+занимаюсь\s+(.+)", "activity"),
    # languages
    (r"я\s+знаю\s+([\w\s]+)\s+(?:язык|языки)", "language"),
    (r"говорю\s+на\s+([\w\s]+)", "language"),
]

# Patterns that mean "this is a command/action, not a fact to save"
_SKIP_PATTERNS = [
    r"^(создай|добавь|запиши|удали|покажи|открой|выгрузи|сделай backup)",
    r"^(напомни|remind|задача|расход|потратил)",
    r"^(/\w+)",  # bot commands
]


def _should_skip(text: str) -> bool:
    """Return True if message looks like a command, not a personal fact."""
    t = text.strip().lower()
    if len(t.split()) < 3:
        return True
    for pat in _SKIP_PATTERNS:
        if re.search(pat, t):
            return True
    return False


def _try_extract(text: str) -> tuple | None:
    """Try to extract (category, key_name, value) from text.

    Returns None if no pattern matches.
    """
    t = text.strip().lower().replace("ё", "е")
    for pattern, category in _SAVE_PATTERNS:
        m = re.search(pattern, t)
        if m:
            value = m.group(1).strip().rstrip(".!?,") if m.lastindex else t
            if len(value) < 3 or len(value) > 300:
                continue
            key_name = pattern.split(r"\s+")[0].strip(r"^(")[:20]
            return category, key_name, value
    return None


async def auto_extract_memory(user_id: int, message_text: str, log_id: int = None) -> bool:
    """Attempt to extract and save a personal fact from the user's message.

    Returns True if a new memory was saved or updated.
    """
    if _should_skip(message_text):
        return False

    extracted = _try_extract(message_text)
    if not extracted:
        return False

    category, key_name, value = extracted

    try:
        # Check if a similar memory already exists (same category, value overlap)
        existing = await db.memory_recall(user_id, category=category)
        for mem in existing:
            existing_val = str(mem.get("value") or "").lower()
            new_val = value.lower()
            # Simple similarity: if 60%+ words overlap, treat as duplicate
            ev_words = set(existing_val.split())
            nv_words = set(new_val.split())
            # Dedup: if new value is substantially covered by existing value
            if nv_words and len(ev_words & nv_words) / max(len(nv_words), 1) >= 0.6:
                logging.debug(
                    "auto_memory: skipping duplicate (user=%s, cat=%s)", user_id, category
                )
                return False

        await db.memory_save(
            user_id=user_id,
            category=category,
            value=value,
            key_name=key_name or None,
        )
        logging.info("auto_memory: saved [%s] '%s' for user %s", category, value[:60], user_id)
        return True

    except Exception as e:
        logging.warning("auto_memory error (user=%s): %s", user_id, e)
        return False


_AI_EXTRACT_PROMPT = """Твоя задача — определить, содержит ли сообщение пользователя долгосрочный личный факт, который стоит запомнить.

Долгосрочные факты: имя, место проживания, работа, профессия, предпочтения, привычки, отношения, цели, хобби, стиль жизни.
НЕ сохранять: вопросы, команды боту, разовые действия, расходы, задачи.

Если факт найден, верни JSON:
{"found": true, "category": "habit|preference|dislike|like|work|location|goal|relationship|activity|personal_info|name", "key_name": "краткое_имя_ключа_без_пробелов", "value": "точная формулировка факта на русском"}

Если факта нет:
{"found": false}

Верни ТОЛЬКО JSON, без пояснений."""


async def auto_extract_memory_ai(user_id: int, message_text: str) -> bool:
    """AI-based memory extraction — called when router flagged memory_update_needed=True
    but regex extraction found nothing.

    Uses gpt-4o-mini (cheap, fast) to detect personal facts.
    Returns True if a fact was saved.
    """
    if _should_skip(message_text):
        return False

    # Skip if regex already found something (avoid double work)
    if _try_extract(message_text):
        return False

    try:
        import config as _cfg
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=_cfg.OPENAI_API_KEY)

        resp = await _client.chat.completions.create(
            model=_cfg.MODEL_ROUTER,  # cheapest model
            messages=[
                {"role": "system", "content": _AI_EXTRACT_PROMPT},
                {"role": "user", "content": message_text[:500]},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_completion_tokens=150,
        )
        import json
        raw = json.loads(resp.choices[0].message.content)

        if not raw.get("found"):
            return False

        category = str(raw.get("category", "general"))
        key_name = str(raw.get("key_name", ""))[:30] or None
        value = str(raw.get("value", "")).strip()

        if not value or len(value) < 3:
            return False

        # Dedup check
        existing = await db.memory_recall(user_id, category=category)
        for mem in existing:
            existing_val = str(mem.get("value") or "").lower()
            new_val = value.lower()
            ev_words = set(existing_val.split())
            nv_words = set(new_val.split())
            if nv_words and len(ev_words & nv_words) / max(len(nv_words), 1) >= 0.6:
                logging.debug("auto_memory_ai: duplicate skipped (user=%s)", user_id)
                return False

        await db.memory_save(
            user_id=user_id,
            category=category,
            value=value,
            key_name=key_name,
        )
        logging.info(
            "auto_memory_ai: saved [%s] '%s' for user %s", category, value[:60], user_id
        )
        return True

    except Exception as e:
        logging.warning("auto_memory_ai error (user=%s): %s", user_id, e)
        return False
