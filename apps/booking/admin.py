from django.contrib import admin
from django.utils import timezone

from .models import Appointment, AppointmentAttachment, AppointmentStatusHistory


class AppointmentStatusHistoryInline(admin.TabularInline):
    model = AppointmentStatusHistory
    extra = 0
    autocomplete_fields = ("changed_by",)
    readonly_fields = ("created_at",)
    verbose_name = "Изменение статуса"
    verbose_name_plural = "История статусов"


class AppointmentAttachmentInline(admin.TabularInline):
    model = AppointmentAttachment
    extra = 1
    verbose_name = "Файл"
    verbose_name_plural = "Файлы"


@admin.action(description="Отметить как подтверждённые")
def mark_as_confirmed(modeladmin, request, queryset):
    updated_count = 0
    for appointment in queryset:
        old_status = appointment.status
        if old_status != Appointment.Status.CONFIRMED:
            appointment.status = Appointment.Status.CONFIRMED
            appointment.confirmed_by = request.user
            appointment.confirmed_at = timezone.now()
            appointment.save()

            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                old_status=old_status,
                new_status=Appointment.Status.CONFIRMED,
                changed_by=request.user,
                comment="Статус изменён через действие в админке.",
            )
            updated_count += 1

    modeladmin.message_user(request, f"Подтверждено записей: {updated_count}")


@admin.action(description="Отметить как завершённые")
def mark_as_completed(modeladmin, request, queryset):
    updated_count = 0
    for appointment in queryset:
        old_status = appointment.status
        if old_status != Appointment.Status.COMPLETED:
            appointment.status = Appointment.Status.COMPLETED
            appointment.save()

            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                old_status=old_status,
                new_status=Appointment.Status.COMPLETED,
                changed_by=request.user,
                comment="Статус изменён через действие в админке.",
            )
            updated_count += 1

    modeladmin.message_user(request, f"Завершено записей: {updated_count}")


@admin.action(description="Отметить как отменённые")
def mark_as_cancelled(modeladmin, request, queryset):
    updated_count = 0
    for appointment in queryset:
        old_status = appointment.status
        if old_status != Appointment.Status.CANCELLED:
            appointment.status = Appointment.Status.CANCELLED
            appointment.cancelled_by = request.user
            appointment.cancelled_at = timezone.now()
            if not appointment.cancel_reason:
                appointment.cancel_reason = "Отменено через админку"
            appointment.save()

            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                old_status=old_status,
                new_status=Appointment.Status.CANCELLED,
                changed_by=request.user,
                comment="Статус изменён через действие в админке.",
            )
            updated_count += 1

    modeladmin.message_user(request, f"Отменено записей: {updated_count}")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "client",
        "master",
        "service",
        "start_at",
        "end_at",
        "status",
        "source",
        "price",
    )
    list_filter = (
        "status",
        "source",
        "master",
        "service",
        "start_at",
    )
    search_fields = (
        "client__first_name",
        "client__last_name",
        "client__phone",
        "client__email",
        "master__display_name",
        "service__name",
        "comment",
    )
    autocomplete_fields = (
        "client",
        "master",
        "service",
        "created_by",
        "confirmed_by",
        "cancelled_by",
    )
    readonly_fields = ("created_at", "updated_at", "confirmed_at", "cancelled_at")
    date_hierarchy = "start_at"
    actions = [mark_as_confirmed, mark_as_completed, mark_as_cancelled]
    inlines = [AppointmentStatusHistoryInline, AppointmentAttachmentInline]

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "client",
                    "master",
                    "service",
                    "status",
                    "source",
                )
            },
        ),
        (
            "Дата и время",
            {
                "fields": (
                    "start_at",
                    "end_at",
                )
            },
        ),
        (
            "Дополнительно",
            {
                "fields": (
                    "price",
                    "comment",
                )
            },
        ),
        (
            "Подтверждение и отмена",
            {
                "fields": (
                    "confirmed_by",
                    "confirmed_at",
                    "cancelled_by",
                    "cancelled_at",
                    "cancel_reason",
                )
            },
        ),
        (
            "Служебные поля",
            {
                "fields": (
                    "created_by",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )


@admin.register(AppointmentStatusHistory)
class AppointmentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "appointment",
        "old_status",
        "new_status",
        "changed_by",
        "created_at",
    )
    list_filter = ("new_status", "old_status", "created_at")
    search_fields = (
        "appointment__client__first_name",
        "appointment__client__last_name",
        "appointment__client__phone",
        "comment",
    )
    autocomplete_fields = ("appointment", "changed_by")
    readonly_fields = ("created_at",)


@admin.register(AppointmentAttachment)
class AppointmentAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "appointment", "description", "created_at")
    search_fields = (
        "appointment__client__first_name",
        "appointment__client__last_name",
        "appointment__client__phone",
        "description",
    )
    autocomplete_fields = ("appointment",)
    readonly_fields = ("created_at",)