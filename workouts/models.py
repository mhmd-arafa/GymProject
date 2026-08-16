from django.db import models
from django.conf import settings

class WorkoutPlan(models.Model):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="workout_plans",
        limit_choices_to={"role": "CLIENT"},
    )
    title = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.client.username}"


class WorkoutDay(models.Model):
    plan = models.ForeignKey(
        WorkoutPlan,
        on_delete=models.CASCADE,
        related_name="days",
    )
    day_name = models.CharField(max_length=50)  # e.g. "Push Day"

    def __str__(self):
        return f"{self.day_name} ({self.plan.title})"


class Exercise(models.Model):
    day = models.ForeignKey(
        WorkoutDay,
        on_delete=models.CASCADE,
        related_name="exercises",
    )
    name = models.CharField(max_length=100)
    sets = models.PositiveIntegerField()
    reps = models.PositiveIntegerField()
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.name} ({self.sets}x{self.reps})"