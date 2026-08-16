from django import forms
from django.forms import inlineformset_factory
from .models import NutritionPlan, Meal


class NutritionPlanForm(forms.ModelForm):
    class Meta:
        model = NutritionPlan
        fields = ["client", "title"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.model.objects.filter(role="CLIENT")


MealFormSet = inlineformset_factory(
    NutritionPlan,
    Meal,
    fields=["name", "calories", "protein", "carbs", "fats", "notes"],
    extra=3,
    can_delete=True,
)
