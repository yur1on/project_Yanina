from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.notifications.services import (
    TelegramNotificationService,
    build_new_appointment_message,
    notify_new_appointment,
)


class TelegramNotificationServiceTests(SimpleTestCase):
    @override_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=False,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="chat",
    )
    def test_send_message_returns_false_when_notifications_disabled(self):
        self.assertFalse(TelegramNotificationService.send_message("hello"))

    @override_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="chat",
    )
    @patch("apps.notifications.services.request.urlopen")
    def test_send_message_returns_true_on_successful_api_response(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = b'{"ok": true}'
        mock_urlopen.return_value.__enter__.return_value = response

        self.assertTrue(TelegramNotificationService.send_message("hello"))

    @override_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="owner-chat, second-owner",
    )
    @patch("apps.notifications.services.request.urlopen")
    def test_send_message_sends_to_multiple_chat_ids(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = b'{"ok": true}'
        mock_urlopen.return_value.__enter__.return_value = response

        self.assertTrue(TelegramNotificationService.send_message("hello"))
        self.assertEqual(mock_urlopen.call_count, 2)

    def test_build_new_appointment_message_contains_essential_data(self):
        appointment = MagicMock()
        appointment.client.first_name = "Инна"
        appointment.client.last_name = "Петрова"
        appointment.client.phone = "+375291112233"
        appointment.master.display_name = "Юля"
        appointment.service.name = "Перманент бровей"
        appointment.comment = "Нужна консультация"
        appointment.price = "100.00"
        appointment.get_status_display.return_value = "Новая"

        with patch("apps.notifications.services.timezone.localtime") as mock_localtime:
            mock_localtime.return_value.strftime.side_effect = ["12.06.2026", "14:30"]
            message = build_new_appointment_message(appointment)

        self.assertIn("Новая запись с сайта", message)
        self.assertIn("Инна Петрова", message)
        self.assertIn("+375291112233", message)
        self.assertIn("Юля", message)
        self.assertIn("Перманент бровей", message)
        self.assertIn("100.00 BYN", message)
        self.assertIn("Нужна консультация", message)

    @override_settings(
        TELEGRAM_NOTIFICATIONS_ENABLED=True,
        TELEGRAM_BOT_TOKEN="token",
        TELEGRAM_CHAT_ID="owner-chat",
    )
    @patch("apps.notifications.services.TelegramNotificationService.send_message")
    def test_notify_new_appointment_includes_master_chat_id(self, mock_send_message):
        mock_send_message.return_value = True
        appointment = MagicMock()
        appointment.master.telegram_chat_id = "master-chat"

        notify_new_appointment(appointment)

        _, kwargs = mock_send_message.call_args
        self.assertEqual(kwargs["chat_ids"], ["owner-chat", "master-chat"])
