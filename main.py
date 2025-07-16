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
    is_slot_available,
    save_to_sheet,
)
from scheduler import schedule_reminder

# ————— Завантажуємо змінні оточення —————
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")
ADMIN_CHAT_ID      = os.getenv("ADMIN_CHAT_ID")  # для повідомлень адміну

# ————— Перевірка конфігурації —————
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment variables")
if not OPENAI_API_KEY:
    logging.warning("OPENAI_API_KEY is not set; AI‑функції не працюватимуть")
if not GOOGLE_SHEET_ID:
    raise ValueError("GOOGLE_SHEET_ID is not set in environment variables")
if not ADMIN_CHAT_ID:
    logging.warning("ADMIN_CHAT_ID is not set; адміністратор не отримає сповіщень")

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
    await message.answer("Напишіть, що саме бажаєте скасувати (процедуру, дату, інтервал або час).")

# ————— Основний хендлер —————
@dp.message_handler()
async def handle_message(message: types.Message):
    user_input = message.text
    await message.answer("🔍 Аналізую ваше повідомлення...")

    # 1) AI‑парсинг intent
    parsed     = await parse_request_with_gpt(user_input, openai)
    proc       = parsed.get("procedure")    # манікюр/педикюр
    raw_date   = parsed.get("date")         # YYYY-MM-DD або день тижня
    time_exact = parsed.get("time")         # HH:MM
    time_range = parsed.get("time_range")   # "ранком"/"після обіду"/"ввечері"

    # 2) Нормалізація дати
    date = normalize_date(raw_date)

    # === Сценарій 1: якщо GPT витягнув конкретний час ===
    if proc and date and time_exact:
        # Перевіряємо вільність слоту
        if not is_slot_available(date, time_exact, GOOGLE_SHEET_ID):
            return await message.answer("❌ Вибачте, цей час вже зайнятий. Спробуйте інший.")
        # Зберігаємо бронювання
        save_to_sheet(message, user_input, parsed, GOOGLE_SHEET_ID)
        await message.answer(f"✅ Вас записано на {proc} {date} о {time_exact}! Очікуйте підтвердження.")
        # Плануємо нагадування
        schedule_reminder(bot, message.chat.id, date, time_exact, proc)
        # Сповіщаємо адміну
        if ADMIN_CHAT_ID:
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"📬 Новий запис:\nКлієнт: {message.from_user.full_name}\nПроцедура: {proc}\nДата: {date}\nЧас: {time_exact}"
            )
        return

    # === Сценарій 2: якщо GPT витягнув лише інтервал часу ===
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
                f"Вільні слоти у {raw_date} ({time_range}): {', '.join(recs)}\n"
                "Щоб забронювати, просто напишіть: напр. «манікюр 2025-07-21 15:30»"
            )
        else:
            return await message.answer(
                f"На {raw_date} {time_range} немає вільних слотів."
            )

    # === Сценарій 3: fallback — AI‑чат ===
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
        await message.answer("❌ Вибачте, сталася помилка при зверненні до AI.")

# ————— Точка входу —————
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
