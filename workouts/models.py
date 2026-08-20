from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class ExerciseCatalog(models.Model):
    """Canonical exercise. Plan exercises point here so that history, charts and
    personal records survive the trainer renaming or rebuilding a plan."""

    class MuscleGroup(models.TextChoices):
        CHEST = "CHEST", _("Chest")
        BACK = "BACK", _("Back")
        SHOULDERS = "SHOULDERS", _("Shoulders")
        BICEPS = "BICEPS", _("Biceps")
        TRICEPS = "TRICEPS", _("Triceps")
        QUADS = "QUADS", _("Quadriceps")
        HAMSTRINGS = "HAMSTRINGS", _("Hamstrings")
        GLUTES = "GLUTES", _("Glutes")
        CALVES = "CALVES", _("Calves")
        CORE = "CORE", _("Core")
        FULL_BODY = "FULL_BODY", _("Full body")
        CARDIO = "CARDIO", _("Cardio")

    class Equipment(models.TextChoices):
        BARBELL = "BARBELL", _("Barbell")
        DUMBBELL = "DUMBBELL", _("Dumbbell")
        MACHINE = "MACHINE", _("Machine")
        CABLE = "CABLE", _("Cable")
        BODYWEIGHT = "BODYWEIGHT", _("Bodyweight")
        KETTLEBELL = "KETTLEBELL", _("Kettlebell")
        BAND = "BAND", _("Resistance band")
        OTHER = "OTHER", _("Other")

    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=120, unique=True, blank=True)
    muscle_group = models.CharField(
        _("muscle group"), max_length=12, choices=MuscleGroup.choices
    )
    equipment = models.CharField(
        _("equipment"),
        max_length=12,
        choices=Equipment.choices,
        default=Equipment.OTHER,
    )
    video_url = models.URLField(_("demo video"), blank=True)
    instructions = models.TextField(_("instructions"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["muscle_group", "name"]
        verbose_name = _("catalog exercise")
        verbose_name_plural = _("exercise library")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120]
        super().save(*args, **kwargs)


class WorkoutPlan(models.Model):
    """A workout plan, either assigned to a client or held as a reusable template.

    A template has ``client=None`` and ``is_template=True``; an assigned plan has
    a client and ``is_template=False``. The check constraint below makes the
    invalid combinations unrepresentable at the database level.
    """

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workout_plans",
        limit_choices_to={"role": "CLIENT"},
        null=True,
        blank=True,
        verbose_name=_("client"),
    )
    title = models.CharField(_("title"), max_length=100)
    description = models.TextField(_("description"), blank=True)
    is_template = models.BooleanField(
        _("is a reusable template"),
        default=False,
        help_text=_("Templates have no client and can be cloned onto any client."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("workout plan")
        verbose_name_plural = _("workout plans")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(is_template=True, client__isnull=True)
                | models.Q(is_template=False, client__isnull=False),
                name="workoutplan_template_xor_client",
            )
        ]

    def __str__(self):
        if self.is_template:
            return f"{self.title} (template)"
        return f"{self.title} - {self.client.username}"

    @transaction.atomic
    def clone_for(self, client, title=None):
        """Deep-copy this plan onto ``client``, including days and exercises.

        This is the whole reason a trainer would choose this app over a
        spreadsheet: build "PPL - Beginner" once, assign it twenty times.
        Returns the newly created plan.
        """
        new_plan = WorkoutPlan.objects.create(
            client=client,
            title=title or self.title,
            description=self.description,
            is_template=False,
        )

        for day in self.days.all():
            new_day = WorkoutDay.objects.create(
                plan=new_plan, day_name=day.day_name, order=day.order
            )
            Exercise.objects.bulk_create(
                [
                    Exercise(
                        day=new_day,
                        catalog_exercise=exercise.catalog_exercise,
                        name=exercise.name,
                        sets=exercise.sets,
                        reps=exercise.reps,
                        reps_max=exercise.reps_max,
                        target_weight_kg=exercise.target_weight_kg,
                        rest_seconds=exercise.rest_seconds,
                        order=exercise.order,
                        notes=exercise.notes,
                    )
                    for exercise in day.exercises.all()
                ]
            )

        return new_plan


class WorkoutDay(models.Model):
    plan = models.ForeignKey(
        WorkoutPlan,
        on_delete=models.CASCADE,
        related_name="days",
        verbose_name=_("plan"),
    )
    day_name = models.CharField(_("day name"), max_length=50)  # e.g. "Push Day"
    order = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = _("workout day")
        verbose_name_plural = _("workout days")

    def __str__(self):
        return f"{self.day_name} ({self.plan.title})"


class Exercise(models.Model):
    """One prescribed exercise inside a plan day: what the client *should* do."""

    day = models.ForeignKey(
        WorkoutDay,
        on_delete=models.CASCADE,
        related_name="exercises",
        verbose_name=_("day"),
    )
    catalog_exercise = models.ForeignKey(
        ExerciseCatalog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_exercises",
        verbose_name=_("library exercise"),
        help_text=_("Link to the library to unlock history, charts and records."),
    )
    name = models.CharField(_("name"), max_length=100)
    sets = models.PositiveIntegerField(_("sets"))
    reps = models.PositiveIntegerField(
        _("reps"), help_text=_("Bottom of the target rep range.")
    )
    reps_max = models.PositiveIntegerField(
        _("reps (upper bound)"),
        null=True,
        blank=True,
        help_text=_("Top of the target rep range. Leave empty for a fixed rep count."),
    )
    target_weight_kg = models.DecimalField(
        _("target weight (kg)"), max_digits=6, decimal_places=2, null=True, blank=True
    )
    rest_seconds = models.PositiveIntegerField(_("rest (seconds)"), default=90)
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = _("exercise")
        verbose_name_plural = _("exercises")

    def __str__(self):
        return f"{self.name} ({self.sets}x{self.reps})"

    def save(self, *args, **kwargs):
        # Keep the free-text name in step with the library entry when one is
        # chosen, so the client-facing plan and the charts agree on naming.
        if self.catalog_exercise and not self.name:
            self.name = self.catalog_exercise.name
        super().save(*args, **kwargs)

    @property
    def rep_range_top(self):
        """Top of the prescribed rep range; ``reps`` when no upper bound is set."""
        return self.reps_max or self.reps

    @property
    def rep_range_display(self):
        if self.reps_max and self.reps_max != self.reps:
            return f"{self.reps}-{self.reps_max}"
        return str(self.reps)


class WorkoutSession(models.Model):
    """One actual trip to the gym: what the client *did*, as opposed to Exercise."""

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workout_sessions",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    plan = models.ForeignKey(
        WorkoutPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name=_("plan"),
    )
    day = models.ForeignKey(
        WorkoutDay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name=_("day"),
    )
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    completed_at = models.DateTimeField(_("completed at"), null=True, blank=True)
    perceived_effort = models.PositiveSmallIntegerField(
        _("session effort (1-10)"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("workout session")
        verbose_name_plural = _("workout sessions")
        indexes = [
            models.Index(fields=["client", "-started_at"]),
        ]

    def __str__(self):
        label = self.day.day_name if self.day else "Ad-hoc session"
        return f"{self.client.username} — {label} — {self.started_at:%Y-%m-%d}"

    @property
    def is_complete(self):
        return self.completed_at is not None

    @property
    def total_volume_kg(self):
        """Sum of weight x reps across working sets."""
        return sum(
            (s.volume_kg for s in self.set_logs.all() if not s.is_warmup),
            start=0,
        )


class SetLog(models.Model):
    """A single logged set. The atom the whole progress feature is built on."""

    session = models.ForeignKey(
        WorkoutSession,
        on_delete=models.CASCADE,
        related_name="set_logs",
        verbose_name=_("session"),
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="set_logs",
        verbose_name=_("plan exercise"),
    )
    catalog_exercise = models.ForeignKey(
        ExerciseCatalog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="set_logs",
        verbose_name=_("library exercise"),
    )
    exercise_name = models.CharField(
        _("exercise name"),
        max_length=100,
        blank=True,
        help_text=_("Denormalised so history survives the plan being deleted."),
    )
    set_number = models.PositiveSmallIntegerField(_("set number"), default=1)
    weight_kg = models.DecimalField(
        _("weight (kg)"), max_digits=6, decimal_places=2, default=0
    )
    reps = models.PositiveSmallIntegerField(_("reps"), default=0)
    rpe = models.DecimalField(
        _("RPE"),
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text=_("Rate of perceived exertion, 1-10."),
    )
    is_warmup = models.BooleanField(_("warm-up set"), default=False)
    completed_at = models.DateTimeField(_("completed at"), auto_now_add=True)

    class Meta:
        ordering = ["set_number", "id"]
        verbose_name = _("set log")
        verbose_name_plural = _("set logs")
        indexes = [
            # Drives "last time you did this" and the per-exercise charts.
            models.Index(fields=["catalog_exercise", "-completed_at"]),
        ]

    def __str__(self):
        return f"{self.exercise_name or self.catalog_exercise} — {self.weight_kg}kg x {self.reps}"

    def save(self, *args, **kwargs):
        # Denormalise identity from the plan exercise at write time. Doing this
        # here rather than in the view means every code path -- admin, shell,
        # import -- gets consistent history.
        if self.exercise:
            if self.catalog_exercise_id is None:
                self.catalog_exercise = self.exercise.catalog_exercise
            if not self.exercise_name:
                self.exercise_name = self.exercise.name
        if not self.exercise_name and self.catalog_exercise:
            self.exercise_name = self.catalog_exercise.name
        super().save(*args, **kwargs)

    @property
    def volume_kg(self):
        return self.weight_kg * self.reps

    @property
    def estimated_1rm_kg(self):
        """Epley estimate. Deterministic and good enough to trend against."""
        if self.reps <= 0:
            return None
        if self.reps == 1:
            return float(self.weight_kg)
        return round(float(self.weight_kg) * (1 + self.reps / 30.0), 2)


class PersonalRecord(models.Model):
    """An auto-detected best. Written by ``workouts.services.detect_prs``."""

    class RecordType(models.TextChoices):
        MAX_WEIGHT = "MAX_WEIGHT", _("Heaviest weight")
        MAX_REPS = "MAX_REPS", _("Most reps")
        MAX_VOLUME = "MAX_VOLUME", _("Best single-set volume")
        ESTIMATED_1RM = "ESTIMATED_1RM", _("Best estimated 1RM")

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_records",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    catalog_exercise = models.ForeignKey(
        ExerciseCatalog,
        on_delete=models.CASCADE,
        related_name="personal_records",
        verbose_name=_("exercise"),
    )
    record_type = models.CharField(
        _("record type"), max_length=15, choices=RecordType.choices
    )
    value = models.DecimalField(_("value"), max_digits=8, decimal_places=2)
    set_log = models.ForeignKey(
        SetLog,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="records",
        verbose_name=_("set"),
    )
    achieved_on = models.DateField(_("achieved on"))

    class Meta:
        ordering = ["-achieved_on"]
        unique_together = [("client", "catalog_exercise", "record_type")]
        verbose_name = _("personal record")
        verbose_name_plural = _("personal records")

    def __str__(self):
        return (
            f"{self.client.username} — {self.catalog_exercise} — "
            f"{self.get_record_type_display()}: {self.value}"
        )
