from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from . import services
from .models import PaymentProof, Subscription, SubscriptionPlan


class PaymentProofInline(admin.TabularInline):
    model = PaymentProof
    extra = 0
    readonly_fields = ("submitted_at", "reviewed_by", "reviewed_at")


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "duration_days", "price_egp", "is_active")
    list_filter = ("is_active",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("client", "plan", "status", "start_date", "end_date", "days_remaining")
    list_filter = ("status", "plan")
    search_fields = ("client__username",)
    inlines = [PaymentProofInline]

    @admin.display(description=_("days remaining"))
    def days_remaining(self, obj):
        return obj.days_remaining


@admin.register(PaymentProof)
class PaymentProofAdmin(admin.ModelAdmin):
    list_display = (
        "subscription",
        "method",
        "amount_egp",
        "reference_number",
        "status",
        "submitted_at",
    )
    list_filter = ("status", "method")
    search_fields = ("reference_number", "subscription__client__username")
    readonly_fields = ("submitted_at", "reviewed_by", "reviewed_at")
    actions = ["approve_selected", "reject_selected"]

    @admin.action(description=_("Approve payment and activate subscription"))
    def approve_selected(self, request, queryset):
        activated = 0
        for proof in queryset:
            services.approve_payment(proof, request.user)
            activated += 1
        self.message_user(
            request,
            _("Approved %(count)d payment(s).") % {"count": activated},
            messages.SUCCESS,
        )

    @admin.action(description=_("Reject payment"))
    def reject_selected(self, request, queryset):
        for proof in queryset:
            services.reject_payment(proof, request.user)
        self.message_user(request, _("Rejected."), messages.WARNING)
