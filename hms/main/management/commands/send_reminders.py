from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import Booking
from main.views import send_email_notification

class Command(BaseCommand):
    help = 'Sends email reminders to doctors and patients 1 hour before scheduled slots'

    def handle(self, *args, **options):
        now = timezone.now()
        start_range = now + timezone.timedelta(minutes=55)
        end_range = now + timezone.timedelta(minutes=65)

        # Find confirmed bookings starting in 55 to 65 minutes
        bookings = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            slot__start_time__range=(start_range, end_range)
        )

        self.stdout.write(f"[{timezone.now().isoformat()}] Checking for upcoming bookings between {start_range.strftime('%H:%M')} and {end_range.strftime('%H:%M')}...")

        count = 0
        for booking in bookings:
            slot = booking.slot
            doctor = booking.doctor
            patient = booking.patient

            email_data = {
                "doctor_name": doctor.get_full_name() or doctor.username,
                "patient_name": patient.get_full_name() or patient.username,
                "time": f"{slot.start_time.strftime('%Y-%m-%d %H:%M')} - {slot.end_time.strftime('%H:%M')}"
            }

            # Send reminder to patient
            patient_sent = send_email_notification("APPOINTMENT_REMINDER", patient.email, email_data)
            # Send reminder to doctor
            doctor_sent = send_email_notification("APPOINTMENT_REMINDER", doctor.email, email_data)

            if patient_sent and doctor_sent:
                self.stdout.write(self.style.SUCCESS(f"Sent reminder for Booking ID {booking.id} (Patient: {patient.username}, Doctor: {doctor.username})"))
                count += 1
            else:
                self.stdout.write(self.style.WARNING(f"Failed to send some reminders for Booking ID {booking.id}"))

        self.stdout.write(self.style.SUCCESS(f"Finished sending reminders. Total sent: {count}"))
