import logging
import json
import os
import threading
import datetime
import openai
import gspread
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TerminatedByOtherGetUpdates
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

# Конфігурація з environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID       = os.getenv("ADMIN_CHAT_ID")
GOOGLE_SHEET_ID     = os.getenv("GOOGLE_SHEET_ID")

# Перевірка налаштувань
logging.basicConfig(level=logging.INFO)
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    logging.warning("OPENAI_API_KEY is not set; AI features will fail.")

# Логування OpenAI API Key (для перевірки)
logging.info(f"🚀 OPENAI_API_KEY = {OPENAI_API_KEY}")

# Ініціалізація клієнтів
openai.api_key = OPENAI_API_KEY
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)

# Healthcheck endpoint
async def health(request):
    return web.Response(text="OK")

# Запуск невеликого веб-сервера для Railway
def start_health_server():
    app = web.Application()
    app.add_routes([web.get('/', health)])
    port = int(os.getenv('PORT', 8000))
    web.run_app(app, port=port, handle_signals=False)

# Видалити webhook при старті polling
async def on_startup(dp):
    await bot.delete_webhook(drop_pending_updates=True)

# Інтервали часу бронювання
TIME_INTERVALS = {
    "ранком":      ("08:00", "12:00"),
    "після обіду": ("13:00", "17:00"),
    "ввечері":     ("17:00", "20:00")
}

# Команда /start
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Напишіть, на яку процедуру бажаєте записатись і коли 💅")

# Команда /cancel
@dp.message_handler(commands=['cancel'])
async def cancel_handler(message: types.Message):
    await message.answer("Напишіть, що саме бажаєте скасувати (процедуру, дату, інтервал).")

# Основний хендлер: smart бронювання + fallback AI чат
@dp.message_handler()
async def handle_message(message: types.Message):
    user_input = message.text
    await message.answer("🔍 Аналізую ваше повідомлення...")

    # AI парсинг запиту
    parsed     = await parse_request_with_gpt(user_input, openai)
    proc       = parsed.get("procedure")
    raw_date   = parsed.get("date")
    time_range = parsed.get("time_range")

    # Нормалізація дати до YYYY-MM-DD
    date = normalize_date(raw_date)

    # Smart бронювання
    if proc and date and time_range:
        start, end = TIME_INTERVALS.get(time_range, (None, None))
        if not start:
            return await message.answer(
                "Не розумію інтервал; скажіть 'ранком', 'після обіду' або 'ввечері'."
            )
        free_slots = get_free_slots(date, GOOGLE_SHEET_ID, os.getenv("GOOGLE_CREDENTIALS"))
        recs = filter_slots_by_interval(free_slots, start, end)
        if recs:
            return await message.answer(f"Вільні слоти у {raw_date} ({time_range}): {', '.join(recs)}")
        else:
            return await message.answer(f"На {raw_date} {time_range} немає вільних слотів.")

    # Fallback: AI чат
    await message.answer("🤖 Надаю відповідь AI...")
    try:
        resp = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": user_input}],
            timeout=15
        )
        await message.answer(resp.choices[0].message.content)
    except Exception as e:
        logging.error("Fallback AI error", exc_info=e)
        await message.answer("Вибачте, помилка при зверненні до AI.")

# Старт бота
if __name__ == '__main__':
    # Запустити Health сервер
    threading.Thread(target=start_health_server, daemon=True).start()
    # Long polling з автоматичним рестартом при конфлікті
    from aiogram import executor
    while True:
        try:
            executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
            break
        except TerminatedByOtherGetUpdates:
            logging.warning("Polling terminated by other getUpdates, restarting...")
            continue
