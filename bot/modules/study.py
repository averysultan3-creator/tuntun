from bot.db.database import db
from bot.utils.formatters import format_study_records

_TYPE_LABELS = {"debt": "долг", "absence": "пропуск", "task": "задание", "note": "заметка"}


async def handle_add_subject(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    name = params.get("name", "").strip()
    if not name:
        return "❌ Укажи название предмета"

    short_name = params.get("short_name") or name
    sid = await db.study_add_subject(user_id, name, short_name)
    return f"📚 Предмет добавлен: {name} ({short_name}) #{sid}"


async def handle_add_record(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    subject = params.get("subject", "")
    record_type = params.get("type", "note")
    content = params.get("content", "").strip()
    due_date = params.get("due_date")

    if not content:
        return "❌ Укажи что записать"

    rid = await db.study_add_record(user_id, subject, record_type, content, due_date)

    label = _TYPE_LABELS.get(record_type, record_type)
    subject_str = f" по {subject}" if subject else ""
    due_str = f" (до {due_date})" if due_date else ""
    return f"📝 Записано{subject_str} [{label}]: {content}{due_str} #{rid}"


async def handle_list(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    subject = params.get("subject")
    record_type = params.get("type")

    records = await db.study_list(user_id, subject_name=subject, record_type=record_type)

    title = "Учёба"
    if subject:
        title = f"Учёба — {subject}"
    if record_type:
        type_titles = {"debt": "долги", "absence": "пропуски", "task": "задания", "note": "заметки"}
        title += f" ({type_titles.get(record_type, record_type)})"

    return format_study_records(records, title)
