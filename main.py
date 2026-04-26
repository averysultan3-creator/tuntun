import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

import config
from bot.db.database import db
from bot.handlers.message import router as msg_router
from bot.handlers.callbacks import router as cb_router
from bot.handlers.photo import router as photo_router
from bot.handlers.document import router as doc_router
from bot.utils.scheduler import setup_scheduler

# Fix Windows console encoding so Cyrillic isn't garbled
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _setup_logging():
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOGS_DIR / "app.log"
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


_setup_logging()


async def main():
    if not config.BOT_TOKEN:
        logging.critical("TELEGRAM_BOT_TOKEN не задан — заполни .env файл")
        sys.exit(1)
    if not config.OPENAI_API_KEY:
        logging.critical("OPENAI_API_KEY не задан — заполни .env файл")
        sys.exit(1)

    # Create all dirs
    for d in config.STORAGE_DIRS:
        d.mkdir(parents=True, exist_ok=True)
    logging.info("Папки storage созданы")

    # Init database
    await db.init()
    logging.info("База данных инициализирована")

    # Create bot
    bot = Bot(token=config.BOT_TOKEN)

    # Start scheduler
    scheduler = await setup_scheduler(bot)

    # Dispatcher with FSM memory storage
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(msg_router)
    dp.include_router(cb_router)
    dp.include_router(photo_router)
    dp.include_router(doc_router)

    logging.info("TUNTUN запускается...")
    try:
        await dp.start_polling(bot, scheduler=scheduler, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logging.info("TUNTUN остановлен")


if __name__ == "__main__":
    # --init-db: initialise database tables and exit (used by deployment scripts)
    if "--init-db" in sys.argv:
        async def _init_only():
            for d in config.STORAGE_DIRS:
                d.mkdir(parents=True, exist_ok=True)
            await db.init()
            logging.info("Database initialised successfully.")
        asyncio.run(_init_only())
        sys.exit(0)

    asyncio.run(main())
