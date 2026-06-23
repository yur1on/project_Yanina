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
from apps.catalog.models import Master, MasterService, Service
from apps.notifications.services import notify_new_appointment


class PublicBookingView(View):
    template_name = "booking/booking_form.html"

    @staticmethod
    def _serialize_service(service, master_service=None):
        duration_minutes = (
            master_service.custom_duration_minutes
            if master_service and master_service.custom_duration_minutes is not None
            else service.duration_minutes
        )
        price = (
            master_service.custom_price
            if master_service and master_service.custom_price is not None
            else service.base_price
        )
        return {
            "id": service.id,
            "price": str(price),
            "duration_minutes": duration_minutes,
            "total_duration_minutes": duration_minutes
            + service.buffer_before_minutes
            + service.buffer_after_minutes,
            "prepayment_required": service.prepayment_required,
        }

    @staticmethod
    def _get_master_service_map(master, services):
        if not master or not services:
            return {}

        service_ids = [service.id for service in services]
        master_services = (
            MasterService.objects.filter(
                master=master,
                service_id__in=service_ids,
                is_active=True,
                master__is_active=True,
                service__is_active=True,
            )
            .select_related("service")
        )
        return {item.service_id: item for item in master_services}

    def _get_selected_master(self, master_id):
        if not master_id:
            return None

        return (
            Master.objects.filter(is_active=True, pk=master_id)
            .select_related("user")
            .prefetch_related("master_services__service")
            .first()
        )

    def _build_context(self, *, form, selected_master=None):
        services = list(form.fields["service"].queryset)
        master_service_map = self._get_master_service_map(selected_master, services)
        return {
            "form": form,
            "selected_master": selected_master,
            "service_meta": [
                self._serialize_service(service, master_service_map.get(service.id))
                for service in services
            ],
        }

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
        return render(
            request,
            self.template_name,
            self._build_context(
                form=form,
                selected_master=self._get_selected_master(initial.get("master")),
            ),
        )

    def post(self, request):
        form = PublicBookingForm(request.POST)
        selected_master = self._get_selected_master(request.POST.get("master"))

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                self._build_context(form=form, selected_master=selected_master),
            )

        client = form.get_or_create_client()
        service = form.cleaned_data["service"]
        master = form.cleaned_data["master"]
        comment = form.cleaned_data["comment"]
        slot_value = form.cleaned_data["slot"]

        start_at = datetime.fromisoformat(slot_value)
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(start_at, timezone.get_current_timezone())

        try:
            appointment = BookingService.create_appointment(
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
            return render(
                request,
                self.template_name,
                self._build_context(form=form, selected_master=selected_master),
            )

        request.session["last_booking_summary"] = {
            "service_name": service.name,
            "master_name": master.display_name,
            "date": timezone.localtime(appointment.start_at).strftime("%d.%m.%Y"),
            "time": timezone.localtime(appointment.start_at).strftime("%H:%M"),
            "price": str(appointment.price) if appointment.price is not None else "",
            "duration_minutes": appointment.duration_minutes,
            "prepayment_required": service.prepayment_required,
            "phone": client.phone,
        }

        notify_new_appointment(appointment)

        messages.success(request, "Ваша заявка на запись успешно отправлена.")
        return redirect("booking:booking_success")


class BookingSuccessView(View):
    template_name = "booking/booking_success.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {"booking_summary": request.session.pop("last_booking_summary", None)},
        )


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


class AvailableServicesView(View):
    def get(self, request):
        master_id = request.GET.get("master")
        selected_service_id = request.GET.get("selected_service")

        if not master_id:
            return JsonResponse({"services": []})

        master_services = (
            MasterService.objects.filter(
                master_id=master_id,
                is_active=True,
                master__is_active=True,
                service__is_active=True,
            )
            .select_related("service")
            .order_by("service__sort_order", "service__name")
        )

        data = [
            {
                "id": master_service.service.id,
                "name": master_service.service.name,
                "selected": str(master_service.service.id) == str(selected_service_id),
                "price": str(master_service.actual_price),
                "duration_minutes": master_service.actual_duration_minutes,
                "total_duration_minutes": master_service.actual_duration_minutes
                + master_service.service.buffer_before_minutes
                + master_service.service.buffer_after_minutes,
                "prepayment_required": master_service.service.prepayment_required,
            }
            for master_service in master_services
        ]
        return JsonResponse({"services": data})


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

        if not AvailabilityService.is_date_within_booking_window(parsed_date):
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


class AvailableCalendarDaysView(View):
    def get(self, request):
        service_id = request.GET.get("service")
        master_id = request.GET.get("master")
        month_value = request.GET.get("month")

        if not service_id or not master_id or not month_value:
            return JsonResponse({"days": {}})

        try:
            service = Service.objects.get(pk=service_id, is_active=True)
            master = Master.objects.get(pk=master_id, is_active=True)
            parsed_month = datetime.strptime(month_value, "%Y-%m")
        except (Service.DoesNotExist, Master.DoesNotExist, ValueError):
            return JsonResponse({"days": {}})

        latest_booking_date = AvailabilityService.get_latest_booking_date()
        requested_month_start = parsed_month.date().replace(day=1)
        if requested_month_start > latest_booking_date.replace(day=1):
            return JsonResponse({"days": {}})

        day_statuses = AvailabilityService.get_month_day_statuses(
            master=master,
            service=service,
            year=parsed_month.year,
            month=parsed_month.month,
            slot_step_minutes=30,
        )

        return JsonResponse({"days": day_statuses})
