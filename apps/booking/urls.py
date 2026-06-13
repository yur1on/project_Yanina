from django.urls import path

from .views import (
    AvailableCalendarDaysView,
    AvailableMastersView,
    AvailableServicesView,
    AvailableSlotsView,
    BookingSuccessView,
    PublicBookingView,
)

app_name = "booking"

urlpatterns = [
    path("", PublicBookingView.as_view(), name="booking_form"),
    path("success/", BookingSuccessView.as_view(), name="booking_success"),
    path("api/masters/", AvailableMastersView.as_view(), name="available_masters"),
    path("api/services/", AvailableServicesView.as_view(), name="available_services"),
    path("api/slots/", AvailableSlotsView.as_view(), name="available_slots"),
    path("api/calendar-days/", AvailableCalendarDaysView.as_view(), name="available_calendar_days"),
]
