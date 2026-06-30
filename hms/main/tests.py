import threading
from django.test import TransactionTestCase, TestCase
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import User, AvailabilitySlot, Booking

class HMSModelTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            username='doctor_test',
            email='doc@test.com',
            password='testpassword123',
            role=User.Role.DOCTOR
        )
        self.patient = User.objects.create_user(
            username='patient_test',
            email='pat@test.com',
            password='testpassword123',
            role=User.Role.PATIENT
        )

    def test_user_roles(self):
        self.assertTrue(self.doctor.is_doctor())
        self.assertFalse(self.doctor.is_patient())
        self.assertTrue(self.patient.is_patient())
        self.assertFalse(self.patient.is_doctor())

    def test_availability_slot_validation(self):
        # Time in past should raise ValidationError
        past_time = timezone.now() - timezone.timedelta(hours=2)
        end_time = timezone.now() - timezone.timedelta(hours=1)
        
        slot = AvailabilitySlot(
            doctor=self.doctor,
            start_time=past_time,
            end_time=end_time
        )
        with self.assertRaises(ValidationError):
            slot.save()

        # End time before start time should raise ValidationError
        future_start = timezone.now() + timezone.timedelta(hours=1)
        future_end = timezone.now() + timezone.timedelta(minutes=30)
        
        slot2 = AvailabilitySlot(
            doctor=self.doctor,
            start_time=future_start,
            end_time=future_end
        )
        with self.assertRaises(ValidationError):
            slot2.save()


class BookingConcurrencyTests(TransactionTestCase):
    def setUp(self):
        # We recreate objects since TransactionTestCase does not roll back in-memory changes from standard TestCase setup
        self.doctor = User.objects.create_user(
            username='con_doc',
            email='condoc@test.com',
            password='testpassword123',
            role=User.Role.DOCTOR
        )
        self.patient1 = User.objects.create_user(
            username='con_pat1',
            email='conpat1@test.com',
            password='testpassword123',
            role=User.Role.PATIENT
        )
        self.patient2 = User.objects.create_user(
            username='con_pat2',
            email='conpat2@test.com',
            password='testpassword123',
            role=User.Role.PATIENT
        )
        
        # Create a valid future slot
        self.slot = AvailabilitySlot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + timezone.timedelta(days=1, hours=2),
            end_time=timezone.now() + timezone.timedelta(days=1, hours=3)
        )

    def test_concurrent_booking_race_condition(self):
        results = []
        errors = []

        def book_for_patient(patient):
            try:
                # Simulate the book_slot view transaction block
                with transaction.atomic():
                    slot_to_book = AvailabilitySlot.objects.select_for_update().get(id=self.slot.id)
                    if slot_to_book.is_booked:
                        raise ValidationError("This slot is already booked.")
                    
                    slot_to_book.is_booked = True
                    slot_to_book.save()
                    
                    Booking.objects.create(
                        patient=patient,
                        doctor=self.doctor,
                        slot=slot_to_book
                    )
                results.append(patient.username)
            except Exception as e:
                errors.append(str(e))

        # Launch two threads to book the same slot simultaneously
        t1 = threading.Thread(target=book_for_patient, args=(self.patient1,))
        t2 = threading.Thread(target=book_for_patient, args=(self.patient2,))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # Check results: Only one patient must succeed, and the other must catch the ValidationError or Database Lock error
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        
        err_msg = errors[0].lower()
        self.assertTrue(
            "already booked" in err_msg or 
            "locked" in err_msg,
            f"Expected concurrency exception, got: {errors[0]}"
        )
        
        # Verify exactly 1 booking exists in database for this slot
        self.assertEqual(Booking.objects.filter(slot=self.slot).count(), 1)


class HMSBookingFlowTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            username='doctor_flow',
            email='docflow@test.com',
            password='testpassword123',
            role=User.Role.DOCTOR
        )
        self.patient = User.objects.create_user(
            username='patient_flow',
            email='patflow@test.com',
            password='testpassword123',
            role=User.Role.PATIENT,
            age=25,
            gender='Male'
        )
        self.slot = AvailabilitySlot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + timezone.timedelta(hours=5),
            end_time=timezone.now() + timezone.timedelta(hours=6)
        )
        self.near_slot = AvailabilitySlot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + timezone.timedelta(minutes=45),
            end_time=timezone.now() + timezone.timedelta(minutes=105)
        )

    def test_booking_starts_pending(self):
        booking = Booking.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            slot=self.slot,
            disease_description="Flu symptoms"
        )
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertEqual(booking.disease_description, "Flu symptoms")
        self.assertTrue(booking.can_cancel())

    def test_cancellation_constraint(self):
        # Booking far in the future can be cancelled
        far_booking = Booking.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            slot=self.slot,
            status=Booking.Status.CONFIRMED
        )
        self.assertTrue(far_booking.can_cancel())

        # Booking starting in 45 minutes cannot be cancelled
        near_booking = Booking.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            slot=self.near_slot,
            status=Booking.Status.CONFIRMED
        )
        self.assertFalse(near_booking.can_cancel())

