import asyncio
import logging
import os
from datetime import date as dt_date
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from dotenv import load_dotenv
from utils import normalize_date, get_free_slots, save_visitor_to_sheet, save_to_sheet
from scheduler import schedule_reminder

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()
USER_DATA = {}

def get_main_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="⬅️ Назад")],
            [types.KeyboardButton(text="Розпочати запис"), types.KeyboardButton(text="Відмінити запис")]
        ],
        resize_keyboard=True
    )

def get_procedure_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Стрижка"), types.KeyboardButton(text="Брови")],
            [types.KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_time_keyboard(date):
    free_slots = get_free_slots(date, GOOGLE_SHEET_ID)
    if not free_slots:
        return None
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=slot)] for slot in free_slots if slot.endswith(":00")] + [[types.KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

@router.message(Command('start'))
async def start_handler(message: types.Message):
    save_visitor_to_sheet(message.from_user.id, message.from_user.full_name)
    await message.answer("Вітаю! Щоб зробити бронювання, натисніть кнопку нижче👇", reply_markup=get_main_keyboard())

@router.message(F.text == "⬅️ Назад")
async def back_handler(message: types.Message):
    await start_handler(message)

@router.message(F.text == "Розпочати запис")
async def begin_booking(message: types.Message):
    await message.answer("Будь ласка, введіть ваше ім’я:", reply_markup=get_main_keyboard())

@router.message(F.text == "Відмінити запис")
async def cancel_booking(message: types.Message):
    user_id = message.from_user.id
    removed = any(USER_DATA.pop(k, None) for k in list(USER_DATA.keys()) if str(user_id) in str(k))
    await message.answer("Ваш запис було скасовано." if removed else "У вас немає активного запису.", reply_markup=get_main_keyboard())

@router.message(F.text & ~F.text.in_(["⬅️ Назад", "Розпочати запис", "Відмінити запис"]))
async def collect_flow(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in USER_DATA:
        USER_DATA[user_id] = text
        await message.answer(f"{text}, яку процедуру бажаєте?", reply_markup=get_procedure_keyboard())
        return

    if not USER_DATA.get(f"{user_id}_proc"):
        if text not in ("Стрижка", "Брови"):
            await message.answer("Оберіть процедуру кнопкою:", reply_markup=get_procedure_keyboard())
            return
        USER_DATA[f"{user_id}_proc"] = text
        await message.answer("Оберіть дату через календар:", reply_markup=await SimpleCalendar(min_date=dt_date.today()).start_calendar())
        return

    if text.endswith(":00"):
        date = USER_DATA.get(f"{user_id}_date")
        time = text
        proc = USER_DATA.get(f"{user_id}_proc")
        if time not in get_free_slots(date, GOOGLE_SHEET_ID):
            await message.answer("Цей час зайнятий. Виберіть інший:", reply_markup=get_time_keyboard(date))
            return
        save_to_sheet(message, USER_DATA[user_id], {
            "procedure": proc,
            "date": date,
            "time_range": time
        }, GOOGLE_SHEET_ID)
        await schedule_reminder(bot, message.chat.id, date, time, proc)
        await message.answer(f"Вас записано на {proc} {date} о {time}.", reply_markup=types.ReplyKeyboardRemove())
        return

    await message.answer("Будь ласка, натисніть кнопку «Розпочати запис».", reply_markup=get_main_keyboard())

@router.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: types.CallbackQuery, callback_data: dict):
    selected, date = await SimpleCalendar(min_date=dt_date.today()).process_selection(callback_query, callback_data)
    if selected:
        user_id = callback_query.from_user.id
        USER_DATA[f"{user_id}_date"] = date.strftime("%Y-%m-%d")
        await bot.send_message(user_id, f"Дата: {date.strftime('%d-%m-%Y')}. Оберіть час:", reply_markup=get_time_keyboard(date.strftime("%Y-%m-%d")))

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
