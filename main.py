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

# ==== Локалізація українською для календаря ====
UA_MONTHS = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"
]
UA_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()
USER_NAMES = {}

def get_main_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Розпочати запис"), types.KeyboardButton(text="Відмінити запис")]
        ],
        resize_keyboard=True
    )

def get_procedure_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Стрижка"), types.KeyboardButton(text="Брови")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_time_keyboard(date):
    # Тільки вільні години для цієї дати
    free_slots = get_free_slots(date, GOOGLE_SHEET_ID)
    if not free_slots:
        return None
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=slot)] for slot in free_slots if slot.endswith(":00")],
        resize_keyboard=True,
        one_time_keyboard=True
    )

@router.message(Command('start'))
async def start_handler(message: types.Message):
    # Автоматично записуємо всіх відвідувачів
    save_visitor_to_sheet(message.from_user.id, message.from_user.full_name)
    await message.answer(
        "Вітаю! Щоб зробити бронювання, натисніть кнопку нижче👇",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "Розпочати запис")
async def begin_booking(message: types.Message):
    await message.answer(
        "Будь ласка, введіть ваше ім’я (як до вас звертатись):",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "Відмінити запис")
async def cancel_booking(message: types.Message):
    user_id = message.from_user.id
    removed = False
    for key in list(USER_NAMES.keys()):
        if str(user_id) in str(key):
            USER_NAMES.pop(key)
            removed = True
    await message.answer(
        "Ваш запис було скасовано." if removed else "У вас немає активного запису для скасування.",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text & ~F.text.in_(["Розпочати запис", "Відмінити запис"]))
async def collect_name_and_book(message: types.Message):
    user_id = message.from_user.id
    if user_id not in USER_NAMES:
        USER_NAMES[user_id] = message.text.strip()
        await message.answer(
            f"Шановний {USER_NAMES[user_id]}, оберіть процедуру:",
            reply_markup=get_procedure_keyboard()
        )
        return

    if not USER_NAMES.get(str(user_id) + "_proc"):
        text = message.text.strip().lower()
        if text not in ("стрижка", "брови"):
            await message.answer(
                "Оберіть процедуру кнопкою нижче:",
                reply_markup=get_procedure_keyboard()
            )
            return
        USER_NAMES[str(user_id) + "_proc"] = text
        await message.answer(
            "Оберіть дату через календар:",
            reply_markup=await SimpleCalendar(min_date=dt_date.today()).start_calendar()
        )
        return

    if message.text.endswith(":00"):
        time = message.text
        date = USER_NAMES.get(str(user_id) + "_date")
        proc = USER_NAMES.get(str(user_id) + "_proc")
        free = get_free_slots(date, GOOGLE_SHEET_ID)
        if time not in free:
            suggestions = [t for t in free if t.endswith(":00")]
            if suggestions:
                await message.answer(
                    "На жаль, цей час зайнятий. Ось вільні години цього дня:\n"
                    + ", ".join(suggestions),
                    reply_markup=get_time_keyboard(date)
                )
            else:
                await message.answer("Немає вільних годин на цю дату. Виберіть іншу дату:",
                    reply_markup=await SimpleCalendar(min_date=dt_date.today()).start_calendar()
                )
            return
        # Записуємо у Google Sheets
        save_to_sheet(message, USER_NAMES[user_id], {
            "procedure": proc,
            "date": date,
            "time_range": time
        }, GOOGLE_SHEET_ID)
        await schedule_reminder(bot, message.chat.id, date, time, proc)
        await message.answer(
            f"Дякуємо, {USER_NAMES[user_id]}! Вас записано на {proc} {date} о {time}.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        # Позначаємо користувача як booked у visitor-таблиці (опціонально)
        return

    await message.answer(
        "Натисніть «Розпочати запис» та дотримуйтесь підказок.",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: types.CallbackQuery, callback_data: dict):
    selected, date = await SimpleCalendar(min_date=dt_date.today()).process_selection(callback_query, callback_data)
    if selected:
        user_id = callback_query.from_user.id
        USER_NAMES[str(user_id) + "_date"] = date.strftime("%Y-%m-%d")
        free = get_free_slots(date.strftime("%Y-%m-%d"), GOOGLE_SHEET_ID)
        if not free:
            await bot.send_message(
                user_id,
                "У цей день немає жодного вільного часу. Виберіть іншу дату:",
                reply_markup=await SimpleCalendar(min_date=dt_date.today()).start_calendar()
            )
            return
        await bot.send_message(
            user_id,
            f"Обрано дату: {date.strftime('%d-%m-%Y')}\nОберіть бажаний час:",
            reply_markup=get_time_keyboard(date.strftime("%Y-%m-%d"))
        )

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
