from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Doctor endpoints
    path('doctor/dashboard/', views.doctor_dashboard, name='doctor_dashboard'),
    path('doctor/slot/create/', views.create_slot, name='create_slot'),
    path('doctor/booking/<int:booking_id>/accept/', views.accept_booking, name='accept_booking'),
    path('doctor/booking/<int:booking_id>/reject/', views.reject_booking, name='reject_booking'),
    path('doctor/booking/<int:booking_id>/cancel/', views.cancel_booking, name='cancel_booking'),
    
    # Patient endpoints
    path('patient/dashboard/', views.patient_dashboard, name='patient_dashboard'),
    path('patient/book/<int:slot_id>/', views.book_slot, name='book_slot'),
    
    # Google OAuth2 endpoints
    path('oauth2/connect/', views.google_oauth2_connect, name='google_connect'),
    path('oauth2/callback/', views.google_oauth2_callback, name='google_callback'),
    path('oauth2/disconnect/', views.google_oauth2_disconnect, name='google_disconnect'),
]
