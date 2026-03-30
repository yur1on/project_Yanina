from datetime import datetime

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from apps.booking.availability import AvailabilityService
from apps.booking.forms import PublicBookingForm
from apps.booking.models import Appointment
from apps.booking.services import BookingService
from apps.catalog.models import Master, Service


class PublicBookingView(View):
    template_name = "booking/booking_form.html"

    def get(self, request):
        service_id = request.GET.get("service")
        master_id = request.GET.get("master")
        booking_date = request.GET.get("date")

        initial = {}

        if service_id:
            try:
                initial["service"] = int(service_id)
            except (TypeError, ValueError):
                pass

        if master_id:
            try:
                initial["master"] = int(master_id)
            except (TypeError, ValueError):
                pass

        if booking_date:
            try:
                initial["booking_date"] = datetime.strptime(booking_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        form = PublicBookingForm(initial=initial)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = PublicBookingForm(request.POST)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        client = form.get_or_create_client()
        service = form.cleaned_data["service"]
        master = form.cleaned_data["master"]
        comment = form.cleaned_data["comment"]
        slot_value = form.cleaned_data["slot"]

        start_at = datetime.fromisoformat(slot_value)
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at, timezone.get_current_timezone())

        try:
            BookingService.create_appointment(
                client=client,
                master=master,
                service=service,
                start_at=start_at,
                source=Appointment.Source.WEBSITE,
                status=Appointment.Status.PENDING,
                comment=comment,
                created_by=None,
            )
        except Exception as exc:
            form.add_error(None, str(exc))
            return render(request, self.template_name, {"form": form})

        messages.success(request, "Ваша заявка на запись успешно отправлена.")
        return redirect("booking:booking_success")


class BookingSuccessView(View):
    template_name = "booking/booking_success.html"

    def get(self, request):
        return render(request, self.template_name)


class AvailableMastersView(View):
    def get(self, request):
        service_id = request.GET.get("service")
        selected_master_id = request.GET.get("selected_master")

        if not service_id:
            return JsonResponse({"masters": []})

        masters = (
            Master.objects.filter(
                is_active=True,
                master_services__service_id=service_id,
                master_services__is_active=True,
            )
            .distinct()
            .order_by("sort_order", "display_name")
        )

        data = [
            {
                "id": master.id,
                "name": master.display_name,
                "selected": str(master.id) == str(selected_master_id),
            }
            for master in masters
        ]
        return JsonResponse({"masters": data})


class AvailableSlotsView(View):
    def get(self, request):
        service_id = request.GET.get("service")
        master_id = request.GET.get("master")
        booking_date = request.GET.get("date")

        if not service_id or not master_id or not booking_date:
            return JsonResponse({"slots": []})

        try:
            service = Service.objects.get(pk=service_id, is_active=True)
            master = Master.objects.get(pk=master_id, is_active=True)
            parsed_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        except (Service.DoesNotExist, Master.DoesNotExist, ValueError):
            return JsonResponse({"slots": []})

        slots = AvailabilityService.get_available_slots(
            master=master,
            service=service,
            target_date=parsed_date,
            slot_step_minutes=30,
        )

        data = [
            {
                "value": slot.start_at.isoformat(),
                "label": slot.label,
            }
            for slot in slots
        ]

        return JsonResponse({"slots": data})