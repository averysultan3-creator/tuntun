import logging
from io import BytesIO
from pathlib import Path
from datetime import datetime

from aiogram.types import Message
from openai import AsyncOpenAI

import config
from bot.ai.model_router import get_model

_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


async def transcribe_and_save(message: Message) -> tuple[str | None, str | None]:
    """Download voice, save to storage/voice/, transcribe with Whisper.
    Returns (transcription_text, local_path)."""
    voice = message.voice
    if not voice:
        return None, None

    try:
        buf = BytesIO()
        await message.bot.download(voice, destination=buf)
        buf.seek(0)

        # Save locally
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"voice_{message.from_user.id}_{ts}.ogg"
        local_path = config.VOICE_DIR / filename
        local_path.write_bytes(buf.getvalue())
        buf.seek(0)
        buf.name = "voice.ogg"

        # Transcribe
        response = await _client.audio.transcriptions.create(
            model=get_model("transcribe"),
            file=buf,
            language="ru",
        )
        return response.text.strip(), str(local_path)

    except Exception as e:
        logging.error(f"Voice transcription error: {e}")
        return None, None
