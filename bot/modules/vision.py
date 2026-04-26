"""Vision analysis module for TUNTUN.

Sends a photo to OpenAI vision model and returns structured JSON with:
- photo_type: screenshot | receipt | study_task | schedule | document | object | unknown
- summary: brief description
- extracted_text: raw text visible in the image
- detected_entities: amount, currency, date, merchant, subject, deadline
- suggested_actions: list of {intent, params}
- needs_confirmation: whether to ask before executing actions

Public API:
    analyze_photo(image_url_or_b64, caption, user_id) -> dict
    build_reply(vision_result, att_id)               -> str
"""
import base64
import json
import logging
from pathlib import Path

from openai import AsyncOpenAI

import config
from bot.ai.model_router import get_model

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client


_VISION_SYSTEM = """Ты анализируешь изображение и возвращаешь ТОЛЬКО JSON без markdown-блоков.

Формат ответа:
{
  "photo_type": "screenshot|receipt|study_task|schedule|document|object|unknown",
  "summary": "краткое описание что на фото (1-3 предложения)",
  "extracted_text": "весь видимый текст, если есть",
  "detected_entities": {
    "amount": null,
    "currency": null,
    "date": null,
    "merchant": null,
    "subject": null,
    "deadline": null
  },
  "suggested_actions": [
    {"intent": "expense_add", "params": {"amount": 42.0, "currency": "PLN", "description": "еда"}}
  ],
  "needs_confirmation": true
}

Типы photo_type:
- receipt: фото чека/квитанции — detected_entities.amount/currency обязательны
- study_task: задание/условие/учебный материал
- schedule: расписание с датами/временем
- screenshot: скриншот интерфейса/экрана
- document: документ/письмо/текст
- object: товар, машина, ремонт, предмет
- unknown: непонятно

Правила:
- Для receipt всегда предложи intent=expense_add с реальными params из фото
- Для study_task предложи intent=study_add_record
- Для schedule предложи intent=schedule_add_event для каждого события
- needs_confirmation=true ВСЕГДА (не выполнять автоматически)
- extracted_text — весь текст который ты видишь на фото, дословно
- Если текста нет — extracted_text=""
- Отвечай ТОЛЬКО JSON"""


async def analyze_photo(
    local_path: str,
    caption: str = "",
    user_id: int = None,
) -> dict | None:
    """Analyze a photo using the vision model.

    Args:
        local_path: Absolute path to the saved image file.
        caption: Optional caption/text the user sent with the photo.
        user_id: For logging.

    Returns:
        Parsed dict from vision model, or None on failure.
    """
    if not config.VISION_ENABLED:
        return None

    try:
        path = Path(local_path)
        if not path.exists():
            logging.warning("vision.analyze_photo: file not found: %s", local_path)
            return None

        # Encode to base64
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        user_prompt = "Проанализируй это изображение."
        if caption:
            user_prompt = f"Пользователь написал: «{caption}». Проанализируй изображение с учётом этого контекста."

        response = await _get_client().chat.completions.create(
            model=get_model("vision"),
            messages=[
                {"role": "system", "content": _VISION_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=1000,
            temperature=0.1,
        )

        content = response.choices[0].message.content.strip()
        # Strip any accidental markdown fences
        import re
        content = re.sub(r"```(?:json)?", "", content).strip().rstrip("`")
        result = json.loads(content)
        return result

    except json.JSONDecodeError as e:
        logging.error("vision.analyze_photo: JSON parse error: %s", e)
        return None
    except Exception as e:
        logging.error("vision.analyze_photo error (user=%s): %s", user_id, e)
        return None


def build_reply(vision_result: dict, att_id: int, caption: str = "") -> str:
    """Build a human-readable reply from a vision analysis result.

    Returns a string to send to the user. If suggested_actions exist,
    appends confirmation prompt.
    """
    if not vision_result:
        return "📸 Фото сохранено. Анализ не удался — попробуй ещё раз."

    photo_type = vision_result.get("photo_type", "unknown")
    summary = vision_result.get("summary", "")
    extracted = vision_result.get("extracted_text", "")
    entities = vision_result.get("detected_entities") or {}
    actions = vision_result.get("suggested_actions") or []

    type_emoji = {
        "receipt": "🧾",
        "study_task": "📚",
        "schedule": "📅",
        "screenshot": "🖥️",
        "document": "📄",
        "object": "📦",
        "unknown": "📸",
    }.get(photo_type, "📸")

    lines = [f"{type_emoji} **{_type_label(photo_type)}** (#{att_id})"]

    if summary:
        lines.append(summary)

    if extracted and len(extracted) > 3:
        lines.append(f"\n📝 Текст: _{extracted[:300]}_")

    # For receipts — show extracted amount
    if photo_type == "receipt":
        amount = entities.get("amount")
        currency = entities.get("currency", "")
        merchant = entities.get("merchant", "")
        date_val = entities.get("date", "")
        if amount:
            detail = f"{amount} {currency}".strip()
            if merchant:
                detail += f" — {merchant}"
            if date_val:
                detail += f" ({date_val})"
            lines.append(f"\n💰 Сумма: {detail}")

    # Suggested actions → confirmation prompt
    if actions:
        action_descs = []
        for a in actions[:3]:
            intent = a.get("intent", "")
            params = a.get("params", {})
            label = _intent_label(intent, params)
            if label:
                action_descs.append(label)
        if action_descs:
            lines.append("\n\n💡 Могу сделать:")
            for d in action_descs:
                lines.append(f"  — {d}")
            lines.append("\nОтветь «да» или «сохрани» чтобы выполнить.")

    return "\n".join(lines)


def _type_label(photo_type: str) -> str:
    return {
        "receipt": "Чек",
        "study_task": "Учебное задание",
        "schedule": "Расписание",
        "screenshot": "Скриншот",
        "document": "Документ",
        "object": "Объект",
        "unknown": "Фото",
    }.get(photo_type, "Фото")


def _intent_label(intent: str, params: dict) -> str:
    if intent == "expense_add":
        return f"Записать расход: {params.get('amount', '?')} {params.get('currency', '')} — {params.get('description', '')}"
    if intent == "study_add_record":
        return f"Сохранить как учебную запись: {params.get('subject', 'без предмета')}"
    if intent == "schedule_add_event":
        return f"Добавить в расписание: {params.get('title', '?')} {params.get('date', '')}"
    if intent == "section_record_add":
        return f"Добавить запись в раздел {params.get('section_name', '?')}"
    return ""
