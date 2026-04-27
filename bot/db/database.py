import aiosqlite
import json
from datetime import datetime
from typing import Optional
import config

_CREATE_SQL = [
    """CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        timezone TEXT DEFAULT 'Europe/Warsaw',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, key)
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        priority TEXT DEFAULT 'normal',
        due_date TEXT,
        due_time TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS study_subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        short_name TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS study_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject_id INTEGER,
        subject_name TEXT,
        type TEXT NOT NULL,
        content TEXT NOT NULL,
        due_date TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS schedule_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        date TEXT,
        start_time TEXT,
        end_time TEXT,
        recurring INTEGER DEFAULT 0,
        recurrence_rule TEXT,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        remind_at TEXT NOT NULL,
        recurring INTEGER DEFAULT 0,
        interval_minutes INTEGER,
        status TEXT DEFAULT 'active',
        job_id TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        key_name TEXT,
        value TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        title TEXT,
        description TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        project_id INTEGER,
        project_name TEXT,
        amount REAL NOT NULL,
        currency TEXT DEFAULT 'USD',
        description TEXT,
        date TEXT DEFAULT (date('now')),
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS dynamic_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        title TEXT NOT NULL,
        fields TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS dynamic_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        section_id INTEGER NOT NULL,
        section_name TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS daily_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        plan_json TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, date)
    )""",
    """CREATE TABLE IF NOT EXISTS message_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message_type TEXT DEFAULT 'text',
        original_text TEXT,
        transcription TEXT,
        actions_json TEXT,
        bot_response TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        file_type TEXT NOT NULL,
        file_id TEXT,
        local_path TEXT,
        caption TEXT,
        section_name TEXT,
        record_id INTEGER,
        vision_summary TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS exports_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        export_type TEXT NOT NULL,
        file_path TEXT,
        params_json TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        period_type TEXT NOT NULL,
        period_label TEXT NOT NULL,
        target TEXT,
        content TEXT NOT NULL,
        date_from TEXT,
        date_to TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    # Conversation state — active context for contextual follow-ups
    """CREATE TABLE IF NOT EXISTS conversation_state (
        user_id INTEGER PRIMARY KEY,
        active_topic TEXT,
        active_section TEXT,
        active_object_type TEXT,
        active_object_id INTEGER,
        active_date TEXT,
        last_user_message TEXT,
        last_bot_response TEXT,
        last_plan_json TEXT,
        last_table_json TEXT,
        last_export_target TEXT,
        last_photo_id INTEGER,
        last_discussed_reminder_ids TEXT,
        last_discussed_task_ids TEXT,
        last_discussed_record_ids TEXT,
        last_discussed_idea_ids TEXT,
        onboarding_step INTEGER DEFAULT 0,
        pending_vision_actions_json TEXT,
        pending_vision_expires_at TEXT,
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    # Ideas — user ideas, attached to projects, can be converted to tasks
    """CREATE TABLE IF NOT EXISTS ideas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        category TEXT DEFAULT 'general',
        status TEXT DEFAULT 'new',
        related_project TEXT,
        related_section TEXT,
        source_message_id INTEGER,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    # Vision summaries for photos/documents
    """CREATE TABLE IF NOT EXISTS vision_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        attachment_id INTEGER,
        photo_type TEXT,
        summary TEXT,
        extracted_text TEXT,
        detected_entities TEXT,
        suggested_actions TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""",
    # Google sync queue — pending operations when Google API is unavailable
    """CREATE TABLE IF NOT EXISTS google_sync_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        object_type TEXT NOT NULL,
        object_id INTEGER,
        target TEXT NOT NULL,
        action TEXT NOT NULL,
        payload_json TEXT,
        status TEXT DEFAULT 'pending',
        error_text TEXT,
        retry_count INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""",
    # Google links — maps local objects to their Google counterparts
    """CREATE TABLE IF NOT EXISTS google_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        object_type TEXT NOT NULL,
        object_id INTEGER,
        google_type TEXT NOT NULL,
        spreadsheet_id TEXT,
        sheet_name TEXT,
        row_number INTEGER,
        doc_id TEXT,
        drive_file_id TEXT,
        url TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, object_type, object_id, google_type)
    )""",
]


class Database:
    def __init__(self, db_path: str = None):
        self._path = db_path or config.DB_PATH

    async def init(self):
        async with aiosqlite.connect(self._path) as db:
            for sql in _CREATE_SQL:
                await db.execute(sql)
            await db.commit()
        await self.db_health_migrate()

    async def db_health_migrate(self) -> dict:
        """Safe migration: add missing columns to existing tables, log changes.

        Never drops data. Safe to call on first run and on upgrades.
        Returns dict with lists of created tables/columns.
        """
        import logging
        report = {"tables_created": [], "columns_added": []}

        # Required columns per table: {table: [(col, definition), ...]}
        _REQUIRED_COLUMNS = {
            "attachments": [
                ("vision_summary", "TEXT"),
            ],
            "conversation_state": [
                ("pending_vision_actions_json", "TEXT"),
                ("pending_vision_expires_at", "TEXT"),
                ("last_photo_id", "INTEGER"),
            ],
            "vision_results": [
                ("needs_confirmation", "INTEGER DEFAULT 1"),
                ("error_text", "TEXT"),
            ],
            "google_sync_queue": [
                ("updated_at", "TEXT DEFAULT (datetime('now'))"),
            ],
        }

        async with aiosqlite.connect(self._path) as conn:
            # 1. Ensure all tables exist (run CREATE TABLE IF NOT EXISTS)
            for sql in _CREATE_SQL:
                await conn.execute(sql)
            await conn.commit()

            # 2. Add missing columns
            for table, columns in _REQUIRED_COLUMNS.items():
                for col_name, col_def in columns:
                    try:
                        await conn.execute(
                            f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
                        )
                        await conn.commit()
                        msg = f"{table}.{col_name} ({col_def})"
                        report["columns_added"].append(msg)
                        logging.info("DB migrate: added column %s", msg)
                    except Exception as exc:
                        err_lower = str(exc).lower()
                        if "duplicate column" in err_lower or "already exists" in err_lower:
                            pass  # expected on repeated startups
                        else:
                            logging.warning(
                                "DB migrate: unexpected error adding %s.%s: %s",
                                table, col_name, exc,
                            )
                            report.setdefault("errors", []).append(
                                f"{table}.{col_name}: {exc}"
                            )

        if report["columns_added"]:
            logging.info("DB health_migrate done: added columns %s", report["columns_added"])
        else:
            logging.debug("DB health_migrate: schema is up to date")
        return report

    async def _execute(self, sql: str, params: tuple = ()) -> int:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(sql, params)
            await db.commit()
            return cursor.lastrowid

    async def _fetchall(self, sql: str, params: tuple = ()) -> list:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def _fetchone(self, sql: str, params: tuple = ()) -> Optional[dict]:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    # ===== TASKS =====

    async def task_create(self, user_id: int, title: str, description: str = None,
                          priority: str = "normal", due_date: str = None, due_time: str = None) -> int:
        return await self._execute(
            "INSERT INTO tasks (user_id, title, description, priority, due_date, due_time) VALUES (?,?,?,?,?,?)",
            (user_id, title, description, priority, due_date, due_time),
        )

    async def task_list(self, user_id: int, filter_date: str = None, status: str = "pending") -> list:
        if filter_date:
            return await self._fetchall(
                "SELECT * FROM tasks WHERE user_id=? AND due_date=? AND status=? ORDER BY priority DESC, due_time",
                (user_id, filter_date, status),
            )
        return await self._fetchall(
            "SELECT * FROM tasks WHERE user_id=? AND status=? ORDER BY due_date, priority DESC",
            (user_id, status),
        )

    async def task_find_by_title(self, user_id: int, keyword: str) -> list:
        return await self._fetchall(
            "SELECT * FROM tasks WHERE user_id=? AND title LIKE ? AND status='pending'",
            (user_id, f"%{keyword}%"),
        )

    async def task_complete(self, user_id: int, task_id: int) -> bool:
        rows = await self._fetchall(
            "SELECT id FROM tasks WHERE user_id=? AND id=? AND status='pending'",
            (user_id, task_id),
        )
        if rows:
            await self._execute(
                "UPDATE tasks SET status='done' WHERE id=? AND user_id=?",
                (task_id, user_id),
            )
            return True
        return False

    async def task_update(self, user_id: int, task_id: int, **kwargs) -> bool:
        allowed = {"title", "description", "priority", "due_date", "due_time", "status"}
        fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not fields:
            return False
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [task_id, user_id]
        await self._execute(
            f"UPDATE tasks SET {set_clause} WHERE id=? AND user_id=?",
            tuple(values),
        )
        return True

    # ===== STUDY =====

    async def study_add_subject(self, user_id: int, name: str, short_name: str = None) -> int:
        return await self._execute(
            "INSERT INTO study_subjects (user_id, name, short_name) VALUES (?,?,?)",
            (user_id, name, short_name or name),
        )

    async def study_get_subjects(self, user_id: int) -> list:
        return await self._fetchall(
            "SELECT * FROM study_subjects WHERE user_id=?",
            (user_id,),
        )

    async def study_find_subject(self, user_id: int, name: str) -> Optional[dict]:
        return await self._fetchone(
            "SELECT * FROM study_subjects WHERE user_id=? AND (name LIKE ? OR short_name LIKE ?)",
            (user_id, f"%{name}%", f"%{name}%"),
        )

    async def study_add_record(self, user_id: int, subject_name: str, record_type: str,
                               content: str, due_date: str = None) -> int:
        subject = await self.study_find_subject(user_id, subject_name) if subject_name else None
        subject_id = subject["id"] if subject else None
        return await self._execute(
            "INSERT INTO study_records (user_id, subject_id, subject_name, type, content, due_date) VALUES (?,?,?,?,?,?)",
            (user_id, subject_id, subject_name, record_type, content, due_date),
        )

    async def study_list(self, user_id: int, subject_name: str = None, record_type: str = None) -> list:
        sql = "SELECT * FROM study_records WHERE user_id=? AND status='open'"
        params = [user_id]
        if subject_name:
            sql += " AND subject_name LIKE ?"
            params.append(f"%{subject_name}%")
        if record_type:
            sql += " AND type=?"
            params.append(record_type)
        sql += " ORDER BY due_date, created_at"
        return await self._fetchall(sql, tuple(params))

    async def study_complete(self, user_id: int, record_id: int):
        await self._execute(
            "UPDATE study_records SET status='done' WHERE id=? AND user_id=?",
            (record_id, user_id),
        )

    # ===== SCHEDULE =====

    async def schedule_add_event(self, user_id: int, title: str, date: str = None,
                                 start_time: str = None, end_time: str = None,
                                 recurring: bool = False, recurrence_rule: str = None,
                                 notes: str = None) -> int:
        return await self._execute(
            "INSERT INTO schedule_events (user_id, title, date, start_time, end_time, recurring, recurrence_rule, notes) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, title, date, start_time, end_time, int(recurring), recurrence_rule, notes),
        )

    async def schedule_get_day(self, user_id: int, date: str) -> list:
        return await self._fetchall(
            "SELECT * FROM schedule_events WHERE user_id=? AND (date=? OR recurring=1) ORDER BY start_time",
            (user_id, date),
        )

    async def schedule_get_range(self, user_id: int, start_date: str, end_date: str) -> list:
        return await self._fetchall(
            "SELECT * FROM schedule_events WHERE user_id=? AND (date BETWEEN ? AND ? OR recurring=1) ORDER BY date, start_time",
            (user_id, start_date, end_date),
        )

    # ===== REMINDERS =====

    async def reminder_create(self, user_id: int, text: str, remind_at: str,
                              recurring: bool = False, interval_minutes: int = None,
                              job_id: str = None) -> int:
        return await self._execute(
            "INSERT INTO reminders (user_id, text, remind_at, recurring, interval_minutes, job_id) VALUES (?,?,?,?,?,?)",
            (user_id, text, remind_at, int(recurring), interval_minutes, job_id),
        )

    async def reminder_list(self, user_id: int) -> list:
        return await self._fetchall(
            "SELECT * FROM reminders WHERE user_id=? AND status='active' ORDER BY remind_at",
            (user_id,),
        )

    async def reminder_cancel(self, user_id: int, reminder_id: int) -> Optional[dict]:
        reminder = await self._fetchone(
            "SELECT * FROM reminders WHERE id=? AND user_id=?",
            (reminder_id, user_id),
        )
        if reminder:
            await self._execute(
                "UPDATE reminders SET status='cancelled' WHERE id=?",
                (reminder_id,),
            )
        return reminder

    async def reminder_get_all_active(self) -> list:
        return await self._fetchall("SELECT * FROM reminders WHERE status='active'")

    async def reminder_update_job_id(self, reminder_id: int, job_id: str):
        await self._execute(
            "UPDATE reminders SET job_id=? WHERE id=?",
            (job_id, reminder_id),
        )

    # ===== MEMORY =====

    async def memory_save(self, user_id: int, category: str, value: str,
                          key_name: str = None, importance: int = 3, tag: str = None) -> int:
        # Check for near-duplicate (same category + key_name)
        if key_name:
            existing = await self._fetchone(
                "SELECT id FROM memory WHERE user_id=? AND category=? AND key_name=?",
                (user_id, category, key_name),
            )
            if existing:
                await self._execute(
                    "UPDATE memory SET value=?, importance=?, updated_at=datetime('now') WHERE id=?",
                    (value, importance, existing["id"]),
                )
                return existing["id"]
        # Ensure importance column exists (migration guard)
        try:
            await self._execute("ALTER TABLE memory ADD COLUMN importance INTEGER DEFAULT 3", ())
        except Exception:
            pass
        try:
            await self._execute("ALTER TABLE memory ADD COLUMN tag TEXT", ())
        except Exception:
            pass
        try:
            await self._execute("ALTER TABLE memory ADD COLUMN updated_at TEXT", ())
        except Exception:
            pass
        return await self._execute(
            "INSERT INTO memory (user_id, category, key_name, value, importance, tag) VALUES (?,?,?,?,?,?)",
            (user_id, category, key_name, value, importance, tag),
        )

    async def memory_recall(self, user_id: int, category: str = None, query: str = None) -> list:
        if category:
            return await self._fetchall(
                "SELECT * FROM memory WHERE user_id=? AND category LIKE ? ORDER BY created_at DESC",
                (user_id, f"%{category}%"),
            )
        if query:
            return await self._fetchall(
                "SELECT * FROM memory WHERE user_id=? AND (value LIKE ? OR key_name LIKE ? OR category LIKE ?) ORDER BY created_at DESC",
                (user_id, f"%{query}%", f"%{query}%", f"%{query}%"),
            )
        return await self._fetchall(
            "SELECT * FROM memory WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            (user_id,),
        )

    # ===== PROJECTS & EXPENSES =====

    async def project_create(self, user_id: int, name: str, title: str = None, description: str = None) -> int:
        return await self._execute(
            "INSERT INTO projects (user_id, name, title, description) VALUES (?,?,?,?)",
            (user_id, name, title or name, description),
        )

    async def project_list(self, user_id: int) -> list:
        return await self._fetchall(
            "SELECT * FROM projects WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )

    async def project_find(self, user_id: int, name: str) -> Optional[dict]:
        return await self._fetchone(
            "SELECT * FROM projects WHERE user_id=? AND (name LIKE ? OR title LIKE ?)",
            (user_id, f"%{name}%", f"%{name}%"),
        )

    async def expense_add(self, user_id: int, amount: float, currency: str = "USD",
                          description: str = None, project_name: str = None, date: str = None) -> int:
        project = await self.project_find(user_id, project_name) if project_name else None
        project_id = project["id"] if project else None
        return await self._execute(
            "INSERT INTO expenses (user_id, project_id, project_name, amount, currency, description, date) VALUES (?,?,?,?,?,?,?)",
            (user_id, project_id, project_name, amount, currency, description,
             date or datetime.now().strftime("%Y-%m-%d")),
        )

    async def expense_stats(self, user_id: int, project_name: str = None,
                            start_date: str = None, end_date: str = None) -> list:
        sql = "SELECT * FROM expenses WHERE user_id=?"
        params = [user_id]
        if project_name:
            sql += " AND project_name LIKE ?"
            params.append(f"%{project_name}%")
        if start_date:
            sql += " AND date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND date <= ?"
            params.append(end_date)
        sql += " ORDER BY date DESC"
        return await self._fetchall(sql, tuple(params))

    # ===== DYNAMIC SECTIONS =====

    async def section_create(self, user_id: int, name: str, title: str, fields: list) -> int:
        return await self._execute(
            "INSERT INTO dynamic_sections (user_id, name, title, fields) VALUES (?,?,?,?)",
            (user_id, name, title, json.dumps(fields, ensure_ascii=False)),
        )

    async def section_find(self, user_id: int, name: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM dynamic_sections WHERE user_id=? AND (name LIKE ? OR title LIKE ?)",
            (user_id, f"%{name}%", f"%{name}%"),
        )
        if row:
            row["fields"] = json.loads(row["fields"])
        return row

    async def section_list(self, user_id: int) -> list:
        rows = await self._fetchall(
            "SELECT * FROM dynamic_sections WHERE user_id=?",
            (user_id,),
        )
        for row in rows:
            row["fields"] = json.loads(row["fields"])
        return rows

    async def section_record_add(self, user_id: int, section_name: str, data: dict) -> int:
        section = await self.section_find(user_id, section_name)
        if not section:
            return -1
        return await self._execute(
            "INSERT INTO dynamic_records (user_id, section_id, section_name, data) VALUES (?,?,?,?)",
            (user_id, section["id"], section["name"], json.dumps(data, ensure_ascii=False)),
        )

    async def section_query(self, user_id: int, section_name: str, limit: int = 20) -> list:
        section = await self.section_find(user_id, section_name)
        if not section:
            return []
        rows = await self._fetchall(
            "SELECT * FROM dynamic_records WHERE user_id=? AND section_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, section["id"], limit),
        )
        for row in rows:
            row["data"] = json.loads(row["data"])
        return rows

    async def section_records_all(self, user_id: int, section_name: str) -> list:
        section = await self.section_find(user_id, section_name)
        if not section:
            return []
        rows = await self._fetchall(
            "SELECT * FROM dynamic_records WHERE user_id=? AND section_id=? ORDER BY created_at",
            (user_id, section["id"]),
        )
        for row in rows:
            row["data"] = json.loads(row["data"])
        return rows

    # ===== USERS =====

    async def ensure_user(self, user_id: int, username: str = None, first_name: str = None):
        existing = await self._fetchone("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        if not existing:
            await self._execute(
                "INSERT INTO users (user_id, username, first_name) VALUES (?,?,?)",
                (user_id, username, first_name),
            )
        elif username or first_name:
            await self._execute(
                "UPDATE users SET username=?, first_name=?, updated_at=datetime('now') WHERE user_id=?",
                (username, first_name, user_id),
            )

    # ===== SETTINGS =====

    async def setting_get(self, user_id: int, key: str, default: str = None) -> Optional[str]:
        row = await self._fetchone(
            "SELECT value FROM settings WHERE user_id=? AND key=?", (user_id, key)
        )
        return row["value"] if row else default

    async def setting_set(self, user_id: int, key: str, value: str):
        await self._execute(
            "INSERT OR REPLACE INTO settings (user_id, key, value, updated_at) VALUES (?,?,?,datetime('now'))",
            (user_id, key, value),
        )

    # ===== MESSAGE LOGS =====

    async def log_message(self, user_id: int, message_type: str, original_text: str,
                          transcription: str = None, actions_json: str = None,
                          bot_response: str = None) -> int:
        return await self._execute(
            "INSERT INTO message_logs (user_id, message_type, original_text, transcription, actions_json, bot_response) VALUES (?,?,?,?,?,?)",
            (user_id, message_type, original_text, transcription, actions_json, bot_response),
        )

    async def log_update_response(self, log_id: int, bot_response: str, actions_json: str = None):
        await self._execute(
            "UPDATE message_logs SET bot_response=?, actions_json=? WHERE id=?",
            (bot_response, actions_json, log_id),
        )

    # ===== ATTACHMENTS =====

    async def attachment_save(self, user_id: int, file_type: str, file_id: str,
                              local_path: str = None, caption: str = None,
                              section_name: str = None, record_id: int = None) -> int:
        return await self._execute(
            "INSERT INTO attachments (user_id, file_type, file_id, local_path, caption, section_name, record_id) VALUES (?,?,?,?,?,?,?)",
            (user_id, file_type, file_id, local_path, caption, section_name, record_id),
        )

    async def attachment_list(self, user_id: int, file_type: str = None, section_name: str = None) -> list:
        sql = "SELECT * FROM attachments WHERE user_id=?"
        params = [user_id]
        if file_type:
            sql += " AND file_type=?"
            params.append(file_type)
        if section_name:
            sql += " AND section_name LIKE ?"
            params.append(f"%{section_name}%")
        sql += " ORDER BY created_at DESC"
        return await self._fetchall(sql, tuple(params))

    # ===== EXPORTS LOG =====

    async def export_log(self, user_id: int, export_type: str, file_path: str, params: dict = None) -> int:
        return await self._execute(
            "INSERT INTO exports_log (user_id, export_type, file_path, params_json) VALUES (?,?,?,?)",
            (user_id, export_type, file_path,
             json.dumps(params, ensure_ascii=False) if params else None),
        )

    # ===== DAILY PLANS =====

    async def plan_save(self, user_id: int, date: str, plan: dict):
        await self._execute(
            """INSERT INTO daily_plans (user_id, date, plan_json, updated_at)
               VALUES (?,?,?,datetime('now'))
               ON CONFLICT(user_id, date) DO UPDATE SET
               plan_json=excluded.plan_json, updated_at=datetime('now')""",
            (user_id, date, json.dumps(plan, ensure_ascii=False)),
        )

    async def plan_get(self, user_id: int, date: str) -> Optional[dict]:
        row = await self._fetchone(
            "SELECT * FROM daily_plans WHERE user_id=? AND date=?", (user_id, date)
        )
        if row:
            row["plan"] = json.loads(row["plan_json"])
        return row

    # ===== ANALYTICS =====

    async def expenses_total(self, user_id: int, start_date: str = None,
                             end_date: str = None, currency: str = None) -> list:
        sql = "SELECT currency, SUM(amount) as total, COUNT(*) as count FROM expenses WHERE user_id=?"
        params = [user_id]
        if start_date:
            sql += " AND date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND date <= ?"
            params.append(end_date)
        if currency:
            sql += " AND currency=?"
            params.append(currency)
        sql += " GROUP BY currency"
        return await self._fetchall(sql, tuple(params))

    async def tasks_stats(self, user_id: int, start_date: str = None, end_date: str = None) -> dict:
        date_filter = ""
        params_base = [user_id]
        if start_date:
            date_filter += " AND (due_date IS NULL OR due_date >= ?)"
            params_base.append(start_date)
        if end_date:
            date_filter += " AND (due_date IS NULL OR due_date <= ?)"
            params_base.append(end_date)

        total = await self._fetchone(
            f"SELECT COUNT(*) as cnt FROM tasks WHERE user_id=?{date_filter}", tuple(params_base)
        )
        done = await self._fetchone(
            f"SELECT COUNT(*) as cnt FROM tasks WHERE user_id=? AND status='done'{date_filter}", tuple(params_base)
        )
        pending = await self._fetchone(
            f"SELECT COUNT(*) as cnt FROM tasks WHERE user_id=? AND status='pending'{date_filter}", tuple(params_base)
        )
        today = __import__('datetime').date.today().strftime("%Y-%m-%d")
        overdue = await self._fetchone(
            "SELECT COUNT(*) as cnt FROM tasks WHERE user_id=? AND status='pending' AND due_date < ?",
            (user_id, today)
        )
        return {
            "total": total["cnt"] if total else 0,
            "done": done["cnt"] if done else 0,
            "pending": pending["cnt"] if pending else 0,
            "overdue": overdue["cnt"] if overdue else 0,
        }

    # ===== SEARCH / RETRIEVAL =====

    async def message_logs_recent(self, user_id: int, limit: int = 5) -> list:
        """Return the last N non-empty messages for the user."""
        return await self._fetchall(
            """SELECT id, message_type, original_text, bot_response, created_at
               FROM message_logs
               WHERE user_id=? AND original_text IS NOT NULL AND original_text != ''
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (user_id, limit),
        )

    async def dynamic_records_search(self, user_id: int, keywords: list, limit: int = 5) -> list:
        """Full-text keyword search across ALL dynamic section records."""
        if not keywords:
            return []
        conditions = " OR ".join(["data LIKE ?" for _ in keywords])
        params = tuple([user_id] + [f"%{kw}%" for kw in keywords] + [limit])
        rows = await self._fetchall(
            f"SELECT id, section_name, data, created_at FROM dynamic_records "
            f"WHERE user_id=? AND ({conditions}) ORDER BY created_at DESC LIMIT ?",
            params,
        )
        for row in rows:
            try:
                data_dict = json.loads(row["data"])
                row["data_preview"] = " | ".join(
                    f"{k}: {str(v)[:60]}" for k, v in data_dict.items()
                )
            except Exception:
                row["data_preview"] = str(row["data"])[:120]
        return rows

    async def expenses_search(self, user_id: int, keywords: list, limit: int = 5) -> list:
        """Search expenses by description or project_name keywords."""
        if not keywords:
            return []
        conditions = " OR ".join(
            ["description LIKE ? OR project_name LIKE ?" for _ in keywords]
        )
        params = tuple([user_id] + [val for kw in keywords for val in (f"%{kw}%", f"%{kw}%")] + [limit])
        return await self._fetchall(
            f"SELECT amount, currency, description, project_name, date FROM expenses "
            f"WHERE user_id=? AND ({conditions}) ORDER BY date DESC LIMIT ?",
            params,
        )

    # ===== SUMMARIES =====

    async def summary_save(self, user_id: int, period_type: str, period_label: str,
                           content: str, target: str = None,
                           date_from: str = None, date_to: str = None) -> int:
        return await self._execute(
            """INSERT INTO summaries (user_id, period_type, period_label, target, content, date_from, date_to)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, period_type, period_label, target, content, date_from, date_to),
        )

    async def summaries_list(self, user_id: int, period_type: str = None, target: str = None,
                             limit: int = 5) -> list:
        sql = "SELECT * FROM summaries WHERE user_id=?"
        params = [user_id]
        if period_type:
            sql += " AND period_type=?"
            params.append(period_type)
        if target:
            sql += " AND target LIKE ?"
            params.append(f"%{target}%")
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self._fetchall(sql, tuple(params))

    async def summaries_search(self, user_id: int, keywords: list, limit: int = 4) -> list:
        if not keywords:
            return []
        conditions = " OR ".join(["content LIKE ? OR period_label LIKE ? OR target LIKE ?" for _ in keywords])
        params = tuple(
            [user_id]
            + [val for kw in keywords for val in (f"%{kw}%", f"%{kw}%", f"%{kw}%")]
            + [limit]
        )
        return await self._fetchall(
            f"SELECT * FROM summaries WHERE user_id=? AND ({conditions}) ORDER BY created_at DESC LIMIT ?",
            params,
        )

    # ===== DYNAMIC SECTION: FIELD EDITING =====

    async def section_add_field(self, user_id: int, section_name: str, new_field: str) -> bool:
        """Add a new field to an existing section."""
        section = await self.section_find(user_id, section_name)
        if not section:
            return False
        fields = section["fields"]
        if new_field not in fields:
            fields.append(new_field)
            await self._execute(
                "UPDATE dynamic_sections SET fields=? WHERE id=? AND user_id=?",
                (json.dumps(fields, ensure_ascii=False), section["id"], user_id),
            )
        return True

    async def section_rename(self, user_id: int, old_name: str, new_title: str) -> bool:
        """Rename section title (keeps name/id intact)."""
        section = await self.section_find(user_id, old_name)
        if not section:
            return False
        await self._execute(
            "UPDATE dynamic_sections SET title=? WHERE id=? AND user_id=?",
            (new_title, section["id"], user_id),
        )
        return True

    async def record_edit(self, user_id: int, section_name: str,
                          record_id: int, updates: dict) -> bool:
        """Partially update fields in a dynamic record."""
        rows = await self._fetchall(
            "SELECT id, data FROM dynamic_records WHERE id=? AND user_id=?",
            (record_id, user_id),
        )
        if not rows:
            return False
        data = json.loads(rows[0]["data"])
        data.update(updates)
        await self._execute(
            "UPDATE dynamic_records SET data=? WHERE id=? AND user_id=?",
            (json.dumps(data, ensure_ascii=False), record_id, user_id),
        )
        return True

    # ===== IDEAS =====

    async def idea_save(self, user_id: int, title: str, description: str = None,
                        category: str = "general", related_project: str = None,
                        related_section: str = None, source_message_id: int = None) -> int:
        return await self._execute(
            """INSERT INTO ideas (user_id, title, description, category, related_project,
               related_section, source_message_id) VALUES (?,?,?,?,?,?,?)""",
            (user_id, title, description, category, related_project, related_section, source_message_id),
        )

    async def idea_list(self, user_id: int, category: str = None,
                        status: str = None, limit: int = 20) -> list:
        sql = "SELECT * FROM ideas WHERE user_id=?"
        params = [user_id]
        if category:
            sql += " AND category LIKE ?"
            params.append(f"%{category}%")
        if status:
            sql += " AND status=?"
            params.append(status)
        else:
            sql += " AND status != 'archived'"
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self._fetchall(sql, tuple(params))

    async def idea_get(self, user_id: int, idea_id: int) -> Optional[dict]:
        return await self._fetchone(
            "SELECT * FROM ideas WHERE id=? AND user_id=?", (idea_id, user_id)
        )

    async def idea_find_latest(self, user_id: int) -> Optional[dict]:
        return await self._fetchone(
            "SELECT * FROM ideas WHERE user_id=? AND status != 'archived' ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )

    async def idea_update_status(self, user_id: int, idea_id: int, status: str) -> bool:
        rows = await self._fetchall(
            "SELECT id FROM ideas WHERE id=? AND user_id=?", (idea_id, user_id)
        )
        if not rows:
            return False
        await self._execute(
            "UPDATE ideas SET status=?, updated_at=datetime('now') WHERE id=? AND user_id=?",
            (status, idea_id, user_id),
        )
        return True

    async def ideas_search(self, user_id: int, keywords: list, limit: int = 5) -> list:
        if not keywords:
            return []
        conditions = " OR ".join(["title LIKE ? OR description LIKE ?" for _ in keywords])
        params = [user_id] + [val for kw in keywords for val in (f"%{kw}%", f"%{kw}%")] + [limit]
        return await self._fetchall(
            f"SELECT * FROM ideas WHERE user_id=? AND ({conditions}) "
            f"AND status != 'archived' ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )

    # ===== CONVERSATION STATE =====

    async def conversation_state_get(self, user_id: int) -> dict:
        row = await self._fetchone("SELECT * FROM conversation_state WHERE user_id=?", (user_id,))
        return row or {}

    async def conversation_state_update(self, user_id: int, **fields) -> None:
        """Upsert conversation state fields. Only pass fields you want to update."""
        if not fields:
            return
        fields["updated_at"] = datetime.now().isoformat(sep=" ", timespec="seconds")
        existing = await self._fetchone("SELECT user_id FROM conversation_state WHERE user_id=?", (user_id,))
        if existing:
            set_clause = ", ".join(f"{k}=?" for k in fields)
            await self._execute(
                f"UPDATE conversation_state SET {set_clause} WHERE user_id=?",
                tuple(fields.values()) + (user_id,),
            )
        else:
            fields["user_id"] = user_id
            cols = ", ".join(fields.keys())
            placeholders = ", ".join("?" * len(fields))
            await self._execute(
                f"INSERT INTO conversation_state ({cols}) VALUES ({placeholders})",
                tuple(fields.values()),
            )

    # ===== VISION RESULTS =====

    async def vision_save(self, user_id: int, attachment_id: int, photo_type: str,
                          summary: str, extracted_text: str = None,
                          detected_entities: dict = None, suggested_actions: list = None) -> int:
        return await self._execute(
            """INSERT INTO vision_results
               (user_id, attachment_id, photo_type, summary, extracted_text, detected_entities, suggested_actions)
               VALUES (?,?,?,?,?,?,?)""",
            (
                user_id, attachment_id, photo_type, summary, extracted_text or "",
                json.dumps(detected_entities or {}, ensure_ascii=False),
                json.dumps(suggested_actions or [], ensure_ascii=False),
            ),
        )

    async def vision_search(self, user_id: int, keywords: list, limit: int = 5) -> list:
        if not keywords:
            return []
        conditions = " OR ".join(
            ["summary LIKE ? OR extracted_text LIKE ?"] * len(keywords)
        )
        params = (
            [user_id]
            + [val for kw in keywords for val in (f"%{kw}%", f"%{kw}%")]
            + [limit]
        )
        return await self._fetchall(
            f"SELECT * FROM vision_results WHERE user_id=? AND ({conditions}) ORDER BY created_at DESC LIMIT ?",
            params,
        )

    async def attachment_update_vision(self, attachment_id: int, vision_summary: str) -> None:
        """Store brief vision summary on the attachment record itself for quick retrieval."""
        try:
            await self._execute(
                "ALTER TABLE attachments ADD COLUMN vision_summary TEXT",
                (),
            )
        except Exception:
            pass  # column may already exist
        await self._execute(
            "UPDATE attachments SET vision_summary=? WHERE id=?",
            (vision_summary, attachment_id),
        )

    # ===== GOOGLE SYNC QUEUE =====

    async def google_sync_enqueue(self, user_id: int, object_type: str, object_id: int,
                                   target: str, action: str, payload: dict) -> int:
        return await self._execute(
            """INSERT INTO google_sync_queue
               (user_id, object_type, object_id, target, action, payload_json, status)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, object_type, object_id, target, action, json.dumps(payload, ensure_ascii=False), "pending"),
        )

    async def google_sync_pending(self, limit: int = 20) -> list:
        return await self._fetchall(
            "SELECT * FROM google_sync_queue WHERE status='pending' ORDER BY created_at LIMIT ?",
            (limit,),
        )

    async def google_sync_mark_done(self, row_id: int):
        await self._execute(
            "UPDATE google_sync_queue SET status='done', updated_at=datetime('now') WHERE id=?",
            (row_id,),
        )

    async def google_sync_mark_error(self, row_id: int, error: str, retry_count: int):
        status = "error" if retry_count >= 3 else "pending"
        await self._execute(
            """UPDATE google_sync_queue SET status=?, error_text=?, retry_count=?,
               updated_at=datetime('now') WHERE id=?""",
            (status, error[:500], retry_count, row_id),
        )

    # ===== GOOGLE LINKS =====

    async def google_link_save(self, user_id: int, object_type: str, object_id: int,
                                google_type: str, url: str,
                                spreadsheet_id: str = None, sheet_name: str = None,
                                row_number: int = None, doc_id: str = None,
                                drive_file_id: str = None):
        await self._execute(
            """INSERT INTO google_links
               (user_id, object_type, object_id, google_type, spreadsheet_id, sheet_name,
                row_number, doc_id, drive_file_id, url, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'))
               ON CONFLICT(user_id, object_type, object_id, google_type)
               DO UPDATE SET url=excluded.url, spreadsheet_id=excluded.spreadsheet_id,
                 sheet_name=excluded.sheet_name, row_number=excluded.row_number,
                 doc_id=excluded.doc_id, drive_file_id=excluded.drive_file_id,
                 updated_at=datetime('now')""",
            (user_id, object_type, object_id, google_type, spreadsheet_id, sheet_name,
             row_number, doc_id, drive_file_id, url),
        )

    async def google_link_get(self, user_id: int, object_type: str,
                               object_id: int = None) -> list:
        if object_id is not None:
            return await self._fetchall(
                "SELECT * FROM google_links WHERE user_id=? AND object_type=? AND object_id=?",
                (user_id, object_type, object_id),
            )
        return await self._fetchall(
            "SELECT * FROM google_links WHERE user_id=? AND object_type=?",
            (user_id, object_type),
        )

    async def google_spreadsheet_get(self, user_id: int) -> str | None:
        """Return the spreadsheet ID for this user (stored in settings)."""
        row = await self._fetchone(
            "SELECT value FROM settings WHERE user_id=? AND key='google_spreadsheet_id'",
            (user_id,),
        )
        return row["value"] if row else None

    async def google_spreadsheet_set(self, user_id: int, spreadsheet_id: str):
        await self._execute(
            """INSERT INTO settings (user_id, key, value) VALUES (?,?,?)
               ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value""",
            (user_id, "google_spreadsheet_id", spreadsheet_id),
        )


db = Database()

