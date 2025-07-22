import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext

from utils import normalize_date, get_free_slots, save_to_sheet, save_visitor_to_sheet
from keyboards import get_main_keyboard, get_procedure_keyboard, get_time_keyboard

# Імпорт таймера нагадувань (підтримує одразу два варіанти назви файлу)
try:
    from scheduler import scheduler, schedule_reminder
except ImportError:
    from sheduler import scheduler, schedule_reminder

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Детальний лог для APScheduler
logging.getLogger('apscheduler').setLevel(logging.DEBUG)

# Змінні середовища
API_TOKEN = os.getenv("API_TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
logger.info(f"API_TOKEN set: {'Yes' if API_TOKEN else 'No'}")
logger.info(f"GOOGLE_SHEET_ID set: {'Yes' if GOOGLE_SHEET_ID else 'No'}")

if not API_TOKEN:
    logger.error("API_TOKEN is not set. Exiting.")
    exit(1)
if not GOOGLE_SHEET_ID:
    logger.warning("GOOGLE_SHEET_ID is not set. Free slots and save_to_sheet will fail.")

# Ініціалізація бота та диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Стани фреймворку FSM для бронювання
class BookingStates(StatesGroup):
    waiting_procedure = State()
    waiting_date = State()
    waiting_time = State()

# Команда /start
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Вітаю! Оберіть дію:", reply_markup=get_main_keyboard())

# Початок запису
@dp.message_handler(lambda m: m.text and m.text.strip().lower().startswith("📝"), state=None)
async def cmd_book(message: types.Message):
    logger.info(f"User {message.from_user.id} initiated booking")
    save_visitor_to_sheet(message.from_user.id, message.from_user.full_name)
    await message.answer("Будь ласка, оберіть процедуру:", reply_markup=get_procedure_keyboard())
    await BookingStates.waiting_procedure.set()

# Вибір процедури
@dp.message_handler(lambda m: m.text and m.text.strip().lower() in ["стрижка", "брови"], state=BookingStates.waiting_procedure)
async def process_procedure(message: types.Message, state: FSMContext):
    await state.update_data(procedure=message.text.strip())
    await message.answer("Введіть дату (YYYY-MM-DD або день тижня, напр. 'понеділок'):")
    await BookingStates.waiting_date.set()

# Вибір дати
@dp.message_handler(state=BookingStates.waiting_date)
async def process_date(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    date = normalize_date(raw)
    if not date:
        await message.reply("Невірний формат дати. Спробуйте ще раз.")
        return
    await state.update_data(date=date)

    slots = get_free_slots(date, GOOGLE_SHEET_ID)
    if not slots:
        await message.reply("Немає вільних слотів на цю дату. Введіть іншу дату:")
        return
    await message.answer("Оберіть час:", reply_markup=get_time_keyboard(slots))
    await BookingStates.waiting_time.set()

# Вибір часу та підтвердження
@dp.message_handler(state=BookingStates.waiting_time)
async def process_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    selected = message.text.strip()
    if selected not in get_free_slots(data['date'], GOOGLE_SHEET_ID):
        await message.reply("Невірний час. Будь ласка, оберіть час з клавіатури.")
        return

    # Збереження бронювання
    save_to_sheet(
        message,
        user_input=f"{data['procedure']} {data['date']} {selected}",
        parsed={**data, "time_range": selected},
        sheet_id=GOOGLE_SHEET_ID
    )
    # Планування нагадувань
    schedule_reminder(bot, message.chat.id, data['date'], selected, data['procedure'])

    await message.answer(
        f"✅ Ваш запис підтверджено:\nПроцедура: {data['procedure']}\nДата: {data['date']}\nЧас: {selected}",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.finish()

if __name__ == '__main__':
    logger.info("Starting scheduler...")
    scheduler.start()
    logger.info("Starting bot polling...")
    executor.start_polling(dp, skip_updates=True)
