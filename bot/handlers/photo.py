import json
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message

import config
from bot.db.database import db
from bot.core.capabilities import is_vision_enabled

router = Router()


def _is_allowed(user_id: int) -> bool:
    return not config.ALLOWED_USER_IDS or user_id in config.ALLOWED_USER_IDS


@router.message(F.photo)
async def handle_photo(message: Message, scheduler=None):
    if not _is_allowed(message.from_user.id):
        return

    user_id = message.from_user.id
    caption = message.caption or ""
    photo = message.photo[-1]  # largest size

    try:
        # ── Download and save ────────────────────────────────────────────
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"photo_{user_id}_{ts}.jpg"
        local_path = config.PHOTOS_DIR / filename
        await message.bot.download(photo, destination=local_path)

        # Detect section from caption (e.g. "это фото в раздел ремонт")
        section_name = None
        import re
        match = re.search(r"(?:раздел|section|в|для)\s+(\w+)", caption, re.IGNORECASE)
        if match:
            section_name = match.group(1).lower()

        att_id = await db.attachment_save(
            user_id=user_id,
            file_type="photo",
            file_id=photo.file_id,
            local_path=str(local_path),
            caption=caption,
            section_name=section_name,
        )

        # ── Google Drive sync (non-blocking) ───────────────────────────────────────
        if config.GOOGLE_ENABLED:
            import asyncio
            from bot.integrations.google.sync import sync_object_to_google
            asyncio.create_task(sync_object_to_google(
                user_id=user_id,
                object_type="attachment",
                object_id=att_id,
                payload={
                    "file_type": "photo",
                    "local_path": str(local_path),
                    "caption": caption,
                    "section_name": section_name or "",
                },
            ))

        # ── Vision analysis (if enabled) ─────────────────────────────────
        if is_vision_enabled():
            await message.answer("🔍 Анализирую фото...")
            try:
                from bot.modules.vision import analyze_photo, build_reply
                vision_result = await analyze_photo(
                    local_path=str(local_path),
                    caption=caption,
                    user_id=user_id,
                )

                if vision_result:
                    # Persist vision result
                    await db.vision_save(
                        user_id=user_id,
                        attachment_id=att_id,
                        photo_type=vision_result.get("photo_type", "unknown"),
                        summary=vision_result.get("summary", ""),
                        extracted_text=vision_result.get("extracted_text", ""),
                        detected_entities=vision_result.get("detected_entities"),
                        suggested_actions=vision_result.get("suggested_actions"),
                    )
                    # Brief summary on attachment for quick retrieval
                    await db.attachment_update_vision(att_id, vision_result.get("summary", ""))

                    # Save pending actions to conversation_state for follow-up
                    actions = vision_result.get("suggested_actions") or []
                    await db.conversation_state_update(
                        user_id,
                        active_topic="photo",
                        active_object_type="attachment",
                        active_object_id=att_id,
                        last_photo_id=att_id,
                        last_user_message=caption or "[фото]",
                        pending_vision_actions_json=json.dumps(actions, ensure_ascii=False) if actions else None,
                    )

                    # Build and send reply
                    reply = build_reply(vision_result, att_id, caption)

                    # Update conversation state with last discussed photo context
                    await db.conversation_state_update(
                        user_id,
                        active_topic="photo",
                        active_object_type="attachment",
                        active_object_id=att_id,
                        last_user_message=caption or "[фото]",
                        last_bot_response=reply[:300],
                    )

                    try:
                        await message.answer(reply, parse_mode="Markdown")
                    except Exception:
                        await message.answer(reply)
                    return

                else:
                    # vision returned fallback (parse error) — still show something
                    await message.answer("⚠️ Фото сохранил, но анализ не сработал.")
                    return

            except Exception as e:
                logging.error("Vision analysis error: %s", e, exc_info=True)
                # Attachment already saved — report partial success
                await message.answer("⚠️ Фото сохранил, но анализ не сработал.")
                return

        # ── No vision: simple save confirmation ──────────────────────────
        section_str = f" → раздел «{section_name}»" if section_name else ""
        await message.answer(f"📸 Фото сохранено #{att_id}{section_str}")

    except Exception as e:
        logging.error(f"Photo handler error: {e}")
        await message.answer("❌ Не удалось сохранить фото")

