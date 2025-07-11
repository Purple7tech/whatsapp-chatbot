from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os
import io
import requests

app = Flask(__name__)

# === Google API Setup ===
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

# === Google Sheet & Drive Settings ===
SHEET_ID = '' #'1IfaWhGYJzakJb4Xzk_A1RHVeTvJBlSDMOsF1cDC1VM0'
SHEET_RANGE = ''#'chatbot_data!A1'
DRIVE_FOLDER_ID = '1OqMqEPU5rnBUbRf1nFyNio2_pnX3pXMq'

# === Define Form Fields ===
form_fields = [
    {"question": "Owner name?", "field": "owner_name"},
    {"question": "Owner phone number?", "field": "owner_phone"},
    {"question": "Property address?", "field": "property_address"},
    {"question": "Survey number?", "field": "survey_number"},
    {"question": "Village / Taluk / District?", "field": "location"},
    {"question": "Type of property (Vacant / Built-up / Agricultural)?", "field": "property_type"},
    {"question": "Extent (Sq.ft or Cent)?", "field": "extent"},
    {"question": "Current usage (Residential / Commercial / Agricultural)?", "field": "usage"},
    {"question": "Boundaries (North / South / East / West)?", "field": "boundaries"},
    {"question": "Any encroachments?", "field": "encroachments"},
    {"question": "Building details (floors, structure)?", "field": "building_details"},
    {"question": "Inspector name?", "field": "inspector_name"},
    {"question": "Any remarks or notes?", "field": "remarks"}
]

image_fields = ["north_img", "south_img", "east_img", "west_img"]

# === State Tracking ===
user_data = {}
user_index = {}

# Create a single instance of the Google Drive and Sheets services
drive_service = build('drive', 'v3', credentials=creds)
sheet_service = build('sheets', 'v4', credentials=creds)

@app.route("/", methods=["POST"])
def bot():
    user_msg = request.values.get("Body", "").strip().lower()
    user_phone = request.values.get("From", "")
    num_media = int(request.values.get("NumMedia", 0))
    response = MessagingResponse()

    # Initialize new user
    if user_phone not in user_index:
        user_data[user_phone] = {}
        user_index[user_phone] = 0
        if user_msg == 'hi':
            response.message("📝 Welcome to the Site Appraisal Bot.\nLet's begin.")
            response.message(form_fields[0]["question"])
        else:
            response.message("⚠️ Please start by saying 'hi'.")
        return str(response)

    index = user_index[user_phone]

    # Handle form text inputs
    if index < len(form_fields):
        field = form_fields[index]["field"]
        if user_msg:
            user_data[user_phone][field] = user_msg
            user_index[user_phone] += 1
            index += 1
            if index < len(form_fields):
                response.message(form_fields[index]["question"])
            else:
                response.message("📸 Now, please send the image of the **North side** of the site.")
        else:
            response.message("⚠️ Please enter a valid response.")
        return str(response)

    # Handle image uploads (North, South, East, West)
    image_index = index - len(form_fields)
    if image_index < len(image_fields):
        if num_media > 0:
            media_url = request.values.get("MediaUrl0")
            media_type = request.values.get("MediaContentType0")
            file_name = f"{user_phone.replace(':', '_')}_{image_fields[image_index]}.{media_type.split('/')[-1]}"

            # Download the image
            media_resp = requests.get(media_url, auth=(os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH_TOKEN")))
            file_io = io.BytesIO(media_resp.content)

            # Upload to Google Drive
            media = MediaIoBaseUpload(file_io, mimetype=media_type)
            file_metadata = {'name': file_name, 'parents': [DRIVE_FOLDER_ID]}
            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            file_link = f"https://drive.google.com/uc?id={file.get('id')}"

            # Save image link
            user_data[user_phone][image_fields[image_index]] = file_link
            user_index[user_phone] += 1
            image_index += 1

            # Prompt next
            if image_index < len(image_fields):
                response.message(f"📸 Please send the image of the **{image_fields[image_index].split('_')[0].capitalize()} side**.")
            else:
                # Submit to Sheet
                sheet = sheet_service.spreadsheets()
                row_data = [
                    user_data[user_phone].get("owner_name", ""),
                    user_data[user_phone].get("owner_phone", ""),
                    user_data[user_phone].get("property_address", ""),
                    user_data[user_phone].get("survey_number", ""),
                    user_data[user_phone].get("location", ""),
                    user_data[user_phone].get("property_type", ""),
                    user_data[user_phone].get("extent", ""),
                    user_data[user_phone].get("usage", ""),
                    user_data[user_phone].get("boundaries", ""),
                    user_data[user_phone].get("encroachments", ""),
                    user_data[user_phone].get("building_details", ""),
                    user_data[user_phone].get("inspector_name", ""),
                    user_data[user_phone].get("remarks", ""),
                    user_data[user_phone].get("north_img", ""),
                    user_data[user_phone].get("south_img", ""),
                    user_data[user_phone].get("east_img", ""),
                    user_data[user_phone].get("west_img", "")
                ]
                sheet.values().append(
                    spreadsheetId=SHEET_ID,
                    range=SHEET_RANGE,
                    valueInputOption="USER_ENTERED",
                    body={"values": [row_data]}
                ).execute()
                response.message("✅ Site appraisal data and images saved successfully.")
                del user_index[user_phone]
                del user_data[user_phone]
        else:
            response.message("⚠️ Please send an image (photo).")
    else:
        response.message("✅ Form is already completed.")

    return str(response)

if __name__ == "__main__":
    app.run(debug=False)
