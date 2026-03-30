from django.urls import path

from .views import MasterDetailView, MasterListView, ServiceDetailView, ServiceListView

app_name = "catalog"

urlpatterns = [
    path("services/", ServiceListView.as_view(), name="service_list"),
    path("services/<slug:slug>/", ServiceDetailView.as_view(), name="service_detail"),
    path("masters/", MasterListView.as_view(), name="master_list"),
    path("masters/<slug:slug>/", MasterDetailView.as_view(), name="master_detail"),
]