from django.urls import path

from .views import (
    CheckInQueueView,
    CheckInReplyView,
    CheckInScheduleView,
    CheckInSubmitView,
    ClientProgressView,
    MeasurementCreateView,
    MyCheckInsView,
    MyProgressView,
    PhotoConsentToggleView,
    PhotoDeleteView,
    ProgressPhotoCreateView,
    PublicResultsView,
)

urlpatterns = [
    path("me/", MyProgressView.as_view(), name="my-progress"),
    path("measurements/add/", MeasurementCreateView.as_view(), name="measurement-add"),
    path("photos/add/", ProgressPhotoCreateView.as_view(), name="progress-photo-add"),
    path("photos/<int:pk>/consent/", PhotoConsentToggleView.as_view(), name="photo-consent"),
    path("photos/<int:pk>/delete/", PhotoDeleteView.as_view(), name="photo-delete"),
    path("results/", PublicResultsView.as_view(), name="public-results"),

    path("checkins/", MyCheckInsView.as_view(), name="my-checkins"),
    path("checkins/<int:pk>/submit/", CheckInSubmitView.as_view(), name="checkin-submit"),
    path("checkins/queue/", CheckInQueueView.as_view(), name="checkin-queue"),
    path("checkins/<int:pk>/reply/", CheckInReplyView.as_view(), name="checkin-reply"),
    path("checkins/schedule/", CheckInScheduleView.as_view(), name="checkin-schedule"),

    path("clients/<int:pk>/", ClientProgressView.as_view(), name="client-progress"),
]
