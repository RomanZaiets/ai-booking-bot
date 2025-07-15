import logging
import json
import os
import threading
import openai
import datetime
import gspread
from aiohttp import web
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

# Завантажити змінні оточення
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SERVICE_ACCOUNT_FILE = "credentials.json"

# Перевірка наявності токена
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")

logging.basicConfig(level=logging.INFO)
openai.api_key = OPENAI_API_KEY
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)

# HTTP endpoint для healthcheck
async def health(request):
    return web.Response(text="OK")

# Запуск мінімального веб-сервера для Railway як Web service
def start_health_server():
    app = web.Application()
    app.add_routes([web.get('/', health)])
    port = int(os.environ.get('PORT', 8000))
    web.run_app(app, port=port, handle_signals=False)

# Видалення webhook при старті
async def on_startup(dp):
    await bot.delete_webhook(drop_pending_updates=True)

# Мапа часових інтервалів
TIME_INTERVALS = {
    "ранком":      ("08:00", "12:00"),
    "після обіду": ("13:00", "17:00"),
    "ввечері":     ("17:00", "20:00")
}

# /start
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Напишіть, на яку процедуру бажаєте записатись і коли 💅")

# /cancel
@dp.message_handler(commands=['cancel'])
async def cancel_handler(message: types.Message):
    await message.answer("Напишіть, що саме бажаєте скасувати (процедуру, дату, інтервал).")

# Основний хендлер: smart бронювання + fallback
@dp.message_handler()
async def handle_message(message: types.Message):
    user_input = message.text
    await message.answer("🔍 Аналізую ваше повідомлення...")

    # 1) Використовуємо AI для парсингу intent
    parsed = await parse_request_with_gpt(user_input, openai)
    proc       = parsed.get("procedure")
    raw_date   = parsed.get("date")       # e.g. "понеділок" або "2025-07-21"
    time_range = parsed.get("time_range")  # e.g. "після обіду"

    # 2) Нормалізуємо дату
    date = normalize_date(raw_date)

    # 3) Якщо знайдено процедуру, дату та інтервал часу
    if proc and date and time_range:
        # 4) Визначаємо інтервал
        start, end = TIME_INTERVALS.get(time_range, (None, None))
        if not start:
            return await message.answer(
                "Не зрозумів часовий інтервал. Використовуйте 'ранком', 'після обіду' або 'ввечері'."
            )
        # 5) Повертаємо вільні слоти
        free_slots = get_free_slots(date, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_FILE)
        recommendations = filter_slots_by_interval(free_slots, start, end)
        if recommendations:
            return await message.answer(
                f"Вільні слоти у {raw_date} ({time_range}): {', '.join(recommendations)}"
            )
        else:
            return await message.answer(
                f"На {raw_date} {time_range} немає вільних слотів."
            )

    # 6) Якщо не booking intent — fallback як AI-чат
    await message.answer("🤖 Дозволено AI відповісти на ваше питання...")
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_input}],
            timeout=15
        )
        await message.answer(resp.choices[0].message.content)
    except Exception as e:
        logging.error("Fallback AI error", exc_info=e)
        await message.answer("Вибачте, помилка при зверненні до AI.")

if __name__ == '__main__':
    # Запускаємо health сервер у фоні
    threading.Thread(target=start_health_server, daemon=True).start()
    # Long polling Telegram з on_startup
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
