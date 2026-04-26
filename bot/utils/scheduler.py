import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

import config
from bot.db.database import db

_scheduler: AsyncIOScheduler | None = None
_bot = None


async def _send_reminder(user_id: int, text: str, reminder_id: int):
    if not _bot:
        return
    try:
        from bot.modules.reminders import reminder_keyboard
        await _bot.send_message(
            user_id,
            f"⏰ *Напоминание:* {text}",
            parse_mode="Markdown",
            reply_markup=reminder_keyboard(reminder_id),
        )
    except Exception as e:
        logging.error(f"Failed to send reminder #{reminder_id}: {e}")


async def setup_scheduler(bot) -> AsyncIOScheduler:
    global _scheduler, _bot
    _bot = bot

    tz = pytz.timezone(config.TIMEZONE)
    _scheduler = AsyncIOScheduler(timezone=tz)
    _scheduler.start()

    reminders = await db.reminder_get_all_active()
    now = datetime.now(tz)
    restored = 0

    for r in reminders:
        try:
            if r.get("recurring") and r.get("interval_minutes"):
                _scheduler.add_job(
                    _send_reminder,
                    IntervalTrigger(minutes=int(r["interval_minutes"]), timezone=tz),
                    args=[r["user_id"], r["text"], r["id"]],
                    id=f"reminder_{r['id']}",
                    replace_existing=True,
                )
                restored += 1
            else:
                remind_at = datetime.fromisoformat(r["remind_at"])
                if remind_at.tzinfo is None:
                    remind_at = tz.localize(remind_at)
                if remind_at > now:
                    _scheduler.add_job(
                        _send_reminder,
                        DateTrigger(run_date=remind_at, timezone=tz),
                        args=[r["user_id"], r["text"], r["id"]],
                        id=f"reminder_{r['id']}",
                        replace_existing=True,
                    )
                    restored += 1
        except Exception as e:
            logging.error(f"Failed to reschedule reminder #{r['id']}: {e}")

    logging.info(f"Scheduler started, restored {restored}/{len(reminders)} reminder(s)")
    return _scheduler


def add_reminder_job(reminder_id: int, user_id: int, text: str,
                     remind_at_str: str, recurring: bool = False,
                     interval_minutes: int = None) -> str:
    if not _scheduler:
        logging.warning(f"Scheduler not initialized — reminder #{reminder_id} saved to DB only")
        return f"reminder_{reminder_id}"
    tz = pytz.timezone(config.TIMEZONE)
    job_id = f"reminder_{reminder_id}"

    if recurring and interval_minutes:
        _scheduler.add_job(
            _send_reminder,
            IntervalTrigger(minutes=interval_minutes, timezone=tz),
            args=[user_id, text, reminder_id],
            id=job_id,
            replace_existing=True,
        )
    else:
        remind_at = datetime.fromisoformat(remind_at_str)
        if remind_at.tzinfo is None:
            remind_at = tz.localize(remind_at)
        _scheduler.add_job(
            _send_reminder,
            DateTrigger(run_date=remind_at, timezone=tz),
            args=[user_id, text, reminder_id],
            id=job_id,
            replace_existing=True,
        )
    return job_id


def cancel_reminder_job(reminder_id: int):
    if _scheduler:
        try:
            _scheduler.remove_job(f"reminder_{reminder_id}")
        except Exception:
            pass
