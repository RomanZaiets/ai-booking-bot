from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta

scheduler = AsyncIOScheduler()
scheduler.start()

def schedule_reminder(bot, chat_id, date_str, time_str, procedure):
    try:
        appointment_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        for delta in [timedelta(days=1), timedelta(hours=2)]:
            reminder_time = appointment_time - delta
            if reminder_time > datetime.now():
                scheduler.add_job(
                    send_reminder,
                    trigger=DateTrigger(run_date=reminder_time),
                    args=[bot, chat_id, procedure, date_str, time_str]
                )
    except Exception as e:
        print(f"⛔ Error scheduling reminder: {e}")

async def send_reminder(bot, chat_id, procedure, date, time):
    try:
        await bot.send_message(chat_id, f"⏰ Нагадування: ви записані на {procedure} {date} о {time}.")
    except Exception as e:
        print(f"⚠️ Failed to send reminder: {e}")
