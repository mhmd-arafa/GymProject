from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from .views import (
    ClientDetailView,
    ClientHomeView,
    ClientListView,
    DashboardRedirectView,
    IntakeFormUpdateView,
    IntakeFormView,
    ProfileUpdateView,
    RegisterView,
    TrainerDashboardView,
    TrainerNoteCreateView,
)

urlpatterns = [
    path("", TrainerDashboardView.as_view(), name="trainer-dashboard"),
    path("clients/", ClientListView.as_view(), name="client-list"),
    path("clients/<int:pk>/", ClientDetailView.as_view(), name="client-detail"),
    path(
        "clients/<int:pk>/notes/add/",
        TrainerNoteCreateView.as_view(),
        name="trainer-note-add",
    ),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("home/", DashboardRedirectView.as_view(), name="dashboard-home"),
    path("me/", ClientHomeView.as_view(), name="client-home"),
    path("me/profile/", ProfileUpdateView.as_view(), name="profile-edit"),
    path("intake/", IntakeFormView.as_view(), name="intake"),
    path("intake/edit/", IntakeFormUpdateView.as_view(), name="intake-edit"),
]
