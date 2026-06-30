from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from main.models import AvailabilitySlot
import datetime

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds database with default doctors, specialties, and future availability slots.'

    def handle(self, *args, **options):
        # Create Doctors
        doctors_info = [
            {
                'username': 'dr_smith',
                'email': 'smith@example.com',
                'first_name': 'Alice',
                'last_name': 'Smith',
                'specialty': 'Cardiology',
            },
            {
                'username': 'dr_jones',
                'email': 'jones@example.com',
                'first_name': 'Bob',
                'last_name': 'Jones',
                'specialty': 'Dermatology',
            },
            {
                'username': 'dr_evans',
                'email': 'evans@example.com',
                'first_name': 'Carol',
                'last_name': 'Evans',
                'specialty': 'Pediatrics',
            },
            {
                'username': 'dr_miller',
                'email': 'miller@example.com',
                'first_name': 'David',
                'last_name': 'Miller',
                'specialty': 'General Medicine',
            }
        ]

        doctors = []
        for info in doctors_info:
            doctor, created = User.objects.get_or_create(
                username=info['username'],
                defaults={
                    'email': info['email'],
                    'first_name': info['first_name'],
                    'last_name': info['last_name'],
                    'role': User.Role.DOCTOR,
                    'specialty': info['specialty']
                }
            )
            if created:
                doctor.set_password('password123')
                doctor.save()
                self.stdout.write(self.style.SUCCESS(f"Created Doctor: Dr. {doctor.last_name} ({doctor.specialty})"))
            else:
                doctor.specialty = info['specialty']
                doctor.save()
                self.stdout.write(f"Doctor Dr. {doctor.last_name} already exists.")
            doctors.append(doctor)

        # Create Availability Slots (in the future)
        now = timezone.now()
        tomorrow = now.date() + datetime.timedelta(days=1)
        day_after = now.date() + datetime.timedelta(days=2)

        time_slots = [
            (tomorrow, datetime.time(9, 0), datetime.time(10, 0)),
            (tomorrow, datetime.time(10, 30), datetime.time(11, 30)),
            (tomorrow, datetime.time(14, 0), datetime.time(15, 0)),
            (day_after, datetime.time(10, 0), datetime.time(11, 0)),
            (day_after, datetime.time(11, 30), datetime.time(12, 30)),
            (day_after, datetime.time(15, 30), datetime.time(16, 30)),
        ]

        slots_created = 0
        for doc in doctors:
            for date, start_time, end_time in time_slots:
                # Combine date and time, then make aware in current timezone
                start_dt = timezone.make_aware(datetime.datetime.combine(date, start_time))
                end_dt = timezone.make_aware(datetime.datetime.combine(date, end_time))

                # Check if slot already exists
                slot_exists = AvailabilitySlot.objects.filter(
                    doctor=doc,
                    start_time=start_dt
                ).exists()

                if not slot_exists:
                    AvailabilitySlot.objects.create(
                        doctor=doc,
                        start_time=start_dt,
                        end_time=end_dt
                    )
                    slots_created += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {slots_created} new availability slots!"))
