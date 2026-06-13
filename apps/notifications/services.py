import json
import logging
from html import escape
from time import sleep
from urllib import error, parse, request

from django.conf import settings
from django.urls import reverse
from django.utils import timezone


logger = logging.getLogger(__name__)


class TelegramNotificationService:
    RETRY_DELAYS = (0, 1, 2)

    @staticmethod
    def is_configured():
        return bool(
            settings.TELEGRAM_NOTIFICATIONS_ENABLED
            and settings.TELEGRAM_BOT_TOKEN
            and settings.TELEGRAM_CHAT_ID
        )

    @staticmethod
    def send_message(text):
        if not TelegramNotificationService.is_configured():
            logger.info("Telegram notifications are not configured.")
            return False

        api_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = parse.urlencode(
            {
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")

        for attempt, delay in enumerate(TelegramNotificationService.RETRY_DELAYS, start=1):
            if delay:
                sleep(delay)

            try:
                with request.urlopen(api_url, data=payload, timeout=10) as response:
                    response_payload = json.loads(response.read().decode("utf-8"))
            except (error.URLError, TimeoutError, ConnectionResetError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Telegram notification attempt %s failed: %s",
                    attempt,
                    exc,
                    exc_info=True,
                )
                continue

            if not response_payload.get("ok"):
                logger.error("Telegram API returned error: %s", response_payload)
                return False

            return True

        logger.error("Failed to send Telegram notification after retries.")
        return False


def _clean_text(value):
    if value is None:
        return ""
    return escape(str(value).strip())


def _build_appointment_admin_url(appointment):
    if not settings.APP_BASE_URL:
        return ""

    base_url = settings.APP_BASE_URL.rstrip("/")
    path = reverse("core:dashboard_appointment_edit", args=[appointment.id])
    return f"{base_url}{path}"


def build_new_appointment_message(appointment):
    local_start = timezone.localtime(appointment.start_at)
    client_name = " ".join(
        part for part in [_clean_text(appointment.client.first_name), _clean_text(appointment.client.last_name)] if part
    )
    admin_url = _build_appointment_admin_url(appointment)

    lines = [
        "✨ <b>Новая запись с сайта</b>",
        "",
        f"👤 <b>Клиент:</b> {client_name or '—'}",
        f"📞 <b>Телефон:</b> {_clean_text(appointment.client.phone)}",
        f"💁‍♀️ <b>Мастер:</b> {_clean_text(appointment.master.display_name)}",
        f"💅 <b>Услуга:</b> {_clean_text(appointment.service.name)}",
        f"📅 <b>Дата:</b> {local_start.strftime('%d.%m.%Y')}",
        f"🕒 <b>Время:</b> {local_start.strftime('%H:%M')}",
        f"📌 <b>Статус:</b> {_clean_text(appointment.get_status_display())}",
    ]

    if appointment.price is not None:
        lines.append(f"💳 <b>Цена:</b> {_clean_text(appointment.price)} BYN")

    if appointment.comment:
        lines.extend(
            [
                "",
                "💬 <b>Комментарий клиента:</b>",
                _clean_text(appointment.comment),
            ]
        )

    if admin_url:
        lines.extend(
            [
                "",
                f'🔗 <a href="{escape(admin_url, quote=True)}">Открыть запись в админке</a>',
            ]
        )

    return "\n".join(lines)


def notify_new_appointment(appointment):
    message = build_new_appointment_message(appointment)
    return TelegramNotificationService.send_message(message)
