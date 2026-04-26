from bot.db.database import db
from bot.utils.formatters import format_dynamic_records

_SUGGESTED_FIELDS = {
    ("финанс", "деньг", "расход", "трат", "бюджет", "finance", "budget"): [
        "date", "amount", "currency", "category", "payment_method", "comment"
    ],
    ("реклам", "ads", "reklama", "маркет"): [
        "date", "platform", "budget", "spent", "results", "comment"
    ],
    ("здоров", "спорт", "трен", "sport", "health"): [
        "date", "activity", "duration", "calories", "notes"
    ],
    ("еда", "питан", "food", "диет"): [
        "date", "meal", "calories", "protein", "notes"
    ],
    ("учеб", "study", "курс", "образован"): [
        "date", "subject", "topic", "hours", "notes"
    ],
    ("работ", "проект", "task", "work"): [
        "date", "project", "task", "hours", "status", "notes"
    ],
}


def _guess_fields(name: str) -> list[str]:
    name_lower = name.lower()
    for keys, fields in _SUGGESTED_FIELDS.items():
        if any(k in name_lower for k in keys):
            return fields
    return ["date", "notes"]


async def handle_create(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    # Accept both 'name' and 'section_name' (AI may send either)
    name = (params.get("name") or params.get("section_name") or "").strip()
    title = (params.get("title") or params.get("section_title") or name).strip()
    fields = params.get("fields", [])
    # Remove default-only fields ["date", "notes"] that AI adds when user didn't specify
    user_specified_fields = [f for f in fields if f not in ("date", "notes")] if fields else []

    if not name or not title:
        return "❌ Укажи название раздела"

    # Check if exists
    existing = await db.section_find(user_id, name)
    if existing:
        fields_str = ", ".join(existing["fields"])
        return f"📂 Раздел уже существует: {existing['title']} (поля: {fields_str}) #{existing['id']}"

    # If user didn't specify fields — start conversational builder
    if not user_specified_fields:
        suggested = _guess_fields(name)
        suggested_str = ", ".join(suggested)
        return f"__SECTION_BUILDER__:{name}:{title}:{','.join(suggested)}"

    sid = await db.section_create(user_id, name, title, fields)
    fields_str = ", ".join(fields)
    return f"📂 Раздел создан: {title}\nПоля: {fields_str}\n#{sid}\n\nДобавляй записи: «добавь в раздел {title}: ...»"


async def handle_record_add(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    section_name = params.get("section_name", "").strip()
    data = params.get("data", {})

    if not section_name:
        return "❌ Укажи название раздела"

    section = await db.section_find(user_id, section_name)
    if not section:
        # Suggest creating the section
        suggested = _guess_fields(section_name)
        return f"__SECTION_BUILDER__:{section_name.lower()}:{section_name}:{','.join(suggested)}"

    if not data:
        return "❌ Нет данных для записи"

    rid = await db.section_record_add(user_id, section["name"], data)
    data_str = ", ".join(f"{k}: {v}" for k, v in data.items() if v)
    return f"📝 Запись добавлена в «{section['title']}»:\n{data_str}\n#{rid}"


async def handle_query(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    section_name = params.get("section_name", "").strip()

    if not section_name:
        sections = await db.section_list(user_id)
        if not sections:
            return "📂 Динамических разделов нет. Создай: «создай раздел Реклама с полями: расходы, аккаунты»"
        lines = ["📂 Мои разделы:"]
        for s in sections:
            fields_str = ", ".join(s["fields"])
            lines.append(f"  • {s['title']} ({s['name']}): {fields_str}")
        return "\n".join(lines)

    section = await db.section_find(user_id, section_name)
    if not section:
        return f"❌ Раздел «{section_name}» не найден"

    records = await db.section_query(user_id, section["name"])
    return format_dynamic_records(records, section["title"])


async def handle_add_field(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    section_name = params.get("section_name", "").strip()
    field_name = params.get("field_name", "").strip()
    field_type = params.get("field_type", "text")

    if not section_name or not field_name:
        return "❌ Укажи раздел и название нового поля"

    section = await db.section_find(user_id, section_name)
    if not section:
        return f"❌ Раздел «{section_name}» не найден"

    await db.section_add_field(user_id, section["name"], field_name, field_type)
    return f"✅ Поле «{field_name}» добавлено в раздел «{section['title']}»"


async def handle_rename(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    section_name = params.get("section_name", "").strip()
    new_title = params.get("new_title", "").strip()

    if not section_name or not new_title:
        return "❌ Укажи раздел и новое название"

    section = await db.section_find(user_id, section_name)
    if not section:
        return f"❌ Раздел «{section_name}» не найден"

    await db.section_rename(user_id, section["name"], new_title)
    return f"✅ Раздел «{section['title']}» переименован в «{new_title}»"


async def handle_edit(user_id: int, params: dict, ai_response: str, **kwargs) -> str:
    record_id = params.get("record_id")
    section_name = params.get("section_name", "").strip()
    updates = params.get("updates", {})

    if not record_id or not updates:
        return "❌ Укажи ID записи и что изменить"

    await db.record_edit(user_id, record_id, updates)
    return f"✅ Запись #{record_id} обновлена"
