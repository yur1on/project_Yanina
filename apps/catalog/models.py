from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from slugify import slugify


class ServiceCategory(models.Model):
    name = models.CharField("Название", max_length=255, unique=True)
    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)
    description = models.TextField("Описание", blank=True)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    is_active = models.BooleanField("Активна", default=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Категория услуги"
        verbose_name_plural = "Категории услуг"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Service(models.Model):
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="services",
        verbose_name="Категория",
    )
    name = models.CharField("Название", max_length=255, unique=True)
    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)
    image = models.ImageField("Фото услуги", upload_to="services/", blank=True, null=True)
    short_description = models.CharField("Краткое описание", max_length=500, blank=True)
    full_description = models.TextField("Полное описание", blank=True)

    duration_minutes = models.PositiveIntegerField(
        "Длительность (мин.)",
        validators=[MinValueValidator(15)],
        help_text="Длительность услуги в минутах.",
    )
    base_price = models.DecimalField(
        "Базовая цена",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    buffer_before_minutes = models.PositiveIntegerField(
        "Буфер до услуги (мин.)",
        default=0,
        validators=[MinValueValidator(0)],
    )
    buffer_after_minutes = models.PositiveIntegerField(
        "Буфер после услуги (мин.)",
        default=0,
        validators=[MinValueValidator(0)],
    )

    prepayment_required = models.BooleanField("Нужна предоплата", default=False)
    is_active = models.BooleanField("Активна", default=True)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name

    @property
    def total_duration_minutes(self):
        return self.duration_minutes + self.buffer_before_minutes + self.buffer_after_minutes

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Master(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="master_profile",
        verbose_name="Пользователь",
        limit_choices_to={"role": "master"},
    )
    display_name = models.CharField("Имя для сайта", max_length=255)
    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)
    photo = models.ImageField("Фото", upload_to="masters/", blank=True, null=True)
    short_bio = models.CharField("Краткое описание", max_length=500, blank=True)
    full_bio = models.TextField("Полное описание", blank=True)
    telegram_chat_id = models.CharField(
        "Telegram chat ID",
        max_length=64,
        blank=True,
        help_text="Если указан, мастер будет получать уведомления о своих новых записях.",
    )
    experience_years = models.PositiveIntegerField(
        "Опыт (лет)",
        default=0,
        validators=[MinValueValidator(0)],
    )
    is_active = models.BooleanField("Активен", default=True)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Мастер"
        verbose_name_plural = "Мастера"
        ordering = ("sort_order", "display_name")

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.display_name)
        super().save(*args, **kwargs)


class MasterService(models.Model):
    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="master_services",
        verbose_name="Мастер",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name="master_services",
        verbose_name="Услуга",
    )
    custom_price = models.DecimalField(
        "Индивидуальная цена",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text="Оставьте пустым, чтобы использовать базовую цену услуги.",
    )
    custom_duration_minutes = models.PositiveIntegerField(
        "Индивидуальная длительность (мин.)",
        blank=True,
        null=True,
        validators=[MinValueValidator(15)],
        help_text="Оставьте пустым, чтобы использовать стандартную длительность услуги.",
    )
    is_active = models.BooleanField("Активна", default=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Услуга мастера"
        verbose_name_plural = "Услуги мастеров"
        ordering = ("master", "service")
        constraints = [
            models.UniqueConstraint(
                fields=("master", "service"),
                name="unique_master_service",
            )
        ]

    def __str__(self):
        return f"{self.master} — {self.service}"

    @property
    def actual_price(self):
        return self.custom_price if self.custom_price is not None else self.service.base_price

    @property
    def actual_duration_minutes(self):
        return (
            self.custom_duration_minutes
            if self.custom_duration_minutes is not None
            else self.service.duration_minutes
        )


class PortfolioItem(models.Model):
    master = models.ForeignKey(
        Master,
        on_delete=models.CASCADE,
        related_name="portfolio_items",
        verbose_name="Мастер",
    )
    title = models.CharField("Название", max_length=255)
    image = models.ImageField("Изображение", upload_to="portfolio/")
    description = models.TextField("Описание", blank=True)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    is_published = models.BooleanField("Опубликовано", default=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Элемент портфолио"
        verbose_name_plural = "Портфолио"
        ordering = ("sort_order", "title")

    def __str__(self):
        return self.title
