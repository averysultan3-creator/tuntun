"""Tests for Step 3 — Memory, Rules & Learning Layer."""
import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Fake config (no network, no OpenAI) ───────────────────────────────────────

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


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Detection
# ═══════════════════════════════════════════════════════════════════════════════

def test_is_memory_message_positive():
    from bot.modules.memory_rules import is_memory_message

    assert is_memory_message("Запомни: если CTR ниже 1.5%, это слабый креатив")
    assert is_memory_message("Мне не нравятся длинные офферы, делай короче")
    assert is_memory_message("Когда я говорю плохие объявления, значит ads со статусом low_performance")
    assert is_memory_message("Для клиента X всегда сначала проверяй лиды, потом бюджет")
    assert is_memory_message("Исправь: CTR был 2.1%, не 1.2%")
    assert is_memory_message("Это не кампания, это связка креативов. Исправь.")


def test_is_memory_message_negative():
    from bot.modules.memory_rules import is_memory_message

    # Normal business messages should NOT trigger memory detection
    assert not is_memory_message("Сегодня создал 3 кампании для клиента X")
    assert not is_memory_message("CTR вышел 2.4%, завтра проверю лиды")
    assert not is_memory_message("Привет, расскажи о погоде")
    assert not is_memory_message("Что у меня сегодня по задачам?")


def test_classify_memory_types():
    from bot.modules.memory_rules import _classify_memory_type

    assert _classify_memory_type("Запомни: если CTR ниже 1.5%, это слабый креатив") == "rule"
    assert _classify_memory_type("Мне не нравятся длинные офферы") == "preference"
    assert _classify_memory_type("делай офферы короче и жестче") == "preference"
    assert _classify_memory_type("Когда я говорю плохие объявления, значит ads со статусом low_performance") == "definition"
    assert _classify_memory_type("Исправь: CTR был 2.1%, не 1.2%") == "correction"
    assert _classify_memory_type("Это не кампания, это клиент") == "correction"
    assert _classify_memory_type("Для клиента X всегда сначала проверяй лиды, потом бюджет") == "strategy"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Save rule (type=rule)
# ═══════════════════════════════════════════════════════════════════════════════

def test_save_rule_type_rule(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "rules.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        from bot.modules.memory_rules import save_memory_rule
        result = await save_memory_rule(
            user_id=1,
            text="Запомни: если CTR ниже 1.5% за два дня, помечай как слабый",
            sync_google=False,
        )

        assert result["memory_type"] == "rule"
        assert result["rule_id"] > 0
        assert result["scope_type"] == "global"
        assert result["scope_name"] is None

        # Verify in DB
        rows = await test_db.rule_list(user_id=1, memory_type="rule")
        assert len(rows) == 1
        assert rows[0]["memory_type"] == "rule"
        assert "CTR" in rows[0]["text"]

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Save preference
# ═══════════════════════════════════════════════════════════════════════════════

def test_save_preference(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "pref.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        from bot.modules.memory_rules import save_memory_rule
        result = await save_memory_rule(
            user_id=1,
            text="Мне не нравятся длинные офферы, делай короче и жестче",
            sync_google=False,
        )

        assert result["memory_type"] == "preference"
        assert result["scope_type"] == "global"

        rows = await test_db.rule_list(user_id=1, memory_type="preference")
        assert len(rows) == 1

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Save definition
# ═══════════════════════════════════════════════════════════════════════════════

def test_save_definition(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "defn.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        from bot.modules.memory_rules import save_memory_rule
        text = "Когда я говорю плохие объявления, значит ads со статусом low_performance"
        result = await save_memory_rule(user_id=1, text=text, sync_google=False)

        assert result["memory_type"] == "definition"
        assert "definition" in result
        defn = result["definition"]
        assert "плохие объявления" in defn["trigger"]
        assert "low_performance" in defn.get("meaning", "")

        # Check that parsed meaning extracted target_type=ad
        assert defn.get("target_type") == "ad", f"expected target_type=ad, got {defn}"
        assert "low_performance" in defn.get("target_status", "")

        # Verify DB
        rows = await test_db.rule_list(user_id=1, memory_type="definition")
        assert len(rows) == 1

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Scoped rule (client)
# ═══════════════════════════════════════════════════════════════════════════════

def test_save_scoped_rule_for_client(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "scoped.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        from bot.modules.memory_rules import save_memory_rule
        text = "Для клиента X всегда сначала проверяй лиды, потом бюджет"
        result = await save_memory_rule(user_id=1, text=text, sync_google=False)

        assert result["scope_type"] == "client"
        assert result["scope_name"] == "X"
        assert result["memory_type"] in ("strategy", "rule")

        rows = await test_db.rule_list(user_id=1, scope_type="client", scope_name="X")
        assert len(rows) == 1
        assert rows[0]["scope_name"] == "X"

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Retrieval
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_relevant_memory_returns_rules(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "retrieval.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        # Save some rules
        await test_db.rule_create(
            user_id=1,
            memory_type="rule",
            text="если CTR < 1.5%, пометить как слабый",
            normalized_key="ctr слабый",
        )
        await test_db.rule_create(
            user_id=1,
            memory_type="preference",
            text="делай офферы короче",
            normalized_key="офферы короткий",
        )
        await test_db.rule_create(
            user_id=1,
            memory_type="definition",
            text="плохие объявления = ads low_performance",
            normalized_key="плохие объявления",
            extra_json='{"trigger": "плохие объявления", "meaning": "ads low_performance", "target_type": "ad", "target_status": "low_performance"}',
        )

        from bot.modules.memory_rules import get_relevant_memory
        # Business message that mentions CTR and creative
        rules = await get_relevant_memory(
            text="CTR кампании 1.2%, креатив слабый",
            user_id=1,
            limit=10,
        )

        # Should return global rules (all 3 are global)
        assert len(rules) >= 2
        rule_types = {r["memory_type"] for r in rules}
        assert "rule" in rule_types

        # Scoped-only search: client Y should not return client X rules
        await test_db.rule_create(
            user_id=1,
            memory_type="strategy",
            text="для клиента X сначала лиды",
            normalized_key="лиды клиент",
            scope_type="client",
            scope_name="X",
        )

        rules_x = await get_relevant_memory(
            text="проверяем клиента",
            user_id=1,
            scope_candidates=["X"],
            limit=10,
        )
        scope_names = [r.get("scope_name") for r in rules_x]
        # Rules for client X should be included
        assert "X" in scope_names

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Definition applied in ingest
# ═══════════════════════════════════════════════════════════════════════════════

def test_definition_applies_in_ingest(monkeypatch, tmp_path):
    """Definition 'плохие объявления = ads low_performance' should enrich tasks."""
    import bot.db.database as db_mod
    import bot.modules.business_graph as graph

    async def run():
        test_db = _make_db(str(tmp_path / "def_ingest.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)
        monkeypatch.setattr(graph, "db", test_db)

        async def fake_index(**kwargs):
            return 99
        monkeypatch.setattr(graph, "index_memory_item", fake_index)

        # Pre-load definition rule
        await test_db.rule_create(
            user_id=1,
            memory_type="definition",
            text="когда говорю плохие объявления, значит ads со статусом low_performance",
            normalized_key="плохие объявления ads",
            extra_json='{"trigger": "плохие объявления", "meaning": "ads со статусом low_performance", "target_type": "ad", "target_status": "low_performance"}',
        )

        from bot.modules.memory_rules import get_relevant_memory
        rules = await get_relevant_memory("выключить плохие объявления", user_id=1, limit=10)

        result = await graph.ingest_business_text(
            text="завтра надо выключить плохие объявления",
            user_id=1,
            date_today="2026-05-02",
            date_tomorrow="2026-05-03",
            sync_google=False,
            rules=rules,
        )

        # Should have at least one task
        assert len(result["tasks"]) >= 1

        # The task should be enriched with target_type=ad from the definition
        task_with_target = next(
            (t for t in result["tasks"] if t.get("target_type") == "ad"),
            None,
        )
        assert task_with_target is not None, (
            f"No task with target_type=ad found. Tasks: {result['tasks']}"
        )
        assert task_with_target.get("target_status") == "low_performance"

        # applied_rules should mention the definition
        assert len(result.get("applied_rules", [])) >= 1

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Correction — metric update
# ═══════════════════════════════════════════════════════════════════════════════

def test_correction_metric_update(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "correction.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        # Create a CTR metric in DB (simulating previous ingestion)
        entity_id = await test_db.entity_upsert(
            user_id=1, type="creative", name="Kreativ A", canonical_key="kreativ-a",
        )
        metric_id = await test_db.metric_create(
            user_id=1, entity_type="creative", entity_id=entity_id,
            metric_name="CTR", metric_value=1.2, unit="%", date="2026-05-02",
        )

        from bot.modules.memory_rules import process_correction
        result = await process_correction(
            text="Исправь: CTR был 2.1%, не 1.2%",
            user_id=1,
        )

        # A correction rule should be saved
        assert result["rule_id"] > 0
        assert result["memory_type"] == "correction"

        correction = result.get("correction", {})
        assert correction.get("metric_name") == "CTR"
        assert abs(correction.get("new_value", 0) - 2.1) < 0.01

        # Verify DB metric was updated
        if correction.get("updated"):
            metrics = await test_db.metrics_for_entity(
                user_id=1, entity_type="creative", entity_id=entity_id, metric_name="CTR"
            )
            assert len(metrics) >= 1
            assert abs(metrics[0]["metric_value"] - 2.1) < 0.01
            # Old value preserved in data_json
            data = metrics[0].get("data") or {}
            assert "corrected_from" in data

        # DB correction rule
        rules = await test_db.rule_list(user_id=1, memory_type="correction")
        assert len(rules) >= 1

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Correction — type mismatch
# ═══════════════════════════════════════════════════════════════════════════════

def test_correction_type_mismatch(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "type_corr.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        from bot.modules.memory_rules import process_correction
        result = await process_correction(
            text="Нет, это не кампания, это клиент. Исправь.",
            user_id=1,
        )

        assert result["rule_id"] > 0
        assert result["memory_type"] == "correction"
        type_corr = result.get("type_correction") or {}
        assert type_corr.get("old_type") == "кампания"
        assert type_corr.get("new_type") == "клиент"

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Feedback builder
# ═══════════════════════════════════════════════════════════════════════════════

def test_build_memory_feedback():
    from bot.modules.memory_rules import build_memory_feedback

    # Rule
    fb = build_memory_feedback({
        "memory_type": "rule",
        "text": "если CTR < 1.5%, пометить слабый",
        "scope_type": "global",
        "scope_name": None,
    })
    assert "правило" in fb.lower()
    assert "CTR" in fb

    # Preference
    fb = build_memory_feedback({
        "memory_type": "preference",
        "text": "делай офферы короче и жестче",
        "scope_type": "global",
        "scope_name": None,
    })
    assert "предпочтение" in fb.lower()

    # Definition
    fb = build_memory_feedback({
        "memory_type": "definition",
        "text": "плохие объявления = ads low_performance",
        "scope_type": "global",
        "scope_name": None,
        "definition": {
            "trigger": "плохие объявления",
            "meaning": "ads со статусом low_performance",
        },
    })
    assert "определение" in fb.lower()
    assert "плохие объявления" in fb

    # Correction with update
    fb = build_memory_feedback({
        "memory_type": "correction",
        "text": "Исправь CTR",
        "scope_type": "global",
        "scope_name": None,
        "correction": {
            "metric_name": "CTR",
            "old_value": 1.2,
            "new_value": 2.1,
            "updated": True,
        },
    })
    assert "1.2" in fb and "2.1" in fb

    # Scoped rule
    fb = build_memory_feedback({
        "memory_type": "strategy",
        "text": "сначала лиды, потом бюджет",
        "scope_type": "client",
        "scope_name": "X",
    })
    assert "X" in fb


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Google sync for memory_rule
# ═══════════════════════════════════════════════════════════════════════════════

def test_sync_memory_rule_appends_to_memoryindex(monkeypatch):
    import bot.integrations.google.sync as sync_mod
    import bot.integrations.google.sheets as sheets_mod

    async def run():
        appended = []

        async def fake_spreadsheet(user_id):
            return "spreadsheet-1"

        async def fake_append(spreadsheet_id, sheet_name, row, **kwargs):
            appended.append((spreadsheet_id, sheet_name, row))
            return 5

        monkeypatch.setattr(sync_mod, "_get_spreadsheet", fake_spreadsheet)
        monkeypatch.setattr(sheets_mod, "append_row", fake_append)

        ok = await sync_mod.sync_memory_rule(
            user_id=1,
            rule_id=42,
            payload={
                "memory_type": "definition",
                "scope_type": "global",
                "scope_name": "",
                "text": "плохие объявления = ads low_performance",
                "normalized_key": "плохие объявления ads",
            },
        )

        assert ok is True
        assert len(appended) == 1
        sheet_name = appended[0][1]
        row = appended[0][2]
        assert sheet_name == "MemoryIndex"
        assert row[1] == "42"          # id
        assert row[2] == "memory_rule" # source_type
        assert row[4] == "definition"  # category = memory_type
        assert "плохие" in row[5]      # summary = text

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 12. rule_search by keyword and scope
# ═══════════════════════════════════════════════════════════════════════════════

def test_rule_search_keyword_and_scope(monkeypatch, tmp_path):
    import bot.db.database as db_mod

    async def run():
        test_db = _make_db(str(tmp_path / "search.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)

        # Global rule with CTR
        await test_db.rule_create(
            user_id=1, memory_type="rule",
            text="если CTR < 2%, пометить плохим",
            normalized_key="ctr плохой",
        )
        # Scoped rule for client X
        await test_db.rule_create(
            user_id=1, memory_type="strategy",
            text="для клиента X проверяй лиды",
            normalized_key="лиды клиент",
            scope_type="client", scope_name="X",
        )
        # Global definition
        await test_db.rule_create(
            user_id=1, memory_type="definition",
            text="плохие объявления = ads",
            normalized_key="плохие объявления",
        )

        # Search by keyword "ctr"
        rows = await test_db.rule_search(user_id=1, keywords=["ctr"], limit=10)
        texts = [r["text"] for r in rows]
        # Global rules always included; the CTR rule should match
        assert any("CTR" in t for t in texts), f"Expected CTR rule in {texts}"

        # Search by scope candidate X
        rows_x = await test_db.rule_search(user_id=1, scope_candidates=["X"], limit=10)
        scopes = [r["scope_name"] for r in rows_x]
        assert "X" in scopes

        # Deactivate a rule and verify it's excluded
        rule_ids = [r["id"] for r in rows_x if r.get("scope_name") == "X"]
        if rule_ids:
            await test_db.rule_deactivate(user_id=1, rule_id=rule_ids[0])
            rows_after = await test_db.rule_search(user_id=1, scope_candidates=["X"], limit=10)
            active_x = [r for r in rows_after if r.get("scope_name") == "X"]
            assert len(active_x) == 0

    asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Old business graph tests still pass (regression)
# ═══════════════════════════════════════════════════════════════════════════════

def test_old_ingest_still_works(monkeypatch, tmp_path):
    """Make sure ingest_business_text still works with rules=[] (no definitions)."""
    import bot.db.database as db_mod
    import bot.modules.business_graph as graph

    async def run():
        test_db = _make_db(str(tmp_path / "regression.db"))
        await test_db.init()
        monkeypatch.setattr(db_mod, "db", test_db)
        monkeypatch.setattr(graph, "db", test_db)

        async def fake_index(**kwargs):
            return 77
        monkeypatch.setattr(graph, "index_memory_item", fake_index)

        text = (
            "Сегодня создал 3 кампании для клиента X, два креатива не понравились, "
            "один дал CTR 2.4%, завтра надо проверить лиды и выключить плохие объявления."
        )

        result = await graph.ingest_business_text(
            text=text, user_id=1,
            date_today="2026-05-02",
            date_tomorrow="2026-05-03",
            sync_google=False,
            rules=[],  # no definitions — empty list, not None
        )

        entity_types = {e["type"] for e in result["entities"]}
        assert "client" in entity_types
        assert "campaign" in entity_types
        assert "creative" in entity_types
        assert len(result["metrics"]) == 1
        assert result["metrics"][0]["name"] == "CTR"
        assert len(result["tasks"]) == 2

    asyncio.run(run())
