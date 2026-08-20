from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from .models import (
    Exercise,
    ExerciseCatalog,
    SetLog,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
)


class WorkoutPlanForm(forms.ModelForm):
    """Plan assigned directly to a client."""

    class Meta:
        model = WorkoutPlan
        fields = ["client", "title", "description"]
        widgets = {
            "client": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.model.objects.filter(role="CLIENT")
        self.fields["client"].required = True


class WorkoutTemplateForm(forms.ModelForm):
    """Reusable template: no client, so the field is not offered at all."""

    class Meta:
        model = WorkoutPlan
        fields = ["title", "description"]


class ExerciseForm(forms.ModelForm):
    """Plan exercise with library autocomplete.

    The datalist gives fast plan-building without a JS dependency: the trainer
    types and picks, and the browser handles the suggestion list.
    """

    class Meta:
        model = Exercise
        fields = [
            "catalog_exercise",
            "name",
            "sets",
            "reps",
            "reps_max",
            "target_weight_kg",
            "rest_seconds",
            "order",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["catalog_exercise"].queryset = ExerciseCatalog.objects.filter(
            is_active=True
        )
        self.fields["catalog_exercise"].required = False
        self.fields["name"].required = False
        self.fields["name"].widget.attrs["list"] = "exercise-catalog-options"

    def clean(self):
        cleaned = super().clean()
        catalog = cleaned.get("catalog_exercise")
        name = (cleaned.get("name") or "").strip()

        # One of the two must identify the exercise. Prefer the library entry,
        # since that is what unlocks history and charts.
        if not catalog and not name:
            raise forms.ValidationError(
                _("Pick an exercise from the library or type a name.")
            )
        if catalog and not name:
            cleaned["name"] = catalog.name

        reps = cleaned.get("reps")
        reps_max = cleaned.get("reps_max")
        if reps and reps_max and reps_max < reps:
            self.add_error(
                "reps_max", _("The top of the rep range cannot be below the bottom.")
            )
        return cleaned


WorkoutDayFormSet = inlineformset_factory(
    WorkoutPlan,
    WorkoutDay,
    fields=["day_name", "order"],
    extra=3,
    can_delete=True,
)

ExerciseFormSet = inlineformset_factory(
    WorkoutDay,
    Exercise,
    form=ExerciseForm,
    extra=3,
    can_delete=True,
)


class SetLogForm(forms.ModelForm):
    """One logged set. Number inputs so phones show a numeric keypad."""

    class Meta:
        model = SetLog
        fields = ["set_number", "weight_kg", "reps", "rpe", "is_warmup"]
        widgets = {
            "set_number": forms.HiddenInput(),
            "weight_kg": forms.NumberInput(
                attrs={"step": "0.5", "min": "0", "inputmode": "decimal"}
            ),
            "reps": forms.NumberInput(attrs={"step": "1", "min": "0", "inputmode": "numeric"}),
            "rpe": forms.NumberInput(
                attrs={"step": "0.5", "min": "1", "max": "10", "inputmode": "decimal"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["set_number"].required = False
        self.fields["rpe"].required = False

    def clean_reps(self):
        reps = self.cleaned_data["reps"]
        if reps == 0:
            raise forms.ValidationError(_("Log at least one rep."))
        return reps


class SessionCompleteForm(forms.ModelForm):
    class Meta:
        model = WorkoutSession
        fields = ["perceived_effort", "notes"]
        widgets = {
            "perceived_effort": forms.NumberInput(
                attrs={"min": "1", "max": "10", "inputmode": "numeric"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
