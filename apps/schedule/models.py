from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.catalog.models import Master


class WorkingHours(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 1, "Понедельник"
        TUESDAY = 2, "Вторник"
        WEDNESDAY = 3, "Среда"
        THURSDAY = 4, "Четверг"
        FRIDAY = 5, "Пятница"
        SATURDAY = 6, "Суббота"
        SUNDAY = 7, "Воскресенье"

    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="working_hours",
        verbose_name="Мастер",
    )
    weekday = models.PositiveSmallIntegerField("День недели", choices=Weekday.choices)
    start_time = models.TimeField("Начало рабочего дня", blank=True, null=True)
    end_time = models.TimeField("Конец рабочего дня", blank=True, null=True)
    is_day_off = models.BooleanField("Выходной", default=False)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Рабочее время"
        verbose_name_plural = "Рабочее время"
        ordering = ("master", "weekday")
        constraints = [
            models.UniqueConstraint(
                fields=("master", "weekday"),
                name="unique_master_weekday_working_hours",
            )
        ]

    def __str__(self):
        weekday_label = self.get_weekday_display()
        if self.is_day_off:
            return f"{self.master} — {weekday_label}: выходной"
        return f"{self.master} — {weekday_label}: {self.start_time}–{self.end_time}"

    def clean(self):
        if self.is_day_off:
            return

        if not self.start_time or not self.end_time:
            raise ValidationError("Для рабочего дня нужно указать время начала и окончания.")

        if self.start_time >= self.end_time:
            raise ValidationError("Время окончания должно быть позже времени начала.")


class ScheduleException(models.Model):
    class ExceptionType(models.TextChoices):
        VACATION = "vacation", "Отпуск"
        SICK_LEAVE = "sick_leave", "Больничный"
        TRAINING = "training", "Обучение"
        DAY_OFF = "day_off", "Выходной"
        CUSTOM = "custom", "Другое"

    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="schedule_exceptions",
        verbose_name="Мастер",
    )
    date = models.DateField("Дата")
    exception_type = models.CharField(
        "Тип исключения",
        max_length=30,
        choices=ExceptionType.choices,
        default=ExceptionType.CUSTOM,
    )
    start_time = models.TimeField("Начало", blank=True, null=True)
    end_time = models.TimeField("Окончание", blank=True, null=True)
    reason = models.CharField("Причина", max_length=255, blank=True)
    is_full_day = models.BooleanField("На весь день", default=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Исключение в расписании"
        verbose_name_plural = "Исключения в расписании"
        ordering = ("-date", "master")

    def __str__(self):
        if self.is_full_day:
            return f"{self.master} — {self.date} ({self.get_exception_type_display()}, весь день)"
        return f"{self.master} — {self.date} {self.start_time}–{self.end_time}"

    def clean(self):
        if not self.is_full_day:
            if not self.start_time or not self.end_time:
                raise ValidationError("Для неполного дня нужно указать время начала и окончания.")
            if self.start_time >= self.end_time:
                raise ValidationError("Время окончания должно быть позже времени начала.")


class TimeBlock(models.Model):
    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="time_blocks",
        verbose_name="Мастер",
    )
    start_at = models.DateTimeField("Начало блокировки")
    end_at = models.DateTimeField("Окончание блокировки")
    reason = models.CharField("Причина", max_length=255)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_time_blocks",
        verbose_name="Кто создал",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Блокировка времени"
        verbose_name_plural = "Блокировки времени"
        ordering = ("-start_at",)

    def __str__(self):
        return f"{self.master} — {self.start_at:%d.%m.%Y %H:%M} → {self.end_at:%d.%m.%Y %H:%M}"

    def clean(self):
        if self.start_at >= self.end_at:
            raise ValidationError("Окончание блокировки должно быть позже начала.")