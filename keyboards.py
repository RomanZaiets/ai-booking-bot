# keyboards.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard():
    """
    Головне меню: тільки кнопка 'Записатися'
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📝 Записатися"))
    return keyboard


def get_procedure_keyboard():
    """
    Вибір процедури: Манікюр / Педикюр
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("💅 Манікюр"),
        KeyboardButton("🦶 Педикюр")
    )
    return keyboard


def get_time_keyboard(times: list[str]):
    """
    Клавіатура з доступним часом
    """
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    buttons = [KeyboardButton(time) for time in times]
    keyboard.add(*buttons)
    return keyboard
