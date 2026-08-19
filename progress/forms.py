from django import forms
from .models import ProgressLog


class ProgressLogForm(forms.ModelForm):
    class Meta:
        model = ProgressLog
        fields = ["date", "weight", "photo", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "weight": forms.NumberInput(attrs={"step": "0.1", "placeholder": "مثال: 78.50"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "اكتب أي ملاحظات عن طاقتك والتزامك بالدايت والتمرين..."}),
        }
