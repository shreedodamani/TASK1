from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, AvailabilitySlot, Booking, GoogleCredential

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Roles', {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Custom Roles', {'fields': ('role',)}),
    )
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_staff']
    list_filter = ['role', 'is_staff', 'is_superuser']

admin.site.register(User, CustomUserAdmin)
admin.site.register(AvailabilitySlot)
admin.site.register(Booking)
admin.site.register(GoogleCredential)
