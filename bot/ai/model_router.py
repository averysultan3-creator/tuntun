"""bot/ai/model_router.py — Optimized model routing for TUNTUN.

Routing priority (cheapest first):
  1. ROUTER     (gpt-5.4-mini)  — always first: intent classification
  2. BACKEND ONLY               — no model call: template response from handler
  3. CHAT       (gpt-5.4-mini)  — conversation, advice, formatting, simple queries
  4. REASONING  (gpt-5.4)       — plan day, complex analytics, ambiguous, dangerous

Public API:
    get_model(purpose)                     → model name string
    should_use_backend_only(intents, ...)  → bool  (skip all model calls)
    should_use_reasoning(intents, ...)     → bool
    choose_model(purpose, *, ...)          → model name string
    log_model_choice(purpose, model, ...)  → None  (debug log, no secrets)

Fallback chains:
    REASONING → CHAT → ROUTER
    VISION    → CHAT → ROUTER
    CHAT      → ROUTER
"""
import logging

import config

# ──────────────────────────────────────────────────────────────
# Model registry  (loaded once at import)
# ──────────────────────────────────────────────────────────────

_MODELS: dict[str, str] = {
    "router":     config.MODEL_ROUTER,
    "chat":       config.MODEL_CHAT,
    "reasoning":  config.MODEL_REASONING,
    "vision":     config.MODEL_VISION,
    "transcribe": config.WHISPER_MODEL,
    "embeddings": config.MODEL_EMBEDDINGS,
}

_FALLBACK_CHAIN: dict[str, list[str]] = {
    "reasoning":  ["reasoning", "chat", "router"],
    "vision":     ["vision", "chat", "router"],
    "chat":       ["chat", "router"],
    "router":     ["router"],
    "transcribe": ["transcribe"],
    "embeddings": ["embeddings"],
}


def get_model(purpose: str) -> str:
    """Return the configured model for *purpose*, following the fallback chain.

    Never returns an empty string — falls back to MODEL_ROUTER at minimum.
    """
    chain = _FALLBACK_CHAIN.get(purpose, ["router"])
    for p in chain:
        m = _MODELS.get(p, "")
        if m:
            return m
    return config.MODEL_ROUTER or "gpt-4o-mini"


# ──────────────────────────────────────────────────────────────
# Intent classification sets
# ──────────────────────────────────────────────────────────────

# These intents produce a complete template response from the handler.
# No model call is needed — backend handles it fully.
BACKEND_ONLY_INTENTS: frozenset = frozenset({
    # Finance
    "expense_add",          # "Записал расход: еда — 40 PLN."
    "expense_stats",        # formatted sum/table from DB
    # Tasks
    "task_create",          # "✅ Задача создана: ..."
    "task_complete",        # "✅ Задача выполнена: ..."
    "task_list",            # list output from DB
    "task_update",          # "✅ Задача обновлена" (explicit params)
    "task_delete",          # "✅ Задача удалена" (only when exact ID found)
    # Reminders
    "reminder_create",      # "⏰ Напоминание поставлено на ..."
    "reminder_list",        # list output from DB
    "reminder_cancel",      # "✅ Напоминание отменено" (exact ID case)
    # Export / Backup
    "export_excel",         # "✅ Экспорт готов → файл"
    "export_txt",           # "✅ Экспорт готов → файл"
    "backup_create",        # "✅ Backup создан"
    # Sections & records
    "section_record_add",   # "✅ Запись добавлена в [раздел]"
    # Study
    "study_add_record",     # "✅ Запись по учёбе добавлена"
    "study_add_subject",    # "✅ Предмет добавлен"
    "study_list",           # list output from DB
    # Memory & settings
    "memory_save",          # "✅ Запомнил: ..."
    "setting_save",         # "✅ Настройка сохранена"
    # Projects & ideas
    "project_create",       # "✅ Проект создан: ..."
    "project_list",         # list output from DB
    "idea_save",            # "💡 Идея сохранена: ..."
    "idea_list",            # list output from DB
    # Schedule & regime
    "schedule_view",        # list output from DB
    "regime_sleep_calc",    # calculation result (deterministic)
    # Google integration
    "google_show_link",     # just returns spreadsheet URL from DB
    "google_sync_status",   # shows sync queue size from DB
})

# These intents always need the REASONING model.
REASONING_INTENTS: frozenset = frozenset({
    "regime_day_plan",       # complex daily planning
    "schedule_plan_day",     # complex schedule planning
    "analytics_query",       # multi-source analytics
    "section_add_field",     # schema change
    "section_rename",        # schema change
    "record_edit",           # edit existing record — needs context
    "idea_convert_to_task",  # conversion with context lookup
})

# These intents are destructive — need reasoning only when ambiguous.
DESTRUCTIVE_INTENTS: frozenset = frozenset({
    "task_delete",
    "section_delete",
    "memory_clear",
})


# ──────────────────────────────────────────────────────────────
# Decision functions
# ──────────────────────────────────────────────────────────────

def should_use_backend_only(
    intents: list[str],
    confidence: float = 1.0,
) -> bool:
    """Return True if backend handlers can fully respond without any model call.

    Conditions:
    - All intents are in BACKEND_ONLY_INTENTS
    - Confidence is high enough (>= 0.85) — not ambiguous

    Note: This OVERRIDES chat_response_needed from the router for known simple
    intents. If the router incorrectly marks a simple action as chat_response_needed,
    backend_only still prevents an unnecessary model call.
    """
    if not intents:
        return False
    if confidence < 0.85:
        return False
    return all(i in BACKEND_ONLY_INTENTS for i in intents)


def should_use_reasoning(
    intents: list[str] | None = None,
    confidence: float = 1.0,
    safety_level: str = "safe",
    refers_to_previous: bool = False,
    complexity: str = "simple",
    needs_reasoning: bool = False,
) -> bool:
    """Return True if the REASONING model must be used.

    Args:
        intents:          Intent names from the router.
        confidence:       Router confidence (0.0–1.0).
        safety_level:     safe | confirm | dangerous
        refers_to_previous: Message references something from prior context.
        complexity:       simple | complex  (derived by caller from action count etc.)
        needs_reasoning:  Explicit flag from the router JSON.
    """
    intents = intents or []

    # Explicit router signal
    if needs_reasoning:
        return True

    # Dangerous / confirmation required
    if safety_level in ("confirm", "dangerous"):
        return True

    # Intents that always need deep reasoning
    if any(i in REASONING_INTENTS for i in intents):
        return True

    # Destructive intents — only reasoning when ambiguous
    if any(i in DESTRUCTIVE_INTENTS for i in intents):
        if refers_to_previous or confidence < 0.85:
            return True

    # Low confidence — message is ambiguous
    if confidence < 0.75:
        return True

    # Caller says this is a complex operation
    if complexity == "complex":
        return True

    return False


def choose_model(
    purpose: str = "chat",
    *,
    confidence: float = 0.9,
    safety_level: str = "safe",
    refers_to_previous: bool = False,
    complexity: str = "simple",
    intents: list[str] | None = None,
    needs_reasoning: bool = False,
) -> str:
    """Choose the right model for generating the response (after routing).

    ROUTER step always uses get_model("router") — this function decides
    what model to use for the *final response*.

    Args:
        purpose:          Hint: chat | reasoning | vision | transcribe
        confidence:       Router confidence (0.0–1.0)
        safety_level:     safe | confirm | dangerous
        refers_to_previous: Message references prior context
        complexity:       simple | complex
        intents:          Intent names from router
        needs_reasoning:  Explicit flag from router JSON

    Returns:
        Model name string (never empty).
    """
    intents = intents or []

    if should_use_reasoning(
        intents=intents,
        confidence=confidence,
        safety_level=safety_level,
        refers_to_previous=refers_to_previous,
        complexity=complexity,
        needs_reasoning=needs_reasoning,
    ):
        reason = _reasoning_reason(
            intents, confidence, safety_level,
            refers_to_previous, complexity, needs_reasoning,
        )
        model = get_model("reasoning")
        log_model_choice("reasoning", model, confidence=confidence, reason=reason)
        return model

    model = get_model("chat")
    log_model_choice("chat", model, confidence=confidence, reason="standard chat/data response")
    return model


def _reasoning_reason(
    intents: list,
    confidence: float,
    safety_level: str,
    refers_to_previous: bool,
    complexity: str,
    needs_reasoning: bool,
) -> str:
    """Build a short human-readable string explaining why REASONING was chosen."""
    if needs_reasoning:
        return "router flagged needs_reasoning=true"
    if safety_level in ("confirm", "dangerous"):
        return f"safety_level={safety_level}"
    matched = [i for i in intents if i in REASONING_INTENTS]
    if matched:
        return f"reasoning intent: {matched[0]}"
    destructive = [i for i in intents if i in DESTRUCTIVE_INTENTS]
    if destructive:
        return (
            f"destructive intent with ambiguity "
            f"(confidence={confidence:.2f}, refers_to_previous={refers_to_previous})"
        )
    if confidence < 0.75:
        return f"low confidence ({confidence:.2f})"
    if complexity == "complex":
        return "complexity=complex"
    return "unknown"


def log_model_choice(
    purpose: str,
    model: str,
    *,
    confidence: float | None = None,
    reason: str = "",
) -> None:
    """Log which model was chosen and why.

    Uses DEBUG level. Never logs API keys or user data.
    Format: model_router | purpose=chat  model=gpt-5.4-mini  confidence=0.92, reason=standard chat
    """
    conf_str = f"  confidence={confidence:.2f}" if confidence is not None else ""
    reason_str = f", reason={reason}" if reason else ""
    logging.debug(
        "model_router | purpose=%-12s model=%-24s%s%s",
        purpose, model, conf_str, reason_str,
    )
