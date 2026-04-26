import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message

import config
from bot.db.database import db

router = Router()


def _is_allowed(user_id: int) -> bool:
    return not config.ALLOWED_USER_IDS or user_id in config.ALLOWED_USER_IDS


@router.message(F.document)
async def handle_document(message: Message, scheduler=None):
    if not _is_allowed(message.from_user.id):
        return

    user_id = message.from_user.id
    doc = message.document
    caption = message.caption or ""

    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in (doc.file_name or "file") if c.isalnum() or c in "._-")
        filename = f"{ts}_{safe_name}"
        local_path = config.DOCUMENTS_DIR / filename
        await message.bot.download(doc, destination=local_path)

        import re
        section_name = None
        match = re.search(r"(?:раздел|section)\s+(\w+)", caption, re.IGNORECASE)
        if match:
            section_name = match.group(1).lower()

        att_id = await db.attachment_save(
            user_id=user_id,
            file_type="document",
            file_id=doc.file_id,
            local_path=str(local_path),
            caption=caption,
            section_name=section_name,
        )

        section_str = f" → раздел «{section_name}»" if section_name else ""
        await message.answer(f"📎 Документ сохранён: {doc.file_name}#{att_id}{section_str}")

    except Exception as e:
        logging.error(f"Document handler error: {e}")
        await message.answer("❌ Не удалось сохранить документ")
