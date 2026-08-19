from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from accounts.mixins import AdminRequiredMixin
from .models import Subscription
from .forms import AdminSubscriptionForm, ClientSubscriptionRequestForm


class SubscriptionListView(AdminRequiredMixin, ListView):
    model = Subscription
    template_name = "subscriptions/subscription_list.html"
    context_object_name = "subscriptions"

    def get_queryset(self):
        queryset = Subscription.objects.select_related("client").all()
        status_filter = self.request.GET.get("status")
        if status_filter in Subscription.Status.values:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_status_filter"] = self.request.GET.get("status", "")
        context["pending_count"] = Subscription.objects.filter(status=Subscription.Status.PENDING).count()
        return context


class SubscriptionCreateView(AdminRequiredMixin, CreateView):
    model = Subscription
    form_class = AdminSubscriptionForm
    template_name = "subscriptions/subscription_form.html"
    success_url = reverse_lazy("subscription-list")

    def get_initial(self):
        initial = super().get_initial()
        client_id = self.request.GET.get("client")
        if client_id:
            initial["client"] = client_id
        return initial


class SubscriptionUpdateView(AdminRequiredMixin, UpdateView):
    model = Subscription
    form_class = AdminSubscriptionForm
    template_name = "subscriptions/subscription_form.html"
    success_url = reverse_lazy("subscription-list")


class MySubscriptionView(LoginRequiredMixin, TemplateView):
    template_name = "subscriptions/my_subscription.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_subscriptions = Subscription.objects.filter(client=self.request.user)
        active_subscriptions = [sub for sub in user_subscriptions if sub.is_currently_active()]
        
        context["active_subscription"] = active_subscriptions[0] if active_subscriptions else None
        context["subscriptions_history"] = user_subscriptions
        return context


class SubscriptionRequestView(LoginRequiredMixin, CreateView):
    model = Subscription
    form_class = ClientSubscriptionRequestForm
    template_name = "subscriptions/subscription_request.html"
    success_url = reverse_lazy("my-subscription")

    def form_valid(self, form):
        form.instance.client = self.request.user
        form.instance.status = Subscription.Status.PENDING
        return super().form_valid(form)


class NoActiveSubscriptionView(LoginRequiredMixin, TemplateView):
    template_name = "subscriptions/no_active_subscription.html"
