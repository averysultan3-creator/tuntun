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

    for name in ("Entities", "Relations", "Events", "Metrics", "Campaigns", "Creatives", "Orders"):
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
