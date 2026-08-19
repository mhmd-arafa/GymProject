from django import forms
from .models import Subscription


class AdminSubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ["client", "plan_type", "status", "start_date", "end_date", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.model.objects.filter(role="CLIENT")


class ClientSubscriptionRequestForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ["plan_type", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "أي تفاصيل أو ملاحظات تود إضافتها للمدرب..."}),
        }
