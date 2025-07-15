import openai
import json
import datetime
import logging
from dateutil import parser as date_parser
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Мапінг українських днів тижня
WEEKDAYS = {
    'понеділок': 0,
    'вівторок': 1,
    'середа': 2,
    'четвер': 3,
    'пʼятниця': 4,
    'пятниця': 4,
    'субота': 5,
    'неділя': 6
}

async def parse_request_with_gpt(user_input, openai_module):
    """
    Витягує з природньомовного повідомлення:
      - procedure: манікюр/педикюр
      - date: YYYY-MM-DD або день тижня українською
      - time_range: один з "ранком", "після обіду", "ввечері"
    """
    prompt = f"""
Проаналізуй повідомлення користувача та поверни JSON з полями:
- "procedure": манікюр або педикюр
- "date": дата у форматі YYYY-MM-DD або день тижня українською
- "time_range": один з "ранком", "після обіду", "ввечері"

Повідомлення: "{user_input}"
"""
    try:
        resp = await openai_module.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":prompt}],
            timeout=15
        )
        content = resp.choices[0].message.content.strip()
        logging.info(f"GPT parse response: {content}")
        data = json.loads(content)
        return data if isinstance(data, dict) else {"procedure":"","date":"","time_range":""}
    except Exception as e:
        logging.error("parse_request_with_gpt error", exc_info=e)
        return {"procedure":"","date":"","time_range":""}


def normalize_date(raw_date):
    """
    Перетворює:
      - YYYY-MM-DD -> повертає без змін
      - день тижня -> найближчий наступний день
    """
    if not raw_date:
        return None
    rd = raw_date.strip().lower()
    # ISO-формат
    try:
        datetime.datetime.strptime(rd, "%Y-%m-%d")
        return rd
    except ValueError:
        pass
    # Український день тижня
    wd = WEEKDAYS.get(rd)
    if wd is not None:
        today = datetime.date.today()
        days_ahead = (wd - today.weekday() + 7) % 7 or 7
        target = today + datetime.timedelta(days=days_ahead)
        return target.strftime("%Y-%m-%d")
    return None


def get_all_slots(start_hour=8, end_hour=20, step_minutes=30):
    """
    Генерує часові слоти між start_hour і end_hour з кроком step_minutes
    """
    slots = []
    current = datetime.datetime.combine(datetime.date.today(), datetime.time(start_hour, 0))
    end = datetime.datetime.combine(datetime.date.today(), datetime.time(end_hour, 0))
    while current <= end:
        slots.append(current.strftime("%H:%M"))
        current += datetime.timedelta(minutes=step_minutes)
    return slots


def get_free_slots(date_str, sheet_id, credentials_file='credentials.json'):
    """
    Повертає список вільних слотів у Google Sheets для date_str
    """
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        records = sheet.get_all_records()
        occupied = {(r.get('date'), r.get('time')) for r in records}
        free = [slot for slot in get_all_slots() if (date_str, slot) not in occupied]
        return free
    except Exception as e:
        logging.error("get_free_slots error", exc_info=e)
        return []


def filter_slots_by_interval(slots, start, end):
    """
    Фільтрує список слотів між start і end (включно)
    """
    return [t for t in slots if start <= t <= end]


def is_slot_available(date, time, sheet_id, credentials_file='credentials.json'):
    """
    Перевіряє, чи слот вільний у Google Sheets
    """
    free = get_free_slots(date, sheet_id, credentials_file)
    return time in free


def save_to_sheet(message, user_input, parsed, sheet_id, credentials_file='credentials.json'):
    """
    Додає запис бронювання до Google Sheets
    """
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([
            now,
            message.from_user.full_name,
            user_input,
            parsed.get('procedure'),
            parsed.get('date'),
            parsed.get('time_range')
        ])
    except Exception as e:
        logging.error("save_to_sheet error", exc_info=e)
