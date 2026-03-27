from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from .views import (
    CampaignCreateView,
    CampaignListView,
    Index,
    ManageMultiRouteView,
    ManageRouteView,
    MissionsCreateView,
    MissionsListView,
    import_kml_fields,
)

app_name = "mainapp"

urlpatterns = [
    path("", Index.as_view(), name="index"),
    path("add-field/", TemplateView.as_view(template_name="mainapp/add_field.html"), name="add_field"),
    path("add-mission/", MissionsCreateView.as_view(), name="add_mission"),
    path("list-mission/", MissionsListView.as_view(), name="list_mission"),
    path("import-kml/", import_kml_fields, name="fields_import_kml"),
    path("manage-route/<int:mission_id>/", ManageRouteView.as_view(), name="manage_route"),
    path("add-campaign/", CampaignCreateView.as_view(), name="add_campaign"),
    path("list-campaign/", CampaignListView.as_view(), name="list_campaign"),
    path("manage-multi-route/<int:campaign_id>/", ManageMultiRouteView.as_view(), name="manage_multi_route"),
    path("login/", auth_views.LoginView.as_view(template_name="auth/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
