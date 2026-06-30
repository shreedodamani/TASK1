from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone

class User(AbstractUser):
    class Role(models.TextChoices):
        DOCTOR = 'DOCTOR', 'Doctor'
        PATIENT = 'PATIENT', 'Patient'
        
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.PATIENT
    )
    specialty = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="For doctors, e.g. Cardiology, Dermatology"
    )
    gender = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')]
    )
    age = models.IntegerField(blank=True, null=True)
    
    def is_doctor(self):
        return self.role == self.Role.DOCTOR

    def is_patient(self):
        return self.role == self.Role.PATIENT

class AvailabilitySlot(models.Model):
    doctor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='availability_slots',
        limit_choices_to={'role': User.Role.DOCTOR}
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_booked = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['start_time']
        unique_together = ('doctor', 'start_time')
        
    def clean(self):
        if self.start_time and self.start_time < timezone.now():
            raise ValidationError("Availability slots cannot be set in the past.")
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")
            
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"Dr. {self.doctor.get_full_name() or self.doctor.username}: {self.start_time.strftime('%Y-%m-%d %H:%M')} - {self.end_time.strftime('%H:%M')}"

class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    patient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings_as_patient',
        limit_choices_to={'role': User.Role.PATIENT}
    )
    doctor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings_as_doctor',
        limit_choices_to={'role': User.Role.DOCTOR}
    )
    slot = models.OneToOneField(
        AvailabilitySlot,
        on_delete=models.CASCADE,
        related_name='booking'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Advanced dashboard fields
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING
    )
    disease_description = models.TextField(
        blank=True,
        null=True,
        help_text="Symptoms described by the patient"
    )
    prescription = models.TextField(
        blank=True,
        null=True,
        help_text="Prescription written by the doctor"
    )
    patient_status = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Previous status or health condition updated by doctor"
    )
    
    # Store Google Calendar Event IDs
    google_calendar_doctor_event_id = models.CharField(max_length=255, null=True, blank=True)
    google_calendar_patient_event_id = models.CharField(max_length=255, null=True, blank=True)
    
    def can_cancel(self):
        # Return True if slot start time is at least 90 minutes in the future
        time_until_slot = self.slot.start_time - timezone.now()
        return time_until_slot.total_seconds() >= 90 * 60

    def __str__(self):
        return f"Booking ({self.status}): {self.patient.username} with Dr. {self.doctor.username}"

class GoogleCredential(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='google_credential'
    )
    token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    token_uri = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    scopes = models.TextField()
    expiry = models.DateTimeField()
    
    def __str__(self):
        return f"Google Credential for {self.user.username}"
