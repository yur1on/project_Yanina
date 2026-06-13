from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, DateTimeField, F, IntegerField, Prefetch, Value, When
from django.http import JsonResponse
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.booking.availability import AvailabilityService
from apps.booking.models import Appointment
from apps.booking.services import BookingService
from apps.catalog.models import Master, MasterService, Service, ServiceCategory
from apps.clients.models import Client, ClientNote
from apps.core.forms import (
    DashboardAppointmentCreateForm,
    DashboardAppointmentEditForm,
    DashboardClientCreateForm,
    DashboardClientEditForm,
    DashboardClientNoteCreateForm,
    DashboardTimeOffCreateForm,
    DashboardTimeOffEditForm,
)
from apps.schedule.models import ScheduleException, TimeBlock, WorkingHours

WEEKDAY_LABELS_RU = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс",
}


def apply_appointment_search(queryset, search_query):
    search_query = (search_query or "").strip()
    if not search_query:
        return queryset

    terms = [term.casefold() for term in search_query.split() if term]
    if not terms:
        return queryset

    matched_ids = []
    for appointment in queryset:
        values = [
            appointment.client.first_name,
            appointment.client.last_name,
            f"{appointment.client.first_name} {appointment.client.last_name}".strip(),
            appointment.client.phone,
            appointment.client.email,
            appointment.master.display_name,
            appointment.service.name,
        ]
        haystack = " ".join(str(value or "").casefold() for value in values if value)
        if all(term in haystack for term in terms):
            matched_ids.append(appointment.id)

    return queryset.filter(id__in=matched_ids)


def apply_client_search(queryset, search_query):
    search_query = (search_query or "").strip()
    if not search_query:
        return queryset

    terms = [term.casefold() for term in search_query.split() if term]
    if not terms:
        return queryset

    matched_ids = []
    for client in queryset:
        values = [
            client.first_name,
            client.last_name,
            f"{client.first_name} {client.last_name}".strip(),
            client.phone,
            client.email,
        ]
        haystack = " ".join(str(value or "").casefold() for value in values if value)
        if all(term in haystack for term in terms):
            matched_ids.append(client.id)

    return queryset.filter(id__in=matched_ids)


def weekday_label_ru(target_date):
    return WEEKDAY_LABELS_RU[target_date.isoweekday()]


class HomePageView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = ServiceCategory.objects.filter(
            is_active=True
        ).order_by("sort_order", "name")
        context["services"] = (
            Service.objects.filter(is_active=True)
            .select_related("category")
            .order_by("sort_order", "name")[:6]
        )
        context["masters"] = (
            Master.objects.filter(is_active=True)
            .select_related("user")
            .order_by("sort_order", "display_name")[:4]
        )
        return context


class ContactsPageView(TemplateView):
    template_name = "core/contacts.html"


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"

    def get(self, request, *args, **kwargs):
        return redirect("core:dashboard_appointments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        now = timezone.localtime()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        today_start = timezone.make_aware(
            datetime.combine(today, time.min),
            timezone.get_current_timezone(),
        )
        tomorrow_start = timezone.make_aware(
            datetime.combine(tomorrow, time.min),
            timezone.get_current_timezone(),
        )

        appointments_today = (
            Appointment.objects.select_related("client", "master", "service")
            .filter(start_at__gte=today_start, start_at__lt=tomorrow_start)
            .order_by("start_at")
        )

        upcoming_appointments = (
            Appointment.objects.select_related("client", "master", "service")
            .filter(start_at__gte=now)
            .order_by("start_at")[:10]
        )

        pending_appointments = (
            Appointment.objects.select_related("client", "master", "service")
            .filter(
                status=Appointment.Status.PENDING,
                start_at__gte=now,
            )
            .order_by("start_at")[:8]
        )

        week_days = []
        week_end = today + timedelta(days=6)
        appointments_this_week = (
            Appointment.objects.filter(
                start_at__date__gte=today,
                start_at__date__lte=week_end,
            )
            .values("start_at__date", "status")
            .order_by("start_at__date")
        )
        appointments_map = {}
        for item in appointments_this_week:
            target_date = item["start_at__date"]
            status = item["status"]
            day_stats = appointments_map.setdefault(
                target_date,
                {
                    "total": 0,
                    "pending": 0,
                    "confirmed": 0,
                },
            )
            day_stats["total"] += 1
            if status == Appointment.Status.PENDING:
                day_stats["pending"] += 1
            if status == Appointment.Status.CONFIRMED:
                day_stats["confirmed"] += 1

        for offset in range(7):
            target_date = today + timedelta(days=offset)
            day_stats = appointments_map.get(
                target_date,
                {"total": 0, "pending": 0, "confirmed": 0},
            )
            week_days.append(
                {
                    "date": target_date,
                    "label": target_date.strftime("%d.%m"),
                    "weekday": weekday_label_ru(target_date),
                    "total": day_stats["total"],
                    "pending": day_stats["pending"],
                    "confirmed": day_stats["confirmed"],
                    "calendar_url": f"{reverse('core:dashboard_calendar')}?{urlencode({'date': target_date.isoformat()})}",
                    "is_today": target_date == today,
                }
            )

        context["appointments_today"] = appointments_today
        context["upcoming_appointments"] = upcoming_appointments
        context["pending_appointments"] = pending_appointments
        context["today_total"] = appointments_today.count()
        context["today_pending"] = appointments_today.filter(
            status=Appointment.Status.PENDING
        ).count()
        context["today_confirmed"] = appointments_today.filter(
            status=Appointment.Status.CONFIRMED
        ).count()
        context["today_completed"] = appointments_today.filter(
            status=Appointment.Status.COMPLETED
        ).count()
        context["today_no_show"] = appointments_today.filter(
            status=Appointment.Status.NO_SHOW
        ).count()
        context["active_clients_today"] = appointments_today.values("client_id").distinct().count()
        context["week_days"] = week_days
        context["pending_total"] = Appointment.objects.filter(
            status=Appointment.Status.PENDING,
            start_at__gte=now,
        ).count()
        context["cancelled_recent"] = Appointment.objects.filter(
            status=Appointment.Status.CANCELLED,
            cancelled_at__date__gte=today - timedelta(days=7),
        ).count()
        context["no_show_recent"] = Appointment.objects.filter(
            status=Appointment.Status.NO_SHOW,
            start_at__date__gte=today - timedelta(days=30),
        ).count()
        context["today_calendar_url"] = f"{reverse('core:dashboard_calendar')}?{urlencode({'date': today.isoformat()})}"
        context["today_appointments_url"] = f"{reverse('core:dashboard_appointments')}?{urlencode({'status': '', 'master': '', 'q': ''})}"
        context["pending_appointments_url"] = f"{reverse('core:dashboard_appointments')}?{urlencode({'status': Appointment.Status.PENDING})}"
        context["confirmed_today_url"] = f"{reverse('core:dashboard_appointments')}?{urlencode({'status': Appointment.Status.CONFIRMED})}"

        return context


class DashboardAppointmentListView(LoginRequiredMixin, ListView):
    model = Appointment
    template_name = "dashboard/appointments.html"
    context_object_name = "appointments"
    paginate_by = 20

    def get_queryset(self):
        now = timezone.now()
        queryset = (
            Appointment.objects.select_related("client", "master", "service")
            .annotate(
                is_past_order=Case(
                    When(start_at__lt=now, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                upcoming_sort_at=Case(
                    When(start_at__gte=now, then=F("start_at")),
                    default=Value(None),
                    output_field=DateTimeField(),
                ),
                past_sort_at=Case(
                    When(start_at__lt=now, then=F("start_at")),
                    default=Value(None),
                    output_field=DateTimeField(),
                ),
            )
            .order_by("is_past_order", "upcoming_sort_at", "-past_sort_at")
        )

        status = self.request.GET.get("status")
        master_id = self.request.GET.get("master")
        q = self.request.GET.get("q")

        if status:
            queryset = queryset.filter(status=status)

        if master_id:
            queryset = queryset.filter(master_id=master_id)

        return apply_appointment_search(queryset, q)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.localtime()
        today = now.date()
        tomorrow = today + timedelta(days=1)

        today_start = timezone.make_aware(
            datetime.combine(today, time.min),
            timezone.get_current_timezone(),
        )
        tomorrow_start = timezone.make_aware(
            datetime.combine(tomorrow, time.min),
            timezone.get_current_timezone(),
        )

        appointments_today = (
            Appointment.objects.select_related("client", "master", "service")
            .filter(start_at__gte=today_start, start_at__lt=tomorrow_start)
            .order_by("start_at")
        )

        pending_appointments = (
            Appointment.objects.select_related("client", "master", "service")
            .filter(
                status=Appointment.Status.PENDING,
                start_at__gte=now,
            )
            .order_by("start_at")[:4]
        )

        week_days = []
        week_end = today + timedelta(days=4)
        appointments_this_week = (
            Appointment.objects.filter(
                start_at__date__gte=today,
                start_at__date__lte=week_end,
            )
            .values("start_at__date")
            .order_by("start_at__date")
        )
        appointments_map = {}
        for item in appointments_this_week:
            target_date = item["start_at__date"]
            appointments_map[target_date] = appointments_map.get(target_date, 0) + 1

        for offset in range(5):
            target_date = today + timedelta(days=offset)
            week_days.append(
                {
                    "label": target_date.strftime("%d.%m"),
                    "weekday": weekday_label_ru(target_date),
                    "total": appointments_map.get(target_date, 0),
                    "calendar_url": f"{reverse('core:dashboard_calendar')}?{urlencode({'date': target_date.isoformat()})}",
                    "is_today": target_date == today,
                }
            )

        context["statuses"] = Appointment.Status.choices
        context["masters"] = Master.objects.filter(is_active=True).order_by(
            "display_name"
        )
        context["current_status"] = self.request.GET.get("status", "")
        context["current_master"] = self.request.GET.get("master", "")
        context["current_q"] = self.request.GET.get("q", "")
        context["today_total"] = appointments_today.count()
        context["pending_total"] = Appointment.objects.filter(
            status=Appointment.Status.PENDING,
            start_at__gte=now,
        ).count()
        context["today_confirmed"] = appointments_today.filter(
            status=Appointment.Status.CONFIRMED
        ).count()
        context["today_no_show"] = appointments_today.filter(
            status=Appointment.Status.NO_SHOW
        ).count()
        context["pending_appointments"] = pending_appointments
        context["week_days"] = week_days
        context["today_calendar_url"] = f"{reverse('core:dashboard_calendar')}?{urlencode({'date': today.isoformat()})}"
        context["today_date"] = today
        context["tomorrow_date"] = tomorrow
        return context


class DashboardCalendarView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/calendar.html"

    START_HOUR = 8
    END_HOUR = 21
    DAY_GRID_STEP_MINUTES = 30

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_date = self._get_selected_date()
        selected_master_id = self.request.GET.get("master", "")
        q = self.request.GET.get("q", "")

        masters = Master.objects.filter(is_active=True).order_by("display_name")
        services = Service.objects.filter(is_active=True).order_by("sort_order", "name")
        clients = Client.objects.all().order_by("first_name", "last_name", "phone")[:300]

        appointments = (
            Appointment.objects.select_related("client", "master", "service")
            .filter(start_at__date=selected_date)
            .order_by("start_at")
        )

        timeoffs = (
            TimeBlock.objects.select_related("master", "created_by")
            .filter(start_at__date=selected_date)
            .order_by("start_at")
        )

        exceptions = (
            ScheduleException.objects.select_related("master")
            .filter(date=selected_date)
            .order_by("master__display_name", "start_time")
        )

        if selected_master_id:
            appointments = appointments.filter(master_id=selected_master_id)
            timeoffs = timeoffs.filter(master_id=selected_master_id)
            exceptions = exceptions.filter(master_id=selected_master_id)

        appointments = apply_appointment_search(appointments, q)

        hours = list(range(self.START_HOUR, self.END_HOUR + 1))
        calendar_rows = []

        for hour in hours:
            row_appointments = []
            for appointment in appointments:
                local_start = timezone.localtime(appointment.start_at)
                if local_start.hour == hour:
                    row_appointments.append(appointment)

            row_timeoffs = []
            for timeoff in timeoffs:
                local_start = timezone.localtime(timeoff.start_at)
                if local_start.hour == hour:
                    row_timeoffs.append(timeoff)

            row_exceptions = []
            for exception in exceptions:
                if exception.is_full_day:
                    row_exceptions.append(exception)
                elif exception.start_time and exception.start_time.hour == hour:
                    row_exceptions.append(exception)

            calendar_rows.append(
                {
                    "hour_label": f"{hour:02d}:00",
                    "appointments": row_appointments,
                    "timeoffs": row_timeoffs,
                    "exceptions": row_exceptions,
                }
            )

        day_grid_rows = []
        selected_master = None

        if selected_master_id:
            selected_master = masters.filter(id=selected_master_id).first()
            if selected_master:
                day_grid_rows = self._build_day_grid(
                    master=selected_master,
                    target_date=selected_date,
                )

        context["selected_date"] = selected_date
        context["selected_master_id"] = str(selected_master_id)
        context["selected_master"] = selected_master
        context["masters"] = masters
        context["services"] = services
        context["clients"] = clients
        context["calendar_rows"] = calendar_rows
        context["appointments"] = appointments
        context["timeoffs"] = timeoffs
        context["exceptions"] = exceptions
        context["day_grid_rows"] = day_grid_rows
        context["prev_date"] = (selected_date - timedelta(days=1)).isoformat()
        context["next_date"] = (selected_date + timedelta(days=1)).isoformat()
        context["current_q"] = q

        return context

    def _get_selected_date(self):
        date_str = self.request.GET.get("date")
        if not date_str:
            return timezone.localdate()

        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return timezone.localdate()

    def _build_day_grid(self, *, master: Master, target_date):
        tz = timezone.get_current_timezone()
        day_start = timezone.make_aware(
            datetime.combine(target_date, time(hour=self.START_HOUR, minute=0)),
            tz,
        )
        day_end = timezone.make_aware(
            datetime.combine(target_date, time(hour=self.END_HOUR, minute=30)),
            tz,
        )

        appointments = list(
            Appointment.objects.select_related("client", "service")
            .filter(
                master=master,
                start_at__lt=day_end,
                end_at__gt=day_start,
            )
            .order_by("start_at")
        )

        timeoffs = list(
            TimeBlock.objects.filter(
                master=master,
                start_at__lt=day_end,
                end_at__gt=day_start,
            ).order_by("start_at")
        )

        exceptions = list(
            ScheduleException.objects.filter(
                master=master,
                date=target_date,
            ).order_by("start_time")
        )

        working_hours = WorkingHours.objects.filter(
            master=master,
            weekday=target_date.isoweekday(),
        ).first()

        rows = []
        cursor = day_start
        step = timedelta(minutes=self.DAY_GRID_STEP_MINUTES)

        while cursor < day_end:
            slot_end = cursor + step
            slot_type = "free"
            slot_title = "Свободно"
            slot_meta = ""
            slot_actions = {}
            slot_obj = None

            slot_dt = timezone.localtime(cursor)
            slot_date_value = slot_dt.date().isoformat()
            slot_time_value = slot_dt.strftime("%H:%M")
            slot_end_value = timezone.localtime(slot_end).strftime("%H:%M")

            if self._is_outside_working_hours(
                cursor=cursor,
                slot_end=slot_end,
                working_hours=working_hours,
                target_date=target_date,
                tz=tz,
            ):
                slot_type = "outside"
                slot_title = "Вне рабочего времени"
            else:
                matched_exception = self._find_matching_exception(
                    exceptions=exceptions,
                    cursor=cursor,
                    slot_end=slot_end,
                    target_date=target_date,
                    tz=tz,
                )
                if matched_exception:
                    slot_type = "exception"
                    slot_title = matched_exception.get_exception_type_display()
                    slot_meta = matched_exception.reason or ""
                    slot_obj = matched_exception
                else:
                    matched_timeoff = self._find_matching_timeoff(
                        timeoffs=timeoffs,
                        cursor=cursor,
                        slot_end=slot_end,
                    )
                    if matched_timeoff:
                        slot_type = "blocked"
                        slot_title = "Блокировка"
                        slot_meta = matched_timeoff.reason
                        slot_obj = matched_timeoff
                        slot_actions = {
                            "edit_url": f"/dashboard/timeoff/{matched_timeoff.id}/edit/",
                        }
                    else:
                        matched_appointment = self._find_matching_appointment(
                            appointments=appointments,
                            cursor=cursor,
                            slot_end=slot_end,
                        )
                        if matched_appointment:
                            slot_type = "busy"
                            slot_title = f"{matched_appointment.client}"
                            slot_meta = f"{matched_appointment.service} · {matched_appointment.get_status_display()}"
                            slot_obj = matched_appointment
                            slot_actions = {
                                "edit_url": f"/dashboard/appointments/{matched_appointment.id}/edit/",
                                "move_url": f"/dashboard/appointments/{matched_appointment.id}/quick-move/",
                            }
                        else:
                            slot_actions = {
                                "master_id": master.id,
                                "date": slot_date_value,
                                "time": slot_time_value,
                                "end_time": slot_end_value,
                                "slot_value": cursor.isoformat(),
                            }

            rows.append(
                {
                    "time_label": timezone.localtime(cursor).strftime("%H:%M"),
                    "end_label": timezone.localtime(slot_end).strftime("%H:%M"),
                    "slot_type": slot_type,
                    "slot_title": slot_title,
                    "slot_meta": slot_meta,
                    "slot_obj": slot_obj,
                    "slot_actions": slot_actions,
                }
            )

            cursor = slot_end

        return rows

    def _is_outside_working_hours(self, *, cursor, slot_end, working_hours, target_date, tz):
        if not working_hours:
            return True

        if working_hours.is_day_off:
            return True

        if not working_hours.start_time or not working_hours.end_time:
            return True

        working_start = timezone.make_aware(
            datetime.combine(target_date, working_hours.start_time),
            tz,
        )
        working_end = timezone.make_aware(
            datetime.combine(target_date, working_hours.end_time),
            tz,
        )

        return cursor < working_start or slot_end > working_end

    def _find_matching_exception(self, *, exceptions, cursor, slot_end, target_date, tz):
        for exception in exceptions:
            if exception.is_full_day:
                return exception

            if not exception.start_time or not exception.end_time:
                continue

            exception_start = timezone.make_aware(
                datetime.combine(target_date, exception.start_time),
                tz,
            )
            exception_end = timezone.make_aware(
                datetime.combine(target_date, exception.end_time),
                tz,
            )

            if cursor < exception_end and slot_end > exception_start:
                return exception

        return None

    def _find_matching_timeoff(self, *, timeoffs, cursor, slot_end):
        for timeoff in timeoffs:
            if cursor < timeoff.end_at and slot_end > timeoff.start_at:
                return timeoff
        return None

    def _find_matching_appointment(self, *, appointments, cursor, slot_end):
        for appointment in appointments:
            if cursor < appointment.end_at and slot_end > appointment.start_at:
                return appointment
        return None


class DashboardAppointmentStatusUpdateView(LoginRequiredMixin, View):
    ALLOWED_STATUSES = {
        "confirm": Appointment.Status.CONFIRMED,
        "complete": Appointment.Status.COMPLETED,
        "cancel": Appointment.Status.CANCELLED,
        "no_show": Appointment.Status.NO_SHOW,
    }

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment, pk=pk)
        action = request.POST.get("action")
        redirect_to = request.POST.get("redirect_to") or "core:dashboard_appointments"

        new_status = self.ALLOWED_STATUSES.get(action)
        if not new_status:
            messages.error(request, "Некорректное действие.")
            return redirect(redirect_to)

        comment = (request.POST.get("comment") or "").strip()

        if new_status == Appointment.Status.CANCELLED and not comment:
            messages.error(request, "Укажите причину отмены записи.")
            return redirect(redirect_to)

        if new_status == Appointment.Status.NO_SHOW and not comment:
            comment = "Клиент не пришёл"

        try:
            BookingService.change_status(
                appointment=appointment,
                new_status=new_status,
                changed_by=request.user,
                comment=comment,
            )
            messages.success(request, "Статус записи обновлён.")
        except Exception as exc:
            messages.error(request, f"Не удалось обновить статус: {exc}")

        return redirect(redirect_to)


class DashboardAppointmentCreateView(LoginRequiredMixin, View):
    template_name = "dashboard/appointment_create.html"

    def get(self, request):
        initial = {}
        client_id = request.GET.get("client")
        service_id = request.GET.get("service")
        master_id = request.GET.get("master")
        booking_date = request.GET.get("date")
        slot_value = request.GET.get("slot")

        if client_id:
            initial["client"] = client_id
        if service_id:
            initial["service"] = service_id
        if master_id:
            initial["master"] = master_id
        if booking_date:
            try:
                initial["booking_date"] = datetime.strptime(
                    booking_date, "%Y-%m-%d"
                ).date()
            except ValueError:
                pass
        if slot_value:
            initial["slot"] = slot_value

        form = DashboardAppointmentCreateForm(initial=initial)

        if slot_value:
            form.fields["slot"].choices = [(slot_value, "Выбранный слот")]

        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = DashboardAppointmentCreateForm(request.POST)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        client = form.cleaned_data["client"]
        service = form.cleaned_data["service"]
        master = form.cleaned_data["master"]
        comment = form.cleaned_data["comment"]
        slot_value = form.cleaned_data["slot"]

        start_at = datetime.fromisoformat(slot_value)
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(
                start_at, timezone.get_current_timezone()
            )

        try:
            BookingService.create_appointment(
                client=client,
                master=master,
                service=service,
                start_at=start_at,
                source=Appointment.Source.ADMIN,
                status=Appointment.Status.CONFIRMED,
                comment=comment,
                created_by=request.user,
            )
            messages.success(request, "Запись успешно создана.")

            next_url = request.POST.get("next")
            if next_url:
                return redirect(next_url)

            return redirect("core:dashboard_appointments")
        except Exception as exc:
            form.add_error(None, str(exc))
            return render(request, self.template_name, {"form": form})


class DashboardAppointmentEditView(LoginRequiredMixin, View):
    template_name = "dashboard/appointment_edit.html"

    def get(self, request, pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related("client", "master", "service"),
            pk=pk,
        )

        initial = {
            "client": appointment.client_id,
            "service": appointment.service_id,
            "master": appointment.master_id,
            "booking_date": timezone.localtime(appointment.start_at).date(),
            "slot": appointment.start_at.isoformat(),
            "comment": appointment.comment,
        }

        form = DashboardAppointmentEditForm(
            initial=initial,
            appointment=appointment,
        )
        return render(
            request,
            self.template_name,
            {"form": form, "appointment": appointment},
        )

    def post(self, request, pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related("client", "master", "service"),
            pk=pk,
        )
        form = DashboardAppointmentEditForm(
            request.POST,
            appointment=appointment,
        )

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form, "appointment": appointment},
            )

        client = form.cleaned_data["client"]
        service = form.cleaned_data["service"]
        master = form.cleaned_data["master"]
        comment = form.cleaned_data["comment"]
        slot_value = form.cleaned_data["slot"]

        start_at = datetime.fromisoformat(slot_value)
        if timezone.is_naive(start_at):
            start_at = timezone.make_aware(
                start_at, timezone.get_current_timezone()
            )

        availability = BookingService.check_availability(
            master=master,
            service=service,
            start_at=start_at,
            exclude_appointment_id=appointment.id,
        )
        if not availability.is_available:
            form.add_error(None, availability.message)
            return render(
                request,
                self.template_name,
                {"form": form, "appointment": appointment},
            )

        effective_duration_minutes = BookingService.get_effective_duration_minutes(
            master,
            service,
        )
        effective_price = BookingService.get_effective_price(master, service)
        end_at = start_at + timedelta(minutes=effective_duration_minutes)

        appointment.client = client
        appointment.service = service
        appointment.master = master
        appointment.start_at = start_at
        appointment.end_at = end_at
        appointment.price = effective_price
        appointment.comment = comment
        appointment.save()

        messages.success(request, "Запись успешно обновлена.")
        return redirect("core:dashboard_appointments")


class DashboardAppointmentQuickMoveView(LoginRequiredMixin, View):
    template_name = "dashboard/appointment_quick_move.html"

    def get(self, request, pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related("client", "master", "service"),
            pk=pk,
        )
        initial_date = timezone.localtime(appointment.start_at).date()
        context = {
            "appointment": appointment,
            "selected_date": initial_date,
            "selected_date_value": initial_date.isoformat(),
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related("client", "master", "service"),
            pk=pk,
        )

        booking_date_str = request.POST.get("booking_date")
        slot_value = request.POST.get("slot")

        try:
            selected_date = datetime.strptime(booking_date_str, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            messages.error(request, "Некорректная дата.")
            current_date = timezone.localtime(appointment.start_at).date()
            return render(
                request,
                self.template_name,
                {
                    "appointment": appointment,
                    "selected_date": current_date,
                    "selected_date_value": current_date.isoformat(),
                },
            )

        if not slot_value:
            messages.error(request, "Выберите новый слот.")
            return render(
                request,
                self.template_name,
                {
                    "appointment": appointment,
                    "selected_date": selected_date,
                    "selected_date_value": selected_date.isoformat(),
                },
            )

        try:
            start_at = datetime.fromisoformat(slot_value)
            if timezone.is_naive(start_at):
                start_at = timezone.make_aware(
                    start_at, timezone.get_current_timezone()
                )
        except ValueError:
            messages.error(request, "Некорректный слот времени.")
            return render(
                request,
                self.template_name,
                {
                    "appointment": appointment,
                    "selected_date": selected_date,
                    "selected_date_value": selected_date.isoformat(),
                },
            )

        availability = BookingService.check_availability(
            master=appointment.master,
            service=appointment.service,
            start_at=start_at,
            exclude_appointment_id=appointment.id,
        )
        if not availability.is_available:
            messages.error(request, availability.message)
            return render(
                request,
                self.template_name,
                {
                    "appointment": appointment,
                    "selected_date": selected_date,
                    "selected_date_value": selected_date.isoformat(),
                },
            )

        effective_duration_minutes = BookingService.get_effective_duration_minutes(
            appointment.master,
            appointment.service,
        )
        end_at = start_at + timedelta(minutes=effective_duration_minutes)

        appointment.start_at = start_at
        appointment.end_at = end_at
        appointment.save()

        messages.success(request, "Запись успешно перенесена.")
        redirect_date = timezone.localtime(start_at).date().isoformat()
        return redirect(
            f"/dashboard/calendar/?date={redirect_date}&master={appointment.master_id}"
        )


class DashboardAppointmentDeleteView(LoginRequiredMixin, View):
    template_name = "dashboard/appointment_delete.html"

    def get(self, request, pk):
        appointment = get_object_or_404(
            Appointment.objects.select_related("client", "master", "service"),
            pk=pk,
        )
        return render(request, self.template_name, {"appointment": appointment})

    def post(self, request, pk):
        appointment = get_object_or_404(Appointment, pk=pk)
        cancel_reason = (request.POST.get("cancel_reason") or "").strip()
        if not cancel_reason:
            messages.error(request, "Укажите причину отмены записи.")
            return render(request, self.template_name, {"appointment": appointment})

        try:
            BookingService.change_status(
                appointment=appointment,
                new_status=Appointment.Status.CANCELLED,
                changed_by=request.user,
                comment=cancel_reason,
            )
        except Exception as exc:
            messages.error(request, f"Не удалось отменить запись: {exc}")
            return render(request, self.template_name, {"appointment": appointment})

        messages.success(request, "Запись отменена и сохранена в истории клиента.")
        return redirect("core:dashboard_appointments")


class DashboardClientCreateView(LoginRequiredMixin, View):
    template_name = "dashboard/client_create.html"

    def get(self, request):
        form = DashboardClientCreateForm()
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "back_url": self._build_back_url(request),
            },
        )

    def post(self, request):
        form = DashboardClientCreateForm(request.POST)
        back_url = self._build_back_url(request)

        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "back_url": back_url,
                },
            )

        client = form.save()
        messages.success(request, "Клиент успешно создан.")

        params = self._collect_return_params(request)
        params["client"] = client.id

        return redirect(f"{back_url}?{urlencode(params)}")

    def _build_back_url(self, request):
        return (
            request.GET.get("next")
            or request.POST.get("next")
            or "/dashboard/appointments/create/"
        )

    def _collect_return_params(self, request):
        source = request.GET if request.method == "GET" else request.POST
        params = {}

        for key in ["service", "master", "date"]:
            value = source.get(key)
            if value:
                params[key] = value

        return params


class DashboardClientDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = "dashboard/client_detail.html"
    context_object_name = "client"

    def get_queryset(self):
        return Client.objects.prefetch_related(
            "tags",
            Prefetch(
                "client_notes",
                queryset=ClientNote.objects.select_related("author").order_by(
                    "-created_at"
                ),
            ),
            Prefetch(
                "appointments",
                queryset=Appointment.objects.select_related(
                    "master", "service"
                ).order_by("-start_at"),
            ),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate().isoformat()

        active_services = Service.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )[:12]
        active_masters = Master.objects.filter(is_active=True).order_by(
            "sort_order", "display_name"
        )[:8]
        master_services = (
            MasterService.objects.select_related("master", "service")
            .filter(
                is_active=True,
                master__is_active=True,
                service__is_active=True,
            )
            .order_by("master__display_name", "service__name")[:20]
        )

        context["new_appointment_url"] = (
            f"/dashboard/appointments/create/?client={self.object.id}"
        )
        context["new_appointment_today_url"] = (
            f"/dashboard/appointments/create/?client={self.object.id}&date={today}"
        )
        context["note_form"] = DashboardClientNoteCreateForm()
        context["active_services"] = active_services
        context["active_masters"] = active_masters
        context["master_services"] = master_services
        context["today_value"] = today
        return context


class DashboardClientEditView(LoginRequiredMixin, View):
    template_name = "dashboard/client_edit.html"

    def get(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        form = DashboardClientEditForm(instance=client)
        return render(request, self.template_name, {"form": form, "client": client})

    def post(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        form = DashboardClientEditForm(request.POST, instance=client)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "client": client})

        form.save()
        messages.success(request, "Данные клиента обновлены.")
        return redirect("core:dashboard_client_detail", pk=client.pk)


class DashboardClientNoteCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        form = DashboardClientNoteCreateForm(request.POST)

        if not form.is_valid():
            messages.error(request, "Не удалось добавить заметку. Проверьте текст.")
            return redirect("core:dashboard_client_detail", pk=client.pk)

        note = form.save(commit=False)
        note.client = client
        note.author = request.user
        note.save()

        messages.success(request, "Заметка добавлена.")
        return redirect("core:dashboard_client_detail", pk=client.pk)


class DashboardTimeOffCreateView(LoginRequiredMixin, View):
    template_name = "dashboard/timeoff_create.html"

    def get(self, request):
        initial = {}
        master_id = request.GET.get("master")
        block_date = request.GET.get("date")
        start_time = request.GET.get("start_time")

        if master_id:
            initial["master"] = master_id
        if block_date:
            try:
                initial["block_date"] = datetime.strptime(
                    block_date, "%Y-%m-%d"
                ).date()
            except ValueError:
                pass
        if start_time:
            try:
                parsed_start = datetime.strptime(start_time, "%H:%M").time()
                initial["start_time"] = parsed_start
                initial["end_time"] = (
                    datetime.combine(datetime.today(), parsed_start) + timedelta(minutes=30)
                ).time()
            except ValueError:
                pass

        form = DashboardTimeOffCreateForm(initial=initial)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = DashboardTimeOffCreateForm(request.POST, created_by=request.user)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form})

        timeoff = form.save(commit=False)
        timeoff.created_by = request.user
        timeoff.save()

        messages.success(request, "Блокировка времени успешно создана.")

        next_url = request.POST.get("next")
        if next_url:
            return redirect(next_url)

        redirect_date = timezone.localtime(timeoff.start_at).date().isoformat()
        return redirect(f"/dashboard/calendar/?date={redirect_date}&master={timeoff.master_id}")


class DashboardTimeOffEditView(LoginRequiredMixin, View):
    template_name = "dashboard/timeoff_edit.html"

    def get(self, request, pk):
        timeoff = get_object_or_404(TimeBlock.objects.select_related("master"), pk=pk)
        local_start = timezone.localtime(timeoff.start_at)
        local_end = timezone.localtime(timeoff.end_at)

        initial = {
            "master": timeoff.master_id,
            "block_date": local_start.date(),
            "start_time": local_start.time().replace(second=0, microsecond=0),
            "end_time": local_end.time().replace(second=0, microsecond=0),
            "reason": timeoff.reason,
        }

        form = DashboardTimeOffEditForm(instance=timeoff, initial=initial)
        return render(request, self.template_name, {"form": form, "timeoff": timeoff})

    def post(self, request, pk):
        timeoff = get_object_or_404(TimeBlock.objects.select_related("master"), pk=pk)
        form = DashboardTimeOffEditForm(request.POST, instance=timeoff, created_by=request.user)

        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "timeoff": timeoff})

        form.save()
        messages.success(request, "Блокировка времени обновлена.")

        redirect_date = timezone.localtime(timeoff.start_at).date().isoformat()
        return redirect(f"/dashboard/calendar/?date={redirect_date}&master={timeoff.master_id}")


class DashboardTimeOffDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        timeoff = get_object_or_404(TimeBlock, pk=pk)

        redirect_date = request.POST.get("date")
        redirect_master = request.POST.get("master")

        if not redirect_date:
            redirect_date = timezone.localtime(timeoff.start_at).date().isoformat()

        if not redirect_master:
            redirect_master = str(timeoff.master_id)

        timeoff.delete()
        messages.success(request, "Блокировка времени удалена.")

        return redirect(f"/dashboard/calendar/?date={redirect_date}&master={redirect_master}")


class DashboardAvailableMastersView(LoginRequiredMixin, View):
    def get(self, request):
        service_id = request.GET.get("service")
        selected_master_id = request.GET.get("selected_master")

        queryset = Master.objects.filter(is_active=True)

        if service_id:
            queryset = queryset.filter(
                master_services__service_id=service_id,
                master_services__is_active=True,
            ).distinct()

        queryset = queryset.order_by("sort_order", "display_name")

        data = [
            {
                "id": master.id,
                "name": master.display_name,
                "selected": str(master.id) == str(selected_master_id),
            }
            for master in queryset
        ]
        return JsonResponse({"masters": data})


class DashboardAvailableServicesView(LoginRequiredMixin, View):
    def get(self, request):
        master_id = request.GET.get("master")
        selected_service_id = request.GET.get("selected_service")

        queryset = Service.objects.filter(is_active=True)

        if master_id:
            queryset = queryset.filter(
                master_services__master_id=master_id,
                master_services__is_active=True,
                master_services__master__is_active=True,
            ).distinct()

        queryset = queryset.order_by("sort_order", "name")

        data = [
            {
                "id": service.id,
                "name": service.name,
                "selected": str(service.id) == str(selected_service_id),
            }
            for service in queryset
        ]
        return JsonResponse({"services": data})


class DashboardAvailableSlotsView(LoginRequiredMixin, View):
    def get(self, request):
        service_id = request.GET.get("service")
        master_id = request.GET.get("master")
        booking_date = request.GET.get("date")
        appointment_id = request.GET.get("appointment")

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

        if appointment_id:
            try:
                appointment = Appointment.objects.get(pk=appointment_id)
                local_start = timezone.localtime(appointment.start_at)
                if local_start.date() == parsed_date:
                    current_value = appointment.start_at.isoformat()
                    if current_value not in {item["value"] for item in data}:
                        data.insert(
                            0,
                            {
                                "value": current_value,
                                "label": f"{local_start.strftime('%H:%M')} (текущее время записи)",
                            },
                        )
            except Appointment.DoesNotExist:
                pass

        return JsonResponse({"slots": data})


class DashboardAvailableClientsView(LoginRequiredMixin, View):
    def get(self, request):
        q = request.GET.get("q", "").strip()

        queryset = Client.objects.all().order_by("first_name", "last_name", "phone")
        queryset = apply_client_search(queryset, q)

        clients = queryset[:20]

        data = [
            {
                "id": client.id,
                "name": str(client),
                "phone": client.phone,
            }
            for client in clients
        ]
        return JsonResponse({"clients": data})
