from django.urls import path

from .views import (
    MySubscriptionView,
    PaymentApproveView,
    PaymentProofUploadView,
    PaymentRejectView,
    PaymentReviewQueueView,
    SubscriptionAssignView,
    SubscriptionListView,
    SubscriptionPlanCreateView,
    SubscriptionPlanListView,
    SubscriptionStartView,
)

urlpatterns = [
    path("me/", MySubscriptionView.as_view(), name="my-subscription"),
    path("start/", SubscriptionStartView.as_view(), name="subscription-start"),
    path(
        "<int:subscription_pk>/payment-proof/",
        PaymentProofUploadView.as_view(),
        name="payment-proof-upload",
    ),

    path("payments/queue/", PaymentReviewQueueView.as_view(), name="payment-queue"),
    path("payments/<int:pk>/approve/", PaymentApproveView.as_view(), name="payment-approve"),
    path("payments/<int:pk>/reject/", PaymentRejectView.as_view(), name="payment-reject"),

    path("all/", SubscriptionListView.as_view(), name="subscription-list"),
    path("assign/", SubscriptionAssignView.as_view(), name="subscription-assign"),
    path("plans/", SubscriptionPlanListView.as_view(), name="subscription-plan-list"),
    path("plans/add/", SubscriptionPlanCreateView.as_view(), name="subscription-plan-add"),
]
