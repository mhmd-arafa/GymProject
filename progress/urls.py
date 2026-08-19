from django.urls import path
from .views import (
    MyProgressHistoryView,
    ProgressLogCreateView,
    ClientProgressAdminView,
)

urlpatterns = [
    path("my-progress/", MyProgressHistoryView.as_view(), name="my-progress"),
    path("add/", ProgressLogCreateView.as_view(), name="progress-add"),
    path("client/<int:client_id>/", ClientProgressAdminView.as_view(), name="client-progress-admin"),
]
