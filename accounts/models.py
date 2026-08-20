from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", _("Admin")
        CLIENT = "CLIENT", _("Client")

    role = models.CharField(
        _("role"), max_length=10, choices=Role.choices, default=Role.CLIENT
    )
    phone = models.CharField(
        _("phone number"),
        max_length=20,
        blank=True,
        help_text=_("Egyptian mobile, e.g. 01012345678. Used for WhatsApp."),
    )
    language = models.CharField(
        _("preferred language"),
        max_length=5,
        choices=settings.LANGUAGES,
        default="en",
    )


class TrainerNote(models.Model):
    """Private note the trainer keeps on a client. Never shown to the client."""

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trainer_notes",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="authored_notes",
        limit_choices_to={"role": "ADMIN"},
        verbose_name=_("author"),
    )
    body = models.TextField(_("note"))
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("trainer note")
        verbose_name_plural = _("trainer notes")

    def __str__(self):
        return f"Note on {self.client.username} ({self.created_at:%Y-%m-%d})"


class IntakeForm(models.Model):
    """Questionnaire the client fills in once, before a plan is written."""

    class Goal(models.TextChoices):
        LOSE_FAT = "LOSE_FAT", _("Lose fat")
        BUILD_MUSCLE = "BUILD_MUSCLE", _("Build muscle")
        RECOMP = "RECOMP", _("Body recomposition")
        STRENGTH = "STRENGTH", _("Get stronger")
        GENERAL = "GENERAL", _("General fitness")

    class Equipment(models.TextChoices):
        FULL_GYM = "FULL_GYM", _("Full gym")
        HOME_BASIC = "HOME_BASIC", _("Home — dumbbells / bands")
        BODYWEIGHT = "BODYWEIGHT", _("Bodyweight only")

    client = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="intake",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    goal = models.CharField(
        _("main goal"), max_length=20, choices=Goal.choices, default=Goal.GENERAL
    )
    equipment_access = models.CharField(
        _("equipment access"),
        max_length=20,
        choices=Equipment.choices,
        default=Equipment.FULL_GYM,
    )
    training_days_per_week = models.PositiveSmallIntegerField(
        _("training days available per week"), default=3
    )
    injuries = models.TextField(_("injuries or pain"), blank=True)
    allergies = models.TextField(_("food allergies"), blank=True)
    food_dislikes = models.TextField(_("foods you dislike"), blank=True)
    notes = models.TextField(_("anything else"), blank=True)
    submitted_at = models.DateTimeField(_("submitted at"), auto_now_add=True)

    class Meta:
        verbose_name = _("intake form")
        verbose_name_plural = _("intake forms")

    def __str__(self):
        return f"Intake — {self.client.username}"
