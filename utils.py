import os
import json
import datetime
import logging
from dateutil import parser as date_parser
import gspread
from oauth2client.service_account import ServiceAccountCredentials

WEEKDAYS = {
    'понеділок': 0, 'вівторок': 1, 'середа': 2, 'четвер': 3,
    'пʼятниця': 4, 'пятниця': 4, 'субота': 5, 'неділя': 6
}

def write_credentials_to_file(env_var: str, file_path: str = "credentials.json"):
    if not env_var:
        logging.error("GOOGLE_CREDENTIALS environment variable is not set")
        return
    try:
        credentials_data = json.loads(env_var)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(credentials_data, f)
    except Exception as e:
        logging.error("Error writing credentials file", exc_info=e)

def normalize_date(raw_date):
    if not raw_date:
        return None
    rd = raw_date.strip().lower()
    try:
        datetime.datetime.strptime(rd, "%Y-%m-%d")
        return rd
    except ValueError:
        pass
    wd = WEEKDAYS.get(rd)
    if wd is not None:
        today = datetime.date.today()
        days_ahead = (wd - today.weekday() + 7) % 7 or 7
        target = today + datetime.timedelta(days=days_ahead)
        return target.strftime("%Y-%m-%d")
    return None

def get_all_slots(start_hour=8, end_hour=20, step_minutes=30):
    slots = []
    current = datetime.datetime.combine(datetime.date.today(), datetime.time(start_hour, 0))
    end = datetime.datetime.combine(datetime.date.today(), datetime.time(end_hour, 0))
    while current <= end:
        slots.append(current.strftime("%H:%M"))
        current += datetime.timedelta(minutes=step_minutes)
    return slots

def get_free_slots(date_str, sheet_id, credentials_env_var=None):
    write_credentials_to_file(credentials_env_var or os.getenv("GOOGLE_CREDENTIALS"))
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json",
            ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        records = sheet.get_all_records()
        occupied = {(r.get('date'), r.get('time')) for r in records}
        return [slot for slot in get_all_slots() if (date_str, slot) not in occupied]
    except Exception as e:
        logging.error("get_free_slots error", exc_info=e)
        return []

def filter_slots_by_interval(slots, start, end):
    return [t for t in slots if start <= t <= end]

def is_slot_available(date_str, time_str, sheet_id, credentials_env_var=None):
    free = get_free_slots(date_str, sheet_id, credentials_env_var)
    return time_str in free

def save_to_sheet(message, user_input, parsed, sheet_id, credentials_env_var=None):
    write_credentials_to_file(credentials_env_var or os.getenv("GOOGLE_CREDENTIALS"))
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json",
            ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
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
