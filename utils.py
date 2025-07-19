import os
import json
import datetime
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from typing import Optional, Dict, Any, List, Tuple, Set

WEEKDAYS = {
    'понеділок': 0, 'вівторок': 1, 'середа': 2, 'четвер': 3,
    'пʼятниця': 4, 'пятниця': 4, 'субота': 5, 'неділя': 6
}

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

SHEET_BOOKINGS_TITLE = "Записи"
SHEET_VISITORS_TITLE = "Visitors"

_client_cache = None

def get_gspread_client(credentials_env_var: Optional[str] = None):
    global _client_cache
    if _client_cache:
        return _client_cache
    raw = credentials_env_var or os.getenv("GOOGLE_CREDENTIALS")
    if not raw:
        logging.error("GOOGLE_CREDENTIALS not set.")
        return None
    try:
        creds_dict = json.loads(raw)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        _client_cache = gspread.authorize(creds)
        return _client_cache
    except Exception as e:
        logging.error("Failed to init gspread client", exc_info=e)
        return None

def normalize_date(raw_date: Optional[str]) -> Optional[str]:
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

def get_all_slots(start_hour: int = 8, end_hour: int = 20, step_minutes: int = 30) -> List[str]:
    slots = []
    today = datetime.date.today()
    current = datetime.datetime.combine(today, datetime.time(start_hour, 0))
    end = datetime.datetime.combine(today, datetime.time(end_hour, 0))
    while current < end:
        slots.append(current.strftime("%H:%M"))
        current += datetime.timedelta(minutes=step_minutes)
    return slots

def _ensure_worksheet(sheet, title: str, headers: Optional[List[str]] = None):
    try:
        ws = sheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=title, rows="200", cols=str(len(headers) if headers else 10))
        if headers:
            ws.append_row(headers)
    return ws

def get_free_slots(date_str: str, sheet_id: str, credentials_env_var: Optional[str] = None) -> List[str]:
    client = get_gspread_client(credentials_env_var)
    if not client:
        return []
    try:
        sheet = client.open_by_key(sheet_id)
        ws = _ensure_worksheet(sheet, SHEET_BOOKINGS_TITLE, ["created_at", "user_id", "full_name", "raw_input", "procedure", "date", "time"])
        records = ws.get_all_records()
        occupied: Set[Tuple[str, str]] = {(str(r.get('date')), str(r.get('time'))) for r in records}
        all_slots = get_all_slots()
        free = [slot for slot in all_slots if (date_str, slot) not in occupied]
        return free
    except Exception as e:
        logging.error("get_free_slots error", exc_info=e)
        return []

def save_to_sheet(message, user_input: str, parsed: Dict[str, Any], sheet_id: str, credentials_env_var: Optional[str] = None):
    client = get_gspread_client(credentials_env_var)
    if not client:
        return
    try:
        sheet = client.open_by_key(sheet_id)
        ws = _ensure_worksheet(sheet, SHEET_BOOKINGS_TITLE, ["created_at", "user_id", "full_name", "raw_input", "procedure", "date", "time"])
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([
            now,
            str(message.from_user.id),
            message.from_user.full_name,
            user_input or "",
            parsed.get('procedure') or "",
            parsed.get('date') or "",
            parsed.get('time_range') or ""
        ])
    except Exception as e:
        logging.error("save_to_sheet error", exc_info=e)

def save_visitor_to_sheet(user_id: int, full_name: str, sheet_id: Optional[str] = None):
    sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        logging.error("GOOGLE_SHEET_ID not set for visitors.")
        return
    client = get_gspread_client()
    if not client:
        return
    try:
        sheet = client.open_by_key(sheet_id)
        ws = _ensure_worksheet(sheet, SHEET_VISITORS_TITLE, ["datetime", "user_id", "full_name", "status"])
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([now, str(user_id), full_name, "started"])
    except Exception as e:
        logging.error("save_visitor_to_sheet error", exc_info=e)