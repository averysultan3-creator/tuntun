"""Google integration Telegram commands for TUNTUN.

Intents handled:
    google_connect    — show setup instructions
    google_show_link  — return link to user's spreadsheet
    google_sync_now   — process sync queue now
"""
import logging


async def handle_connect(user_id: int, params: dict = None, **_) -> str:
    """Show instructions for connecting Google Service Account."""
    import config

    sa_file = config.GOOGLE_SERVICE_ACCOUNT_FILE
    enabled = config.GOOGLE_ENABLED

    if not enabled:
        return (
            "🔌 *Google интеграция отключена.*\n\n"
            "Чтобы включить:\n"
            "1. В Google Cloud Console создай проект и включи *Sheets API*, *Docs API*, *Drive API*\n"
            "2. Создай Service Account → скачай JSON ключ\n"
            f"3. Положи JSON в `{sa_file}`\n"
            "4. В `.env` установи `GOOGLE_ENABLED=true`\n"
            "5. Перезапусти бота\n\n"
            "После этого пиши «покажи мою таблицу» — бот создаст её автоматически."
        )

    from bot.integrations.google.auth import is_google_enabled
    if not is_google_enabled():
        return (
            "⚠️ Google включён в настройках, но авторизация не работает.\n"
            f"Проверь файл: `{sa_file}`\n"
            "Убедись, что файл существует и содержит корректный JSON Service Account."
        )

    from bot.db.database import db
    sid = await db.google_spreadsheet_get(user_id)
    if sid:
        from bot.integrations.google.sheets import get_spreadsheet_url
        url = get_spreadsheet_url(sid)
        return (
            "✅ *Google интеграция подключена.*\n\n"
            f"Твоя таблица: {url}\n\n"
            "Все расходы, задачи, напоминания и заметки синхронизируются автоматически."
        )

    return (
        "✅ *Google интеграция активна.*\n\n"
        "Таблица будет создана автоматически при первой записи данных.\n"
        "Или напиши «покажи мою таблицу» — создам прямо сейчас."
    )


async def handle_show_link(user_id: int, params: dict = None, **_) -> str:
    """Return link to user's Google Spreadsheet (create if needed)."""
    import config

    if not config.GOOGLE_ENABLED:
        return "Google интеграция отключена. Напиши «как подключить Google» для инструкции."

    from bot.integrations.google.auth import is_google_enabled
    if not is_google_enabled():
        return "⚠️ Авторизация Google не работает. Проверь `credentials/google_service_account.json`."

    from bot.integrations.google.sheets import get_or_create_spreadsheet, get_spreadsheet_url
    sid = await get_or_create_spreadsheet("TUNTUN — Personal Database", user_id)

    if not sid:
        return "❌ Не удалось создать или получить таблицу. Проверь Google API credentials."

    url = get_spreadsheet_url(sid)
    return f"📊 [Открыть таблицу Google Sheets]({url})"


async def handle_sync_now(user_id: int, params: dict = None, **_) -> str:
    """Process the sync queue immediately."""
    import config

    if not config.GOOGLE_ENABLED:
        return "Google интеграция отключена."

    from bot.integrations.google.auth import is_google_enabled
    if not is_google_enabled():
        return "⚠️ Авторизация Google не работает."

    from bot.db.database import db
    pending = await db.google_sync_pending(limit=1)
    count = len(pending)

    if count == 0:
        return "✅ Очередь синхронизации пуста — всё уже синхронизировано."

    try:
        from bot.integrations.google.sync import process_sync_queue
        await process_sync_queue()
        return f"✅ Запустил синхронизацию ({count} элементов в очереди)."
    except Exception as e:
        logging.error("google_handler: sync_now error: %s", e)
        return f"❌ Ошибка при синхронизации: {e}"
