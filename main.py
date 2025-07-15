import logging
from aiogram import Bot, Dispatcher, executor, types
import openai
from utils import parse_request_with_gpt, is_slot_available, save_to_sheet, remove_user_booking, get_free_slots
from scheduler import schedule_reminder
import os

API_TOKEN = '8132057865:AAGdiUerADRj9vVNP75nDmsou7269IrB0QM'
OPENAI_API_KEY = 'sk-proj-hFgbIwg0g9lqEsMIw5vVFC-3tSAy4duLLJBnRmeQEHGBI-NGNRxPG7Em6a_Ibwg27hz90YjL4BT3BlbkFJlQmof2rCc84k9Cgfran0mlg1wsOnKBnI9aZAW_YQ52FI-3v63fgTrxBkG7u3q3_g1aQpLztn8AY'
ADMIN_CHAT_ID = '5334530615'
GOOGLE_SHEET_ID = '1Oo_pI-c6qVorAsbPhnG4hEN3R4tjMUk0EJxfcMNKdJ4'
SERVICE_ACCOUNT_FILE = 'alonaandjana-salon-e52156e552b4.json'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
openai.api_key = OPENAI_API_KEY

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer("Привіт! Напишіть, на яку процедуру бажаєте записатись і коли 💅")

@dp.message_handler(commands=['вільно'])
async def free_slots_handler(message: types.Message):
    await message.answer("🗓 Введіть дату у форматі РРРР-ММ-ДД (наприклад, 2025-07-12):")

@dp.message_handler(lambda message: message.text.startswith("2025-"))
async def handle_free_slots(message: types.Message):
    date = message.text.strip()
    free_times = get_free_slots(date, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_FILE)
    if free_times:
        await message.answer(f"🟢 Вільні години на {date}:" + "\n".join(free_times))
    else:
        await message.answer(f"🔴 На {date} немає вільних годин або невірний формат.")

@dp.callback_query_handler(lambda c: c.data == 'cancel_booking')
async def cancel_booking(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    removed = remove_user_booking(user_id, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_FILE)
    if removed:
        await bot.send_message(user_id, "❌ Ваш запис було скасовано.")
    else:
        await bot.send_message(user_id, "⚠️ Запис не знайдено або вже скасовано.")

@dp.message_handler()
async def handle_message(message: types.Message):
    user_input = message.text
    await message.answer("🔍 Аналізую ваше повідомлення...")

    parsed = await parse_request_with_gpt(user_input, openai)
    await message.answer(f"🧠 Я зрозумів:{parsed}")

    proc, date, time = parsed.get("procedure"), parsed.get("date"), parsed.get("time")
    if not (proc and date and time):
        await message.answer("⚠️ Не вдалося точно визначити процедуру, дату або час.")
        return

    available = is_slot_available(date, time, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_FILE)
    if not available:
        await message.answer("❌ Цей слот уже зайнятий. Спробуйте інший час.")
        return

    save_to_sheet(message, user_input, parsed, GOOGLE_SHEET_ID, SERVICE_ACCOUNT_FILE)
    await message.answer("✅ Вас записано! Очікуйте підтвердження.", reply_markup=types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("❌ Скасувати запис", callback_data="cancel_booking")
    ))

    schedule_reminder(bot, message.chat.id, date, time, proc)
    await bot.send_message(ADMIN_CHAT_ID, f"📬 Новий запис від {message.from_user.full_name}:{parsed}")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
