from django.contrib import admin

from .models import Page, SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "site_name",
                    "logo",
                )
            },
        ),
        (
            "Контакты",
            {
                "fields": (
                    "phone",
                    "email",
                    "address",
                )
            },
        ),
        (
            "Социальные сети",
            {
                "fields": (
                    "instagram",
                    "telegram",
                    "whatsapp",
                )
            },
        ),
        (
            "Главная страница",
            {
                "fields": (
                    "hero_title",
                    "hero_subtitle",
                )
            },
        ),
        (
            "Подвал сайта",
            {
                "fields": (
                    "footer_text",
                )
            },
        ),
        (
            "Служебные поля",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "slug", "is_published", "updated_at")
    list_filter = ("is_published",)
    list_editable = ("is_published",)
    search_fields = ("title", "slug", "content", "meta_title", "meta_description")
    prepopulated_fields = {"slug": ("title",)}