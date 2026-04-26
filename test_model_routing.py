"""Tests for optimized model routing in TUNTUN.

9 tests covering:
1.  simple_expense_backend_only          вЂ” expense_add в†’ should_use_backend_only True
2.  simple_reminder_no_reasoning         вЂ” reminder_create в†’ CHAT not REASONING
3.  capabilities_uses_chat_not_reasoning вЂ” pure chat question в†’ CHAT
4.  day_plan_uses_reasoning              вЂ” regime_day_plan в†’ REASONING
5.  ambiguous_delete_uses_reasoning      вЂ” task_delete + refers_to_previous в†’ REASONING
6.  exact_delete_by_id_no_reasoning      вЂ” task_delete + high conf + no ambiguity в†’ CHAT
7.  photo_uses_vision                    вЂ” get_model("vision") returns VISION model
8.  low_confidence_escalates_reasoning   вЂ” confidence=0.6 в†’ REASONING
9.  backend_export_no_model              вЂ” export_excel в†’ should_use_backend_only True

Run with:
    cd d:\\AackREF\\TUNTUN
    python test_model_routing.py
"""
import os
import sys
import importlib
import unittest

sys.path.insert(0, os.path.dirname(__file__))


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Helpers
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

def _reload_with_env(**overrides):
    """Set env vars, reload config + model_router, return (module, restore_fn)."""
    original = {}
    for key, val in overrides.items():
        original[key] = os.environ.get(key)
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val

    import config as _cfg
    importlib.reload(_cfg)
    import bot.ai.model_router as _mr
    importlib.reload(_mr)

    def restore():
        for key, val in original.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        importlib.reload(_cfg)
        importlib.reload(_mr)

    return _mr, restore


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Tests
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

class TestModelRouting(unittest.TestCase):

    # в”Ђв”Ђ 1 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_simple_expense_backend_only(self):
        """expense_add with high confidence в†’ should_use_backend_only True."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            result = mr.should_use_backend_only(["expense_add"], confidence=0.95)
            self.assertTrue(result, "expense_add РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ backend_only")

            # choose_model should still return chat (backend_only is for dispatcher,
            # choose_model is about what model to use when a model IS needed)
            model = mr.choose_model("chat", confidence=0.95, intents=["expense_add"])
            self.assertEqual(model, "chat-x")
            self.assertNotEqual(model, "reasoning-x")
        finally:
            restore()

    # в”Ђв”Ђ 2 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_simple_reminder_no_reasoning(self):
        """reminder_create в†’ should_use_backend_only True, choose_model returns CHAT."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            self.assertTrue(
                mr.should_use_backend_only(["reminder_create"], confidence=0.95)
            )
            model = mr.choose_model(
                "chat",
                confidence=0.95,
                safety_level="safe",
                intents=["reminder_create"],
                needs_reasoning=False,
            )
            self.assertEqual(model, "chat-x")
            self.assertNotEqual(model, "reasoning-x",
                                "РџСЂРѕСЃС‚РѕРµ РЅР°РїРѕРјРёРЅР°РЅРёРµ РќР• РґРѕР»Р¶РЅРѕ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ REASONING")
        finally:
            restore()

    # в”Ђв”Ђ 3 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_capabilities_uses_chat_not_reasoning(self):
        """Pure chat question (no actions, no intents) в†’ CHAT, not REASONING."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            # "Р§С‚Рѕ С‚С‹ СѓРјРµРµС€СЊ?" в†’ no intents, high confidence, safe
            model = mr.choose_model(
                "chat",
                confidence=0.98,
                safety_level="safe",
                intents=[],
                needs_reasoning=False,
            )
            self.assertEqual(model, "chat-x",
                             "'Р§С‚Рѕ С‚С‹ СѓРјРµРµС€СЊ' РґРѕР»Р¶РµРЅ РёРґС‚Рё РІ CHAT, РЅРµ REASONING")

            # Also verify should_use_reasoning returns False
            self.assertFalse(
                mr.should_use_reasoning(intents=[], confidence=0.98)
            )
        finally:
            restore()

    # в”Ђв”Ђ 4 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_day_plan_uses_reasoning(self):
        """regime_day_plan and schedule_plan_day always use REASONING."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            for intent in ("regime_day_plan", "schedule_plan_day"):
                with self.subTest(intent=intent):
                    model = mr.choose_model(
                        "chat",
                        confidence=0.95,
                        safety_level="safe",
                        intents=[intent],
                    )
                    self.assertEqual(model, "reasoning-x",
                                     f"{intent} РґРѕР»Р¶РµРЅ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ REASONING")
        finally:
            restore()

    # в”Ђв”Ђ 5 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_ambiguous_delete_uses_reasoning(self):
        """task_delete + refers_to_previous=True в†’ REASONING (ambiguous 'СЌС‚Рѕ')."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            model = mr.choose_model(
                "chat",
                confidence=0.85,
                safety_level="safe",
                refers_to_previous=True,   # "СѓР±РµСЂРё СЌС‚Рѕ" вЂ” ambiguous reference
                intents=["task_delete"],
            )
            self.assertEqual(model, "reasoning-x",
                             "РќРµРѕРґРЅРѕР·РЅР°С‡РЅРѕРµ СѓРґР°Р»РµРЅРёРµ РґРѕР»Р¶РЅРѕ РёРґС‚Рё РІ REASONING")
        finally:
            restore()

    # в”Ђв”Ђ 6 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_exact_delete_by_id_no_reasoning(self):
        """task_delete + high confidence + no ambiguity в†’ CHAT (exact ID case)."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            model = mr.choose_model(
                "chat",
                confidence=0.96,           # router is confident
                safety_level="safe",
                refers_to_previous=False,  # explicit ID given, no ambiguity
                intents=["task_delete"],
            )
            self.assertEqual(model, "chat-x",
                             "РЈРґР°Р»РµРЅРёРµ РїРѕ С‚РѕС‡РЅРѕРјСѓ ID РЅРµ РґРѕР»Р¶РЅРѕ РёСЃРїРѕР»СЊР·РѕРІР°С‚СЊ REASONING")
        finally:
            restore()

    # в”Ђв”Ђ 7 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_photo_uses_vision(self):
        """get_model('vision') returns the configured VISION model."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_VISION="vision-x",
        )
        try:
            result = mr.get_model("vision")
            self.assertEqual(result, "vision-x")
        finally:
            restore()

    # в”Ђв”Ђ 8 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_low_confidence_escalates_reasoning(self):
        """confidence=0.6 в†’ ambiguous в†’ should escalate to REASONING."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            model = mr.choose_model(
                "chat",
                confidence=0.6,   # below 0.75 threshold
                safety_level="safe",
                intents=["task_create"],
            )
            self.assertEqual(model, "reasoning-x",
                             "РќРёР·РєР°СЏ СѓРІРµСЂРµРЅРЅРѕСЃС‚СЊ РґРѕР»Р¶РЅР° СЌСЃРєР°Р»РёСЂРѕРІР°С‚СЊ РІ REASONING")
        finally:
            restore()

    # в”Ђв”Ђ 9 в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
    def test_backend_export_no_model(self):
        """export_excel and backup_create в†’ should_use_backend_only True."""
        mr, restore = _reload_with_env(
            OPENAI_MODEL_ROUTER="router-x",
            OPENAI_MODEL_CHAT="chat-x",
            OPENAI_MODEL_REASONING="reasoning-x",
        )
        try:
            for intent in ("export_excel", "backup_create"):
                with self.subTest(intent=intent):
                    result = mr.should_use_backend_only([intent], confidence=0.95)
                    self.assertTrue(result,
                                    f"{intent} РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ backend_only (Р±РµР· РІС‹Р·РѕРІР° РјРѕРґРµР»Рё)")
        finally:
            restore()


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Verbose runner
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

_NAMES = {
    "test_simple_expense_backend_only":       "expense_add в†’ backend_only (РЅРµС‚ РІС‹Р·РѕРІР° РјРѕРґРµР»Рё)",
    "test_simple_reminder_no_reasoning":      "reminder_create в†’ CHAT, РЅРµ REASONING",
    "test_capabilities_uses_chat_not_reasoning": "'С‡С‚Рѕ СѓРјРµРµС€СЊ' в†’ CHAT, РЅРµ REASONING",
    "test_day_plan_uses_reasoning":           "РїР»Р°РЅ РґРЅСЏ в†’ REASONING",
    "test_ambiguous_delete_uses_reasoning":   "РЅРµРѕРґРЅРѕР·РЅР°С‡РЅРѕРµ СѓРґР°Р»РµРЅРёРµ в†’ REASONING",
    "test_exact_delete_by_id_no_reasoning":   "СѓРґР°Р»РµРЅРёРµ РїРѕ ID в†’ CHAT (РЅРµ REASONING)",
    "test_photo_uses_vision":                 "С„РѕС‚Рѕ в†’ VISION РјРѕРґРµР»СЊ",
    "test_low_confidence_escalates_reasoning": "conf=0.6 в†’ СЌСЃРєР°Р»Р°С†РёСЏ РІ REASONING",
    "test_backend_export_no_model":           "export/backup в†’ backend_only",
}


def run_tests_verbose():
    print("\n" + "в•ђ" * 62)
    print("  TUNTUN вЂ” Optimized Model Routing Tests")
    print("в•ђ" * 62)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestModelRouting)
    total = suite.countTestCases()
    passed = 0
    failed_names = []

    for test in suite:
        name = test._testMethodName
        label = _NAMES.get(name, name.replace("test_", "").replace("_", " "))
        try:
            result = unittest.TestResult()
            test.run(result)
            if result.wasSuccessful():
                passed += 1
                print(f"  вњ…  {label}")
            else:
                failed_names.append(name)
                err = result.errors or result.failures
                msg = err[0][1].strip().split("\n")[-1] if err else "unknown"
                print(f"  вќЊ  {label}")
                print(f"       в†’ {msg}")
        except Exception as e:
            failed_names.append(name)
            print(f"  вќЊ  {label}  в†’ {e}")

    print("в”Ђ" * 62)
    print(f"  РРўРћР“: {passed}/{total} С‚РµСЃС‚РѕРІ РїСЂРѕС€Р»Рё")
    if failed_names:
        print(f"  РџСЂРѕРІР°Р»РµРЅРѕ: {', '.join(failed_names)}")
    print("в•ђ" * 62 + "\n")
    return passed == total


if __name__ == "__main__":
    ok = run_tests_verbose()
    sys.exit(0 if ok else 1)
