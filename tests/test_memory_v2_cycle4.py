"""Tests for Memory V2 Cycle 4: Google ingestion into memory_items.

All Google API calls are mocked — no real credentials needed.

Run: python -B -m pytest test_memory_v2_cycle4.py -v
"""
import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── config stub ────────────────────────────────────────────────────────────────
def _make_fake_config():
    m = types.ModuleType("config")
    m.OPENAI_API_KEY = "sk-test"
    m.VISION_ENABLED = False
    m.GOOGLE_ENABLED = False
    m.ALLOWED_USER_IDS = []
    m.DB_PATH = ":memory:"
    m.MODEL_ROUTER = "gpt-4o-mini"
    m.MODEL_CHAT = "gpt-4o-mini"
    m.MODEL_REASONING = "gpt-4o"
    m.MODEL_VISION = "gpt-4o-mini"
    m.WHISPER_MODEL = "whisper-1"
    m.MODEL_EMBEDDINGS = "text-embedding-3-small"
    m.TIMEZONE = "Europe/Warsaw"
    m.MIN_CONFIDENCE = 0.65
    m.PHOTOS_DIR = "/tmp"
    return m


sys.modules["config"] = _make_fake_config()


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    fake = _make_fake_config()
    monkeypatch.setitem(sys.modules, "config", fake)
    yield fake


def _make_db(path: str):
    from bot.db.database import Database
    return Database(path)


# ══════════════════════════════════════════════════════════════════════════════
# 1. ingest_sheet_rows creates memory_items
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_sheet_rows_creates_items(monkeypatch, tmp_path):
    """ingest_sheet_rows must create memory_items for each row."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    rows = [
        {"date": "2025-01-10", "amount": "150", "currency": "USD",
         "description": "Реклама Facebook"},
        {"date": "2025-01-11", "amount": "200", "currency": "USD",
         "description": "Таргет Instagram"},
    ]

    async def run():
        await test_db.init()
        report = await ingestion_mod.ingest_sheet_rows(
            user_id=1,
            spreadsheet_id="sheet123",
            sheet_name="Finance",
            rows=rows,
        )
        assert report["indexed"] == 2
        assert report["errors"] == 0

        count = await test_db.memory_items_count(1)
        assert count >= 2

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 2. ingest_sheet_rows deduplication — same rows twice → no duplicates
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_sheet_rows_no_duplicates(monkeypatch, tmp_path):
    """Running ingest_sheet_rows twice on same rows must not create duplicates."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    rows = [
        {"date": "2025-01-10", "id": "42", "amount": "150", "currency": "USD",
         "description": "реклама ФБ"},
    ]

    async def run():
        await test_db.init()
        await ingestion_mod.ingest_sheet_rows(
            user_id=1, spreadsheet_id="s1", sheet_name="Finance", rows=rows
        )
        await ingestion_mod.ingest_sheet_rows(
            user_id=1, spreadsheet_id="s1", sheet_name="Finance", rows=rows
        )
        count = await test_db.memory_items_count(1)
        assert count == 1  # only one unique item

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 3. ingest_sheet_rows skips empty rows
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_sheet_rows_skips_empty(monkeypatch, tmp_path):
    """Empty rows must be skipped without errors."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    rows = [
        {},
        {"date": "", "amount": ""},
        {"date": "2025-01-01", "description": "реальная запись"},
    ]

    async def run():
        await test_db.init()
        report = await ingestion_mod.ingest_sheet_rows(
            user_id=1, spreadsheet_id="s2", sheet_name="Memory", rows=rows
        )
        assert report["skipped"] == 2
        assert report["indexed"] == 1
        assert report["errors"] == 0

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 4. ingest_doc_text creates memory_item (with injected text)
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_doc_text_creates_item(monkeypatch, tmp_path):
    """ingest_doc_text must index the provided text as google_doc source_type."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        rid = await ingestion_mod.ingest_doc_text(
            user_id=1,
            doc_id="doc_abc",
            doc_url="https://docs.google.com/document/d/doc_abc",
            title="Стратегия рекламы Q1 2025",
            text="Основные цели: снизить CPM до 2 USD, запустить 5 кампаний на ФБ.",
        )
        assert rid > 0

        # Verify it's in the DB with correct source_type
        rows = await test_db.memory_items_search(
            user_id=1, keywords=["реклам"], limit=10
        )
        assert any(r["source_type"] == "google_doc" for r in rows)

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 5. ingest_doc_text deduplication (same doc_id)
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_doc_text_no_duplicate(monkeypatch, tmp_path):
    """Ingesting the same doc twice must not create a duplicate."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        await ingestion_mod.ingest_doc_text(
            user_id=1, doc_id="doc_xyz",
            doc_url="https://docs.google.com/document/d/doc_xyz",
            title="Заметки",
            text="Хочу запустить кампанию на YouTube.",
        )
        await ingestion_mod.ingest_doc_text(
            user_id=1, doc_id="doc_xyz",
            doc_url="https://docs.google.com/document/d/doc_xyz",
            title="Заметки",
            text="Хочу запустить кампанию на YouTube.",
        )
        count = await test_db.memory_items_count(1)
        assert count == 1

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 6. ingest_doc_text with empty text returns 0
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_doc_text_empty_returns_zero(monkeypatch, tmp_path):
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        rid = await ingestion_mod.ingest_doc_text(
            user_id=1, doc_id="doc_empty",
            doc_url="", title="пустой", text="",
        )
        assert rid == 0

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 7. ingest_drive_file creates memory_item
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_drive_file_creates_item(monkeypatch, tmp_path):
    """ingest_drive_file must create a google_drive_file memory_item."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        rid = await ingestion_mod.ingest_drive_file(
            user_id=1,
            file_id="file_001",
            filename="отчёт_реклама_январь.xlsx",
            url="https://drive.google.com/file/d/file_001/view",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            description="Отчёт по расходам на рекламу за январь 2025",
            created_date="2025-01-15",
        )
        assert rid > 0

        rows = await test_db.memory_items_search(
            user_id=1, keywords=["реклам", "отчет"], limit=5
        )
        assert any(r["source_type"] == "google_drive_file" for r in rows)

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 8. ingest_drive_file deduplication
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_drive_file_no_duplicate(monkeypatch, tmp_path):
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def run():
        await test_db.init()
        await ingestion_mod.ingest_drive_file(
            user_id=1, file_id="file_dup",
            filename="план.docx",
            url="https://drive.google.com/file/d/file_dup/view",
        )
        await ingestion_mod.ingest_drive_file(
            user_id=1, file_id="file_dup",
            filename="план.docx",
            url="https://drive.google.com/file/d/file_dup/view",
        )
        count = await test_db.memory_items_count(1)
        assert count == 1

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 9. ingest_sheet_rows — read_sheet failure is graceful
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_sheet_rows_api_failure_graceful(monkeypatch, tmp_path):
    """If read_sheet raises (no credentials), ingest returns empty report, no crash."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    async def fake_read_sheet(spreadsheet_id, sheet_name, limit=100):
        raise ConnectionError("no credentials")

    # Patch sheets module used inside ingestion
    fake_sheets = types.ModuleType("bot.integrations.google.sheets")
    fake_sheets.read_sheet = fake_read_sheet
    monkeypatch.setitem(sys.modules, "bot.integrations.google.sheets", fake_sheets)

    async def run():
        await test_db.init()
        # rows=None forces real API path (which will raise)
        report = await ingestion_mod.ingest_sheet_rows(
            user_id=1,
            spreadsheet_id="broken",
            sheet_name="Finance",
            rows=None,  # triggers real API path
        )
        # Should return gracefully
        assert report["indexed"] == 0
        assert report["errors"] == 0  # connection error counts as pre-ingestion failure

    asyncio.run(run())


# ══════════════════════════════════════════════════════════════════════════════
# 10. ingest_all_sheets aggregates correctly
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_all_sheets_aggregates(monkeypatch, tmp_path):
    """ingest_all_sheets must return aggregated report across all sheets."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod
    import bot.integrations.google.ingestion as ingestion_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)

    # Patch read_sheet to return 1 row for each sheet
    async def fake_read_sheet(spreadsheet_id, sheet_name, limit=100):
        return [{"date": "2025-01-01", "description": f"запись из {sheet_name}"}]

    fake_sheets = types.ModuleType("bot.integrations.google.sheets")
    fake_sheets.read_sheet = fake_read_sheet
    monkeypatch.setitem(sys.modules, "bot.integrations.google.sheets", fake_sheets)

    async def run():
        await test_db.init()
        report = await ingestion_mod.ingest_all_sheets(
            user_id=1, spreadsheet_id="s_all"
        )
        # 1 row per sheet — indexed count should equal number of sheets processed
        from bot.integrations.google.ingestion import _IMPORTANT_SHEETS
        assert report["indexed"] == len(_IMPORTANT_SHEETS)
        assert report["errors"] == 0

    asyncio.run(run())
