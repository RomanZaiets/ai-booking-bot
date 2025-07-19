from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta
import asyncio

scheduler = AsyncIOScheduler()

def schedule_reminder(bot, chat_id, date_str, time_str, procedure):
    try:
        appointment_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        reminder_1_time = appointment_time - timedelta(days=1)
        if reminder_1_time > datetime.now():
            scheduler.add_job(
                lambda: asyncio.create_task(send_reminder(bot, chat_id, procedure, date_str, time_str)),
                trigger=DateTrigger(run_date=reminder_1_time)
            )

        reminder_2_time = appointment_time - timedelta(hours=2)
        if reminder_2_time > datetime.now():
            scheduler.add_job(
                lambda: asyncio.create_task(send_reminder(bot, chat_id, procedure, date_str, time_str)),
                trigger=DateTrigger(run_date=reminder_2_time)
            )
    except Exception as e:
        print(f"⛔ Error in scheduling reminder: {e}")

async def send_reminder(bot, chat_id, procedure, date, time):
    try:
        await bot.send_message(chat_id, f"⏰ Нагадування: ви записані на {procedure} {date} о {time}.")
    except Exception as e:
        print(f"⚠️ Failed to send reminder: {e}")
