from django.db import models
from django.conf import settings
from django.utils import timezone


class ProgressLog(models.Model):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="progress_logs",
        limit_choices_to={"role": "CLIENT"},
    )
    date = models.DateField(default=timezone.localdate)
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="الوزن بالكيلوجرام (مثال: 75.50)",
    )
    photo = models.ImageField(
        upload_to="progress_photos/",
        blank=True,
        null=True,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.client.username} - {self.weight} kg ({self.date})"
