from django.conf import settings
from django.db import models


class ClientTag(models.Model):
    name = models.CharField("Название", max_length=100, unique=True)
    color = models.CharField(
        "Цвет",
        max_length=20,
        blank=True,
        help_text="Например: red, green, blue или hex-значение.",
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Тег клиента"
        verbose_name_plural = "Теги клиентов"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Client(models.Model):
    class Source(models.TextChoices):
        WEBSITE = "website", "Сайт"
        PHONE = "phone", "Телефон"
        INSTAGRAM = "instagram", "Instagram"
        WHATSAPP = "whatsapp", "WhatsApp"
        TELEGRAM = "telegram", "Telegram"
        REFERRAL = "referral", "По рекомендации"
        OTHER = "other", "Другое"

    first_name = models.CharField("Имя", max_length=150)
    last_name = models.CharField("Фамилия", max_length=150, blank=True)
    phone = models.CharField("Телефон", max_length=30, unique=True)
    email = models.EmailField("Email", blank=True)
    birth_date = models.DateField("Дата рождения", blank=True, null=True)
    notes = models.TextField("Общая заметка", blank=True)
    source = models.CharField(
        "Источник",
        max_length=30,
        choices=Source.choices,
        default=Source.WEBSITE,
    )
    tags = models.ManyToManyField(
        ClientTag,
        verbose_name="Теги",
        related_name="clients",
        blank=True,
    )
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Клиент"
        verbose_name_plural = "Клиенты"
        ordering = ("first_name", "last_name", "phone")

    def __str__(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.phone

    @property
    def full_name(self):
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.phone


class ClientNote(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="client_notes",
        verbose_name="Клиент",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="client_notes",
        verbose_name="Автор",
        blank=True,
        null=True,
    )
    text = models.TextField("Текст заметки")
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Заметка по клиенту"
        verbose_name_plural = "Заметки по клиентам"
        ordering = ("-created_at",)

    def __str__(self):
        return f"Заметка: {self.client} ({self.created_at:%d.%m.%Y %H:%M})"