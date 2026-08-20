from django import forms
from django.utils.translation import gettext_lazy as _

from .images import ImageRejected, process_upload
from .models import BodyMeasurement, CheckIn, ProgressPhoto


class PhotoField(forms.ImageField):
    """ImageField that normalises orientation and size on the way in."""

    def clean(self, data, initial=None):
        cleaned = super().clean(data, initial)
        # Only reprocess a fresh upload; an untouched existing file is already
        # normalised and has no read cursor to rewind.
        if not cleaned or not hasattr(cleaned, "read"):
            return cleaned
        try:
            return process_upload(cleaned)
        except ImageRejected as error:
            raise forms.ValidationError(str(error)) from None


class BodyMeasurementForm(forms.ModelForm):
    class Meta:
        model = BodyMeasurement
        fields = [
            "date",
            "weight_kg",
            "waist_cm",
            "chest_cm",
            "arm_cm",
            "thigh_cm",
            "hip_cm",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "weight_kg": forms.NumberInput(attrs={"step": "0.1", "inputmode": "decimal"}),
            "waist_cm": forms.NumberInput(attrs={"step": "0.5", "inputmode": "decimal"}),
            "chest_cm": forms.NumberInput(attrs={"step": "0.5", "inputmode": "decimal"}),
            "arm_cm": forms.NumberInput(attrs={"step": "0.5", "inputmode": "decimal"}),
            "thigh_cm": forms.NumberInput(attrs={"step": "0.5", "inputmode": "decimal"}),
            "hip_cm": forms.NumberInput(attrs={"step": "0.5", "inputmode": "decimal"}),
        }


class ProgressPhotoForm(forms.ModelForm):
    """Standalone photo upload, outside the weekly check-in."""

    image = PhotoField(label=_("photo"))

    class Meta:
        model = ProgressPhoto
        fields = ["date", "image", "pose", "consent_public"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


#: The three angles a coach needs to judge change. Separate inputs beat a
#: multi-file picker here: each photo arrives already labelled with its pose, and
#: a phone camera roll is much easier to work through one slot at a time.
POSE_SLOTS = [
    ("photo_front", ProgressPhoto.Pose.FRONT, _("Front")),
    ("photo_side", ProgressPhoto.Pose.SIDE, _("Side")),
    ("photo_back", ProgressPhoto.Pose.BACK, _("Back")),
]


class CheckInSubmitForm(forms.ModelForm):
    """What the client fills in. Coach fields are deliberately absent.

    Photos are optional: a client with nothing to show should still be able to
    send the week's numbers rather than skip the check-in entirely.
    """

    class Meta:
        model = CheckIn
        fields = [
            "weight_kg",
            "energy_rating",
            "sleep_rating",
            "adherence_rating",
            "note",
        ]
        widgets = {
            "weight_kg": forms.NumberInput(attrs={"step": "0.1", "inputmode": "decimal"}),
            "energy_rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "sleep_rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "adherence_rating": forms.NumberInput(attrs={"min": 1, "max": 5}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, _pose, label in POSE_SLOTS:
            self.fields[name] = PhotoField(
                label=label,
                required=False,
                widget=forms.ClearableFileInput(
                    # capture= lets a phone open the camera directly.
                    attrs={"accept": "image/*", "capture": "environment"}
                ),
            )
        self.fields["consent_public"] = forms.BooleanField(
            required=False,
            initial=False,
            label=_("My coach may share these photos publicly"),
            help_text=_("Optional. Leave unticked and only your coach sees them."),
        )

    def photo_uploads(self):
        """Yield ``(pose, file)`` for each slot the client actually filled."""
        for name, pose, _label in POSE_SLOTS:
            uploaded = self.cleaned_data.get(name)
            if uploaded:
                yield pose, uploaded


class CheckInReplyForm(forms.ModelForm):
    """What the coach fills in."""

    class Meta:
        model = CheckIn
        fields = ["trainer_reply"]
        widgets = {"trainer_reply": forms.Textarea(attrs={"rows": 4})}
        labels = {"trainer_reply": _("Your reply to the client")}


class CheckInScheduleForm(forms.ModelForm):
    class Meta:
        model = CheckIn
        fields = ["client", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields[
            "client"
        ].queryset.model.objects.filter(role="CLIENT")
