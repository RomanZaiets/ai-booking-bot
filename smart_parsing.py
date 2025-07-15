import logging
import json
import datetime
import os
import openai
from aiogram import Bot, Dispatcher, types
from dotenv import load_dotenv
from utils import (
    parse_request_with_gpt, 
    is_slot_available, 
    save_to_sheet, 
    get_free_slots, 
    filter_slots_by_interval, 
    normalize_date
)
from scheduler import schedule_reminder

# Завантажуємо конфіг
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEET_ID     = os.getenv("GOOGLE_SHEET_ID")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp  = Dispatcher(bot)

# Мапа часових інтервалів
TIME_INTERVALS = {
    "ранком":      ("08:00", "12:00"),
    "після обіду": ("13:00", "17:00"),
    "ввечері":     ("17:00", "20:00")
}

@dp.message_handler()
async def handle_message(message: types.Message):
    user_input = message.text
    await message.answer("🔍 Аналізую ваше повідомлення...")

    # 1) AI‑парсинг
    parsed     = await parse_request_with_gpt(user_input, openai)
    proc       = parsed.get("procedure")
    raw_date   = parsed.get("date")        # напр. "понеділок"
    time_range = parsed.get("time_range")  # напр. "після обіду"

    # 2) Нормалізуємо дату (з дня тижня у YYYY-MM-DD)
    date = normalize_date(raw_date)

    # 3) Якщо є інтерес до бронювання
    if proc and date and time_range:
        start, end = TIME_INTERVALS.get(time_range, (None, None))
        if not start:
            return await message.answer(
                "Не зрозумів інтервал. Скажіть «ранком», «після обіду» або «ввечері»."
            )

        # 4) Отримати вільні слоти
        free_slots = get_free_slots(date, GOOGLE_SHEET_ID)

        # 5) Відфільтрувати й запропонувати
        recommendations = [
            t for t in free_slots
            if start <= t <= end
        ]
        if recommendations:
            await message.answer(
                f"Вільні слоти у {raw_date} ({time_range}): {', '.join(recommendations)}"
            )
        else:
            await message.answer(
                f"На {raw_date} {time_range} наразі немає вільних слотів."
            )
        return

    # 6) Інакше — fallback як AI‑чат
    await message.answer("🤖 Надаю відповідь AI...")
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": user_input}]
    )
    await message.answer(response.choices[0].message.content)

if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
