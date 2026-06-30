import os
import json
import logging
from django.conf import settings
from django.utils import timezone
from .models import GoogleCredential
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

MOCK_CALENDAR_FILE = os.path.join(settings.BASE_DIR, 'mock_google_calendar_events.json')

def is_google_configured():
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    return bool(client_id and client_secret)

def get_google_client_config():
    return {
        "web": {
            "client_id": os.environ.get('GOOGLE_OAUTH_CLIENT_ID', ''),
            "client_secret": os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', ''),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [os.environ.get('GOOGLE_OAUTH_REDIRECT_URI', 'http://127.0.0.1:8000/oauth2/callback/')]
        }
    }

def get_user_credentials(user):
    try:
        db_cred = GoogleCredential.objects.get(user=user)
    except GoogleCredential.DoesNotExist:
        return None
        
    # Check if this is a mock credential
    if db_cred.token.startswith('mock_'):
        return 'MOCK'
        
    creds = Credentials(
        token=db_cred.token,
        refresh_token=db_cred.refresh_token,
        token_uri=db_cred.token_uri,
        client_id=db_cred.client_id,
        client_secret=db_cred.client_secret,
        scopes=db_cred.scopes.split(',')
    )
    
    # Check expiry and refresh if needed
    if db_cred.expiry and db_cred.expiry < timezone.now():
        try:
            creds.refresh(Request())
            # Save updated credentials
            db_cred.token = creds.token
            db_cred.expiry = timezone.make_aware(creds.expiry) if creds.expiry else timezone.now() + timezone.timedelta(hours=1)
            db_cred.save()
        except Exception as e:
            logger.error(f"Failed to refresh Google token for {user.username}: {e}")
            return None
            
    return creds

def create_calendar_event(booking):
    """
    Creates calendar events for both Doctor and Patient.
    If either user is not connected, it skips that calendar.
    If credentials are mock, it logs to a local JSON file.
    """
    doctor = booking.doctor
    patient = booking.patient
    slot = booking.slot
    
    doctor_event_id = None
    patient_event_id = None
    
    # 1. Create event for Doctor
    doctor_creds = get_user_credentials(doctor)
    if doctor_creds:
        title = f"Appointment with {patient.get_full_name() or patient.username}"
        description = f"Patient email: {patient.email}. Booking reference ID: {booking.id}"
        if doctor_creds == 'MOCK':
            doctor_event_id = write_mock_event(doctor, title, description, slot)
        else:
            doctor_event_id = call_google_calendar_api(doctor_creds, title, description, slot)
            
    # 2. Create event for Patient
    patient_creds = get_user_credentials(patient)
    if patient_creds:
        title = f"Appointment with Dr. {doctor.get_full_name() or doctor.username}"
        description = f"Doctor email: {doctor.email}. Booking reference ID: {booking.id}"
        if patient_creds == 'MOCK':
            patient_event_id = write_mock_event(patient, title, description, slot)
        else:
            patient_event_id = call_google_calendar_api(patient_creds, title, description, slot)
            
    # Save event IDs back to booking
    booking.google_calendar_doctor_event_id = doctor_event_id
    booking.google_calendar_patient_event_id = patient_event_id
    booking.save()
    
    return doctor_event_id, patient_event_id

def call_google_calendar_api(creds, title, description, slot):
    try:
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': slot.start_time.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': slot.end_time.isoformat(),
                'timeZone': 'UTC',
            },
        }
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return created_event.get('id')
    except Exception as e:
        logger.error(f"Google Calendar API call failed: {e}")
        # Return fallback mock event ID on failure to prevent app from crashing
        return f"failed-google-event-{timezone.now().timestamp()}"

def write_mock_event(user, title, description, slot):
    """
    Logs mock event payload to a local JSON file.
    """
    event_id = f"mock-event-{user.username}-{int(timezone.now().timestamp())}"
    event_payload = {
        "event_id": event_id,
        "user": user.username,
        "user_role": user.role,
        "title": title,
        "description": description,
        "start_time": slot.start_time.isoformat(),
        "end_time": slot.end_time.isoformat(),
        "created_at": timezone.now().isoformat()
    }
    
    # Read existing mock events
    events = []
    if os.path.exists(MOCK_CALENDAR_FILE):
        try:
            with open(MOCK_CALENDAR_FILE, 'r') as f:
                events = json.load(f)
        except Exception:
            events = []
            
    events.append(event_payload)
    
    try:
        with open(MOCK_CALENDAR_FILE, 'w') as f:
            json.dump(events, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to write mock event to file: {e}")
        
    return event_id
