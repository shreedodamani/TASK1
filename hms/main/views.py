import os
import requests
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.conf import settings

from .models import User, AvailabilitySlot, Booking, GoogleCredential
from .decorators import doctor_required, patient_required
from .calendar_helper import (
    is_google_configured,
    get_google_client_config,
    create_calendar_event
)

from google_auth_oauthlib.flow import Flow
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

def send_email_notification(trigger_type, recipient_email, data):
    """
    Sends email notification by calling serverless offline function.
    Falls back automatically to direct SMTP localhost:1025 if serverless is offline.
    """
    try:
        response = requests.post(
            settings.EMAIL_SERVICE_URL,
            json={
                "trigger_type": trigger_type,
                "recipient_email": recipient_email,
                "data": data
            },
            timeout=1.5
        )
        if response.status_code == 200:
            logger.info(f"Email sent successfully via Serverless for {trigger_type} to {recipient_email}.")
            return True
    except Exception as e:
        logger.warning(f"Serverless email service failed or not running: {e}. Falling back to direct SMTP.")
        
    # Fallback to direct SMTP (port 1025)
    try:
        smtp_host = os.environ.get('SMTP_HOST', '127.0.0.1')
        smtp_port = int(os.environ.get('SMTP_PORT', '1025'))
        smtp_user = os.environ.get('SMTP_USER', '')
        smtp_password = os.environ.get('SMTP_PASSWORD', '')
        sender_email = os.environ.get('SENDER_EMAIL', 'noreply@minihms.com')
        
        subject = ""
        html_content = ""
        
        if trigger_type == 'SIGNUP_WELCOME':
            subject = "Welcome to Mini HMS!"
            name = data.get('name', 'User')
            role = data.get('role', 'patient')
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 1.5rem; color: #1e293b;">
                    <div style="background: #ffffff; border-radius: 8px; padding: 2rem; border: 1px solid #e2e8f0; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #0ea5e9; margin-top: 0;">Welcome to Mini HMS, {name}!</h2>
                        <p>Thank you for signing up as a <strong>{role}</strong>.</p>
                        <p>You can now log in to manage schedules or book appointments.</p>
                    </div>
                </body>
            </html>
            """
        elif trigger_type == 'BOOKING_REQUEST':
            subject = "New Appointment Request - Mini HMS"
            patient_name = data.get('patient_name')
            age = data.get('patient_age', 'N/A')
            gender = data.get('patient_gender', 'N/A')
            disease = data.get('disease_description', 'No symptoms detailed.')
            time_slot = data.get('time')
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 1.5rem; color: #1e293b;">
                    <div style="background: #ffffff; border-radius: 8px; padding: 2rem; border: 1px solid #e2e8f0; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #f59e0b; margin-top: 0;">New Appointment Request</h2>
                        <p>Patient <strong>{patient_name}</strong> (Age: {age}, Gender: {gender}) has requested an appointment:</p>
                        <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 1rem 0;">
                        <p><strong>Proposed Time:</strong> {time_slot}</p>
                        <p><strong>Patient Symptoms/Disease:</strong> {disease}</p>
                        <p>Please log in to your Doctor Dashboard to Accept or Reject this booking request.</p>
                    </div>
                </body>
            </html>
            """
        elif trigger_type == 'BOOKING_CONFIRMATION':
            subject = "Booking Confirmed - Mini HMS"
            doctor_name = data.get('doctor_name')
            patient_name = data.get('patient_name')
            date = data.get('date')
            time = data.get('time')
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 1.5rem; color: #1e293b;">
                    <div style="background: #ffffff; border-radius: 8px; padding: 2rem; border: 1px solid #e2e8f0; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #10b981; margin-top: 0;">Booking Confirmed!</h2>
                        <p>An appointment has been successfully confirmed and scheduled:</p>
                        <ul>
                            <li><strong>Doctor:</strong> Dr. {doctor_name}</li>
                            <li><strong>Patient:</strong> {patient_name}</li>
                            <li><strong>Date:</strong> {date}</li>
                            <li><strong>Time:</strong> {time}</li>
                        </ul>
                    </div>
                </body>
            </html>
            """
        elif trigger_type == 'BOOKING_REJECTED':
            subject = "Appointment Request Declined - Mini HMS"
            doctor_name = data.get('doctor_name')
            time_slot = data.get('time')
            reason = data.get('reason', 'Doctor unavailable')
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 1.5rem; color: #1e293b;">
                    <div style="background: #ffffff; border-radius: 8px; padding: 2rem; border: 1px solid #e2e8f0; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #ef4444; margin-top: 0;">Appointment Request Declined</h2>
                        <p>Dear Patient,</p>
                        <p>Dr. <strong>{doctor_name}</strong> is unable to accept your booking request for the slot <strong>{time_slot}</strong>.</p>
                        <p><strong>Reason:</strong> {reason}</p>
                        <p>Please log in to your dashboard to choose a different slot.</p>
                    </div>
                </body>
            </html>
            """
        elif trigger_type == 'BOOKING_CANCELLED':
            subject = "Appointment Cancelled - Mini HMS"
            doctor_name = data.get('doctor_name')
            time_slot = data.get('time')
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 1.5rem; color: #1e293b;">
                    <div style="background: #ffffff; border-radius: 8px; padding: 2rem; border: 1px solid #e2e8f0; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #ef4444; margin-top: 0;">Appointment Cancelled</h2>
                        <p>Dear Patient,</p>
                        <p>Your confirmed appointment with Dr. <strong>{doctor_name}</strong> scheduled for <strong>{time_slot}</strong> has been cancelled.</p>
                    </div>
                </body>
            </html>
            """
        elif trigger_type == 'APPOINTMENT_REMINDER':
            subject = "Appointment Reminder - Mini HMS"
            doctor_name = data.get('doctor_name')
            patient_name = data.get('patient_name')
            time_slot = data.get('time')
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; background-color: #f1f5f9; padding: 1.5rem; color: #1e293b;">
                    <div style="background: #ffffff; border-radius: 8px; padding: 2rem; border: 1px solid #e2e8f0; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #0ea5e9; margin-top: 0;">Upcoming Appointment Reminder</h2>
                        <p>This is a reminder that your confirmed appointment starts in <strong>1 hour</strong>:</p>
                        <ul>
                            <li><strong>Doctor:</strong> Dr. {doctor_name}</li>
                            <li><strong>Patient:</strong> {patient_name}</li>
                            <li><strong>Time:</strong> {time_slot}</li>
                        </ul>
                    </div>
                </body>
            </html>
            """
            
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg.attach(MIMEText(html_content, 'html'))
        
        with smtplib.SMTP(smtp_host, smtp_port, timeout=1.5) as server:
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, [recipient_email], msg.as_string())
        logger.info(f"Email sent successfully via direct SMTP fallback for {trigger_type} to {recipient_email}.")
        return True
    except Exception as smtp_err:
        logger.error(f"SMTP fallback send failed: {smtp_err}")
        return False


def home(request):
    if request.user.is_authenticated:
        if request.user.role == User.Role.DOCTOR:
            return redirect('doctor_dashboard')
        elif request.user.role == User.Role.PATIENT:
            return redirect('patient_dashboard')
    return render(request, 'landing.html')


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', User.Role.PATIENT)
        
        gender = request.POST.get('gender', '') if role == User.Role.PATIENT else None
        age_str = request.POST.get('age', '') if role == User.Role.PATIENT else None
        age = int(age_str) if age_str else None
        
        if not (username and email and password and role):
            messages.error(request, "Please fill in all required fields.")
            return render(request, 'signup.html')
            
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'signup.html')
            
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.")
            return render(request, 'signup.html')
            
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered.")
            return render(request, 'signup.html')
            
        try:
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
                gender=gender,
                age=age
            )
            user.save()
            
            # Welcome Notification
            send_email_notification(
                "SIGNUP_WELCOME",
                user.email,
                {
                    "name": user.get_full_name() or user.username,
                    "role": user.role.lower()
                }
            )
            
            login(request, user)
            messages.success(request, f"Welcome, {user.username}! Your account has been created.")
            return redirect('home')
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            
    return render(request, 'signup.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    if request.method == 'POST':
        username_or_email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        user = None
        if '@' in username_or_email:
            try:
                user_obj = User.objects.get(email=username_or_email)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            user = authenticate(username=username_or_email, password=password)
            
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect('home')
        else:
            messages.error(request, "Invalid username/email or password.")
            
    return render(request, 'login.html')


def logout_view(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect('home')


@doctor_required
def doctor_dashboard(request):
    # Split bookings into pending requests and confirmed slots
    pending_bookings = Booking.objects.filter(
        doctor=request.user,
        status=Booking.Status.PENDING
    ).order_by('slot__start_time')
    
    confirmed_bookings = Booking.objects.filter(
        doctor=request.user,
        status=Booking.Status.CONFIRMED
    ).order_by('slot__start_time')
    
    slots = AvailabilitySlot.objects.filter(doctor=request.user).order_by('start_time')
    is_connected = GoogleCredential.objects.filter(user=request.user).exists()
    
    context = {
        'pending_bookings': pending_bookings,
        'confirmed_bookings': confirmed_bookings,
        'slots': slots,
        'is_connected': is_connected,
        'now': timezone.now()
    }
    return render(request, 'doctor_dashboard.html', context)


@doctor_required
def create_slot(request):
    if request.method == 'POST':
        date_str = request.POST.get('date')
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time')
        
        if not (date_str and start_time_str and end_time_str):
            messages.error(request, "Please enter all date and time fields.")
            return redirect('doctor_dashboard')
            
        try:
            naive_start = timezone.datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M")
            naive_end = timezone.datetime.strptime(f"{date_str} {end_time_str}", "%Y-%m-%d %H:%M")
            
            start_time = timezone.make_aware(naive_start)
            end_time = timezone.make_aware(naive_end)
            
            slot = AvailabilitySlot(
                doctor=request.user,
                start_time=start_time,
                end_time=end_time
            )
            slot.save()
            messages.success(request, "Availability slot created successfully.")
        except ValidationError as ve:
            messages.error(request, ve.messages[0] if hasattr(ve, 'messages') else str(ve))
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            
    return redirect('doctor_dashboard')


@doctor_required
def accept_booking(request, booking_id):
    if request.method == 'POST':
        booking = get_object_or_404(Booking, id=booking_id, doctor=request.user)
        prescription = request.POST.get('prescription', '').strip()
        patient_status = request.POST.get('patient_status', '').strip()
        
        try:
            with transaction.atomic():
                booking.status = Booking.Status.CONFIRMED
                if prescription:
                    booking.prescription = prescription
                if patient_status:
                    booking.patient_status = patient_status
                booking.save()
            
            # Send Confirmation Emails to both Patient and Doctor
            slot = booking.slot
            email_data = {
                "doctor_name": request.user.get_full_name() or request.user.username,
                "patient_name": booking.patient.get_full_name() or booking.patient.username,
                "date": slot.start_time.strftime('%Y-%m-%d'),
                "time": f"{slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}"
            }
            send_email_notification("BOOKING_CONFIRMATION", booking.patient.email, email_data)
            send_email_notification("BOOKING_CONFIRMATION", request.user.email, email_data)
            
            # Create Google Calendar Event upon Confirmation
            create_calendar_event(booking)
            
            messages.success(request, f"Appointment request from {booking.patient.username} has been confirmed!")
        except Exception as e:
            messages.error(request, f"Error accepting booking: {str(e)}")
            
    return redirect('doctor_dashboard')


@doctor_required
def reject_booking(request, booking_id):
    if request.method == 'POST':
        booking = get_object_or_404(Booking, id=booking_id, doctor=request.user)
        reason = request.POST.get('rejection_reason', '').strip()
        
        try:
            with transaction.atomic():
                booking.status = Booking.Status.REJECTED
                booking.save()
                
                # Free up the slot again for other patients
                slot = booking.slot
                slot.is_booked = False
                slot.save()
            
            # Send rejection email alert to the patient
            email_data = {
                "doctor_name": request.user.get_full_name() or request.user.username,
                "time": f"{slot.start_time.strftime('%Y-%m-%d %H:%M')} - {slot.end_time.strftime('%H:%M')}",
                "reason": reason or "Doctor unavailable at this slot."
            }
            send_email_notification("BOOKING_REJECTED", booking.patient.email, email_data)
            
            messages.success(request, f"Appointment request from {booking.patient.username} has been declined.")
        except Exception as e:
            messages.error(request, f"Error declining booking: {str(e)}")
            
    return redirect('doctor_dashboard')


@doctor_required
def cancel_booking(request, booking_id):
    if request.method == 'POST':
        booking = get_object_or_404(Booking, id=booking_id, doctor=request.user)
        slot = booking.slot
        
        # Enforce 1.5 Hour Cancellation Constraint
        time_until_appointment = slot.start_time - timezone.now()
        if time_until_appointment.total_seconds() < 90 * 60:
            messages.error(request, "Cancellation Error: You cannot cancel appointments scheduled to start in less than 1.5 hours.")
            return redirect('doctor_dashboard')
            
        try:
            with transaction.atomic():
                booking.status = Booking.Status.CANCELLED
                booking.save()
                
                # Unlock availability slot
                slot.is_booked = False
                slot.save()
                
            # Send cancellation email to patient
            email_data = {
                "doctor_name": request.user.get_full_name() or request.user.username,
                "time": slot.start_time.strftime('%Y-%m-%d %H:%M')
            }
            send_email_notification("BOOKING_CANCELLED", booking.patient.email, email_data)
            
            messages.success(request, "Appointment cancelled successfully.")
        except Exception as e:
            messages.error(request, f"Error cancelling booking: {str(e)}")
            
    return redirect('doctor_dashboard')


@patient_required
def patient_dashboard(request):
    doctors = User.objects.filter(role=User.Role.DOCTOR)
    is_connected = GoogleCredential.objects.filter(user=request.user).exists()
    
    # Calculate patient diagnostics
    visits_count = Booking.objects.filter(
        patient=request.user,
        status=Booking.Status.CONFIRMED
    ).count()
    
    # Retrieve doctor diagnoses / patient statuses and prescriptions from past bookings
    past_bookings = Booking.objects.filter(
        patient=request.user
    ).exclude(status=Booking.Status.PENDING).order_by('-slot__start_time')
    
    # Get available slots in the future
    available_slots = AvailabilitySlot.objects.filter(
        is_booked=False,
        start_time__gt=timezone.now()
    ).order_by('start_time')
    
    # Filter slots by doctor if requested
    doctor_filter = request.GET.get('doctor_id')
    if doctor_filter:
        available_slots = available_slots.filter(doctor_id=doctor_filter)
        
    # Filter slots by date selected from the calendar
    date_filter = request.GET.get('date')
    if date_filter:
        available_slots = available_slots.filter(start_time__date=date_filter)
        
    # Retrieve all bookings for this patient to display in history/status list
    bookings = Booking.objects.filter(
        patient=request.user
    ).order_by('-slot__start_time')

    context = {
        'doctors': doctors,
        'visits_count': visits_count,
        'bookings': bookings,
        'past_bookings': past_bookings,
        'available_slots': available_slots,
        'is_connected': is_connected,
        'selected_doctor': doctor_filter,
        'selected_date': date_filter,
        'now': timezone.now()
    }
    return render(request, 'patient_dashboard.html', context)


@patient_required
def book_slot(request, slot_id):
    if request.method == 'POST':
        disease = request.POST.get('disease_description', '').strip()
        if not disease:
            messages.error(request, "Please describe your symptoms or disease.")
            return redirect('patient_dashboard')
            
        try:
            with transaction.atomic():
                slot = AvailabilitySlot.objects.select_for_update().get(id=slot_id)
                
                if slot.is_booked:
                    messages.error(request, "This slot is no longer available. Someone else just booked it!")
                    return redirect('patient_dashboard')
                    
                if slot.start_time < timezone.now():
                    messages.error(request, "You cannot book slots that are in the past.")
                    return redirect('patient_dashboard')
                    
                slot.is_booked = True
                slot.save()
                
                # Booking created as PENDING approval
                booking = Booking.objects.create(
                    patient=request.user,
                    doctor=slot.doctor,
                    slot=slot,
                    status=Booking.Status.PENDING,
                    disease_description=disease
                )
                
            # Send Booking Request Email to the Doctor
            email_data = {
                "patient_name": request.user.get_full_name() or request.user.username,
                "patient_age": request.user.age or 'N/A',
                "patient_gender": request.user.gender or 'N/A',
                "time": slot.start_time.strftime('%Y-%m-%d %H:%M'),
                "disease_description": disease
            }
            send_email_notification("BOOKING_REQUEST", slot.doctor.email, email_data)
            
            messages.success(request, "Appointment request sent! Awaiting doctor's approval.")
            
        except AvailabilitySlot.DoesNotExist:
            messages.error(request, "Selected availability slot does not exist.")
        except Exception as e:
            messages.error(request, f"Error requesting slot: {str(e)}")
            
    return redirect('patient_dashboard')


def google_oauth2_connect(request):
    if not request.user.is_authenticated:
        return redirect('login')
        
    # Check if Google client credentials are set in environment
    if is_google_configured():
        try:
            client_config = get_google_client_config()
            flow = Flow.from_client_config(
                client_config,
                scopes=['https://www.googleapis.com/auth/calendar.events'],
                redirect_uri=request.build_absolute_uri(reverse('google_callback'))
            )
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            request.session['oauth_state'] = state
            return redirect(authorization_url)
        except Exception as e:
            logger.error(f"Error starting OAuth flow: {e}")
            messages.warning(request, f"Error starting OAuth flow: {e}. Falling back to Mock integration.")
            
    # Mock integration fallback (instant success)
    try:
        GoogleCredential.objects.update_or_create(
            user=request.user,
            defaults={
                'token': f'mock_token_{request.user.username}',
                'refresh_token': f'mock_refresh_{request.user.username}',
                'token_uri': 'https://oauth2.googleapis.com/token',
                'client_id': 'mock_client_id',
                'client_secret': 'mock_client_secret',
                'scopes': 'https://www.googleapis.com/auth/calendar.events',
                'expiry': timezone.now() + timezone.timedelta(days=365)
            }
        )
        messages.success(request, "Mock Google Calendar integrated successfully!")
    except Exception as e:
        messages.error(request, f"Failed to connect mock calendar: {e}")
        
    return redirect('home')


def google_oauth2_callback(request):
    if not request.user.is_authenticated:
        return redirect('login')
        
    state = request.session.get('oauth_state')
    code = request.GET.get('code')
    
    if is_google_configured() and state and code:
        try:
            client_config = get_google_client_config()
            flow = Flow.from_client_config(
                client_config,
                scopes=['https://www.googleapis.com/auth/calendar.events'],
                redirect_uri=request.build_absolute_uri(reverse('google_callback')),
                state=state
            )
            flow.fetch_token(authorization_response=request.build_absolute_uri(request.get_full_path()))
            creds = flow.credentials
            
            GoogleCredential.objects.update_or_create(
                user=request.user,
                defaults={
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': ','.join(creds.scopes),
                    'expiry': timezone.make_aware(creds.expiry) if creds.expiry else timezone.now() + timezone.timedelta(hours=1)
                }
            )
            messages.success(request, "Google Calendar integrated successfully!")
            return redirect('home')
        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            messages.error(request, f"Google Calendar connection failed: {e}")
            return redirect('home')
            
    # Mock fallback if called directly
    messages.info(request, "Using mock OAuth callback configuration.")
    return redirect('home')


def google_oauth2_disconnect(request):
    if not request.user.is_authenticated:
        return redirect('login')
        
    GoogleCredential.objects.filter(user=request.user).delete()
    messages.success(request, "Google Calendar disconnected.")
    return redirect('home')

