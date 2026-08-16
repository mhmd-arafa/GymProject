from django.urls import path
from .views import ClientListView
from .views import ClientListView, ClientDetailView
from .views import RegisterView
from django.contrib.auth.views import LoginView, LogoutView
from .views import DashboardRedirectView, ClientHomeView


urlpatterns = [
    path("clients/", ClientListView.as_view(), name="client-list"),
    path("clients/<int:pk>/", ClientDetailView.as_view(), name="client-detail"),
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("home/", DashboardRedirectView.as_view(), name="dashboard-home"),
    path("me/", ClientHomeView.as_view(), name="client-home"),
]