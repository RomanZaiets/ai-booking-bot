from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta

scheduler = AsyncIOScheduler()
scheduler.start()

# 🔔 Створює нагадування для користувача
def schedule_reminder(bot, chat_id, date_str, time_str, procedure):
    try:
        appointment_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        # За день до
        reminder_1_time = appointment_time - timedelta(days=1)
        if reminder_1_time > datetime.now():
            scheduler.add_job(
                send_reminder,
                trigger=DateTrigger(run_date=reminder_1_time),
                args=[bot, chat_id, procedure, date_str, time_str]
            )

        # За 2 години до
        reminder_2_time = appointment_time - timedelta(hours=2)
        if reminder_2_time > datetime.now():
            scheduler.add_job(
                send_reminder,
                trigger=DateTrigger(run_date=reminder_2_time),
                args=[bot, chat_id, procedure, date_str, time_str]
            )
    except Exception as e:
        print(f"⛔ Error in scheduling reminder: {e}")

# ✅ Відправка нагадування
async def send_reminder(bot, chat_id, procedure, date, time):
    text = f"⏰ Нагадування: ви записані на {procedure} {date} о {time}."
    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        print(f"⚠️ Failed to send reminder: {e}")