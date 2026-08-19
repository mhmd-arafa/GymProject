from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from .models import Subscription


class ActiveSubscriptionRequiredMixin(LoginRequiredMixin):
    """
    Mixin to ensure the user is an Admin OR a Client with an active subscription.
    Inactive/expired clients are redirected to a notification page.
    """
    no_active_subscription_url = reverse_lazy("no-active-subscription")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if request.user.role == "ADMIN":
            return super().dispatch(request, *args, **kwargs)

        active_subs = Subscription.objects.filter(
            client=request.user,
            status=Subscription.Status.ACTIVE,
        )
        has_active = any(sub.is_currently_active() for sub in active_subs)

        if not has_active:
            return redirect(self.no_active_subscription_url)

        return super().dispatch(request, *args, **kwargs)
