import zipfile
import logging
from datetime import datetime
from pathlib import Path

import config
from bot.db.database import db


async def create_backup(user_id: int) -> str | None:
    """Create a zip backup of DB + storage and return local path."""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"tuntun_backup_{ts}.zip"
        backup_path = config.BACKUPS_DIR / filename

        readme = (
            f"TUNTUN Backup\n"
            f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"User: {user_id}\n\n"
            f"Contents:\n"
            f"  tuntun.db     — SQLite database\n"
            f"  photos/       — saved photos\n"
            f"  voice/        — voice recordings\n"
            f"  documents/    — saved documents\n"
            f"  exports/      — previous exports\n"
        )
        readme_path = config.STORAGE_DIR / "README_backup.txt"
        readme_path.write_text(readme, encoding="utf-8")

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Database
            db_path = Path(config.DB_PATH)
            if db_path.exists():
                zf.write(db_path, "tuntun.db")

            # README
            zf.write(readme_path, "README_backup.txt")

            # Storage folders (exclude backups to avoid recursion)
            for folder in [config.PHOTOS_DIR, config.VOICE_DIR,
                           config.DOCUMENTS_DIR, config.EXPORTS_DIR]:
                if folder.exists():
                    for file in folder.iterdir():
                        if file.is_file():
                            zf.write(file, f"{folder.name}/{file.name}")

        await db.export_log(user_id, "backup", str(backup_path))
        logging.info(f"Backup created: {backup_path}")
        return str(backup_path)

    except Exception as e:
        logging.error(f"Backup error: {e}")
        return None


async def handle_create(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    file_path = await create_backup(user_id)
    if not file_path:
        return "❌ Ошибка при создании backup"
    size_kb = Path(file_path).stat().st_size // 1024
    summary = f"💾 Backup создан ({size_kb} KB): `{Path(file_path).name}`"
    return f"{summary}\n__FILE__:{file_path}"
