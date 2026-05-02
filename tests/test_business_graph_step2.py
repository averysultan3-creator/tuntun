"""Tests for Step 2 Business Graph foundation."""
import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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
    m.GOOGLE_SERVICE_ACCOUNT_FILE = "credentials/google_service_account.json"
    m.GOOGLE_SPREADSHEET_ID = ""
    m.GOOGLE_DRIVE_ROOT_FOLDER_ID = ""
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


def test_database_business_graph_roundtrip(tmp_path):
    async def run():
        test_db = _make_db(str(tmp_path / "graph.db"))
        await test_db.init()

        campaign_id = await test_db.entity_upsert(
            user_id=1,
            type="campaign",
            name="Launch 26 Apr",
            canonical_key="launch-26-apr",
            data={"platform": "meta"},
        )
        same_id = await test_db.entity_upsert(
            user_id=1,
            type="campaign",
            name="Launch 26 Apr Updated",
            canonical_key="launch-26-apr",
            status="active",
        )
        creative_id = await test_db.entity_upsert(
            user_id=1,
            type="creative",
            name="Creative 01",
            canonical_key="creative-01",
        )

        relation_id = await test_db.relation_upsert(
            user_id=1,
            from_type="campaign",
            from_id=campaign_id,
            relation_type="has_creative",
            to_type="creative",
            to_id=creative_id,
        )
        event_id = await test_db.event_create(
            user_id=1,
            entity_type="campaign",
            entity_id=campaign_id,
            event_type="launch",
            date="2026-04-26",
            title="Запуск кампании",
        )
        metric_id = await test_db.metric_create(
            user_id=1,
            entity_type="campaign",
            entity_id=campaign_id,
            metric_name="budget",
            metric_value=20,
            unit="USD",
            date="2026-04-26",
        )

        assert campaign_id == same_id
        assert relation_id > 0
        assert event_id > 0
        assert metric_id > 0

        entities = await test_db.entity_find(1, type="campaign", query="Updated")
        assert len(entities) == 1
        assert entities[0]["id"] == campaign_id

        relations = await test_db.relations_for_entity(1, "campaign", campaign_id)
        assert relations[0]["relation_type"] == "has_creative"

        metrics = await test_db.metrics_for_entity(1, "campaign", campaign_id)
        assert metrics[0]["metric_name"] == "budget"

    asyncio.run(run())


def test_business_graph_helper_indexes(monkeypatch, tmp_path):
    import bot.db.database as db_mod
    import bot.modules.business_graph as graph

    async def run():
        test_db = _make_db(str(tmp_path / "graph_helper.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)
        monkeypatch.setattr(graph, "db", test_db)

        index_calls = []

        async def fake_index(**kwargs):
            index_calls.append(kwargs)
            return 77

        monkeypatch.setattr(graph, "index_memory_item", fake_index)

        entity_id = await graph.create_or_update_entity(
            user_id=1,
            type="campaign",
            name="Campaign A",
            canonical_key="campaign-a",
            data={"budget": 20},
            sync_google=False,
        )
        metric_id = await graph.record_metric(
            user_id=1,
            entity_type="campaign",
            entity_id=entity_id,
            metric_name="budget",
            metric_value=20,
            unit="USD",
            sync_google=False,
        )

        assert entity_id > 0
        assert metric_id > 0
        assert len(index_calls) == 2
        assert index_calls[0]["source_type"] == "entity"
        assert index_calls[1]["source_type"] == "metric"

    asyncio.run(run())


def test_google_sheet_headers_include_graph_tabs():
    from bot.integrations.google.sheets import _SHEET_HEADERS

    for name in ("Entities", "Relations", "Events", "Metrics", "Campaigns", "Creatives", "Orders", "Ads"):
        assert name in _SHEET_HEADERS
        assert "id" in _SHEET_HEADERS[name]


def test_google_sync_relation_appends_expected_row(monkeypatch):
    import bot.integrations.google.sync as sync_mod
    import bot.integrations.google.sheets as sheets_mod

    async def run():
        appended = []

        async def fake_spreadsheet(user_id):
            return "spreadsheet-1"

        async def fake_append(spreadsheet_id, sheet_name, row, **kwargs):
            appended.append((spreadsheet_id, sheet_name, row, kwargs))
            return 2

        monkeypatch.setattr(sync_mod, "_get_spreadsheet", fake_spreadsheet)
        monkeypatch.setattr(sheets_mod, "append_row", fake_append)

        ok = await sync_mod.sync_relation(
            user_id=1,
            relation_id=10,
            payload={
                "from_type": "campaign",
                "from_id": 1,
                "relation_type": "has_creative",
                "to_type": "creative",
                "to_id": 2,
                "confidence": 0.95,
            },
        )

        assert ok is True
        assert appended[0][1] == "Relations"
        assert appended[0][2][2:7] == ["campaign", 1, "has_creative", "creative", 2]

    asyncio.run(run())


def test_google_sync_order_matches_sheet_schema(monkeypatch):
    import bot.integrations.google.sync as sync_mod
    import bot.integrations.google.sheets as sheets_mod
    from bot.integrations.google.sheets import _SHEET_HEADERS

    async def run():
        appended = []

        async def fake_spreadsheet(user_id):
            return "spreadsheet-1"

        async def fake_append(spreadsheet_id, sheet_name, row, **kwargs):
            appended.append((spreadsheet_id, sheet_name, row, kwargs))
            return 4

        monkeypatch.setattr(sync_mod, "_get_spreadsheet", fake_spreadsheet)
        monkeypatch.setattr(sheets_mod, "append_row", fake_append)

        ok = await sync_mod.sync_order(
            user_id=1,
            order_id=44,
            payload={
                "date": "2026-05-02",
                "project_id": "project-1",
                "campaign_id": "campaign-9",
                "amount": 120,
                "currency": "EUR",
                "status": "paid",
                "customer": "Client X",
                "notes": "first order",
            },
        )

        assert ok is True
        assert appended[0][1] == "Orders"
        row = appended[0][2]
        assert len(row) == len(_SHEET_HEADERS["Orders"])
        assert row[2:8] == ["project-1", "campaign-9", "120", "EUR", "paid", "Client X"]

    asyncio.run(run())


def test_google_sync_ads_handler(monkeypatch):
    import bot.integrations.google.sync as sync_mod
    import bot.integrations.google.sheets as sheets_mod
    from bot.integrations.google.sheets import _SHEET_HEADERS

    async def run():
        appended = []

        async def fake_spreadsheet(user_id):
            return "spreadsheet-1"

        async def fake_append(spreadsheet_id, sheet_name, row, **kwargs):
            appended.append((spreadsheet_id, sheet_name, row, kwargs))
            return 5

        monkeypatch.setattr(sync_mod, "_get_spreadsheet", fake_spreadsheet)
        monkeypatch.setattr(sheets_mod, "append_row", fake_append)

        assert "ads" in sync_mod._SYNC_HANDLERS
        ok = await sync_mod.sync_object_to_google(
            user_id=1,
            object_type="ads",
            object_id=7,
            payload={
                "date": "2026-05-02",
                "platform": "Meta",
                "account": "Main",
                "project_id": "project-1",
                "status": "paused",
                "notes": "bad CTR",
            },
        )

        assert ok is False  # Google disabled in test config, so dispatcher queues/returns False
        ok_direct = await sync_mod.sync_ads(
            user_id=1,
            ad_id=7,
            payload={
                "date": "2026-05-02",
                "platform": "Meta",
                "account": "Main",
                "project_id": "project-1",
                "status": "paused",
                "notes": "bad CTR",
            },
        )
        assert ok_direct is True
        assert appended[0][1] == "Ads"
        assert len(appended[0][2]) == len(_SHEET_HEADERS["Ads"])
        assert appended[0][2][2:6] == ["Meta", "Main", "project-1", "paused"]

    asyncio.run(run())


def test_google_sync_dynamic_record_imports_append_row(monkeypatch):
    import bot.integrations.google.sync as sync_mod
    import bot.integrations.google.sheets as sheets_mod

    async def run():
        appended = []

        async def fake_spreadsheet(user_id):
            return "spreadsheet-1"

        async def fake_append(spreadsheet_id, sheet_name, row, **kwargs):
            appended.append((spreadsheet_id, sheet_name, row, kwargs))
            return 6

        monkeypatch.setattr(sync_mod, "_get_spreadsheet", fake_spreadsheet)
        monkeypatch.setattr(sheets_mod, "append_row", fake_append)

        ok = await sync_mod.sync_dynamic_record(
            user_id=1,
            record_id=11,
            payload={"section_name": "Custom", "data": {"x": 1}, "summary": "custom row"},
        )

        assert ok is True
        assert appended[0][1] == "DynamicRecords"

    asyncio.run(run())


def test_google_sync_queues_when_google_enabled_but_auth_missing(monkeypatch, _patch_config):
    import bot.integrations.google.sync as sync_mod

    async def run():
        queued = []

        async def fake_enqueue(user_id, object_type, object_id, target, action, payload):
            queued.append((user_id, object_type, object_id, target, action, payload))

        _patch_config.GOOGLE_ENABLED = True
        monkeypatch.setattr(sync_mod, "is_google_enabled", lambda: False)
        monkeypatch.setattr(sync_mod, "_enqueue", fake_enqueue)

        ok = await sync_mod.sync_object_to_google(
            user_id=1,
            object_type="campaign",
            object_id=9,
            payload={"name": "Launch"},
        )

        assert ok is False
        assert queued == [(1, "campaign", 9, "sheets", "create", {"name": "Launch"})]

    asyncio.run(run())


def test_google_ingestion_includes_graph_sheets():
    from bot.integrations.google.ingestion import _IMPORTANT_SHEETS

    for sheet_name in (
        "Entities",
        "Relations",
        "Events",
        "Metrics",
        "Campaigns",
        "Creatives",
        "Orders",
        "Ads",
        "MemoryIndex",
    ):
        assert sheet_name in _IMPORTANT_SHEETS


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 ingestion tests
# ══════════════════════════════════════════════════════════════════════════════

def test_is_business_message():
    from bot.modules.business_graph import is_business_message

    assert is_business_message("Создал 3 кампании для клиента X") is True
    assert is_business_message("CTR 2.4% показал хороший результат") is True
    assert is_business_message("не понравился креатив") is True
    assert is_business_message("Привет, как дела?") is False
    assert is_business_message("Напомни купить молоко") is False


def test_extraction_helpers():
    """Unit-test the deterministic extraction helpers."""
    from bot.modules.business_graph import (
        _extract_client_name,
        _extract_campaign_count,
        _extract_creative_count,
        _extract_metrics,
        _extract_tasks,
    )

    text = (
        "Сегодня создал 3 кампании для клиента X, два креатива не понравились, "
        "один дал CTR 2.4%, завтра надо проверить лиды и выключить плохие объявления."
    )

    assert _extract_client_name(text) == "X"
    assert _extract_campaign_count(text) == 3
    assert _extract_creative_count(text) == 2

    metrics = _extract_metrics(text)
    assert len(metrics) == 1
    assert metrics[0]["name"] == "CTR"
    assert abs(metrics[0]["value"] - 2.4) < 0.01
    assert metrics[0]["unit"] == "%"

    tasks = _extract_tasks(text, "2026-05-02", "2026-05-03")
    assert len(tasks) == 2
    titles = [t["title"] for t in tasks]
    assert any("лиды" in t.lower() or "проверить" in t.lower() for t in titles), titles
    assert any("выключить" in t.lower() or "объявления" in t.lower() for t in titles), titles
    for t in tasks:
        assert t["due_date"] == "2026-05-03"


def test_ingest_business_text_full_pipeline(monkeypatch, tmp_path):
    """Full pipeline: one Russian phrase → multiple graph objects."""
    import bot.db.database as db_mod
    import bot.modules.business_graph as graph

    async def run():
        test_db = _make_db(str(tmp_path / "ingest.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)
        monkeypatch.setattr(graph, "db", test_db)

        # Stub memory indexer (avoid importing real one)
        index_calls = []
        async def fake_index(**kwargs):
            index_calls.append(kwargs)
            return 77
        monkeypatch.setattr(graph, "index_memory_item", fake_index)

        text = (
            "Сегодня создал 3 кампании для клиента X, два креатива не понравились, "
            "один дал CTR 2.4%, завтра надо проверить лиды и выключить плохие объявления."
        )

        result = await graph.ingest_business_text(
            text=text,
            user_id=1,
            date_today="2026-05-02",
            date_tomorrow="2026-05-03",
            sync_google=False,
        )

        # ── Entities ──────────────────────────────────────────────────────────
        entity_types = {e["type"] for e in result["entities"]}
        assert "client" in entity_types, result["entities"]
        assert "campaign" in entity_types, result["entities"]
        assert "creative" in entity_types, result["entities"]

        # Client name recognized
        client_entity = next(e for e in result["entities"] if e["type"] == "client")
        assert client_entity["name"] == "X"

        # ── Relations ─────────────────────────────────────────────────────────
        rel_types = [r["relation_type"] for r in result["relations"]]
        assert "has_campaign" in rel_types, rel_types
        assert "has_creative" in rel_types, rel_types

        # ── Metrics ───────────────────────────────────────────────────────────
        assert len(result["metrics"]) == 1
        assert result["metrics"][0]["name"] == "CTR"
        assert abs(result["metrics"][0]["value"] - 2.4) < 0.01

        # ── Tasks ─────────────────────────────────────────────────────────────
        assert len(result["tasks"]) == 2
        task_titles = [t["title"].lower() for t in result["tasks"]]
        assert any("лиды" in t or "проверить" in t for t in task_titles), task_titles
        assert any("выключить" in t or "объявления" in t for t in task_titles), task_titles
        for t in result["tasks"]:
            assert t["due_date"] == "2026-05-03"

        # ── Events ────────────────────────────────────────────────────────────
        event_types = {e["event_type"] for e in result["events"]}
        assert "feedback" in event_types, result["events"]
        assert "task" in event_types, result["events"]

        # ── DB check: entities persisted ──────────────────────────────────────
        campaigns = await test_db.entity_find(1, type="campaign")
        assert len(campaigns) >= 1

        clients = await test_db.entity_find(1, type="client")
        assert len(clients) >= 1
        assert clients[0]["name"] == "X"

        creatives = await test_db.entity_find(1, type="creative")
        assert len(creatives) >= 1

        # ── DB check: metric persisted ────────────────────────────────────────
        pos_creative = next(
            (c for c in creatives if c.get("data", {}).get("sentiment") == "positive"
             or "CTR" in c["name"]),
            None,
        )
        if pos_creative:
            metrics_rows = await test_db.metrics_for_entity(1, "creative", pos_creative["id"])
            assert any(m["metric_name"] == "CTR" for m in metrics_rows)

        # ── Summary non-empty ─────────────────────────────────────────────────
        assert result["summary"]

    asyncio.run(run())


def test_ingest_business_text_no_client(monkeypatch, tmp_path):
    """Without a client name, clarification is requested but other data is saved."""
    import bot.db.database as db_mod
    import bot.modules.business_graph as graph

    async def run():
        test_db = _make_db(str(tmp_path / "no_client.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)
        monkeypatch.setattr(graph, "db", test_db)

        async def fake_index(**kwargs):
            return 77
        monkeypatch.setattr(graph, "index_memory_item", fake_index)

        text = "Запустил 2 кампании, CTR вышел 1.8%, завтра нужно проверить статистику."

        result = await graph.ingest_business_text(
            text=text,
            user_id=1,
            date_today="2026-05-02",
            date_tomorrow="2026-05-03",
            sync_google=False,
        )

        # Campaign created even without client
        entity_types = {e["type"] for e in result["entities"]}
        assert "campaign" in entity_types

        # Clarification about missing client
        assert any("клиент" in c.lower() for c in result["clarifications"])

        # CTR metric extracted
        assert any(m["name"] == "CTR" for m in result["metrics"])

        # Task created
        assert len(result["tasks"]) >= 1

    asyncio.run(run())


def test_ingest_no_business_signals():
    """Text with no business signals returns empty result."""
    from bot.modules.business_graph import ingest_business_text

    async def run():
        result = await ingest_business_text(
            text="Привет, расскажи мне про Python",
            user_id=1,
            sync_google=False,
        )
        assert result["entities"] == []
        assert result["metrics"] == []
        assert result["tasks"] == []
        assert result["clarifications"]  # should have at least one

    asyncio.run(run())


def test_sync_creative_appends_correct_row(monkeypatch):
    """sync_creative writes a row to the Creatives sheet."""
    import bot.integrations.google.sync as sync_mod
    import bot.integrations.google.sheets as sheets_mod

    async def run():
        appended = []

        async def fake_spreadsheet(user_id):
            return "spreadsheet-1"

        async def fake_append(spreadsheet_id, sheet_name, row, **kwargs):
            appended.append((spreadsheet_id, sheet_name, row))
            return 3

        monkeypatch.setattr(sync_mod, "_get_spreadsheet", fake_spreadsheet)
        monkeypatch.setattr(sheets_mod, "append_row", fake_append)

        ok = await sync_mod.sync_creative(
            user_id=1,
            creative_id=5,
            payload={
                "campaign_id": 2,
                "name": "Kreativ A",
                "format": "image",
                "status": "active",
                "notes": "CTR=2.4%",
            },
        )

        assert ok is True
        assert len(appended) == 1
        assert appended[0][1] == "Creatives"
        row = appended[0][2]
        assert row[1] == "5"        # id
        assert row[2] == "2"        # campaign_id
        assert row[3] == "Kreativ A"  # name
        assert row[5] == "active"   # status (index 5 = status in our row)

    asyncio.run(run())
