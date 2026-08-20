from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView

from accounts.mixins import AdminRequiredMixin

from . import services
from .forms import (
    PaymentProofForm,
    PaymentRejectForm,
    SubscriptionAssignForm,
    SubscriptionStartForm,
)
from .models import PaymentProof, Subscription, SubscriptionPlan


class MySubscriptionView(LoginRequiredMixin, TemplateView):
    template_name = "subscriptions/my_subscription.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subscriptions = list(
            self.request.user.subscriptions.select_related("plan").prefetch_related(
                "payment_proofs"
            )
        )
        context["subscriptions"] = subscriptions
        context["current"] = next((s for s in subscriptions if s.is_active), None)
        context["pending"] = [
            s for s in subscriptions if s.status == Subscription.Status.PENDING
        ]
        context["plans"] = SubscriptionPlan.objects.filter(is_active=True)
        context["start_form"] = SubscriptionStartForm()
        return context


class NoActiveSubscriptionView(LoginRequiredMixin, TemplateView):
    """Where ActiveSubscriptionRequiredMixin sends clients whose access has lapsed."""

    template_name = "subscriptions/no_active_subscription.html"


class SubscriptionStartView(LoginRequiredMixin, CreateView):
    """Client chooses a package. Activation waits on payment approval."""

    model = Subscription
    form_class = SubscriptionStartForm
    template_name = "subscriptions/subscription_start.html"

    def form_valid(self, form):
        form.instance.client = self.request.user
        form.instance.status = Subscription.Status.PENDING
        self.object = form.save()
        messages.info(
            self.request, _("Now upload your payment details so we can activate it.")
        )
        return redirect("payment-proof-upload", subscription_pk=self.object.pk)


class PaymentProofUploadView(LoginRequiredMixin, CreateView):
    model = PaymentProof
    form_class = PaymentProofForm
    template_name = "subscriptions/payment_proof_form.html"
    success_url = reverse_lazy("my-subscription")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.subscription = get_object_or_404(
                Subscription,
                pk=kwargs["subscription_pk"],
                client=request.user,
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["subscription"] = self.subscription
        return context

    def form_valid(self, form):
        form.instance.subscription = self.subscription
        messages.success(
            self.request, _("Payment details sent. Your coach will confirm shortly.")
        )
        return super().form_valid(form)


class PaymentReviewQueueView(AdminRequiredMixin, ListView):
    template_name = "subscriptions/payment_queue.html"
    context_object_name = "proofs"

    def get_queryset(self):
        return (
            PaymentProof.objects.filter(status=PaymentProof.Status.PENDING)
            .select_related("subscription__client", "subscription__plan")
            .order_by("submitted_at")
        )


class PaymentApproveView(AdminRequiredMixin, View):
    def post(self, request, pk):
        proof = get_object_or_404(PaymentProof, pk=pk)
        subscription = services.approve_payment(proof, request.user)
        messages.success(
            request,
            _("Approved. %(client)s is active until %(end)s.")
            % {
                "client": subscription.client.username,
                "end": subscription.end_date,
            },
        )
        return redirect("payment-queue")


class PaymentRejectView(AdminRequiredMixin, View):
    def post(self, request, pk):
        proof = get_object_or_404(PaymentProof, pk=pk)
        form = PaymentRejectForm(request.POST)
        reason = form.cleaned_data["rejection_reason"] if form.is_valid() else ""
        services.reject_payment(proof, request.user, reason=reason)
        messages.warning(request, _("Payment rejected."))
        return redirect("payment-queue")


class SubscriptionListView(AdminRequiredMixin, ListView):
    template_name = "subscriptions/subscription_list.html"
    context_object_name = "subscriptions"

    def get_queryset(self):
        services.expire_overdue_subscriptions()
        return Subscription.objects.select_related("client", "plan")


class SubscriptionAssignView(AdminRequiredMixin, CreateView):
    model = Subscription
    form_class = SubscriptionAssignForm
    template_name = "subscriptions/subscription_assign.html"
    success_url = reverse_lazy("subscription-list")

    def form_valid(self, form):
        messages.success(self.request, _("Subscription saved."))
        return super().form_valid(form)


class SubscriptionPlanListView(AdminRequiredMixin, ListView):
    model = SubscriptionPlan
    template_name = "subscriptions/plan_list.html"
    context_object_name = "plans"


class SubscriptionPlanCreateView(AdminRequiredMixin, CreateView):
    model = SubscriptionPlan
    template_name = "subscriptions/plan_form.html"
    fields = ["name", "duration_days", "price_egp", "description", "is_active"]
    success_url = reverse_lazy("subscription-plan-list")
