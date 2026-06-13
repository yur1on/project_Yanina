from django.db.models import Count, F, Max, Min, Prefetch, Q
from django.db.models.functions import Coalesce
from django.views.generic import DetailView, ListView

from .models import Master, MasterService, Service, ServiceCategory


class ServiceListView(ListView):
    model = Service
    template_name = "catalog/service_list.html"
    context_object_name = "services"

    def get_queryset(self):
        category_slug = self.request.GET.get("category")
        if not category_slug:
            return Service.objects.none()

        return (
            Service.objects.filter(
                is_active=True,
                category__is_active=True,
                category__slug=category_slug,
            )
            .select_related("category")
            .prefetch_related(
                Prefetch(
                    "master_services",
                    queryset=MasterService.objects.filter(
                        is_active=True,
                        master__is_active=True,
                        service__is_active=True,
                    )
                    .select_related("master", "service")
                    .order_by("master__sort_order", "master__display_name"),
                    to_attr="active_master_offers",
                )
            )
            .annotate(
                min_effective_price=Min(
                    Coalesce("master_services__custom_price", F("base_price")),
                    filter=Q(
                        master_services__is_active=True,
                        master_services__master__is_active=True,
                    ),
                ),
                max_effective_price=Max(
                    Coalesce("master_services__custom_price", F("base_price")),
                    filter=Q(
                        master_services__is_active=True,
                        master_services__master__is_active=True,
                    ),
                ),
            )
            .order_by("sort_order", "name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        categories = (
            ServiceCategory.objects.filter(is_active=True)
            .annotate(
                active_service_count=Count(
                    "services",
                    filter=Q(services__is_active=True),
                    distinct=True,
                )
            )
            .filter(active_service_count__gt=0)
            .order_by("sort_order", "name")
        )
        current_category = self.request.GET.get("category", "")
        context["categories"] = categories
        context["current_category"] = current_category
        context["current_category_obj"] = categories.filter(slug=current_category).first()
        return context


class ServiceDetailView(DetailView):
    model = Service
    template_name = "catalog/service_detail.html"
    context_object_name = "service"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return (
            Service.objects.filter(is_active=True)
            .select_related("category")
            .annotate(
                min_effective_price=Min(
                    Coalesce("master_services__custom_price", F("base_price")),
                    filter=Q(
                        master_services__is_active=True,
                        master_services__master__is_active=True,
                    ),
                ),
                max_effective_price=Max(
                    Coalesce("master_services__custom_price", F("base_price")),
                    filter=Q(
                        master_services__is_active=True,
                        master_services__master__is_active=True,
                    ),
                ),
            )
            .order_by("sort_order", "name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["master_offers"] = (
            self.object.master_services.filter(
                is_active=True,
                master__is_active=True,
                service__is_active=True,
            )
            .select_related("master", "service", "master__user")
            .order_by("master__sort_order", "master__display_name")
        )
        context["related_services"] = (
            Service.objects.filter(
                is_active=True,
                category=self.object.category,
            )
            .exclude(pk=self.object.pk)
            .order_by("sort_order", "name")[:4]
        )
        return context


class MasterListView(ListView):
    model = Master
    template_name = "catalog/master_list.html"
    context_object_name = "masters"

    def get_queryset(self):
        queryset = (
            Master.objects.filter(is_active=True)
            .select_related("user")
            .order_by("sort_order", "display_name")
        )

        service_slug = self.request.GET.get("service")
        if service_slug:
            queryset = queryset.filter(
                master_services__service__slug=service_slug,
                master_services__is_active=True,
                master_services__service__is_active=True,
            ).distinct()

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["services"] = Service.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )
        context["current_service"] = self.request.GET.get("service", "")
        return context


class MasterDetailView(DetailView):
    model = Master
    template_name = "catalog/master_detail.html"
    context_object_name = "master"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return (
            Master.objects.filter(is_active=True)
            .select_related("user")
            .prefetch_related("master_services__service", "portfolio_items")
            .order_by("sort_order", "display_name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        master_services = list(
            self.object.master_services.filter(
                is_active=True,
                service__is_active=True,
            )
            .select_related("service", "service__category")
            .order_by(
                "service__category__sort_order",
                "service__category__name",
                "service__sort_order",
                "service__name",
            )
        )
        grouped_master_services = []

        for item in master_services:
            category = item.service.category
            category_name = category.name if category else "Услуги"

            if not grouped_master_services or grouped_master_services[-1]["category_name"] != category_name:
                grouped_master_services.append(
                    {
                        "category_name": category_name,
                        "items": [],
                    }
                )

            grouped_master_services[-1]["items"].append(item)

        context["master_services"] = master_services
        context["grouped_master_services"] = grouped_master_services
        context["other_masters"] = (
            Master.objects.filter(is_active=True)
            .exclude(pk=self.object.pk)
            .order_by("sort_order", "display_name")[:4]
        )
        return context
