import logging
import os
import openai
from aiogram import Bot, Dispatcher, types
from dotenv import load_dotenv
from utils import (
    parse_request_with_gpt,
    normalize_date,
    get_free_slots,
    filter_slots_by_interval,
)
from scheduler import schedule_reminder

# ————— Завантажуємо змінні оточення —————
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")

# ————— Перевірка конфігурації —————
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    logging.warning("OPENAI_API_KEY is not set; AI‑функції не працюватимуть")

# ————— Ініціалізація клієнтів —————
openai.api_key = OPENAI_API_KEY
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp  = Dispatcher(bot)

# ————— Мапа часових інтервалів —————
TIME_INTERVALS = {
    "ранком":      ("08:00", "12:00"),
    "після обіду": ("13:00", "17:00"),
    "ввечері":     ("17:00", "20:00")
}

# ————— Команда /start —————
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Напишіть, на яку процедуру бажаєте записатись і коли 💅")

# ————— Команда /cancel —————
@dp.message_handler(commands=['cancel'])
async def cancel_handler(message: types.Message):
    await message.answer("Напишіть, що саме бажаєте скасувати (процедуру, дату, інтервал).")

# ————— Основний хендлер —————
@dp.message_handler()
async def handle_message(message: types.Message):
    user_input = message.text
    await message.answer("🔍 Аналізую ваше повідомлення...")

    # 1) AI‑парсинг intent
    parsed     = await parse_request_with_gpt(user_input, openai)
    proc       = parsed.get("procedure")
    raw_date   = parsed.get("date")
    time_range = parsed.get("time_range")

    # 2) Нормалізація дати до YYYY‑MM‑DD
    date = normalize_date(raw_date)

    # 3) Smart‑бронювання
    if proc and date and time_range:
        start, end = TIME_INTERVALS.get(time_range, (None, None))
        if not start:
            return await message.answer(
                "Не розумію інтервал; скажіть 'ранком', 'після обіду' або 'ввечері'."
            )
        free_slots = get_free_slots(date, GOOGLE_SHEET_ID)
        recs = filter_slots_by_interval(free_slots, start, end)
        if recs:
            return await message.answer(
                f"Вільні слоти у {raw_date} ({time_range}): {', '.join(recs)}"
            )
        else:
            return await message.answer(
                f"На {raw_date} {time_range} немає вільних слотів."
            )

    # 4) Fallback — AI‑чат
    await message.answer("🤖 Надаю відповідь AI...")
    try:
        resp = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_input}],
            timeout=15
        )
        await message.answer(resp.choices[0].message.content)
    except Exception as e:
        logging.error("OpenAI API error", exc_info=e)
        await message.answer("❌ Вибачте, помилка при зверненні до AI.")

# ————— Точка входу —————
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
