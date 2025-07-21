import asyncio
import os
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from datetime import date as dt_date

from scheduler import scheduler, schedule_reminder
from utils import save_to_sheet, get_free_slots
from keyboards import get_main_keyboard, get_procedure_keyboard, get_time_keyboard

# Read token and Google Sheet ID from environment
API_TOKEN = os.getenv("API_TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# Ensure the token is set
if not API_TOKEN:
    raise ValueError("❌ API_TOKEN is not set. Add it to your environment variables.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# In-memory storage for user state
auth_data = {}

# /start handler
def reset_user(user_id: int):
    auth_data.pop(user_id, None)

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    user_id = message.from_user.id
    reset_user(user_id)
    await message.answer(
        "Привіт! Натисніть «Розпочати запис», щоб почати.",
        reply_markup=get_main_keyboard()
    )

# Cancel booking
@router.message(F.text == "Відмінити запис")
async def cancel_booking(message: Message):
    user_id = message.from_user.id
    reset_user(user_id)
    await message.answer(
        "Запис скасовано.",
        reply_markup=get_main_keyboard()
    )

# Back button
@router.message(F.text == "⬅️ Назад")
async def go_back(message: Message):
    user_id = message.from_user.id
    user_state = auth_data.get(user_id, {})
    # Remove last step
    if "time" in user_state:
        user_state.pop("time")
        await message.answer("Оберіть час:", reply_markup=get_time_keyboard(user_state.get("date")))
    elif "date" in user_state:
        user_state.pop("date")
        await message.answer("Оберіть дату через календар:", reply_markup=await SimpleCalendar(min_date=dt_date.today()).start_calendar())
    elif "procedure" in user_state:
        user_state.pop("procedure")
        await message.answer("Яку процедуру бажаєте?", reply_markup=get_procedure_keyboard())
    else:
        reset_user(user_id)
        await message.answer(
            "Повернулися до початку.",
            reply_markup=get_main_keyboard()
        )

# Start booking flow
def init_user(user_id: int):
    auth_data[user_id] = {"step": "name"}

@router.message(F.text == "Розпочати запис")
async def start_booking(message: Message):
    user_id = message.from_user.id
    init_user(user_id)
    await message.answer(
        "Будь ласка, введіть ваше ім'я:",
        reply_markup=types.ReplyKeyboardRemove()
    )

# Handle booking dialogue
@router.message(F.text.filter(lambda t: t not in ["⬅️ Назад", "Розпочати запис", "Відмінити запис"]))
async def handle_booking_flow(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    user_state = auth_data.get(user_id)

    # If user not initialized, ask to start
    if not user_state:
        await message.answer(
            "Будь ласка, натисніть «Розпочати запис».", reply_markup=get_main_keyboard()
        )
        return

    # Step: name
    if user_state.get("step") == "name":
        user_state["name"] = text
        user_state["step"] = "procedure"
        await message.answer(
            f"{text}, яку процедуру бажаєте?", reply_markup=get_procedure_keyboard()
        )
        return

    # Step: procedure
    if user_state.get("step") == "procedure":
        if text not in ("Стрижка", "Брови"):
            await message.answer("Оберіть процедуру кнопкою:", reply_markup=get_procedure_keyboard())
            return
        user_state["procedure"] = text
        user_state["step"] = "date"
        await message.answer(
            "Оберіть дату через календар:",
            reply_markup=await SimpleCalendar(min_date=dt_date.today()).start_calendar()
        )
        return

    # Step: date selected via calendar callback
    if user_state.get("step") == "time_selection" or user_state.get("step") == "date":
        # Time selection triggered by calendar callback, ignore raw messages
        await message.answer("Будь ласка, оберіть дату у календарі або час через кнопки.")
        return

    # Step: time as text ends with :00
    if text.endswith(":00") and "date" in user_state:
        date_str = user_state["date"]
        proc = user_state["procedure"]
        slots = get_free_slots(date_str, GOOGLE_SHEET_ID)
        if text not in slots:
            await message.answer(
                "Цей час зайнятий. Виберіть інший:",
                reply_markup=get_time_keyboard(slots)
            )
            return
        # Save to sheet and schedule reminder
        await save_to_sheet(
            message,
            user_state["name"],
            {"procedure": proc, "date": date_str, "time_range": text},
            GOOGLE_SHEET_ID
        )
        await schedule_reminder(bot, message.chat.id, date_str, text, proc)
        await message.answer(
            f"Вас записано на {proc} {date_str} о {text}.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        reset_user(user_id)
        return

    # Fallback
    await message.answer(
        "Будь ласка, натисніть кнопку «Розпочати запис».",
        reply_markup=get_main_keyboard()
    )

# Calendar callback handler
@router.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: types.CallbackQuery, callback_data: dict):
    selected, date_obj = await SimpleCalendar(min_date=dt_date.today()).process_selection(
        callback_query, callback_data
    )
    if selected:
        user_id = callback_query.from_user.id
        user_state = auth_data.get(user_id)
        if not user_state:
            await bot.send_message(user_id, "Будь ласка, почніть запис командою /start.")
            return
        date_str = date_obj.strftime("%Y-%m-%d")
        user_state["date"] = date_str
        user_state["step"] = "time"
        slots = get_free_slots(date_str, GOOGLE_SHEET_ID)
        await bot.send_message(
            user_id,
            f"Дата: {date_obj.strftime('%d-%m-%Y')}. Оберіть час:",
            reply_markup=get_time_keyboard(slots)
        )

async def main():
    scheduler.start()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
