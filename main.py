import logging
import os
from aiogram import Bot, Dispatcher, types
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

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp  = Dispatcher(bot)

TIME_INTERVALS = {
    "ранком":      ("08:00", "12:00"),
    "після обіду": ("13:00", "17:00"),
    "ввечері":     ("17:00", "20:00")
}

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    # привітання й меню «Розпочати запис»
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Розпочати запис")
    await message.answer("Вітаю! Щоб зробити бронювання, натисніть кнопку нижче👇", reply_markup=keyboard)

@dp.message_handler(lambda m: m.text == "Розпочати запис")
async def begin_booking(message: types.Message):
    # тут можна запросити ім’я або відразу перейти до вибору процедури
    await message.answer("Будь ласка, введіть ваше ім’я (як до вас звертатись):")

# збережемо ім’я в state (приклад без FSM — просто в глобальну змінну)
USER_NAMES = {}

@dp.message_handler(lambda m: m.text not in ("Розпочати запис",))
async def collect_name_and_book(message: types.Message):
    user_id = message.from_user.id
    # якщо ще немає імені — вважаємо, що це ім’я
    if user_id not in USER_NAMES:
        USER_NAMES[user_id] = message.text.strip()
        # переходимо до вибору процедури кнопками
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.add("Стрижка", "Брови")
        await message.answer(f"Шановний {USER_NAMES[user_id]}, оберіть процедуру:", reply_markup=kb)
        return

    # якщо ім’я вже є, тлумачимо текст як вибір процедури або дати/часу...
    # Наприклад:
    text = message.text.strip().lower()
    if text in ("стрижка", "брови"):
        # зберігаємо процедуру
        proc = text
        # запрошуємо дату у форматі DD-MM-YYYY або день тижня
        await message.answer(f"Шановний {USER_NAMES[user_id]}, введіть дату (DD-MM-YYYY або день тижня):")
        # зберігаємо proc в якомусь тимчасовому сховищі (аналогічно USER_NAMES)
        USER_NAMES[user_id+"_proc"] = proc
        return

    # якщо прийшов текст у форматі дати
    # тут повинна бути перевірка формату дати:
    date = normalize_date(text)  # поверне "YYYY‑MM‑DD" або None
    if date:
        USER_NAMES[user_id+"_date"] = date
        # формуємо список годинних кнопок
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for h in range(8, 21):
            kb.add(f"{h:02d}:00")
        await message.answer("Оберіть бажаний час (годинно):", reply_markup=kb)
        return

    # якщо це час
    if message.text.endswith(":00"):
        time = message.text
        date = USER_NAMES.get(user_id+"_date")
        proc = USER_NAMES.get(user_id+"_proc")
        # перевіряємо зайнятість
        free = get_free_slots(date, GOOGLE_SHEET_ID)
        if time not in free:
            # підбираємо інші вільні години цього дня
            suggestions = [t for t in free if t.endswith(":00")]
            if suggestions:
                await message.answer(
                    "На жаль, цей час зайнятий. Ось вільні години цього дня:\n"
                    + ", ".join(suggestions)
                )
            else:
                # якщо немає годин, пропонуємо інші дати
                # тут можна викликати логіку get_free_slots для сусідніх дат
                await message.answer("Немає вільних годин на цю дату. Спробуйте іншу дату.")
            return
        # якщо вільно — записуємо й дякуємо
        schedule_reminder(bot, message.chat.id, date, time, proc)
        await message.answer(
            f"Дякуємо, {USER_NAMES[user_id]}! Вас записано на {proc} {date} о {time}.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return

    # якщо жоден із вище — просто нагадуємо натиснути «Розпочати запис»
    await message.answer("Натисніть «Розпочати запис», щоб забронювати процедуру.")

if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
