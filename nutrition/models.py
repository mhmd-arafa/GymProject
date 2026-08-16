from django.db import models
from django.conf import settings


class NutritionPlan(models.Model):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nutrition_plans",
        limit_choices_to={"role": "CLIENT"},
    )
    title = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.client.username}"


class Meal(models.Model):
    plan = models.ForeignKey(
        NutritionPlan,
        on_delete=models.CASCADE,
        related_name="meals",
    )
    name = models.CharField(max_length=100)  # e.g. "Breakfast"
    calories = models.PositiveIntegerField()
    protein = models.PositiveIntegerField(help_text="بالجرام")
    carbs = models.PositiveIntegerField(help_text="بالجرام")
    fats = models.PositiveIntegerField(help_text="بالجرام")
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.name} ({self.calories} kcal)"
