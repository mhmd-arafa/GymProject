from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import IntakeForm, TrainerNote, User


class ClientRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone = forms.CharField(
        required=False,
        label=_("phone number"),
        help_text=_("Egyptian mobile, e.g. 01012345678. Used for WhatsApp."),
    )

    class Meta:
        model = User
        fields = ["username", "email", "phone", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.CLIENT
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "language"]


class TrainerNoteForm(forms.ModelForm):
    class Meta:
        model = TrainerNote
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": _("Injuries, allergies, personality notes…"),
                }
            )
        }
        labels = {"body": _("Private note (client never sees this)")}


class IntakeFormForm(forms.ModelForm):
    class Meta:
        model = IntakeForm
        fields = [
            "goal",
            "equipment_access",
            "training_days_per_week",
            "injuries",
            "allergies",
            "food_dislikes",
            "notes",
        ]
        widgets = {
            "training_days_per_week": forms.NumberInput(
                attrs={"min": 1, "max": 7, "inputmode": "numeric"}
            ),
            "injuries": forms.Textarea(attrs={"rows": 3}),
            "allergies": forms.Textarea(attrs={"rows": 2}),
            "food_dislikes": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_training_days_per_week(self):
        days = self.cleaned_data["training_days_per_week"]
        if not 1 <= days <= 7:
            raise forms.ValidationError(_("Pick between 1 and 7 days."))
        return days
