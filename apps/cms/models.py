from django.db import models


class SiteSettings(models.Model):
    site_name = models.CharField("Название студии", max_length=255, default="Beauty Studio")
    logo = models.ImageField("Логотип", upload_to="site/", blank=True, null=True)

    phone = models.CharField("Телефон", max_length=50, blank=True)
    email = models.EmailField("Email", blank=True)
    address = models.CharField("Адрес", max_length=255, blank=True)

    instagram = models.URLField("Instagram", blank=True)
    telegram = models.URLField("Telegram", blank=True)
    whatsapp = models.URLField("WhatsApp", blank=True)

    hero_title = models.CharField("Заголовок на главной", max_length=255, blank=True)
    hero_subtitle = models.TextField("Подзаголовок на главной", blank=True)

    footer_text = models.CharField("Текст в подвале сайта", max_length=255, blank=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self):
        return self.site_name


class Page(models.Model):
    title = models.CharField("Название страницы", max_length=255)
    slug = models.SlugField("Slug", max_length=255, unique=True)
    content = models.TextField("Содержимое", blank=True)

    meta_title = models.CharField("Meta title", max_length=255, blank=True)
    meta_description = models.CharField("Meta description", max_length=255, blank=True)

    is_published = models.BooleanField("Опубликована", default=True)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Страница"
        verbose_name_plural = "Страницы"
        ordering = ("title",)

    def __str__(self):
        return self.title