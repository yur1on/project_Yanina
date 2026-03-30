from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.catalog.models import Master, Service
from apps.clients.models import Client


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Новая"
        CONFIRMED = "confirmed", "Подтверждена"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"
        NO_SHOW = "no_show", "Не пришёл"

    class Source(models.TextChoices):
        WEBSITE = "website", "Сайт"
        ADMIN = "admin", "Администратор"
        PHONE = "phone", "Телефон"
        INSTAGRAM = "instagram", "Instagram"
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"
        OTHER = "other", "Другое"

    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Клиент",
    )
    master = models.ForeignKey(
        Master,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Мастер",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Услуга",
    )

    start_at = models.DateTimeField("Начало записи")
    end_at = models.DateTimeField("Окончание записи")

    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    source = models.CharField(
        "Источник",
        max_length=20,
        choices=Source.choices,
        default=Source.WEBSITE,
    )

    price = models.DecimalField(
        "Цена на момент записи",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Можно оставить пустым, если цена еще не зафиксирована.",
    )
    comment = models.TextField("Комментарий", blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_appointments",
        verbose_name="Кто создал",
        blank=True,
        null=True,
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="confirmed_appointments",
        verbose_name="Кто подтвердил",
        blank=True,
        null=True,
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="cancelled_appointments",
        verbose_name="Кто отменил",
        blank=True,
        null=True,
    )

    confirmed_at = models.DateTimeField("Подтверждена", blank=True, null=True)
    cancelled_at = models.DateTimeField("Отменена", blank=True, null=True)
    cancel_reason = models.CharField("Причина отмены", max_length=255, blank=True)

    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"
        ordering = ("-start_at",)
        indexes = [
            models.Index(fields=["master", "start_at"], name="appointment_master_start_idx"),
            models.Index(fields=["status", "start_at"], name="appointment_status_start_idx"),
        ]

    def __str__(self):
        return f"{self.client} — {self.service} — {self.start_at:%d.%m.%Y %H:%M}"

    def clean(self):
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValidationError("Окончание записи должно быть позже начала.")

    @property
    def duration_minutes(self):
        delta = self.end_at - self.start_at
        return int(delta.total_seconds() // 60)


class AppointmentStatusHistory(models.Model):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="Запись",
    )
    old_status = models.CharField(
        "Старый статус",
        max_length=20,
        choices=Appointment.Status.choices,
        blank=True,
    )
    new_status = models.CharField(
        "Новый статус",
        max_length=20,
        choices=Appointment.Status.choices,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="appointment_status_changes",
        verbose_name="Кто изменил",
        blank=True,
        null=True,
    )
    comment = models.TextField("Комментарий", blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "История статуса записи"
        verbose_name_plural = "История статусов записей"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.appointment} — {self.old_status} → {self.new_status}"


class AppointmentAttachment(models.Model):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="Запись",
    )
    file = models.FileField("Файл", upload_to="appointments/")
    description = models.CharField("Описание", max_length=255, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        verbose_name = "Файл записи"
        verbose_name_plural = "Файлы записей"
        ordering = ("-created_at",)

    def __str__(self):
        return self.description or f"Файл для записи #{self.appointment_id}"