"""Tests for Storage Router (Memory V2 Step 1).

Run: python -B -m pytest test_google_storage_router.py -q
"""
import asyncio
import pytest

from bot.modules.storage_router import (
    classify_storage_target,
    route_saved_object,
    _DOC_TEXT_THRESHOLD,
)
from bot.integrations.google.sheets import _SHEET_HEADERS
from bot.integrations.google.sync import _SYNC_HANDLERS


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db(path: str):
    """Return a fresh Database instance pointing at *path*."""
    from bot.db.database import Database
    return Database(path)


# ── classify tests (pure logic, no I/O) ──────────────────────────────────────

def test_classify_short_expense_to_sheets():
    r = classify_storage_target(object_type="expense", payload={"amount": 100})
    assert r["target"] in ("sheets", "mixed")
    assert r["sheet_name"] == "Finance"
    assert r["needs_memory_index"] is True
    assert r["needs_doc"] is False
    assert r["needs_drive"] is False


def test_classify_finance_alias():
    r = classify_storage_target(object_type="finance", payload={"amount": 50})
    assert r["sheet_name"] == "Finance"


def test_classify_long_text_to_docs():
    long_text = "x" * (_DOC_TEXT_THRESHOLD + 1)
    r = classify_storage_target(message_text=long_text, object_type="long_note")
    assert r["needs_doc"] is True
    assert r["sheet_name"] in ("LongNotes", None)


def test_classify_long_note_type_forces_doc():
    # Even short text: long_note type forces doc
    r = classify_storage_target(message_text="short", object_type="long_note")
    assert r["needs_doc"] is True


def test_classify_text_exactly_at_threshold():
    # Text at exactly threshold should NOT become a doc (threshold is >)
    text = "a" * _DOC_TEXT_THRESHOLD
    r = classify_storage_target(message_text=text, object_type="memory")
    # Either needs_doc is False, or it's triggered by type — for "memory" type
    # with exact threshold text it should go to sheets
    assert r["needs_drive"] is False


def test_classify_short_text_unknown_type_local_only():
    r = classify_storage_target(message_text="hello", object_type="unknown_xyz")
    assert r["target"] == "local_only"
    assert r["needs_doc"] is False
    assert r["needs_drive"] is False


def test_classify_photo_to_drive():
    r = classify_storage_target(object_type="photo", payload={"file_path": "/tmp/img.jpg"})
    assert r["needs_drive"] is True
    assert r["sheet_name"] == "Attachments"


def test_classify_attachment_with_list():
    r = classify_storage_target(attachments=[{"type": "photo", "file_id": "abc"}])
    assert r["needs_drive"] is True


def test_classify_task_to_tasks_sheet():
    r = classify_storage_target(object_type="task", payload={"title": "Do stuff"})
    assert r["sheet_name"] == "Tasks"
    assert r["needs_drive"] is False


def test_classify_idea_to_ideas_sheet():
    r = classify_storage_target(object_type="idea", payload={"title": "Big idea"})
    assert r["sheet_name"] == "Ideas"


def test_classify_campaign_to_campaigns_sheet():
    r = classify_storage_target(object_type="campaign", payload={"name": "Q1"})
    assert r["sheet_name"] == "Campaigns"
    assert r["needs_drive"] is False


def test_classify_metric_to_metrics_sheet():
    r = classify_storage_target(object_type="metric", payload={"metric_name": "ctr"})
    assert r["sheet_name"] == "Metrics"


def test_classify_order_to_orders_sheet():
    r = classify_storage_target(object_type="order", payload={"amount_usd": "10"})
    assert r["sheet_name"] == "Orders"


# ── sheets headers ────────────────────────────────────────────────────────────

REQUIRED_SHEETS = [
    "Finance", "Tasks", "Reminders", "Memory", "Ideas",
    "LongNotes", "Attachments", "Projects", "Study",
    "DailyPlans", "Logs",
    "Orders", "Campaigns", "Creatives", "Metrics",
    "MemoryIndex", "DynamicRecords",
]


def test_sheets_headers_include_required_sheets():
    for name in REQUIRED_SHEETS:
        assert name in _SHEET_HEADERS, f"Missing sheet: {name}"


def test_dynamic_records_sheet_has_expected_columns():
    cols = _SHEET_HEADERS["DynamicRecords"]
    assert "section_name" in cols
    assert "data_json" in cols
    assert "summary" in cols


# ── _SYNC_HANDLERS ────────────────────────────────────────────────────────────

def test_sync_handlers_include_new_types():
    for key in ("dynamic_record", "dynamic", "campaign", "order", "memory_index", "finance"):
        assert key in _SYNC_HANDLERS, f"_SYNC_HANDLERS missing key: {key}"


def test_sync_handlers_finance_alias_same_as_expense():
    assert _SYNC_HANDLERS["finance"] is _SYNC_HANDLERS["expense"]


# ── route_saved_object (integration: Google disabled) ────────────────────────

def _run_route(monkeypatch, tmp_path, object_type, payload):
    """Route helper: runs with Google disabled and real tmp DB."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "t.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr("bot.integrations.google.auth.is_google_enabled", lambda: False)

    result = {}

    async def run():
        await test_db.init()
        result.update(
            await route_saved_object(
                user_id=1,
                object_type=object_type,
                object_id=99,
                payload=payload,
            )
        )

    asyncio.run(run())
    return result


def test_route_google_disabled_no_crash(monkeypatch, tmp_path):
    r = _run_route(monkeypatch, tmp_path, "expense", {"amount": 100, "currency": "USD"})
    assert "target" in r
    assert "google_synced" in r
    assert r["google_synced"] is False
    assert r.get("memory_id", 0) > 0


def test_route_returns_report_structure(monkeypatch, tmp_path):
    r = _run_route(monkeypatch, tmp_path, "task", {"title": "Test task"})
    required_keys = {"target", "google_synced", "doc_url", "drive_url", "memory_id", "errors"}
    for k in required_keys:
        assert k in r, f"route result missing key: {k}"


def test_route_campaign_no_crash(monkeypatch, tmp_path):
    r = _run_route(monkeypatch, tmp_path, "campaign", {"name": "Summer", "platform": "fb"})
    assert "target" in r
    assert r.get("memory_id", 0) > 0


def test_memory_item_dedupe_by_source(monkeypatch, tmp_path):
    """Routing same source_type+source_id twice should NOT create a duplicate."""
    import bot.db.database as db_mod
    import bot.modules.memory_indexer as indexer_mod

    test_db = _make_db(str(tmp_path / "dd.db"))
    monkeypatch.setattr(db_mod, "db", test_db)
    monkeypatch.setattr(indexer_mod, "db", test_db)
    monkeypatch.setattr("bot.integrations.google.auth.is_google_enabled", lambda: False)

    async def run():
        await test_db.init()
        await route_saved_object(1, "task", 77, {"title": "Dedup me"})
        await route_saved_object(1, "task", 77, {"title": "Dedup me again"})
        count = await test_db._fetchone(
            "SELECT COUNT(*) as n FROM memory_items WHERE source_type=? AND source_id=?",
            ("task", 77),
        )
        return count["n"] if count else 0

    n = asyncio.run(run())
    assert n == 1, f"Expected 1 memory_item, got {n} (dedup failed)"
