import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from dotenv import load_dotenv
from utils import normalize_date, get_free_slots
from scheduler import schedule_reminder

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

def get_time_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=f"{h:02d}:00")] for h in range(8, 21)
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

@router.message(Command('start'))
async def start_handler(message: types.Message):
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
    if removed:
        await message.answer("Ваш запис було скасовано. Ви можете створити новий, натиснувши «Розпочати запис».", reply_markup=get_main_keyboard())
    else:
        await message.answer("У вас немає активного запису для скасування.", reply_markup=get_main_keyboard())

@router.message(F.text & ~F.text.in_(["Розпочати запис", "Відмінити запис"]))
async def collect_name_and_book(message: types.Message):
    user_id = message.from_user.id

    # 1. Очікуємо ім'я
    if user_id not in USER_NAMES:
        USER_NAMES[user_id] = message.text.strip()
        await message.answer(
            f"Шановний {USER_NAMES[user_id]}, оберіть процедуру:",
            reply_markup=get_procedure_keyboard()
        )
        return

    # 2. Очікуємо вибір процедури
    if not USER_NAMES.get(str(user_id)+"_proc"):
        text = message.text.strip().lower()
        if text not in ("стрижка", "брови"):
            await message.answer(
                "Оберіть процедуру кнопкою нижче:",
                reply_markup=get_procedure_keyboard()
            )
            return
        USER_NAMES[str(user_id)+"_proc"] = text
        await message.answer(
            "Оберіть дату через календар:",
            reply_markup=await SimpleCalendar().start_calendar()
        )
        return

    # 3. Очікуємо час
    if message.text.endswith(":00"):
        time = message.text
        date = USER_NAMES.get(str(user_id)+"_date")
        proc = USER_NAMES.get(str(user_id)+"_proc")
        free = get_free_slots(date, GOOGLE_SHEET_ID)
        if time not in free:
            suggestions = [t for t in free if t.endswith(":00")]
            if suggestions:
                await message.answer(
                    "На жаль, цей час зайнятий. Ось вільні години цього дня:\n"
                    + ", ".join(suggestions),
                    reply_markup=get_time_keyboard()
                )
            else:
                await message.answer("Немає вільних годин на цю дату. Спробуйте іншу дату.", reply_markup=get_main_keyboard())
            return
        await schedule_reminder(bot, message.chat.id, date, time, proc)
        await message.answer(
            f"Дякуємо, {USER_NAMES[user_id]}! Вас записано на {proc} {date} о {time}.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    # Якщо нічого не підходить — підказка та стартова клавіатура
    await message.answer(
        "Натисніть «Розпочати запис» та дотримуйтесь підказок. Якщо щось пішло не так — скасуйте і спробуйте ще раз.",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: types.CallbackQuery, callback_data: dict):
    selected, date = await SimpleCalendar().process_selection(callback_query, callback_data)
    if selected:
        user_id = callback_query.from_user.id
        USER_NAMES[str(user_id)+"_date"] = date.strftime("%Y-%m-%d")
        await bot.send_message(
            callback_query.from_user.id,
            f"Обрано дату: {date.strftime('%d-%m-%Y')}\nОберіть бажаний час (годинно):",
            reply_markup=get_time_keyboard()
        )

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
