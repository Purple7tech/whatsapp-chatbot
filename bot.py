from flask import Flask, request
import requests
import os
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = Flask(__name__)

VERIFY_TOKEN = "tarun_123"
ACCESS_TOKEN = os.getenv('EAAKB8PQuIjABPHYsrmkZCYNw7pXxWqtzut6Qd362Up8sr0KY6qYUmkNF7OkDGeo78BC8bhhAw7ODFbk4L4Kkl1kt6VxVTCtpLZA8aCklnPWY2DgoaWGpSA7VGZBigZCiJRDs41peGQpHECBOp8bneq57znL9ao5DNgVROGprhBM642eI9X8U02ZCW4c4nFp6zNZCF9yyK0tvdtwvWBtdDZAF8J2ZCSZB1xoFlTiZAIQTKPXgZDZD')
PHONE_NUMBER_ID = os.getenv('728421923685994')

# Google API setup
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
sheet_service = build('sheets', 'v4', credentials=creds)
drive_service = build('drive', 'v3', credentials=creds)

SHEET_ID = 'YOUR_SHEET_ID'
SHEET_RANGE = 'chatbot_data!A1'
DRIVE_FOLDER_ID = 'YOUR_DRIVE_FOLDER_ID'

user_sessions = {}

@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN:
            return request.args.get('hub.challenge'), 200
        return 'Verification failed', 403

    if request.method == 'POST':
        data = request.get_json()
        if data['object'] == 'whatsapp_business_account':
            for entry in data['entry']:
                for change in entry['changes']:
                    value = change['value']
                    messages = value.get('messages')
                    if messages:
                        message = messages[0]
                        phone = message['from']
                        text = message['text']['body'] if 'text' in message else None
                        media = message.get('image')

                        # Initialize session
                        session = user_sessions.get(phone, {'step': 0, 'data': {}})
                        step = session['step']

                        # Example flow: Collect 2 text answers and 1 image
                        if step == 0 and text:
                            session['data']['name'] = text
                            session['step'] += 1
                            send_whatsapp_message(phone, "✅ Noted your name.\nWhat is your address?")
                        elif step == 1 and text:
                            session['data']['address'] = text
                            session['step'] += 1
                            send_whatsapp_message(phone, "📸 Please send a site image.")
                        elif step == 2 and media:
                            media_id = media['id']
                            file_link = download_and_upload_image(media_id, phone)
                            session['data']['image_url'] = file_link

                            # Save to Google Sheets
                            save_to_sheet(session['data'])
                            send_whatsapp_message(phone, "✅ All data saved successfully.")

                            # Reset session
                            user_sessions.pop(phone, None)
                        else:
                            send_whatsapp_message(phone, "⚠️ Please provide a valid response.")
                        user_sessions[phone] = session
        return 'OK', 200

def send_whatsapp_message(to, message):
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    payload = {
        'messaging_product': 'whatsapp',
        'to': to,
        'type': 'text',
        'text': {'body': message}
    }
    requests.post(url, headers=headers, json=payload)

def download_and_upload_image(media_id, phone):
    # Get media URL
    media_url = requests.get(
        f"https://graph.facebook.com/v19.0/{media_id}",
        headers={'Authorization': f'Bearer {ACCESS_TOKEN}'}
    ).json()['url']

    media_content = requests.get(media_url, headers={'Authorization': f'Bearer {ACCESS_TOKEN}'}).content
    file_io = io.BytesIO(media_content)

    # Upload to Drive
    media_upload = MediaIoBaseUpload(file_io, mimetype='image/jpeg')
    file_metadata = {'name': f'{phone}_site_image.jpg', 'parents': [DRIVE_FOLDER_ID]}
    file = drive_service.files().create(body=file_metadata, media_body=media_upload, fields='id').execute()
    file_link = f"https://drive.google.com/uc?id={file.get('id')}"
    return file_link

def save_to_sheet(data):
    sheet_service.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=SHEET_RANGE,
        valueInputOption='USER_ENTERED',
        body={'values': [[data.get('name'), data.get('address'), data.get('image_url')]]}
    ).execute()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
