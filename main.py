from aiogram import Bot, Dispatcher, types
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
import os
from dotenv import load_dotenv
from utils import (
    normalize_date,
    get_free_slots,
    filter_slots_by_interval,
)
from scheduler import schedule_reminder

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp  = Dispatcher(bot)

USER_NAMES = {}

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Розпочати запис", "Відмінити запис")
    await message.answer("Вітаю! Щоб зробити бронювання, натисніть кнопку нижче👇", reply_markup=keyboard)

@dp.message_handler(lambda m: m.text == "Розпочати запис")
async def begin_booking(message: types.Message):
    await message.answer("Будь ласка, введіть ваше ім’я (як до вас звертатись):")

@dp.message_handler(lambda m: m.text == "Відмінити запис")
async def cancel_booking(message: types.Message):
    user_id = message.from_user.id
    removed = False
    for key in list(USER_NAMES.keys()):
        if str(user_id) in str(key):
            USER_NAMES.pop(key)
            removed = True
    if removed:
        await message.answer("Ваш запис було скасовано. Ви можете створити новий, натиснувши «Розпочати запис».")
    else:
        await message.answer("У вас немає активного запису для скасування.")

@dp.message_handler(lambda m: m.text not in ("Розпочати запис", "Відмінити запис"))
async def collect_name_and_book(message: types.Message):
    user_id = message.from_user.id
    if user_id not in USER_NAMES:
        USER_NAMES[user_id] = message.text.strip()
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("Стрижка", "Брови")
        await message.answer(f"Шановний {USER_NAMES[user_id]}, оберіть процедуру:", reply_markup=kb)
        return

    text = message.text.strip().lower()
    if text in ("стрижка", "брови"):
        proc = text
        USER_NAMES[user_id+"_proc"] = proc
        # ВИКЛИК КАЛЕНДАРЯ
        await message.answer("Оберіть дату через календар:", reply_markup=await SimpleCalendar().start_calendar())
        return

    # інша логіка для часу — нижче, її не чіпаємо

    if message.text.endswith(":00"):
        time = message.text
        date = USER_NAMES.get(user_id+"_date")
        proc = USER_NAMES.get(user_id+"_proc")
        free = get_free_slots(date, GOOGLE_SHEET_ID)
        if time not in free:
            suggestions = [t for t in free if t.endswith(":00")]
            if suggestions:
                await message.answer(
                    "На жаль, цей час зайнятий. Ось вільні години цього дня:\n"
                    + ", ".join(suggestions)
                )
            else:
                await message.answer("Немає вільних годин на цю дату. Спробуйте іншу дату.")
            return
        schedule_reminder(bot, message.chat.id, date, time, proc)
        await message.answer(
            f"Дякуємо, {USER_NAMES[user_id]}! Вас записано на {proc} {date} о {time}.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    await message.answer("Натисніть «Розпочати запис», щоб забронювати процедуру.")

@dp.callback_query_handler(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: types.CallbackQuery, callback_data: dict):
    selected, date = await SimpleCalendar().process_selection(callback_query, callback_data)
    if selected:
        user_id = callback_query.from_user.id
        USER_NAMES[user_id+"_date"] = date.strftime("%Y-%m-%d")
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for h in range(8, 21):
            kb.add(f"{h:02d}:00")
        await bot.send_message(
            callback_query.from_user.id,
            f"Обрано дату: {date.strftime('%d-%m-%Y')}\nОберіть бажаний час (годинно):",
            reply_markup=kb
        )

if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
