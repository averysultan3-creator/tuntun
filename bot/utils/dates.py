from datetime import date, datetime


def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def tomorrow() -> str:
    from datetime import timedelta
    return (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_date(date_str: str) -> str:
    """'2025-07-15' → '15.07.2025'"""
    if not date_str:
        return ""
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return date_str


def format_datetime(dt_str: str) -> str:
    """'2025-07-15 09:00:00' → '15.07.2025 в 09:00'"""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d.%m.%Y в %H:%M")
    except ValueError:
        return dt_str
