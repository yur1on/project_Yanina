from django.contrib import admin

from .models import Client, ClientNote, ClientTag


class ClientNoteInline(admin.TabularInline):
    model = ClientNote
    extra = 1
    autocomplete_fields = ("author",)
    verbose_name = "Заметка"
    verbose_name_plural = "Заметки по клиенту"


@admin.register(ClientTag)
class ClientTagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "color")
    search_fields = ("name",)
    list_editable = ("color",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "first_name",
        "last_name",
        "phone",
        "email",
        "source",
        "created_at",
    )
    list_filter = ("source", "tags", "created_at")
    search_fields = ("first_name", "last_name", "phone", "email")
    filter_horizontal = ("tags",)
    inlines = [ClientNoteInline]


@admin.register(ClientNote)
class ClientNoteAdmin(admin.ModelAdmin):
    list_display = ("id", "client", "author", "created_at")
    list_filter = ("created_at", "author")
    search_fields = ("client__first_name", "client__last_name", "client__phone", "text")
    autocomplete_fields = ("client", "author")