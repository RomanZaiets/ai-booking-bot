import os
import json
import datetime
import logging
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
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(json.loads(env_var), f)
    except Exception as e:
        logging.error("Error writing credentials file", exc_info=e)

def get_all_slots(start_hour=8, end_hour=20, step_minutes=30):
    slots = []
    current = datetime.datetime.combine(datetime.date.today(), datetime.time(start_hour))
    end = datetime.datetime.combine(datetime.date.today(), datetime.time(end_hour))
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
        sheet = client.open_by_key(sheet_id).worksheet("Записи")
        occupied = {(r.get('date'), r.get('time')) for r in sheet.get_all_records()}
        return [slot for slot in get_all_slots() if (date_str, slot) not in occupied]
    except Exception as e:
        logging.error("get_free_slots error", exc_info=e)
        return []

def save_to_sheet(message, user_input, parsed, sheet_id, credentials_env_var=None):
    write_credentials_to_file(credentials_env_var or os.getenv("GOOGLE_CREDENTIALS"))
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json",
            ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).worksheet("Записи")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([
            now,
            str(message.from_user.id),
            message.from_user.full_name,
            user_input,
            parsed.get('procedure'),
            parsed.get('date'),
            parsed.get('time_range')
        ])
    except Exception as e:
        logging.error("save_to_sheet error", exc_info=e)

def save_visitor_to_sheet(user_id, full_name):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json",
            ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(os.getenv("GOOGLE_SHEET_ID"))
        try:
            ws = sheet.worksheet("Visitors")
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title="Visitors", rows="100", cols="4")
            ws.append_row(["datetime", "user_id", "full_name", "status"])
        ws.append_row([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(user_id), full_name, "started"])
    except Exception as e:
        logging.error("save_visitor_to_sheet error", exc_info=e)
