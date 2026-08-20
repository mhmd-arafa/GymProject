from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

RATING_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]


class BodyMeasurement(models.Model):
    """A dated set of tape measurements. Weight alone is a poor progress signal."""

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="measurements",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    date = models.DateField(_("date"), default=timezone.localdate)
    weight_kg = models.DecimalField(
        _("weight (kg)"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    waist_cm = models.DecimalField(
        _("waist (cm)"), max_digits=5, decimal_places=1, null=True, blank=True
    )
    chest_cm = models.DecimalField(
        _("chest (cm)"), max_digits=5, decimal_places=1, null=True, blank=True
    )
    arm_cm = models.DecimalField(
        _("arm (cm)"), max_digits=5, decimal_places=1, null=True, blank=True
    )
    thigh_cm = models.DecimalField(
        _("thigh (cm)"), max_digits=5, decimal_places=1, null=True, blank=True
    )
    hip_cm = models.DecimalField(
        _("hip (cm)"), max_digits=5, decimal_places=1, null=True, blank=True
    )
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["-date"]
        unique_together = [("client", "date")]
        verbose_name = _("body measurement")
        verbose_name_plural = _("body measurements")

    def __str__(self):
        return f"{self.client.username} — {self.date}"


class ProgressPhoto(models.Model):
    """A physique photo. Only usable as a testimonial with explicit consent.

    One model covers both entry points -- a photo attached to a weekly check-in
    and one uploaded standalone -- so the before/after comparison, the coach's
    progress view and the consent gate all see every photo. A check-in photo is
    simply one with ``checkin`` set.
    """

    class Pose(models.TextChoices):
        FRONT = "FRONT", _("Front")
        SIDE = "SIDE", _("Side")
        BACK = "BACK", _("Back")

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="progress_photos",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    checkin = models.ForeignKey(
        "progress.CheckIn",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photos",
        verbose_name=_("check-in"),
        help_text=_("Set when the photo was sent as part of a weekly check-in."),
    )
    date = models.DateField(_("date"), default=timezone.localdate)
    image = models.ImageField(_("photo"), upload_to="progress_photos/%Y/%m/")
    pose = models.CharField(
        _("pose"), max_length=10, choices=Pose.choices, default=Pose.FRONT
    )
    consent_public = models.BooleanField(
        _("I allow my coach to share this photo publicly"),
        default=False,
        help_text=_(
            "Off by default. Only photos you tick here can appear on the public "
            "results page. You can withdraw this at any time."
        ),
    )
    consent_given_at = models.DateTimeField(
        _("consent given at"), null=True, blank=True
    )
    uploaded_at = models.DateTimeField(_("uploaded at"), auto_now_add=True)

    class Meta:
        ordering = ["-date", "pose"]
        verbose_name = _("progress photo")
        verbose_name_plural = _("progress photos")
        indexes = [
            models.Index(fields=["client", "-date"]),
        ]

    def __str__(self):
        return f"{self.client.username} — {self.get_pose_display()} — {self.date}"

    def save(self, *args, **kwargs):
        # Stamp the moment consent was granted, and clear it if withdrawn, so
        # there is an auditable record rather than just a boolean.
        if self.consent_public and self.consent_given_at is None:
            self.consent_given_at = timezone.now()
        elif not self.consent_public:
            self.consent_given_at = None
        super().save(*args, **kwargs)


class CheckIn(models.Model):
    """A scheduled weekly check-in: the cadence clients actually pay for."""

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="checkins",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    due_date = models.DateField(_("due date"))
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)

    weight_kg = models.DecimalField(
        _("weight (kg)"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    energy_rating = models.PositiveSmallIntegerField(
        _("energy (1-5)"), null=True, blank=True, validators=RATING_VALIDATORS
    )
    sleep_rating = models.PositiveSmallIntegerField(
        _("sleep (1-5)"), null=True, blank=True, validators=RATING_VALIDATORS
    )
    adherence_rating = models.PositiveSmallIntegerField(
        _("plan adherence (1-5)"), null=True, blank=True, validators=RATING_VALIDATORS
    )
    note = models.TextField(_("how did the week go?"), blank=True)

    trainer_reply = models.TextField(_("coach reply"), blank=True)
    replied_at = models.DateTimeField(_("replied at"), null=True, blank=True)
    reviewed = models.BooleanField(_("reviewed by coach"), default=False)

    class Meta:
        ordering = ["-due_date"]
        unique_together = [("client", "due_date")]
        verbose_name = _("check-in")
        verbose_name_plural = _("check-ins")

    def __str__(self):
        return f"{self.client.username} — check-in due {self.due_date}"

    @property
    def is_submitted(self):
        return self.submitted_at is not None

    @property
    def is_overdue(self):
        return not self.is_submitted and self.due_date < timezone.localdate()
