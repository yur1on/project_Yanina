from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.booking.models import Appointment, AppointmentStatusHistory
from apps.catalog.models import Master, MasterService, Service
from apps.clients.models import Client
from apps.schedule.models import ScheduleException, TimeBlock, WorkingHours


@dataclass
class AvailabilityResult:
    is_available: bool
    message: str = ""


class BookingService:
    ACTIVE_APPOINTMENT_STATUSES = [
        Appointment.Status.PENDING,
        Appointment.Status.CONFIRMED,
    ]

    @staticmethod
    def get_master_service(master: Master, service: Service) -> MasterService | None:
        return (
            MasterService.objects.filter(
                master=master,
                service=service,
                is_active=True,
                master__is_active=True,
                service__is_active=True,
            )
            .select_related("master", "service")
            .first()
        )

    @staticmethod
    def get_effective_duration_minutes(master: Master, service: Service) -> int:
        master_service = BookingService.get_master_service(master, service)
        if not master_service:
            raise ValidationError("Эта услуга недоступна у выбранного мастера.")

        duration = (
            master_service.custom_duration_minutes
            if master_service.custom_duration_minutes is not None
            else service.duration_minutes
        )

        return duration + service.buffer_before_minutes + service.buffer_after_minutes

    @staticmethod
    def get_effective_price(master: Master, service: Service):
        master_service = BookingService.get_master_service(master, service)
        if not master_service:
            raise ValidationError("Эта услуга недоступна у выбранного мастера.")

        return (
            master_service.custom_price
            if master_service.custom_price is not None
            else service.base_price
        )

    @staticmethod
    def check_master_service(master: Master, service: Service) -> AvailabilityResult:
        master_service = BookingService.get_master_service(master, service)
        if not master_service:
            return AvailabilityResult(
                is_available=False,
                message="Выбранный мастер не оказывает эту услугу.",
            )
        return AvailabilityResult(is_available=True)

    @staticmethod
    def check_not_in_past(start_at: datetime) -> AvailabilityResult:
        now = timezone.now()
        if start_at <= now:
            return AvailabilityResult(
                is_available=False,
                message="Нельзя создать запись в прошедшее время.",
            )
        return AvailabilityResult(is_available=True)

    @staticmethod
    def check_working_hours(master: Master, start_at: datetime, end_at: datetime) -> AvailabilityResult:
        local_start = timezone.localtime(start_at)
        local_end = timezone.localtime(end_at)

        weekday = local_start.isoweekday()

        working_hours = WorkingHours.objects.filter(
            master=master,
            weekday=weekday,
        ).first()

        if not working_hours:
            return AvailabilityResult(
                is_available=False,
                message="Для мастера не настроено рабочее время на этот день.",
            )

        if working_hours.is_day_off:
            return AvailabilityResult(
                is_available=False,
                message="У мастера в этот день выходной.",
            )

        if not working_hours.start_time or not working_hours.end_time:
            return AvailabilityResult(
                is_available=False,
                message="Рабочее время мастера заполнено некорректно.",
            )

        if local_start.date() != local_end.date():
            return AvailabilityResult(
                is_available=False,
                message="Запись должна находиться в пределах одного календарного дня.",
            )

        working_day_start = datetime.combine(local_start.date(), working_hours.start_time)
        working_day_end = datetime.combine(local_start.date(), working_hours.end_time)

        working_day_start = timezone.make_aware(working_day_start, timezone.get_current_timezone())
        working_day_end = timezone.make_aware(working_day_end, timezone.get_current_timezone())

        if start_at < working_day_start or end_at > working_day_end:
            return AvailabilityResult(
                is_available=False,
                message="Запись выходит за пределы рабочего времени мастера.",
            )

        return AvailabilityResult(is_available=True)

    @staticmethod
    def check_schedule_exceptions(master: Master, start_at: datetime, end_at: datetime) -> AvailabilityResult:
        local_start = timezone.localtime(start_at)
        local_end = timezone.localtime(end_at)
        target_date = local_start.date()

        exceptions = ScheduleException.objects.filter(
            master=master,
            date=target_date,
        )

        for exception in exceptions:
            if exception.is_full_day:
                return AvailabilityResult(
                    is_available=False,
                    message=f"На эту дату у мастера стоит исключение: {exception.get_exception_type_display()}.",
                )

            if not exception.start_time or not exception.end_time:
                continue

            exc_start = datetime.combine(target_date, exception.start_time)
            exc_end = datetime.combine(target_date, exception.end_time)

            exc_start = timezone.make_aware(exc_start, timezone.get_current_timezone())
            exc_end = timezone.make_aware(exc_end, timezone.get_current_timezone())

            if BookingService.intervals_overlap(start_at, end_at, exc_start, exc_end):
                return AvailabilityResult(
                    is_available=False,
                    message="Выбранное время пересекается с исключением в расписании мастера.",
                )

        if local_start.date() != local_end.date():
            return AvailabilityResult(
                is_available=False,
                message="Запись должна находиться в пределах одного дня.",
            )

        return AvailabilityResult(is_available=True)

    @staticmethod
    def check_time_blocks(master: Master, start_at: datetime, end_at: datetime) -> AvailabilityResult:
        blocking_items = TimeBlock.objects.filter(
            master=master,
            start_at__lt=end_at,
            end_at__gt=start_at,
        )

        if blocking_items.exists():
            return AvailabilityResult(
                is_available=False,
                message="Это время заблокировано в расписании мастера.",
            )

        return AvailabilityResult(is_available=True)

    @staticmethod
    def check_appointment_conflicts(
        master: Master,
        start_at: datetime,
        end_at: datetime,
        exclude_appointment_id: int | None = None,
    ) -> AvailabilityResult:
        queryset = Appointment.objects.filter(
            master=master,
            status__in=BookingService.ACTIVE_APPOINTMENT_STATUSES,
            start_at__lt=end_at,
            end_at__gt=start_at,
        )

        if exclude_appointment_id:
            queryset = queryset.exclude(id=exclude_appointment_id)

        if queryset.exists():
            return AvailabilityResult(
                is_available=False,
                message="Это время уже занято другой записью.",
            )

        return AvailabilityResult(is_available=True)

    @staticmethod
    def check_availability(
        master: Master,
        service: Service,
        start_at: datetime,
        exclude_appointment_id: int | None = None,
    ) -> AvailabilityResult:
        check_master_service_result = BookingService.check_master_service(master, service)
        if not check_master_service_result.is_available:
            return check_master_service_result

        check_past_result = BookingService.check_not_in_past(start_at)
        if not check_past_result.is_available:
            return check_past_result

        effective_duration_minutes = BookingService.get_effective_duration_minutes(master, service)
        end_at = start_at + timedelta(minutes=effective_duration_minutes)

        checks = [
            BookingService.check_working_hours(master, start_at, end_at),
            BookingService.check_schedule_exceptions(master, start_at, end_at),
            BookingService.check_time_blocks(master, start_at, end_at),
            BookingService.check_appointment_conflicts(
                master=master,
                start_at=start_at,
                end_at=end_at,
                exclude_appointment_id=exclude_appointment_id,
            ),
        ]

        for result in checks:
            if not result.is_available:
                return result

        return AvailabilityResult(is_available=True, message="Время доступно для записи.")

    @staticmethod
    def create_appointment(
        *,
        client: Client,
        master: Master,
        service: Service,
        start_at: datetime,
        source: str = Appointment.Source.WEBSITE,
        status: str = Appointment.Status.PENDING,
        comment: str = "",
        created_by=None,
    ) -> Appointment:
        with transaction.atomic():
            Master.objects.select_for_update().filter(pk=master.pk).exists()

            availability = BookingService.check_availability(
                master=master,
                service=service,
                start_at=start_at,
            )
            if not availability.is_available:
                raise ValidationError(availability.message)

            effective_duration_minutes = BookingService.get_effective_duration_minutes(master, service)
            effective_price = BookingService.get_effective_price(master, service)
            end_at = start_at + timedelta(minutes=effective_duration_minutes)

            appointment = Appointment.objects.create(
                client=client,
                master=master,
                service=service,
                start_at=start_at,
                end_at=end_at,
                status=status,
                source=source,
                price=effective_price,
                comment=comment,
                created_by=created_by,
            )

            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                old_status="",
                new_status=status,
                changed_by=created_by,
                comment="Запись создана.",
            )

            if status == Appointment.Status.CONFIRMED:
                appointment.confirmed_by = created_by
                appointment.confirmed_at = appointment.created_at
                appointment.save(update_fields=["confirmed_by", "confirmed_at"])

            return appointment

    @staticmethod
    def change_status(
        *,
        appointment: Appointment,
        new_status: str,
        changed_by=None,
        comment: str = "",
    ) -> Appointment:
        old_status = appointment.status

        if old_status == new_status:
            return appointment

        allowed_transitions = {
            Appointment.Status.PENDING: {
                Appointment.Status.CONFIRMED,
                Appointment.Status.CANCELLED,
                Appointment.Status.NO_SHOW,
            },
            Appointment.Status.CONFIRMED: {
                Appointment.Status.COMPLETED,
                Appointment.Status.CANCELLED,
                Appointment.Status.NO_SHOW,
            },
            Appointment.Status.COMPLETED: set(),
            Appointment.Status.CANCELLED: set(),
            Appointment.Status.NO_SHOW: {
                Appointment.Status.CONFIRMED,
                Appointment.Status.CANCELLED,
            },
        }

        if new_status not in allowed_transitions.get(old_status, set()):
            raise ValidationError("Такой переход статуса недоступен для текущей записи.")

        appointment.status = new_status

        if new_status == Appointment.Status.CONFIRMED:
            appointment.confirmed_by = changed_by
            appointment.confirmed_at = timezone.now()
            appointment.cancelled_by = None
            appointment.cancelled_at = None
            appointment.cancel_reason = ""

        if new_status == Appointment.Status.CANCELLED:
            appointment.cancelled_by = changed_by
            appointment.cancelled_at = timezone.now()
            appointment.cancel_reason = comment or appointment.cancel_reason or "Отмена без указания причины"

        appointment.save()

        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            comment=comment,
        )

        return appointment

    @staticmethod
    def intervals_overlap(
        start_a: datetime,
        end_a: datetime,
        start_b: datetime,
        end_b: datetime,
    ) -> bool:
        return start_a < end_b and end_a > start_b
