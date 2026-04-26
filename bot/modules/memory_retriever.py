"""Smart memory retrieval for TUNTUN bot.

Architecture:
  MVP  - keyword + synonym + scoring based LIKE search across SQLite.
  V2   - swap retrieve_context() for embeddings + vector search
         (pgvector / ChromaDB) without changing the calling code.

Public API:
  extract_keywords(text)                      -> list[str]
  expand_with_synonyms(keywords)             -> list[str]
  retrieve_context(user_id, query, max_chars) -> str
"""
import re
import logging
from datetime import datetime, timedelta, date as _date

from bot.db.database import db

# ──────────────────────────────────────────────────────────────
# Stopwords (ru + en)
# ──────────────────────────────────────────────────────────────
_STOPWORDS = {
    "и", "в", "на", "с", "по", "для", "что", "как", "это", "не",
    "у", "из", "за", "от", "до", "при", "со", "во", "мне", "мой",
    "моя", "мои", "моё", "я", "мы", "он", "она", "они", "вы", "ты",
    "его", "её", "их", "там", "тут", "здесь", "был", "была", "были",
    "есть", "нет", "да", "всё", "все", "про", "под", "над", "или",
    "если", "но", "а", "то", "уже", "ещё", "можно", "нужно", "надо",
    "хочу", "хочется", "покажи", "скажи", "расскажи", "дай", "сделай",
    "добавь", "создай", "что", "когда", "где", "сколько", "почему",
    "который", "которая", "которые", "какой", "такой",
    "the", "and", "or", "of", "to", "in", "is", "it", "for",
    "мне", "нам", "наш", "наша", "нашей", "нашем",
}

# ──────────────────────────────────────────────────────────────
# Synonym dictionary
# ──────────────────────────────────────────────────────────────
SYNONYMS = {
    "реклама":     ["ads", "ad", "facebook", "fb", "meta", "маркетинг",
                    "кампании", "кампания", "крео", "креативы", "кабинеты",
                    "кабинет", "reklama", "advertising"],
    "финансы":     ["деньги", "расходы", "траты", "бюджет", "expense",
                    "expenses", "spend", "cost", "payment", "финанс", "finance"],
    "еда":         ["питание", "поесть", "завтрак", "обед", "ужин",
                    "meal", "food", "едим", "еду"],
    "сон":         ["спать", "режим", "подъём", "подъем", "wake", "sleep",
                    "встаю", "ложусь", "будильник"],
    "учёба":       ["учеба", "study", "универ", "предмет", "пары",
                    "задание", "коллоквиум", "экзамен", "лекция"],
    "задачи":      ["дела", "todo", "таски", "task", "tasks", "задача"],
    "напоминания": ["напомни", "reminder", "reminders", "будильник",
                    "напоминание", "напомнить"],
    "проекты":     ["проект", "project", "работа", "идея"],
    "машина":      ["авто", "car", "opel", "бензин", "дизель", "топливо",
                    "заправка", "авто", "автомобиль"],
    "здоровье":    ["самочувствие", "тренировка", "бег", "либидо",
                    "энергия", "спорт", "фитнес", "health"],
    "расходы":     ["трата", "траты", "потратил", "expense", "spend",
                    "деньги", "бюджет", "payment"],
}

# Build reverse map: synonym -> canonical
_SYNONYM_REVERSE: dict[str, str] = {}
for _canonical, _syns in SYNONYMS.items():
    for _s in _syns:
        _SYNONYM_REVERSE[_s] = _canonical


def _normalize_text(text: str) -> str:
    """Lowercase, remove punctuation, normalize ё→е, strip extra spaces."""
    text = text.lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_keywords(text: str) -> list:
    """Extract meaningful keywords, normalize text first."""
    text = _normalize_text(text)
    words = text.split()
    seen = set()
    result = []
    for w in words:
        if w not in _STOPWORDS and len(w) >= 3 and w not in seen:
            seen.add(w)
            result.append(w)
    return result[:10]


def expand_with_synonyms(keywords: list) -> list:
    """Expand keywords with synonyms (both directions).

    Returns deduplicated list (original + synonyms, cap 30).
    """
    expanded = list(keywords)
    seen = set(keywords)
    for kw in keywords:
        # forward: kw is canonical
        for syn in SYNONYMS.get(kw, []):
            if syn not in seen:
                seen.add(syn)
                expanded.append(syn)
        # reverse: kw is a synonym
        canonical = _SYNONYM_REVERSE.get(kw)
        if canonical and canonical not in seen:
            seen.add(canonical)
            expanded.append(canonical)
            for syn in SYNONYMS.get(canonical, []):
                if syn not in seen:
                    seen.add(syn)
                    expanded.append(syn)
    return expanded[:30]


def _score_item(text: str, keywords: list, expanded: list,
                created_at: str = None, extra_bonus: int = 0) -> int:
    """Compute relevance score for a retrieved item.

    Scoring:
      +3  exact keyword match
      +2  synonym/expanded match
      +1  item is from today
      +2  item is from this week
    """
    score = extra_bonus
    text_norm = _normalize_text(text)
    for kw in keywords:
        if kw in text_norm:
            score += 3
    for ex in expanded:
        if ex not in keywords and ex in text_norm:
            score += 2
    if created_at:
        try:
            ts = created_at[:10]
            days_ago = (datetime.now().date() - datetime.strptime(ts, "%Y-%m-%d").date()).days
            if days_ago == 0:
                score += 1
            elif days_ago <= 7:
                score += 2
        except Exception:
            pass
    return score


async def retrieve_context(user_id: int, query: str, max_chars: int = 2000) -> str:
    """Search all data sources for context relevant to the user's query.

    MVP: LIKE-based keyword + synonym search, with scoring.
    V2:  replace body with embedding similarity search.
    """
    keywords = extract_keywords(query)
    if not keywords:
        return ""
    expanded = expand_with_synonyms(keywords)

    # items: list of (score, label, text)
    items: list[tuple[int, str, str]] = []

    try:
        # ── 1. Memory facts ──────────────────────────────────────────────
        seen_ids: set[int] = set()
        for kw in expanded[:8]:
            rows = await db.memory_recall(user_id, query=kw)
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    text = "[{}] {}: {}".format(
                        r["category"],
                        r.get("key_name") or "",
                        str(r["value"])[:120],
                    )
                    s = _score_item(text, keywords, expanded, r.get("created_at"), extra_bonus=3)
                    items.append((s, "Память", text))

        # ── 2. Dynamic section records ───────────────────────────────────
        record_hits = await db.dynamic_records_search(user_id, expanded[:10], limit=10)
        for r in record_hits:
            text = "[{}] {}".format(r["section_name"], r["data_preview"])
            s = _score_item(text, keywords, expanded, r.get("created_at"), extra_bonus=5)
            items.append((s, "Раздел", text))

        # ── 3. Tasks matching keywords ────────────────────────────────────
        seen_task_ids: set[int] = set()
        for kw in expanded[:6]:
            rows = await db.task_find_by_title(user_id, kw)
            for r in rows:
                if r["id"] not in seen_task_ids:
                    seen_task_ids.add(r["id"])
                    text = '"{}" (срок: {}, приор: {})'.format(
                        r["title"],
                        r.get("due_date") or "б/д",
                        r.get("priority", "normal"),
                    )
                    s = _score_item(text, keywords, expanded, r.get("created_at"), extra_bonus=2)
                    items.append((s, "Задача", text))

        # ── 4. Expenses matching keywords ────────────────────────────────
        expense_hits = await db.expenses_search(user_id, expanded[:8], limit=8)
        for e in expense_hits:
            text = "{}: {} {} — {}".format(
                e.get("date", "?"),
                e["amount"],
                e["currency"],
                e.get("description") or e.get("project_name") or "",
            )
            s = _score_item(text, keywords, expanded, e.get("date"), extra_bonus=2)
            items.append((s, "Расход", text))

        # ── 5. Projects ──────────────────────────────────────────────────
        projects = await db.project_list(user_id)
        for p in projects:
            text = "{} ({})".format(p["name"], p.get("title") or p["name"])
            s = _score_item(text, keywords, expanded, p.get("created_at"), extra_bonus=0)
            if s > 0:
                items.append((s, "Проект", text))

        # ── 6. Summaries ─────────────────────────────────────────────────
        try:
            sum_hits = await db.summaries_search(user_id, expanded[:6], limit=4)
            for sm in sum_hits:
                text = "[{}] {}".format(sm["period_label"], str(sm["content"])[:200])
                s = _score_item(text, keywords, expanded, sm.get("created_at"), extra_bonus=3)
                items.append((s, "Сводка", text))
        except Exception:
            pass  # summaries table may not exist yet on older DBs

        # ── 7. Study records matching keywords ───────────────────────────
        for kw in keywords[:4]:
            rows = await db.study_list(user_id)
            for r in rows:
                content = str(r.get("content") or "")
                if kw in _normalize_text(content) or kw in _normalize_text(r.get("subject_name") or ""):
                    text = "[{}] {}: {}".format(
                        r.get("subject_name", ""), r.get("type", ""), content[:100]
                    )
                    s = _score_item(text, keywords, expanded, r.get("created_at"), extra_bonus=1)
                    items.append((s, "Учёба", text))

        # ── 8. Attachment captions ───────────────────────────────────────
        for kw in expanded[:6]:
            try:
                atts = await db.attachment_list(user_id)
                for a in atts:
                    cap = str(a.get("caption") or "") + " " + str(a.get("section_name") or "")
                    if kw in _normalize_text(cap):
                        text = "[файл: {}] {}".format(
                            a.get("file_type", "?"), cap[:100]
                        )
                        s = _score_item(text, keywords, expanded, a.get("created_at"), extra_bonus=1)
                        items.append((s, "Файл", text))
            except Exception:
                pass

        # ── 9. Recent conversation history ───────────────────────────────
        recent = await db.message_logs_recent(user_id, limit=6)
        for m in reversed(recent):
            user_text = str(m.get("original_text") or "")
            bot_text  = str(m.get("bot_response") or "")
            combined  = user_text + " " + bot_text
            s = _score_item(combined, keywords, expanded, m.get("created_at"), extra_bonus=0)
            ts = str(m.get("created_at") or "")[:16]
            text = "[{}] Вы: {} | Бот: {}".format(ts, user_text[:70], bot_text[:70])
            items.append((s, "История", text))

        # ── 10. Vision results (photos/docs analyzed by AI) ──────────────
        try:
            vision_hits = await db.vision_search(user_id, expanded[:6], limit=5)
            for v in vision_hits:
                photo_type = str(v.get("photo_type") or "unknown")
                summary = str(v.get("summary") or "")
                extracted = str(v.get("extracted_text") or "")[:100]
                text = f"[Фото-{photo_type}] {summary}: {extracted}"
                s = _score_item(text, keywords, expanded, v.get("created_at"), extra_bonus=2)
                items.append((s, "Фото", text))
        except Exception:
            pass

    except Exception as e:
        logging.warning("memory_retriever error (user=%s): %s", user_id, e)
        return ""

    if not items:
        return ""

    # Sort by score desc, deduplicate labels within same label group, cap at 15
    items.sort(key=lambda x: x[0], reverse=True)
    top = items[:15]

    # Group by label
    grouped: dict[str, list[str]] = {}
    for _score, label, text in top:
        grouped.setdefault(label, []).append(text)

    parts = []
    for label, texts in grouped.items():
        block = label + ":\n" + "\n".join("  " + t for t in texts)
        parts.append(block)

    result = "\n\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n... [контекст обрезан]"
    return result
