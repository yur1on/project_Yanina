from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client as HttpClient, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.booking.forms import PublicBookingForm
from apps.booking.models import Appointment
from apps.booking.services import BookingService
from apps.catalog.models import Master, MasterService, Service, ServiceCategory
from apps.clients.models import Client
from apps.schedule.models import TimeBlock, WorkingHours


class BookingFlowTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(
            email="admin@example.com",
            password="password123",
            first_name="Admin",
            role=user_model.Role.ADMIN,
            is_staff=True,
        )
        master_user = user_model.objects.create_user(
            email="master@example.com",
            password="password123",
            first_name="Master",
            role=user_model.Role.MASTER,
        )
        self.master = Master.objects.create(
            user=master_user,
            display_name="Анна",
            is_active=True,
        )
        self.category = ServiceCategory.objects.create(name="Брови")
        self.service = Service.objects.create(
            category=self.category,
            name="Архитектура бровей",
            duration_minutes=60,
            base_price=Decimal("75.00"),
            buffer_after_minutes=15,
            prepayment_required=True,
            is_active=True,
        )
        self.master_service = MasterService.objects.create(
            master=self.master,
            service=self.service,
            custom_price=Decimal("60.00"),
            custom_duration_minutes=45,
            is_active=True,
        )

        for weekday in range(1, 8):
            WorkingHours.objects.create(
                master=self.master,
                weekday=weekday,
                start_time=time(9, 0),
                end_time=time(20, 0),
                is_day_off=False,
            )

        self.client = Client.objects.create(
            first_name="Елена",
            last_name="Иванова",
            phone="+375447778899",
            source=Client.Source.WEBSITE,
        )
        self.http_client = HttpClient()
        self.http_client.force_login(self.admin_user)

    def _future_start(self, hours=2):
        now = timezone.localtime()
        start = (now + timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)
        if start.hour < 9:
            start = start.replace(hour=10)
        if start.hour >= 19:
            start = (start + timedelta(days=1)).replace(hour=10)
        return start

    def test_create_appointment_blocks_conflicting_slot(self):
        start_at = self._future_start()
        appointment = BookingService.create_appointment(
            client=self.client,
            master=self.master,
            service=self.service,
            start_at=start_at,
            source=Appointment.Source.ADMIN,
            status=Appointment.Status.CONFIRMED,
            created_by=self.admin_user,
        )

        self.assertEqual(appointment.price, Decimal("60.00"))

        with self.assertRaises(ValidationError):
            BookingService.create_appointment(
                client=self.client,
                master=self.master,
                service=self.service,
                start_at=start_at + timedelta(minutes=30),
                source=Appointment.Source.ADMIN,
                status=Appointment.Status.PENDING,
                created_by=self.admin_user,
            )

    def test_create_appointment_respects_time_blocks(self):
        start_at = self._future_start()
        TimeBlock.objects.create(
            master=self.master,
            start_at=start_at,
            end_at=start_at + timedelta(minutes=90),
            reason="Перерыв",
            created_by=self.admin_user,
        )

        with self.assertRaises(ValidationError):
            BookingService.create_appointment(
                client=self.client,
                master=self.master,
                service=self.service,
                start_at=start_at,
                source=Appointment.Source.ADMIN,
                status=Appointment.Status.PENDING,
                created_by=self.admin_user,
            )

    def test_change_status_supports_no_show_and_reopen_to_confirmed(self):
        appointment = BookingService.create_appointment(
            client=self.client,
            master=self.master,
            service=self.service,
            start_at=self._future_start(),
            source=Appointment.Source.ADMIN,
            status=Appointment.Status.PENDING,
            created_by=self.admin_user,
        )

        BookingService.change_status(
            appointment=appointment,
            new_status=Appointment.Status.NO_SHOW,
            changed_by=self.admin_user,
            comment="Клиент не пришёл",
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.NO_SHOW)

        BookingService.change_status(
            appointment=appointment,
            new_status=Appointment.Status.CONFIRMED,
            changed_by=self.admin_user,
            comment="Перезаписали",
        )
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
        self.assertEqual(appointment.cancel_reason, "")

    def test_public_booking_form_normalizes_phone_and_reuses_client(self):
        start_at = self._future_start()
        form = PublicBookingForm(
            data={
                "service": self.service.id,
                "master": self.master.id,
                "booking_date": timezone.localtime(start_at).date().isoformat(),
                "slot": start_at.isoformat(),
                "first_name": "Елена",
                "last_name": "Иванова",
                "phone": "+375 (44) 777-88-99",
                "email": "client@example.com",
                "comment": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        client = form.get_or_create_client()

        self.assertEqual(client.id, self.client.id)
        self.assertEqual(client.phone, "+375447778899")
        self.assertEqual(Client.objects.count(), 1)

    def test_available_services_api_returns_master_specific_price_and_duration(self):
        response = self.http_client.get(
            reverse("booking:available_services"),
            {
                "master": self.master.id,
                "selected_service": self.service.id,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["services"]), 1)
        service_data = payload["services"][0]
        self.assertEqual(service_data["price"], "60.00")
        self.assertEqual(service_data["duration_minutes"], 45)
        self.assertEqual(service_data["total_duration_minutes"], 60)
        self.assertTrue(service_data["selected"])

    def test_dashboard_delete_view_cancels_instead_of_deleting(self):
        appointment = BookingService.create_appointment(
            client=self.client,
            master=self.master,
            service=self.service,
            start_at=self._future_start(),
            source=Appointment.Source.ADMIN,
            status=Appointment.Status.CONFIRMED,
            created_by=self.admin_user,
        )

        response = self.http_client.post(
            reverse("core:dashboard_appointment_delete", args=[appointment.id]),
            {"cancel_reason": "Клиент попросил перенести"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)
        self.assertEqual(appointment.cancel_reason, "Клиент попросил перенести")
        self.assertTrue(Appointment.objects.filter(id=appointment.id).exists())

    def test_dashboard_status_update_requires_cancel_reason(self):
        appointment = BookingService.create_appointment(
            client=self.client,
            master=self.master,
            service=self.service,
            start_at=self._future_start(),
            source=Appointment.Source.ADMIN,
            status=Appointment.Status.CONFIRMED,
            created_by=self.admin_user,
        )

        response = self.http_client.post(
            reverse("core:dashboard_appointment_status", args=[appointment.id]),
            {
                "action": "cancel",
                "redirect_to": reverse("core:dashboard_home"),
                "comment": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CONFIRMED)
