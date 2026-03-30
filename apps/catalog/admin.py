from django.contrib import admin

from .models import Master, MasterService, PortfolioItem, Service, ServiceCategory


class MasterServiceInline(admin.TabularInline):
    model = MasterService
    extra = 1
    autocomplete_fields = ("service",)
    verbose_name = "Услуга мастера"
    verbose_name_plural = "Услуги мастера"


class PortfolioItemInline(admin.TabularInline):
    model = PortfolioItem
    extra = 1
    verbose_name = "Элемент портфолио"
    verbose_name_plural = "Портфолио мастера"


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "category",
        "base_price",
        "duration_minutes",
        "buffer_before_minutes",
        "buffer_after_minutes",
        "is_active",
        "sort_order",
    )
    list_filter = ("category", "is_active", "prepayment_required")
    list_editable = ("base_price", "duration_minutes", "is_active", "sort_order")
    search_fields = ("name", "short_description", "full_description")
    autocomplete_fields = ("category",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Master)
class MasterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "display_name",
        "user",
        "experience_years",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active",)
    list_editable = ("experience_years", "is_active", "sort_order")
    search_fields = ("display_name", "user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
    prepopulated_fields = {"slug": ("display_name",)}
    inlines = [MasterServiceInline, PortfolioItemInline]


@admin.register(MasterService)
class MasterServiceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "master",
        "service",
        "custom_price",
        "custom_duration_minutes",
        "is_active",
    )
    list_filter = ("is_active", "master", "service__category")
    search_fields = ("master__display_name", "service__name")
    autocomplete_fields = ("master", "service")


@admin.register(PortfolioItem)
class PortfolioItemAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "master", "sort_order", "is_published")
    list_filter = ("is_published", "master")
    list_editable = ("sort_order", "is_published")
    search_fields = ("title", "description", "master__display_name")
    autocomplete_fields = ("master",)