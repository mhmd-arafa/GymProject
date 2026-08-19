from django.urls import path
from .views import (
    SubscriptionListView,
    SubscriptionCreateView,
    SubscriptionUpdateView,
    MySubscriptionView,
    SubscriptionRequestView,
    NoActiveSubscriptionView,
)

urlpatterns = [
    path("my-subscription/", MySubscriptionView.as_view(), name="my-subscription"),
    path("request/", SubscriptionRequestView.as_view(), name="subscription-request"),
    path("inactive-notice/", NoActiveSubscriptionView.as_view(), name="no-active-subscription"),
    path("list/", SubscriptionListView.as_view(), name="subscription-list"),
    path("add/", SubscriptionCreateView.as_view(), name="subscription-add"),
    path("<int:pk>/edit/", SubscriptionUpdateView.as_view(), name="subscription-edit"),
]
