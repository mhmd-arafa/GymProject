from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from accounts.mixins import AdminRequiredMixin
from subscriptions.mixins import ActiveSubscriptionRequiredMixin
from .models import ProgressLog
from .forms import ProgressLogForm

User = get_user_model()


class MyProgressHistoryView(ActiveSubscriptionRequiredMixin, ListView):
    model = ProgressLog
    template_name = "progress/my_progress.html"
    context_object_name = "logs"

    def get_queryset(self):
        return ProgressLog.objects.filter(client=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        logs = list(self.get_queryset())
        if logs:
            latest_weight = logs[0].weight
            start_weight = logs[-1].weight
            diff = latest_weight - start_weight
            context["latest_weight"] = latest_weight
            context["start_weight"] = start_weight
            context["weight_diff"] = diff
        return context


class ProgressLogCreateView(ActiveSubscriptionRequiredMixin, CreateView):
    model = ProgressLog
    form_class = ProgressLogForm
    template_name = "progress/progress_form.html"
    success_url = reverse_lazy("my-progress")

    def form_valid(self, form):
        form.instance.client = self.request.user
        return super().form_valid(form)


class ClientProgressAdminView(AdminRequiredMixin, ListView):
    model = ProgressLog
    template_name = "progress/client_progress_admin.html"
    context_object_name = "logs"

    def get_queryset(self):
        return ProgressLog.objects.filter(client_id=self.kwargs["client_id"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target_client"] = get_object_or_404(User, pk=self.kwargs["client_id"], role="CLIENT")
        logs = list(self.get_queryset())
        if logs:
            latest_weight = logs[0].weight
            start_weight = logs[-1].weight
            context["latest_weight"] = latest_weight
            context["start_weight"] = start_weight
            context["weight_diff"] = latest_weight - start_weight
        return context
