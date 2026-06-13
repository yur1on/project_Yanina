from datetime import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.booking.availability import AvailabilityService
from apps.catalog.models import Master, Service
from apps.clients.models import Client, ClientNote
from apps.clients.utils import normalize_phone
from apps.schedule.models import TimeBlock


class DashboardAppointmentBaseForm(forms.Form):
    client = forms.ModelChoiceField(
        queryset=Client.objects.all().order_by("first_name", "last_name", "phone"),
        label="Клиент",
        empty_label="Выберите клиента",
    )
    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(is_active=True).order_by("sort_order", "name"),
        label="Услуга",
        empty_label="Выберите услугу",
    )
    master = forms.ModelChoiceField(
        queryset=Master.objects.none(),
        label="Мастер",
        empty_label="Сначала выберите услугу",
        required=False,
    )
    booking_date = forms.DateField(
        label="Дата",
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
        required=False,
    )
    slot = forms.ChoiceField(
        label="Свободное время",
        choices=[],
        required=False,
    )
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    appointment = None

    def __init__(self, *args, **kwargs):
        self.appointment = kwargs.pop("appointment", None)
        initial = kwargs.get("initial", {}) or {}
        super().__init__(*args, **kwargs)

        self.fields["master"].queryset = self._build_master_queryset(initial)
        self.fields["slot"].choices = self._build_slot_choices(initial)

    def _get_value(self, field_name, initial=None):
        initial = initial or {}
        if self.is_bound:
            return self.data.get(field_name)
        return initial.get(field_name) or self.initial.get(field_name)

    def _build_master_queryset(self, initial=None):
        service_id = self._get_value("service", initial=initial)
        master_id = self._get_value("master", initial=initial)

        queryset = Master.objects.filter(is_active=True)

        if service_id:
            queryset = queryset.filter(
                master_services__service_id=service_id,
                master_services__is_active=True,
            ).distinct()

        if master_id and not service_id:
            queryset = queryset.filter(id=master_id)

        return queryset.order_by("sort_order", "display_name")

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

        current_slot = self._get_current_appointment_slot_value(parsed_date)
        choices = [(slot.start_at.isoformat(), slot.label) for slot in slots]

        if current_slot and current_slot not in {value for value, _ in choices}:
            current_dt = datetime.fromisoformat(current_slot)
            local_dt = timezone.localtime(current_dt)
            choices.insert(
                0,
                (current_slot, f"{local_dt.strftime('%H:%M')} (текущее время записи)"),
            )

        return choices

    def _get_current_appointment_slot_value(self, parsed_date):
        if not self.appointment:
            return None

        local_start = timezone.localtime(self.appointment.start_at)
        if local_start.date() != parsed_date:
            return None

        return self.appointment.start_at.isoformat()

    def clean_booking_date(self):
        booking_date = self.cleaned_data.get("booking_date")
        if not booking_date:
            return booking_date

        if booking_date < timezone.localdate():
            raise ValidationError("Нельзя выбрать дату в прошлом.")

        return booking_date

    def clean(self):
        cleaned_data = super().clean()

        client = cleaned_data.get("client")
        service = cleaned_data.get("service")
        master = cleaned_data.get("master")
        booking_date = cleaned_data.get("booking_date")
        slot = cleaned_data.get("slot")

        if not client:
            raise ValidationError("Выберите клиента.")

        if not service:
            raise ValidationError("Выберите услугу.")

        if not master:
            raise ValidationError("Выберите мастера.")

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

        if not slot:
            raise ValidationError("Выберите свободное время.")

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

        current_slot = None
        if self.appointment:
            current_slot = self.appointment.start_at.isoformat()

        if start_at.isoformat() not in allowed_slots and start_at.isoformat() != current_slot:
            raise ValidationError(
                "Выбранный слот уже недоступен. Обновите страницу и выберите другой."
            )

        return cleaned_data


class DashboardAppointmentCreateForm(DashboardAppointmentBaseForm):
    pass


class DashboardAppointmentEditForm(DashboardAppointmentBaseForm):
    pass


class DashboardClientCreateForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "first_name",
            "last_name",
            "phone",
            "email",
            "birth_date",
            "source",
            "notes",
            "tags",
        ]
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "phone": "Телефон",
            "email": "Email",
            "birth_date": "Дата рождения",
            "source": "Источник",
            "notes": "Заметка",
            "tags": "Теги",
        }
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone or len(phone) < 8:
            raise ValidationError("Телефон обязателен.")
        return phone


class DashboardClientEditForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "first_name",
            "last_name",
            "phone",
            "email",
            "birth_date",
            "source",
            "notes",
            "tags",
        ]
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "phone": "Телефон",
            "email": "Email",
            "birth_date": "Дата рождения",
            "source": "Источник",
            "notes": "Заметка",
            "tags": "Теги",
        }
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone or len(phone) < 8:
            raise ValidationError("Телефон обязателен.")
        return phone


class DashboardClientNoteCreateForm(forms.ModelForm):
    class Meta:
        model = ClientNote
        fields = ["text"]
        labels = {
            "text": "Новая заметка",
        }
        widgets = {
            "text": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Введите заметку по клиенту"}
            ),
        }

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if not text:
            raise ValidationError("Текст заметки не может быть пустым.")
        return text


class DashboardTimeOffBaseForm(forms.ModelForm):
    block_date = forms.DateField(
        label="Дата",
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )
    start_time = forms.TimeField(
        label="Начало",
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M"],
    )
    end_time = forms.TimeField(
        label="Конец",
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M"],
    )

    class Meta:
        model = TimeBlock
        fields = [
            "master",
            "block_date",
            "start_time",
            "end_time",
            "reason",
        ]
        labels = {
            "master": "Мастер",
            "reason": "Причина",
        }
        widgets = {
            "reason": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.created_by = kwargs.pop("created_by", None)
        super().__init__(*args, **kwargs)
        self.fields["master"].queryset = Master.objects.filter(is_active=True).order_by(
            "display_name"
        )

    def clean(self):
        cleaned_data = super().clean()

        master = cleaned_data.get("master")
        block_date = cleaned_data.get("block_date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if not master or not block_date or not start_time or not end_time:
            return cleaned_data

        if end_time <= start_time:
            raise ValidationError("Время окончания должно быть позже времени начала.")

        tz = timezone.get_current_timezone()
        start_at = timezone.make_aware(datetime.combine(block_date, start_time), tz)
        end_at = timezone.make_aware(datetime.combine(block_date, end_time), tz)

        overlaps = TimeBlock.objects.filter(
            master=master,
            start_at__lt=end_at,
            end_at__gt=start_at,
        )

        if self.instance and self.instance.pk:
            overlaps = overlaps.exclude(pk=self.instance.pk)

        if overlaps.exists():
            raise ValidationError("У мастера уже есть пересекающаяся блокировка на это время.")

        cleaned_data["start_at"] = start_at
        cleaned_data["end_at"] = end_at

        self.instance.master = master
        self.instance.reason = cleaned_data.get("reason", "")
        self.instance.start_at = start_at
        self.instance.end_at = end_at

        return cleaned_data


class DashboardTimeOffCreateForm(DashboardTimeOffBaseForm):
    pass


class DashboardTimeOffEditForm(DashboardTimeOffBaseForm):
    pass
