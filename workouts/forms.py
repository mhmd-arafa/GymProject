from django import forms
from django.forms import inlineformset_factory
from .models import WorkoutPlan, WorkoutDay
from .models import Exercise

class WorkoutPlanForm(forms.ModelForm):
    class Meta:
        model = WorkoutPlan
        fields = ["client", "title"]
        widgets = {
            "client": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.model.objects.filter(role="CLIENT")


WorkoutDayFormSet = inlineformset_factory(
    WorkoutPlan,
    WorkoutDay,
    fields=["day_name"],
    extra=3,
    can_delete=True,
)

ExerciseFormSet = inlineformset_factory(
    WorkoutDay,
    Exercise,
    fields=["name", "sets", "reps", "notes"],
    extra=3,
    can_delete=True,
)