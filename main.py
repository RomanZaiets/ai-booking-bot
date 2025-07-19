import asyncio
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from datetime import date as dt_date

from scheduler import scheduler, schedule_reminder
from sheets import save_to_sheet, get_free_slots
from keyboards import get_main_keyboard, get_procedure_keyboard, get_time_keyboard

API_TOKEN = "YOUR_BOT_TOKEN"  # 🔁 Заміни на свій токен
GOOGLE_SHEET_ID = "YOUR_GOOGLE_SHEET_ID"  # 🔁 Заміни на свій ID

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

USER_DATA = {}

# 📥 Обробка основних повідомлень
@router.message(F.text.filter(lambda text: text not in ["⬅️ Назад", "Розпочати запис", "Відмінити запис"]))
async def handle_booking_flow(message: Message):
    user_id = message.from_user.id
    text = message.text

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

# 📅 Обробка календаря
@router.callback_query(SimpleCalendarCallback.filter())
async def process_calendar(callback_query: types.CallbackQuery, callback_data: dict):
    selected, date = await SimpleCalendar(min_date=dt_date.today()).process_selection(callback_query, callback_data)
    if selected:
        user_id = callback_query.from_user.id
        USER_DATA[f"{user_id}_date"] = date.strftime("%Y-%m-%d")
        await bot.send_message(user_id, f"Дата: {date.strftime('%d-%m-%Y')}. Оберіть час:", reply_markup=get_time_keyboard(date.strftime("%Y-%m-%d")))

# 🔁 Основний запуск
async def main():
    scheduler.start()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
