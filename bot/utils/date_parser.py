"""Date range parser for TUNTUN bot.

parse_date_range(text, timezone) -> (date_from: str, date_to: str) | (None, None)

Understands:
  сегодня / вчера / завтра
  эта неделя / за неделю / последние 7 дней
  этот месяц / за месяц / последние 30 дней
  за полгода / последние 6 месяцев
  за год / последние 12 месяцев / последний год
  за 2025 / за 2026                 (calendar year)
  за январь / за апрель / в марте   (current-year month)
  последние N дней/недель/месяцев
"""
import re
from datetime import date, timedelta
from calendar import monthrange

# Month names: ru -> int
_MONTHS_RU = {
    "январь": 1,   "января": 1,
    "февраль": 2,  "февраля": 2,
    "март": 3,     "марта": 3,
    "апрель": 4,   "апреля": 4,
    "май": 5,      "мая": 5,
    "июнь": 6,     "июня": 6,
    "июль": 7,     "июля": 7,
    "август": 8,   "августа": 8,
    "сентябрь": 9, "сентября": 9,
    "октябрь": 10, "октября": 10,
    "ноябрь": 11,  "ноября": 11,
    "декабрь": 12, "декабря": 12,
}


def _fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def parse_date_range(text: str, timezone: str = None) -> tuple:
    """Extract a (date_from, date_to) pair from free-form Russian text.

    Returns (None, None) if no date range pattern is found.
    Both dates are YYYY-MM-DD strings.
    """
    t = text.lower().replace("ё", "е")
    today = date.today()

    # ── exact single days ────────────────────────────────────────────────
    if re.search(r"\bсегодня\b", t):
        return _fmt(today), _fmt(today)
    if re.search(r"\bвчера\b", t):
        d = today - timedelta(days=1)
        return _fmt(d), _fmt(d)
    if re.search(r"\bзавтра\b", t):
        d = today + timedelta(days=1)
        return _fmt(d), _fmt(d)

    # ── named calendar year: за 2025 / за 2026 ───────────────────────────
    m = re.search(r"\b(за|в)\s+(20\d{2})\b", t)
    if m:
        yr = int(m.group(2))
        return f"{yr}-01-01", f"{yr}-12-31"

    # ── named month: за январь / в апреле / за апрель ────────────────────
    for name, idx in _MONTHS_RU.items():
        if name in t:
            yr = today.year
            last_day = monthrange(yr, idx)[1]
            return f"{yr}-{idx:02d}-01", f"{yr}-{idx:02d}-{last_day:02d}"

    # ── last N days/weeks/months: последние 7 дней ───────────────────────
    m = re.search(r"последни[ехй]\s+(\d+)\s*(ден|дн|нед|месяц|месяц)", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if "ден" in unit or "дн" in unit:
            return _fmt(today - timedelta(days=n)), _fmt(today)
        if "нед" in unit:
            return _fmt(today - timedelta(weeks=n)), _fmt(today)
        if "месяц" in unit:
            return _fmt(today - timedelta(days=30 * n)), _fmt(today)

    # ── этот/за неделю ───────────────────────────────────────────────────
    if re.search(r"\b(эта|эту|эту|за|на)\s+недел|за\s+недел|неделю|за\s+7\s+дн", t):
        return _fmt(today - timedelta(days=7)), _fmt(today)
    if re.search(r"\bэтой?\s+недел", t):
        # ISO week: Monday..today
        start = today - timedelta(days=today.weekday())
        return _fmt(start), _fmt(today)

    # ── этот/за месяц ────────────────────────────────────────────────────
    if re.search(r"\b(этот|этого|за|в)\s+месяц|за\s+месяц|за\s+30\s+дн", t):
        return _fmt(today - timedelta(days=30)), _fmt(today)
    if re.search(r"\bэтом\s+месяц", t):
        return _fmt(today.replace(day=1)), _fmt(today)

    # ── полгода ──────────────────────────────────────────────────────────
    if re.search(r"полгода|полу?года|6\s*мес|шест[ьи]\s*месяц", t):
        return _fmt(today - timedelta(days=183)), _fmt(today)

    # ── год ──────────────────────────────────────────────────────────────
    if re.search(r"\bза\s+год\b|последний\s+год|за\s+12\s*мес|последние\s+12", t):
        return _fmt(today - timedelta(days=365)), _fmt(today)

    return None, None
