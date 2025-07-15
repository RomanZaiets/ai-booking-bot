from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

scheduler = BackgroundScheduler()
scheduler.start()

def schedule_reminder(bot, chat_id, date_str, time_str, procedure):
    fmt = "%Y-%m-%d %H:%M"
    dt = datetime.strptime(f"{date_str} {time_str}", fmt)

    def reminder():
        bot.send_message(chat_id, f"⏰ Нагадування: у вас запис на '{procedure}' о {time_str} 🕒")

    remind_1 = dt - timedelta(days=1)
    if remind_1 > datetime.now():
        scheduler.add_job(reminder, trigger='date', run_date=remind_1)

    remind_2 = dt - timedelta(hours=2)
    if remind_2 > datetime.now():
        scheduler.add_job(reminder, trigger='date', run_date=remind_2)
