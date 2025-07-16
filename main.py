import logging
import os
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
import openai
from dotenv import load_dotenv
from utils import write_credentials_to_file, save_to_sheet, get_free_slots, normalize_date
from scheduler import schedule_reminder

# --- Завантаження конфігурації ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
GOOGLE_SHEET_ID    = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set")

# --- Логування ---
logging.basicConfig(level=logging.INFO)
openai.api_key = OPENAI_API_KEY

# --- Ініціалізація ---
storage = MemoryStorage()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher(bot, storage=storage)

# --- Стани FSM ---
class Booking(StatesGroup):
    NAME      = State()
    PROCEDURE= State()
    DATE      = State()
    TIME      = State()

# --- Кнопки ---
main_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("Розпочати запис")
main_kb.add("Повернутися назад")

procedures_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
procedures_kb.add("Стрижка", "Брови")
procedures_kb.add("Повернутися назад")

# --- Привітання залежно від часу доби ---
def time_greeting():
    h = datetime.datetime.now().hour
    if 6 <= h < 12:
        return "Доброго ранку"
    if 12 <= h < 17:
        return "Доброго дня"
    if 17 <= h < 21:
        return "Доброго вечора"
    return "Доброї ночі"

# --- Хендлер старту ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Ласкаво просимо!", reply_markup=main_kb)

# --- Розпочати запис ---
@dp.message_handler(lambda m: m.text == "Розпочати запис")
async def begin_booking(message: types.Message):
    greeting = time_greeting()
    await message.answer(f"{greeting}! Як я можу до Вас звертатися?", reply_markup=types.ReplyKeyboardRemove())
    await Booking.NAME.set()

# --- Повернутися назад ---
@dp.message_handler(lambda m: m.text == "Повернутися назад", state='*')
async def go_back(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Головне меню", reply_markup=main_kb)

# --- Отримання імені ---
@dp.message_handler(state=Booking.NAME)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(f"Шановний {message.text}, оберіть процедуру:", reply_markup=procedures_kb)
    await Booking.PROCEDURE.set()

# --- Обробка процедури ---
@dp.message_handler(state=Booking.PROCEDURE)
async def process_proc(message: types.Message, state: FSMContext):
    await state.update_data(proc=message.text)
    await message.answer("Введіть дату у форматі DD-MM-YYYY або день тижня:", reply_markup=main_kb)
    await Booking.DATE.set()

# --- Обробка дати ---
@dp.message_handler(state=Booking.DATE)
async def process_date(message: types.Message, state: FSMContext):
    raw = message.text
    date = normalize_date(raw)
    if not date:
        return await message.answer("Невірний формат дати. Спробуйте ще раз.")
    await state.update_data(date=date, raw_date=raw)
    # Отримуємо вільні слоти
    write_credentials_to_file(GOOGLE_CREDENTIALS)
    free = get_free_slots(date, GOOGLE_SHEET_ID)
    if not free:
        return await message.answer("Немає вільних слотів на цю дату. Введіть іншу дату:")
    # Формуємо кнопки годин
    kb = types.InlineKeyboardMarkup(row_width=4)
    for hour in range(8, 21):
        t = f"{hour:02d}:00"
        if t in free:
            kb.insert(types.InlineKeyboardButton(text=t, callback_data=f"time:{t}"))
        else:
            kb.insert(types.InlineKeyboardButton(text=f"❌{t}", callback_data="busy"))
    await message.answer("Оберіть час (ціла година):", reply_markup=kb)
    await Booking.TIME.set()

# --- Обробка часу ---
@dp.callback_query_handler(lambda c: c.data and c.data.startswith('time:'), state=Booking.TIME)
async def process_time(cb: types.CallbackQuery, state: FSMContext):
    t = cb.data.split(':',1)[1]
    data = await state.get_data()
    # Зберігаємо в Google Sheet
    write_credentials_to_file(GOOGLE_CREDENTIALS)
    save_to_sheet(cb.message, user_input=f"{data['proc']} {data['raw_date']} {t}", parsed={'procedure':data['proc'],'date':data['date'],'time_range':t}, sheet_id=GOOGLE_SHEET_ID, credentials_env_var=GOOGLE_CREDENTIALS)
    # Плануємо нагадування
    schedule_reminder(bot, cb.from_user.id, data['date'], t, data['proc'])
    await cb.message.edit_reply_markup()  # прибираємо кнопки
    await cb.message.answer(f"Дякуємо, {data['name']}! Ви записані на {data['proc']} {data['date']} о {t}.")
    await state.finish()

# --- Якщо обрано зайнятий ---
@dp.callback_query_handler(lambda c: c.data=='busy', state=Booking.TIME)
async def handle_busy(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer("Цей час зайнятий, оберіть інший.")

# --- Запуск ---
if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
