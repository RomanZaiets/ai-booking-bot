import datetime
import json
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

def parse_request_with_gpt(text, openai):
    prompt = f'''
Ти бот-секретар. Витягни з цього тексту:
- Процедура
- Дата (формат 2025-07-11)
- Час (24-год формат)

Виведи результат у форматі JSON з ключами procedure, date, time.

Повідомлення: "{text}"
    '''
    res = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    content = res['choices'][0]['message']['content']
    try:
        return json.loads(content)
    except:
        return {}

def is_slot_available(date, time, sheet_id, service_file):
    creds = Credentials.from_service_account_file(service_file)
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range="Записи!A2:G").execute()
    rows = result.get('values', [])
    for row in rows:
        if len(row) >= 5 and row[3] == date and row[4] == time:
            return False
    return True

def save_to_sheet(message, user_input, parsed, sheet_id, service_file):
    creds = Credentials.from_service_account_file(service_file)
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        now,
        message.from_user.full_name,
        user_input,
        parsed.get("date"),
        parsed.get("time"),
        parsed.get("procedure"),
        str(message.from_user.id)
    ]
    sheet.values().append(
        spreadsheetId=sheet_id,
        range="Записи!A1",
        valueInputOption="RAW",
        body={"values": [row]}
    ).execute()

def remove_user_booking(user_id, sheet_id, service_file):
    creds = Credentials.from_service_account_file(service_file)
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    data = sheet.values().get(spreadsheetId=sheet_id, range="Записи!A2:G").execute().get("values", [])
    for idx, row in enumerate(data, start=2):
        if len(row) >= 7 and row[6] == str(user_id):
            sheet.values().clear(
                spreadsheetId=sheet_id,
                range=f"Записи!A{idx}:G{idx}"
            ).execute()
            return True
    return False

def get_free_slots(date, sheet_id, service_file):
    all_hours = [f"{h:02}:00" for h in range(9, 18)]
    creds = Credentials.from_service_account_file(service_file)
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=sheet_id, range="Записи!D2:E").execute()
    rows = result.get("values", [])
    booked_times = [r[1] for r in rows if len(r) >= 2 and r[0] == date]
    return [t for t in all_hours if t not in booked_times]
