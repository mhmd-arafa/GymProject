from django import forms
from django.utils.translation import gettext_lazy as _

from .models import PaymentProof, Subscription, SubscriptionPlan


class SubscriptionStartForm(forms.ModelForm):
    """Client picks a package; it stays PENDING until payment is approved."""

    class Meta:
        model = Subscription
        fields = ["plan"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["plan"].queryset = SubscriptionPlan.objects.filter(is_active=True)


class PaymentProofForm(forms.ModelForm):
    class Meta:
        model = PaymentProof
        fields = ["method", "reference_number", "amount_egp", "screenshot", "note"]
        widgets = {
            "amount_egp": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
        }

    def clean(self):
        cleaned = super().clean()
        method = cleaned.get("method")
        reference = (cleaned.get("reference_number") or "").strip()
        screenshot = cleaned.get("screenshot")

        # Cash is handed over in person, so it has neither. For every digital
        # transfer we need something the trainer can actually check against.
        if method and method != PaymentProof.Method.CASH:
            if not reference and not screenshot:
                raise forms.ValidationError(
                    _("Add the transfer reference number or upload a screenshot.")
                )
        return cleaned


class PaymentRejectForm(forms.Form):
    rejection_reason = forms.CharField(
        label=_("Why are you rejecting this?"),
        max_length=255,
        widget=forms.TextInput(),
    )


class SubscriptionAssignForm(forms.ModelForm):
    """Trainer creating a subscription directly, e.g. for a cash payment."""

    class Meta:
        model = Subscription
        fields = ["client", "plan", "status", "start_date", "end_date"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields[
            "client"
        ].queryset.model.objects.filter(role="CLIENT")
