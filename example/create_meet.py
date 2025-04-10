# pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib
from __future__ import print_function
import datetime
import os.path
import google.auth

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these SCOPES, delete the token.json file
SCOPES = ['https://www.googleapis.com/auth/calendar']

def create_meeting():
    creds = None

    # Load saved credentials if they exist
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # If no valid credentials, prompt login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)

    # Set event details
    event = {
        'summary': 'Test Google Meet Meeting',
        'start': {
            'dateTime': (datetime.datetime.utcnow() + datetime.timedelta(minutes=5)).isoformat() + 'Z',
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': (datetime.datetime.utcnow() + datetime.timedelta(minutes=35)).isoformat() + 'Z',
            'timeZone': 'UTC',
        },
        'conferenceData': {
            'createRequest': {
                'requestId': 'some-random-string',  # Should be unique
                'conferenceSolutionKey': {'type': 'hangoutsMeet'}
            }
        },
        'attendees': [],
    }

    created_event = service.events().insert(
        calendarId='primary',
        body=event,
        conferenceDataVersion=1
    ).execute()

    meet_link = created_event.get('conferenceData', {}).get('entryPoints', [])[0].get('uri')
    print(f"Meeting created: {meet_link}")

if __name__ == '__main__':
    create_meeting()
