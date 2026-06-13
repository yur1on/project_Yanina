from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.booking.availability import AvailabilityService
from apps.catalog.models import Master, Service
from apps.clients.models import Client
from apps.clients.utils import normalize_phone


class PublicBookingForm(forms.Form):
    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(is_active=True).order_by("sort_order", "name"),
        label="Услуга",
        empty_label="Выберите услугу",
    )
    master = forms.ModelChoiceField(
        queryset=Master.objects.filter(is_active=True).order_by("sort_order", "display_name"),
        label="Мастер",
        empty_label="Выберите мастера",
        required=False,
    )
    booking_date = forms.DateField(
        label="Дата",
        widget=forms.DateInput(
            attrs={
                "type": "text",
                "autocomplete": "off",
                "placeholder": "Выберите дату",
            }
        ),
        input_formats=["%Y-%m-%d"],
        required=False,
    )
    slot = forms.ChoiceField(
        label="Свободное время",
        choices=[],
        required=False,
    )

    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия (необязательно)", max_length=150, required=False)
    phone = forms.CharField(label="Телефон", max_length=30)
    email = forms.EmailField(label="Email (необязательно)", required=False)
    comment = forms.CharField(
        label="Комментарий (необязательно)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def __init__(self, *args, **kwargs):
        initial = kwargs.get("initial", {}) or {}
        super().__init__(*args, **kwargs)

        self.fields["service"].queryset = self._build_service_queryset(initial)
        self.fields["master"].queryset = self._build_master_queryset(initial)
        self.fields["slot"].choices = self._build_slot_choices(initial)

    def _get_value(self, field_name, initial=None):
        initial = initial or {}

        if self.is_bound:
            return self.data.get(field_name)

        return initial.get(field_name) or self.initial.get(field_name)

    def _build_master_queryset(self, initial=None):
        master_id = self._get_value("master", initial=initial)

        queryset = Master.objects.filter(is_active=True)

        if master_id:
            queryset = queryset.filter(id=master_id)

        return queryset.order_by("sort_order", "display_name")

    def _build_service_queryset(self, initial=None):
        master_id = self._get_value("master", initial=initial)
        queryset = Service.objects.filter(is_active=True)

        if master_id:
            queryset = queryset.filter(
                master_services__master_id=master_id,
                master_services__is_active=True,
                master_services__master__is_active=True,
            ).distinct()
        else:
            queryset = queryset.none()

        return queryset.order_by("sort_order", "name")

    def _build_slot_choices(self, initial=None):
        service = self._get_value("service", initial=initial)
        master = self._get_value("master", initial=initial)
        booking_date = self._get_value("booking_date", initial=initial)

        if not service or not master or not booking_date:
            return []

        try:
            service_obj = Service.objects.get(pk=service, is_active=True)
            master_obj = Master.objects.get(pk=master, is_active=True)

            if hasattr(booking_date, "strftime"):
                parsed_date = booking_date
            else:
                parsed_date = datetime.strptime(str(booking_date), "%Y-%m-%d").date()
        except (Service.DoesNotExist, Master.DoesNotExist, ValueError, TypeError):
            return []

        slots = AvailabilityService.get_available_slots(
            master=master_obj,
            service=service_obj,
            target_date=parsed_date,
            slot_step_minutes=30,
        )

        return [(slot.start_at.isoformat(), slot.label) for slot in slots]

    def clean_booking_date(self):
        booking_date = self.cleaned_data.get("booking_date")
        if not booking_date:
            return booking_date

        today = timezone.localdate()

        if booking_date < today:
            raise ValidationError("Нельзя выбрать дату в прошлом.")

        return booking_date

    def clean(self):
        cleaned_data = super().clean()

        service = cleaned_data.get("service")
        master = cleaned_data.get("master")
        booking_date = cleaned_data.get("booking_date")
        slot = cleaned_data.get("slot")

        if not service:
            raise ValidationError("Выберите услугу.")

        if not master:
            raise ValidationError("Выберите мастера.")

        if service and master:
            allowed_master_ids = set(
                Master.objects.filter(
                    is_active=True,
                    master_services__service=service,
                    master_services__is_active=True,
                ).values_list("id", flat=True)
            )
            if master.id not in allowed_master_ids:
                raise ValidationError("Этот мастер не оказывает выбранную услугу.")

        if not booking_date:
            raise ValidationError("Выберите дату.")

        if service and master and booking_date and not slot:
            raise ValidationError("Выберите свободное время.")

        if service and master and booking_date and slot:
            try:
                start_at = datetime.fromisoformat(slot)
                if timezone.is_naive(start_at):
                    start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
            except ValueError:
                raise ValidationError("Некорректный слот времени.")

            slots = AvailabilityService.get_available_slots(
                master=master,
                service=service,
                target_date=booking_date,
                slot_step_minutes=30,
            )
            allowed_slots = {item.start_at.isoformat() for item in slots}

            if start_at.isoformat() not in allowed_slots:
                raise ValidationError("Выбранный слот уже недоступен. Обновите страницу и выберите другой.")

        return cleaned_data

    def get_or_create_client(self):
        first_name = self.cleaned_data["first_name"]
        last_name = self.cleaned_data.get("last_name", "")
        phone = normalize_phone(self.cleaned_data["phone"])
        email = self.cleaned_data.get("email", "")

        client, _ = Client.objects.get_or_create(
            phone=phone,
            defaults={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "source": Client.Source.WEBSITE,
            },
        )

        changed = False

        if client.first_name != first_name:
            client.first_name = first_name
            changed = True

        if last_name and client.last_name != last_name:
            client.last_name = last_name
            changed = True

        if email and client.email != email:
            client.email = email
            changed = True

        if changed:
            client.save()

        return client

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone or len(phone) < 8:
            raise ValidationError("Введите корректный номер телефона.")
        return phone
