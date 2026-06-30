from django.shortcuts import redirect
from django.contrib import messages

def doctor_required(view_func):
    def _wrapped_view_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role != 'DOCTOR':
            messages.error(request, "Access Denied: Doctors only.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view_func

def patient_required(view_func):
    def _wrapped_view_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role != 'PATIENT':
            messages.error(request, "Access Denied: Patients only.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view_func
