"""Tests for memory system: keywords, synonyms, date_parser, auto_memory.

Run:
    C:\Python310\python.exe test_memory_system.py
"""
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, ".")

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────
PASS = 0
FAIL = 0
WARN = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"  PASS  {name}")


def fail(name, detail=""):
    global FAIL
    FAIL += 1
    print(f"  FAIL  {name}" + (f"  ({detail})" if detail else ""))


def warn(name, detail=""):
    global WARN
    WARN += 1
    print(f"  WARN  {name}" + (f"  ({detail})" if detail else ""))


# ══════════════════════════════════════════════════════════════
# 1. extract_keywords
# ══════════════════════════════════════════════════════════════
print("\n=== 1. extract_keywords ===")
try:
    from bot.modules.memory_retriever import extract_keywords

    # basic
    kw = extract_keywords("Покажи расходы по рекламе в Facebook")
    assert "расходы" in kw or "реклама" in kw or "расход" in kw, f"got: {kw}"
    ok("extracts content words")

    # stopwords removed
    kw2 = extract_keywords("и в на с по для что как это не")
    assert len(kw2) == 0, f"expected empty, got: {kw2}"
    ok("removes all stopwords")

    # short
    kw3 = extract_keywords("да")
    assert len(kw3) == 0
    ok("single word → empty")

    # cap at 10
    long_text = " ".join(f"слово{i}" for i in range(30))
    kw4 = extract_keywords(long_text)
    assert len(kw4) <= 10, f"got {len(kw4)}"
    ok("capped at 10 keywords")

except Exception as e:
    fail("extract_keywords import/run", str(e))


# ══════════════════════════════════════════════════════════════
# 2. expand_with_synonyms
# ══════════════════════════════════════════════════════════════
print("\n=== 2. expand_with_synonyms ===")
try:
    from bot.modules.memory_retriever import expand_with_synonyms

    expanded = expand_with_synonyms(["реклама"])
    assert "facebook" in expanded or "fb" in expanded or "ads" in expanded, f"got: {expanded}"
    ok("реклама → includes facebook/ads")

    expanded2 = expand_with_synonyms(["facebook"])
    assert "реклама" in expanded2 or "маркетинг" in expanded2, f"got: {expanded2}"
    ok("facebook → back-maps to реклама/маркетинг")

    expanded3 = expand_with_synonyms(["финансы"])
    assert any(w in expanded3 for w in ["деньги", "бюджет", "расходы", "трата"]), f"got: {expanded3}"
    ok("финансы → includes деньги/бюджет")

    # cap at 30
    huge = expand_with_synonyms(["реклама", "финансы", "еда", "сон", "здоровье", "машина"])
    assert len(huge) <= 30, f"got {len(huge)}"
    ok("expansion capped at 30")

except Exception as e:
    fail("expand_with_synonyms", str(e))


# ══════════════════════════════════════════════════════════════
# 3. date_parser
# ══════════════════════════════════════════════════════════════
print("\n=== 3. date_parser ===")
try:
    from bot.utils.date_parser import parse_date_range
    from datetime import date, timedelta

    today = date.today()

    # сегодня
    d1, d2 = parse_date_range("сегодня")
    assert d1 == d2 == today.isoformat(), f"got {d1}, {d2}"
    ok("сегодня → today")

    # вчера
    d1, d2 = parse_date_range("вчера")
    assert d1 == d2 == (today - timedelta(days=1)).isoformat(), f"got {d1}, {d2}"
    ok("вчера → yesterday")

    # завтра
    d1, d2 = parse_date_range("завтра")
    assert d1 == d2 == (today + timedelta(days=1)).isoformat(), f"got {d1}, {d2}"
    ok("завтра → tomorrow")

    # последние 7 дней
    d1, d2 = parse_date_range("последние 7 дней")
    assert d2 == today.isoformat(), f"date_to should be today, got: {d2}"
    from datetime import datetime
    delta = (datetime.fromisoformat(d2) - datetime.fromisoformat(d1)).days
    assert delta == 7, f"expected 7 day gap, got {delta}"
    ok("последние 7 дней → correct range")

    # конкретный год
    d1, d2 = parse_date_range("за 2025")
    assert d1 == "2025-01-01" and d2 == "2025-12-31", f"got {d1}, {d2}"
    ok("за 2025 → full year range")

    # named month
    d1, d2 = parse_date_range("за март")
    assert d1.endswith("-03-01"), f"got: {d1}"
    assert d2.endswith("-03-31"), f"got: {d2}"
    ok("за март → march range")

    # неизвестный текст → None, None
    d1, d2 = parse_date_range("привет как дела")
    assert d1 is None and d2 is None, f"expected None, got {d1}, {d2}"
    ok("unrelated text → (None, None)")

    # empty string
    d1, d2 = parse_date_range("")
    assert d1 is None and d2 is None
    ok("empty string → (None, None)")

except Exception as e:
    fail("date_parser", str(e))


# ══════════════════════════════════════════════════════════════
# 4. auto_memory: _should_skip
# ══════════════════════════════════════════════════════════════
print("\n=== 4. auto_memory _should_skip ===")
try:
    from bot.modules.auto_memory import _should_skip

    assert _should_skip("да") is True
    ok("too short → skip")

    assert _should_skip("добавь задачу сделать отчёт") is True
    ok("command 'добавь' → skip")

    assert _should_skip("/start") is True
    ok("/command → skip")

    assert _should_skip("Я обычно встаю в 8 утра и сразу пью кофе") is False
    ok("personal habit → don't skip")

    assert _should_skip("запомни что я не люблю рано вставать") is False
    ok("'запомни' → don't skip")

except Exception as e:
    fail("auto_memory _should_skip", str(e))


# ══════════════════════════════════════════════════════════════
# 5. auto_memory: _try_extract
# ══════════════════════════════════════════════════════════════
print("\n=== 5. auto_memory _try_extract ===")
try:
    from bot.modules.auto_memory import _try_extract

    result = _try_extract("запомни что я предпочитаю краткие ответы")
    assert result is not None, "expected match"
    cat, key, val = result
    assert cat == "preference", f"expected preference, got {cat}"
    assert "кратк" in val, f"got val: {val}"
    ok("'запомни' → preference category")

    result2 = _try_extract("я не люблю длинные объяснения")
    assert result2 is not None
    cat2, _, val2 = result2
    assert cat2 == "dislike"
    ok("'я не люблю' → dislike category")

    result3 = _try_extract("я обычно работаю с 10 до 18")
    assert result3 is not None
    cat3, _, val3 = result3
    assert cat3 == "habit"
    ok("'я обычно' → habit category")

    result4 = _try_extract("встаю в 07:30")
    assert result4 is not None
    cat4, _, val4 = result4
    assert cat4 == "wake_time"
    assert "07:30" in val4 or "07" in val4, f"got: {val4}"
    ok("'встаю в HH:MM' → wake_time")

    result5 = _try_extract("привет как погода")
    assert result5 is None
    ok("no pattern → None")

except Exception as e:
    fail("auto_memory _try_extract", str(e))


# ══════════════════════════════════════════════════════════════
# 6. auto_extract_memory (async, with mocked DB)
# ══════════════════════════════════════════════════════════════
print("\n=== 6. auto_extract_memory async ===")
try:
    import bot.modules.auto_memory as am_module

    async def _test_saves():
        mock_db = MagicMock()
        mock_db.memory_recall = AsyncMock(return_value=[])
        mock_db.memory_save = AsyncMock(return_value=1)

        with patch.object(am_module, "db", mock_db):
            result = await am_module.auto_extract_memory(
                user_id=1,
                message_text="запомни что я не люблю спам в ответах",
            )
        return result, mock_db.memory_save.called

    saved, called = asyncio.run(_test_saves())
    assert saved is True, "expected True"
    assert called, "memory_save should have been called"
    ok("auto_extract_memory saves preference")

    async def _test_skip_command():
        mock_db = MagicMock()
        mock_db.memory_recall = AsyncMock(return_value=[])
        mock_db.memory_save = AsyncMock(return_value=1)

        with patch.object(am_module, "db", mock_db):
            result = await am_module.auto_extract_memory(
                user_id=1,
                message_text="добавь расход 50 злотых на еду",
            )
        return result, mock_db.memory_save.called

    saved2, called2 = asyncio.run(_test_skip_command())
    assert saved2 is False, "command should be skipped"
    assert not called2, "memory_save should NOT be called for commands"
    ok("auto_extract_memory skips commands")

    async def _test_dedup():
        existing = [{"category": "dislike", "value": "длинные объяснения без смысла"}]
        mock_db = MagicMock()
        mock_db.memory_recall = AsyncMock(return_value=existing)
        mock_db.memory_save = AsyncMock(return_value=1)

        with patch.object(am_module, "db", mock_db):
            result = await am_module.auto_extract_memory(
                user_id=1,
                message_text="я не люблю длинные объяснения",
            )
        return result, mock_db.memory_save.called

    saved3, called3 = asyncio.run(_test_dedup())
    assert saved3 is False, "duplicate should be skipped"
    assert not called3, "memory_save should NOT be called for duplicates"
    ok("auto_extract_memory deduplicates")

except Exception as e:
    fail("auto_extract_memory async", str(e))


# ══════════════════════════════════════════════════════════════
# 7. retrieve_context (async, empty DB)
# ══════════════════════════════════════════════════════════════
print("\n=== 7. retrieve_context ===")
try:
    import bot.modules.memory_retriever as mr_module

    async def _test_empty_db():
        mock_db = MagicMock()
        mock_db.memory_recall = AsyncMock(return_value=[])
        mock_db.dynamic_records_search = AsyncMock(return_value=[])
        mock_db.task_find_by_title = AsyncMock(return_value=[])
        mock_db.expenses_search = AsyncMock(return_value=[])
        mock_db.project_list = AsyncMock(return_value=[])
        mock_db.summaries_search = AsyncMock(return_value=[])
        mock_db.study_list = AsyncMock(return_value=[])
        mock_db.attachment_list = AsyncMock(return_value=[])
        mock_db.message_logs_recent = AsyncMock(return_value=[])

        with patch.object(mr_module, "db", mock_db):
            result = await mr_module.retrieve_context(user_id=1, query="реклама facebook")
        return result

    ctx = asyncio.run(_test_empty_db())
    assert ctx == "", f"empty DB should return '', got: {repr(ctx)}"
    ok("retrieve_context returns '' for empty DB")

    async def _test_with_data():
        memory_fact = {"id": 42, "category": "preference", "value": "люблю краткие ответы", "created_at": "2025-01-01", "key_name": None}
        mock_db = MagicMock()
        mock_db.memory_recall = AsyncMock(return_value=[memory_fact])
        mock_db.dynamic_records_search = AsyncMock(return_value=[])
        mock_db.task_find_by_title = AsyncMock(return_value=[])
        mock_db.expenses_search = AsyncMock(return_value=[])
        mock_db.project_list = AsyncMock(return_value=[])
        mock_db.summaries_search = AsyncMock(return_value=[])
        mock_db.study_list = AsyncMock(return_value=[])
        mock_db.attachment_list = AsyncMock(return_value=[])
        mock_db.message_logs_recent = AsyncMock(return_value=[])

        with patch.object(mr_module, "db", mock_db):
            result = await mr_module.retrieve_context(user_id=1, query="предпочтения пользователя")
        return result

    ctx2 = asyncio.run(_test_with_data())
    assert "краткие ответы" in ctx2 or len(ctx2) > 0, f"expected data in ctx, got: {repr(ctx2)}"
    ok("retrieve_context returns memory facts when present")

except Exception as e:
    fail("retrieve_context", str(e))


# ══════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════
total = PASS + FAIL + WARN
print(f"\n{'='*52}")
print(f"  Results: {PASS} PASS / {FAIL} FAIL / {WARN} WARN  (total {total})")
print(f"{'='*52}\n")

if FAIL > 0:
    sys.exit(1)
