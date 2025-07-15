import logging
from aiogram import Bot, Dispatcher, types
import openai
import os
from dotenv import load_dotenv
from utils import parse_request_with_gpt, is_slot_available, save_to_sheet
from scheduler import schedule_reminder
from aiohttp import web
import threading

# Завантажити змінні оточення
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SERVICE_ACCOUNT_FILE = "credentials.json"

# Перевірка наявності токена
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

# HTTP endpoint для healthcheck
async def health(request):
    return web.Response(text="OK")

# Запуск мінімального веб-сервера для Railway як Web service
def start_health_server():
    app = web.Application()
    app.add_routes([web.get('/', health)])
    port = int(os.environ.get('PORT', 8000))
    web.run_app(app, port=port)

# Хендлери Telegram
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Напишіть, на яку процедуру бажаєте записатись і коли 💅")

@dp.message_handler(commands=['cancel'])
async def cancel_handler(message: types.Message):
    await message.answer("Напишіть, що саме бажаєте скасувати (процедуру, дату, час).")

@dp.message_handler()
async def handle_message(message: types.Message):
    user_input = message.text
    await message.answer("🔍 Аналізую ваше повідомлення...")

    parsed = await parse_request_with_gpt(user_input, openai)
    await message.answer(f"🧠 Я зрозумів:\n{parsed}")

    proc, date, time = parsed.get("procedure"), parsed.get("date"), parsed.get("time")
    if not (proc and date and time):
        await message.answer("⚠️ Не вдалося точно визначити процедуру, дату або час.")
        return

    available = is_slot_available(date, time, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_FILE)
    if not available:
        await message.answer("❌ Цей слот уже зайнятий. Спробуйте інший час.")
        return

    save_to_sheet(message, user_input, parsed, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_FILE)
    await message.answer("✅ Вас записано! Очікуйте підтвердження.")

    schedule_reminder(bot, message.chat.id, date, time, proc)
    await bot.send_message(ADMIN_CHAT_ID, f"📬 Новий запис від {message.from_user.full_name}:\n{parsed}")

if __name__ == '__main__':
    # Запускаємо health server у окремому потоці
    threading.Thread(target=start_health_server, daemon=True).start()

    # Починаємо long polling Telegram
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
