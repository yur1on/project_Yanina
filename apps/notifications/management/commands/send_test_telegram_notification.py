from django.core.management.base import BaseCommand

from apps.notifications.services import TelegramNotificationService


class Command(BaseCommand):
    help = "Отправляет тестовое уведомление в Telegram."

    def handle(self, *args, **options):
        success = TelegramNotificationService.send_message(
            "Тестовое уведомление из Beauty Studio.\nЕсли вы видите это сообщение, Telegram-бот подключён правильно."
        )

        if success:
            self.stdout.write(self.style.SUCCESS("Тестовое уведомление отправлено."))
            return

        self.stdout.write(
            self.style.ERROR(
                "Не удалось отправить уведомление. Проверьте TELEGRAM_NOTIFICATIONS_ENABLED, TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID."
            )
        )
