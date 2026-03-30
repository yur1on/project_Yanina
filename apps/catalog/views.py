from django.views.generic import DetailView, ListView

from .models import Master, Service, ServiceCategory


class ServiceListView(ListView):
    model = Service
    template_name = "catalog/service_list.html"
    context_object_name = "services"

    def get_queryset(self):
        queryset = (
            Service.objects.filter(is_active=True)
            .select_related("category")
            .order_by("category__sort_order", "category__name", "sort_order", "name")
        )

        category_slug = self.request.GET.get("category")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = ServiceCategory.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )
        context["current_category"] = self.request.GET.get("category", "")
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
            .order_by("sort_order", "name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["masters"] = (
            Master.objects.filter(
                is_active=True,
                master_services__service=self.object,
                master_services__is_active=True,
            )
            .distinct()
            .order_by("sort_order", "display_name")
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
        context["master_services"] = (
            self.object.master_services.filter(
                is_active=True,
                service__is_active=True,
            )
            .select_related("service")
            .order_by("service__sort_order", "service__name")
        )
        context["other_masters"] = (
            Master.objects.filter(is_active=True)
            .exclude(pk=self.object.pk)
            .order_by("sort_order", "display_name")[:4]
        )
        return context