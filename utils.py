import openai
from dateutil import parser
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 🔍 AI: Парсинг повідомлення користувача
async def parse_request_with_gpt(user_input, openai_module):
    prompt = f"""
    Проаналізуй повідомлення користувача та витягни:
    - Процедура (манікюр або педикюр)
    - Дата (у форматі РРРР-ММ-ДД)
    - Час (у форматі ГГ:ХХ)
    Якщо щось незрозуміло — повертай порожнє значення.

    Повідомлення: "{user_input}"

    Відповідь у форматі JSON:
    {{
        "procedure": "...",
        "date": "...",
        "time": "..."
    }}
    """

    response = await openai_module.ChatCompletion.acreate(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    content = response.choices[0].message.content

    try:
        return eval(content)
    except:
        return {"procedure": "", "date": "", "time": ""}

# 📅 Перевірка чи слот вільний
def is_slot_available(date, time, sheet_id, credentials_file):
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)

    sheet = client.open_by_key(sheet_id).sheet1
    records = sheet.get_all_records()

    for record in records:
        if str(record.get("date")) == str(date) and str(record.get("time")) == str(time):
            return False
    return True

# 💾 Зберігання заявки в Google Sheet
def save_to_sheet(message, user_input, parsed, sheet_id, credentials_file):
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)

    sheet = client.open_by_key(sheet_id).sheet1

    sheet.append_row([
        str(message.from_user.full_name),
        str(message.chat.id),
        user_input,
        parsed.get("procedure"),
        parsed.get("date"),
        parsed.get("time")
    ])