from django.contrib import admin

from .models import ScheduleException, TimeBlock, WorkingHours


@admin.register(WorkingHours)
class WorkingHoursAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "master",
        "weekday",
        "start_time",
        "end_time",
        "is_day_off",
    )
    list_filter = ("weekday", "is_day_off", "master")
    list_editable = ("start_time", "end_time", "is_day_off")
    search_fields = ("master__display_name", "master__user__email")


@admin.register(ScheduleException)
class ScheduleExceptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "master",
        "date",
        "exception_type",
        "is_full_day",
        "start_time",
        "end_time",
        "reason",
    )
    list_filter = ("exception_type", "is_full_day", "date", "master")
    search_fields = ("master__display_name", "reason")
    autocomplete_fields = ("master",)
    date_hierarchy = "date"


@admin.register(TimeBlock)
class TimeBlockAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "master",
        "start_at",
        "end_at",
        "reason",
        "created_by",
    )
    list_filter = ("master", "created_by")
    search_fields = ("master__display_name", "reason")
    autocomplete_fields = ("master", "created_by")
    date_hierarchy = "start_at"