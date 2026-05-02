"""Conversation Episodic Memory — TUNTUN Jarvis layer.

Turns raw message_logs into structured, searchable conversation episodes.
Episodes are saved locally (SQLite), indexed in memory_items, optionally
written to a Google Doc and a ConversationEpisodes sheet.

Public API
──────────
maybe_summarize_conversation(user_id, force=False)  -> dict | None
get_episode_context(user_id, query, limit=3)        -> str
recall_episodes(user_id, query, limit=5)            -> list[dict]
"""
import json
import logging
import re
from datetime import datetime, date as _date
from typing import Optional

import config
from bot.ai.model_router import get_model
from bot.db.database import db

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None  # type: ignore

logger = logging.getLogger(__name__)

# ── Trigger settings ─────────────────────────────────────────────────────────
_MIN_MESSAGES_TO_SUMMARIZE = 6   # summarize when ≥ N unsummarized messages
_MIN_MESSAGES_FORCE = 3          # minimum for manual force
_MAX_MESSAGES_PER_EPISODE = 25   # hard cap per AI call

# ── AI extraction prompt ─────────────────────────────────────────────────────

_EXTRACTION_SYSTEM = """Ты — AI-ассистент, анализирующий диалог между пользователем и ботом.
Твоя задача: извлечь структурированную информацию из переписки.

Верни ТОЛЬКО валидный JSON в формате:
{
  "title": "Краткий заголовок разговора (до 80 символов)",
  "summary": "Резюме разговора (2-4 предложения, что обсуждали, что решили)",
  "key_points": ["факт 1", "факт 2", ...],
  "decisions": ["решение 1", "решение 2", ...],
  "people": [{"name": "Имя", "role": "роль/контекст", "notes": "что о нём узнали"}],
  "projects": ["название проекта 1", ...],
  "entities": ["TUNTUN", "Facebook Ads", ...],
  "tasks": ["задача 1", "задача 2", ...],
  "rules": ["правило/предпочтение 1", ...]
}

Правила:
- key_points: важные факты, которые стоит помнить
- decisions: конкретные договорённости, выводы, что пользователь решил делать
- people: упомянутые люди (не сам пользователь и не бот)
- projects: названия проектов, продуктов, бизнесов
- entities: важные сущности (компании, инструменты, платформы)
- tasks: задачи, которые нужно сделать (если упомянуты)
- rules: правила поведения, предпочтения пользователя, ограничения
- Если нет данных для поля — оставь пустой массив []
- Пиши на русском языке"""


async def _call_ai_extractor(messages_text: str, today: str) -> Optional[dict]:
    """Call GPT to extract structured episode data from conversation text."""
    try:
        if AsyncOpenAI is None:
            logger.warning("auto_summarizer: openai not installed, skipping extraction")
            return None

        client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        model = get_model("reasoning")

        prompt = (
            f"Дата: {today}\n\n"
            f"Диалог:\n{messages_text}\n\n"
            "Извлеки структурированную информацию согласно инструкции."
        )

        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_completion_tokens=1200,
        )
        raw = resp.choices[0].message.content.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("auto_summarizer: JSON parse error: %s", e)
        return None
    except Exception as e:
        logger.error("auto_summarizer: AI extractor error: %s", e)
        return None


def _build_messages_text(messages: list) -> str:
    """Format message_logs rows into a readable dialogue string."""
    lines = []
    for m in messages:
        ts = str(m.get("created_at", ""))[:16]
        user_text = m.get("original_text") or ""
        bot_text = m.get("bot_response") or ""
        if user_text:
            lines.append(f"[{ts}] Пользователь: {user_text[:300]}")
        if bot_text:
            lines.append(f"[{ts}] Бот: {bot_text[:200]}")
    return "\n".join(lines)


async def _upsert_person_entity(user_id: int, person: dict):
    """Store/update a person in the entities table (type='person')."""
    name = (person.get("name") or "").strip()
    if not name:
        return
    canonical_key = re.sub(r"\s+", "_", name.lower())
    extra = {
        "role": person.get("role", ""),
        "notes": person.get("notes", ""),
        "last_mentioned_at": _date.today().isoformat(),
    }
    try:
        await db._execute(
            """INSERT INTO entities (user_id, type, name, title, canonical_key, status, data_json)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(user_id, type, canonical_key) DO UPDATE SET
               data_json=excluded.data_json, updated_at=datetime('now')""",
            (user_id, "person", name, person.get("role", name), canonical_key,
             "active", json.dumps(extra, ensure_ascii=False)),
        )
    except Exception as e:
        logger.warning("auto_summarizer: upsert person entity failed: %s", e)


async def _index_episode_to_memory(user_id: int, episode: dict):
    """Index episode summary + key points in memory_items."""
    try:
        from bot.modules.memory_indexer import index_memory_item
        # Index the summary as a 'episode' memory item
        content = episode.get("summary", "") + " ".join(episode.get("key_points", []))
        if content.strip():
            await index_memory_item(
                user_id=user_id,
                content=content[:1000],
                summary=episode.get("summary", "")[:400],
                category="episode",
                source_type="episode",
                source_id=str(episode.get("id", "")),
                source_title=episode.get("title", ""),
                source_date=episode.get("date", ""),
                importance=4,
                tags=["episode"] + (episode.get("projects") or [])[:3],
            )
        # Index each decision separately
        for decision in (episode.get("decisions") or [])[:5]:
            await index_memory_item(
                user_id=user_id,
                content=decision[:500],
                summary=decision[:200],
                category="decision",
                source_type="episode",
                source_id=str(episode.get("id", "")),
                source_title=episode.get("title", ""),
                source_date=episode.get("date", ""),
                importance=5,
                tags=["decision", "episode"],
            )
    except Exception as e:
        logger.warning("auto_summarizer: memory index failed: %s", e)


async def _create_google_doc_for_episode(user_id: int, episode: dict) -> Optional[str]:
    """Create a Google Doc with the full episode content. Returns doc URL or None."""
    try:
        from bot.integrations.google.auth import is_google_enabled
        if not is_google_enabled():
            return None

        from bot.integrations.google.docs import create_doc

        date_str = episode.get("date", _date.today().isoformat())
        title = f"TUNTUN Memory — {date_str} — {episode.get('title', 'Разговор')[:50]}"

        # Build doc content
        lines = [
            f"# {title}",
            f"\n**Дата:** {date_str}",
            f"\n## Резюме\n{episode.get('summary', '')}",
        ]

        key_points = episode.get("key_points") or []
        if key_points:
            lines.append("\n## Ключевые факты")
            for pt in key_points:
                lines.append(f"- {pt}")

        decisions = episode.get("decisions") or []
        if decisions:
            lines.append("\n## Решения и договорённости")
            for d in decisions:
                lines.append(f"- {d}")

        people = episode.get("people") or []
        if people:
            lines.append("\n## Упомянутые люди")
            for p in people:
                if isinstance(p, dict):
                    lines.append(f"- **{p.get('name','')}** — {p.get('role','')}. {p.get('notes','')}")
                else:
                    lines.append(f"- {p}")

        projects = episode.get("projects") or []
        if projects:
            lines.append(f"\n## Проекты\n{', '.join(str(p) for p in projects)}")

        tasks = episode.get("tasks") or []
        if tasks:
            lines.append("\n## Задачи")
            for t in tasks:
                lines.append(f"- [ ] {t}")

        rules = episode.get("rules") or []
        if rules:
            lines.append("\n## Правила и предпочтения")
            for r in rules:
                lines.append(f"- {r}")

        content = "\n".join(lines)
        url = await create_doc(title=title, content=content, user_id=user_id)
        return url
    except Exception as e:
        logger.warning("auto_summarizer: google doc creation failed: %s", e)
        return None


async def _sync_episode_to_sheets(user_id: int, episode: dict):
    """Sync episode to ConversationEpisodes sheet."""
    try:
        from bot.integrations.google.sync import sync_object_to_google
        await sync_object_to_google(
            user_id=user_id,
            object_type="episode",
            object_id=episode.get("id", 0),
            payload=episode,
            target="sheets",
        )
    except Exception as e:
        logger.warning("auto_summarizer: sheets sync failed: %s", e)


async def maybe_summarize_conversation(user_id: int, force: bool = False) -> Optional[dict]:
    """Main entry point — check if summarization is needed, then summarize.

    Call fire-and-forget after each message. Returns episode dict if created,
    None if not enough content yet.
    """
    try:
        messages = await db.message_logs_unsummarized(user_id, limit=_MAX_MESSAGES_PER_EPISODE)
        n = len(messages)

        min_required = _MIN_MESSAGES_FORCE if force else _MIN_MESSAGES_TO_SUMMARIZE
        if n < min_required:
            return None

        today = _date.today().isoformat()
        messages_text = _build_messages_text(messages)
        if len(messages_text.strip()) < 100:
            return None

        extracted = await _call_ai_extractor(messages_text, today)
        if not extracted:
            return None

        # Validate required fields
        title = extracted.get("title") or "Разговор"
        summary = extracted.get("summary") or ""
        if not summary:
            return None

        source_ids = [m["id"] for m in messages]

        episode_id = await db.episode_create(
            user_id=user_id,
            date=today,
            title=title,
            summary=summary,
            key_points=extracted.get("key_points", []),
            decisions=extracted.get("decisions", []),
            people=extracted.get("people", []),
            projects=extracted.get("projects", []),
            entities=extracted.get("entities", []),
            tasks=extracted.get("tasks", []),
            rules=extracted.get("rules", []),
            source_message_ids=source_ids,
        )

        # Link messages to episode
        await db.message_logs_mark_episode(source_ids, episode_id)

        episode = await db.episode_get(episode_id)
        if not episode:
            return None

        # Upsert people into entities table
        for person in (extracted.get("people") or []):
            await _upsert_person_entity(user_id, person)

        # Index in memory_items (background, no throw)
        try:
            await _index_episode_to_memory(user_id, episode)
        except Exception as e:
            logger.warning("auto_summarizer: indexing failed: %s", e)

        # Google Doc (if enabled)
        try:
            doc_url = await _create_google_doc_for_episode(user_id, episode)
            if doc_url:
                await db.episode_update_doc_url(episode_id, doc_url)
                episode["google_doc_url"] = doc_url
        except Exception as e:
            logger.warning("auto_summarizer: google doc failed: %s", e)

        # Sync to Sheets
        try:
            await _sync_episode_to_sheets(user_id, episode)
        except Exception as e:
            logger.warning("auto_summarizer: sheets sync failed: %s", e)

        logger.info(
            "auto_summarizer: episode #%s created for user=%s, messages=%d, title=%r",
            episode_id, user_id, n, title,
        )
        return episode

    except Exception as e:
        logger.error("auto_summarizer: maybe_summarize_conversation error user=%s: %s", user_id, e)
        return None


async def get_episode_context(user_id: int, query: str, limit: int = 3) -> str:
    """Return a compact context string with relevant episodes for the chat system prompt."""
    try:
        from bot.modules.memory_retriever import extract_keywords, expand_with_synonyms

        keywords = extract_keywords(query) if query else []
        expanded = expand_with_synonyms(keywords) if keywords else []
        # Add capitalized variants for Cyrillic case-insensitive matching
        expanded_with_caps = expanded + [w.capitalize() for w in expanded if w.capitalize() != w]

        episodes: list[dict] = []
        if expanded_with_caps:
            episodes = await db.episode_search(user_id, expanded_with_caps[:10], limit=limit)
        if not episodes:
            # Fallback: just recent episodes
            episodes = await db.episode_get_recent(user_id, limit=limit)

        if not episodes:
            return ""

        parts = [f"**Эпизоды разговора:**"]
        for ep in episodes:
            date_str = ep.get("date", "")
            title = ep.get("title", "")
            summary = ep.get("summary", "")
            decisions = ep.get("decisions") or []
            people = ep.get("people") or []
            doc_url = ep.get("google_doc_url") or ""

            block = [f"[{date_str}] {title}", f"  {summary}"]
            if decisions:
                block.append(f"  Решения: {'; '.join(str(d) for d in decisions[:3])}")
            if people:
                names = [p.get("name", "") if isinstance(p, dict) else str(p) for p in people[:3]]
                block.append(f"  Люди: {', '.join(n for n in names if n)}")
            if doc_url:
                block.append(f"  Документ: {doc_url}")
            parts.append("\n".join(block))

        return "\n\n".join(parts)
    except Exception as e:
        logger.warning("auto_summarizer: get_episode_context error: %s", e)
        return ""


async def recall_episodes(user_id: int, query: str, limit: int = 5) -> list:
    """Search and return matching episodes for user commands like
    'о чём мы говорили по TUNTUN?' or 'найди где мы обсуждали Дарью'."""
    try:
        from bot.modules.memory_retriever import extract_keywords, expand_with_synonyms
        keywords = extract_keywords(query) if query else []
        expanded = expand_with_synonyms(keywords) if keywords else []
        # Add capitalized variants for Cyrillic case-insensitive matching
        expanded_with_caps = expanded + [w.capitalize() for w in expanded if w.capitalize() != w]
        if expanded_with_caps:
            return await db.episode_search(user_id, expanded_with_caps[:12], limit=limit)
        return await db.episode_get_recent(user_id, limit=limit)
    except Exception as e:
        logger.error("auto_summarizer: recall_episodes error: %s", e)
        return []
