from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.booking.models import Appointment
from apps.booking.services import BookingService
from apps.catalog.models import Master, Service
from apps.schedule.models import ScheduleException, TimeBlock, WorkingHours


@dataclass
class TimeSlot:
    start_at: datetime
    end_at: datetime
    label: str


class AvailabilityService:
    DEFAULT_SLOT_STEP_MINUTES = 30
    BOOKING_WINDOW_DAYS = 45

    ACTIVE_APPOINTMENT_STATUSES = [
        Appointment.Status.PENDING,
        Appointment.Status.CONFIRMED,
    ]

    @staticmethod
    def get_latest_booking_date() -> date:
        return timezone.localdate() + timedelta(days=AvailabilityService.BOOKING_WINDOW_DAYS)

    @staticmethod
    def is_date_within_booking_window(target_date: date) -> bool:
        today = timezone.localdate()
        latest_date = AvailabilityService.get_latest_booking_date()
        return today <= target_date <= latest_date

    @staticmethod
    def get_available_slots(
        *,
        master: Master,
        service: Service,
        target_date: date,
        slot_step_minutes: int = DEFAULT_SLOT_STEP_MINUTES,
    ) -> list[TimeSlot]:
        """
        Возвращает список доступных слотов на выбранную дату.
        """

        if slot_step_minutes <= 0:
            return []

        if not AvailabilityService.is_date_within_booking_window(target_date):
            return []

        master_service_result = BookingService.check_master_service(master, service)
        if not master_service_result.is_available:
            return []

        working_hours = AvailabilityService.get_working_hours_for_date(master, target_date)
        if not working_hours:
            return []

        if working_hours.is_day_off:
            return []

        if not working_hours.start_time or not working_hours.end_time:
            return []

        current_tz = timezone.get_current_timezone()

        working_start = timezone.make_aware(
            datetime.combine(target_date, working_hours.start_time),
            current_tz,
        )
        working_end = timezone.make_aware(
            datetime.combine(target_date, working_hours.end_time),
            current_tz,
        )

        effective_duration_minutes = BookingService.get_effective_duration_minutes(master, service)
        slot_duration = timedelta(minutes=effective_duration_minutes)
        slot_step = timedelta(minutes=slot_step_minutes)

        now = timezone.localtime(timezone.now())

        blocked_intervals = AvailabilityService.get_blocked_intervals(
            master=master,
            target_date=target_date,
        )

        slots: list[TimeSlot] = []
        cursor = working_start

        while cursor + slot_duration <= working_end:
            slot_start = cursor
            slot_end = cursor + slot_duration

            if target_date == now.date() and slot_start <= now:
                cursor += slot_step
                continue

            if AvailabilityService.is_interval_available(
                start_at=slot_start,
                end_at=slot_end,
                blocked_intervals=blocked_intervals,
            ):
                slots.append(
                    TimeSlot(
                        start_at=slot_start,
                        end_at=slot_end,
                        label=timezone.localtime(slot_start).strftime("%H:%M"),
                    )
                )

            cursor += slot_step

        return slots

    @staticmethod
    def get_month_day_statuses(
        *,
        master: Master,
        service: Service,
        year: int,
        month: int,
        slot_step_minutes: int = DEFAULT_SLOT_STEP_MINUTES,
    ) -> dict[str, str]:
        """
        Возвращает статусы дней месяца:
        - available: есть хотя бы один слот
        - full: слотов нет
        """

        _, days_in_month = calendar.monthrange(year, month)
        statuses: dict[str, str] = {}

        for day in range(1, days_in_month + 1):
            target_date = date(year, month, day)

            if not AvailabilityService.is_date_within_booking_window(target_date):
                continue

            slots = AvailabilityService.get_available_slots(
                master=master,
                service=service,
                target_date=target_date,
                slot_step_minutes=slot_step_minutes,
            )
            statuses[target_date.isoformat()] = "available" if slots else "full"

        return statuses

    @staticmethod
    def get_working_hours_for_date(master: Master, target_date: date) -> WorkingHours | None:
        weekday = target_date.isoweekday()
        return WorkingHours.objects.filter(master=master, weekday=weekday).first()

    @staticmethod
    def get_blocked_intervals(master: Master, target_date: date) -> list[tuple[datetime, datetime]]:
        """
        Собирает все занятые интервалы на дату:
        - исключения из расписания
        - блокировки времени
        - существующие записи
        """

        current_tz = timezone.get_current_timezone()
        day_start = timezone.make_aware(datetime.combine(target_date, datetime.min.time()), current_tz)
        day_end = timezone.make_aware(datetime.combine(target_date, datetime.max.time()), current_tz)

        intervals: list[tuple[datetime, datetime]] = []

        intervals.extend(
            AvailabilityService.get_exception_intervals(
                master=master,
                target_date=target_date,
                day_start=day_start,
                day_end=day_end,
            )
        )

        intervals.extend(
            AvailabilityService.get_time_block_intervals(
                master=master,
                day_start=day_start,
                day_end=day_end,
            )
        )

        intervals.extend(
            AvailabilityService.get_appointment_intervals(
                master=master,
                day_start=day_start,
                day_end=day_end,
            )
        )

        return intervals

    @staticmethod
    def get_exception_intervals(
        *,
        master: Master,
        target_date: date,
        day_start: datetime,
        day_end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        current_tz = timezone.get_current_timezone()
        intervals: list[tuple[datetime, datetime]] = []

        exceptions = ScheduleException.objects.filter(
            master=master,
            date=target_date,
        )

        for exception in exceptions:
            if exception.is_full_day:
                intervals.append((day_start, day_end))
                continue

            if not exception.start_time or not exception.end_time:
                continue

            exc_start = timezone.make_aware(
                datetime.combine(target_date, exception.start_time),
                current_tz,
            )
            exc_end = timezone.make_aware(
                datetime.combine(target_date, exception.end_time),
                current_tz,
            )

            intervals.append((exc_start, exc_end))

        return intervals

    @staticmethod
    def get_time_block_intervals(
        *,
        master: Master,
        day_start: datetime,
        day_end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        intervals: list[tuple[datetime, datetime]] = []

        blocks = TimeBlock.objects.filter(
            master=master,
            start_at__lt=day_end,
            end_at__gt=day_start,
        )

        for block in blocks:
            intervals.append((block.start_at, block.end_at))

        return intervals

    @staticmethod
    def get_appointment_intervals(
        *,
        master: Master,
        day_start: datetime,
        day_end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        intervals: list[tuple[datetime, datetime]] = []

        appointments = Appointment.objects.filter(
            master=master,
            status__in=AvailabilityService.ACTIVE_APPOINTMENT_STATUSES,
            start_at__lt=day_end,
            end_at__gt=day_start,
        )

        for appointment in appointments:
            intervals.append((appointment.start_at, appointment.end_at))

        return intervals

    @staticmethod
    def is_interval_available(
        *,
        start_at: datetime,
        end_at: datetime,
        blocked_intervals: list[tuple[datetime, datetime]],
    ) -> bool:
        for blocked_start, blocked_end in blocked_intervals:
            if AvailabilityService.intervals_overlap(start_at, end_at, blocked_start, blocked_end):
                return False
        return True

    @staticmethod
    def intervals_overlap(
        start_a: datetime,
        end_a: datetime,
        start_b: datetime,
        end_b: datetime,
    ) -> bool:
        return start_a < end_b and end_a > start_b
