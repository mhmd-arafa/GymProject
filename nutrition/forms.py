from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from .models import (
    FoodItem,
    MacroTarget,
    Meal,
    MealFoodItem,
    NutritionPlan,
    SupplementSchedule,
)


class NutritionPlanForm(forms.ModelForm):
    class Meta:
        model = NutritionPlan
        fields = ["client", "title"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.model.objects.filter(role="CLIENT")


class MealForm(forms.ModelForm):
    """Meal that can either be primary or an alternative to another meal."""

    class Meta:
        model = Meal
        fields = ["name", "alternative_of", "calories", "protein", "carbs", "fats", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only meals in the same plan can be alternatives, and only primary ones
        # (no alternatives-of-alternatives, which would be ambiguous to display).
        plan = getattr(self.instance, "plan", None)
        queryset = Meal.objects.none()
        if plan is not None and plan.pk:
            queryset = Meal.objects.filter(plan=plan, alternative_of__isnull=True)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
        self.fields["alternative_of"].queryset = queryset
        self.fields["alternative_of"].required = False


MealFormSet = inlineformset_factory(
    NutritionPlan,
    Meal,
    fields=["name", "calories", "protein", "carbs", "fats", "notes"],
    extra=3,
    can_delete=True,
)

MealAlternativeFormSet = inlineformset_factory(
    NutritionPlan,
    Meal,
    form=MealForm,
    extra=2,
    can_delete=True,
)


class MealFoodItemForm(forms.ModelForm):
    class Meta:
        model = MealFoodItem
        fields = ["food", "grams"]
        widgets = {"grams": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Egyptian staples first: they are what this trainer reaches for most.
        self.fields["food"].queryset = FoodItem.objects.order_by(
            "-is_egyptian_staple", "name"
        )


MealFoodItemFormSet = inlineformset_factory(
    Meal,
    MealFoodItem,
    form=MealFoodItemForm,
    extra=4,
    can_delete=True,
)


class MacroTargetForm(forms.ModelForm):
    class Meta:
        model = MacroTarget
        fields = [
            "target_calories",
            "target_protein",
            "target_carbs",
            "target_fats",
            "water_ml",
        ]


class FoodItemForm(forms.ModelForm):
    class Meta:
        model = FoodItem
        fields = [
            "name",
            "category",
            "calories_per_100g",
            "protein_per_100g",
            "carbs_per_100g",
            "fats_per_100g",
            "is_egyptian_staple",
        ]


SupplementScheduleFormSet = inlineformset_factory(
    NutritionPlan,
    SupplementSchedule,
    fields=["supplement", "dose", "timing"],
    extra=2,
    can_delete=True,
)
