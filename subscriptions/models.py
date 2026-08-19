from django.db import models
from django.conf import settings
from django.utils import timezone


class Subscription(models.Model):
    class PlanType(models.TextChoices):
        MONTHLY = "MONTHLY", "شهري (شهر واحد)"
        QUARTERLY = "QUARTERLY", "ربع سنوي (3 شهور)"
        SEMI_ANNUAL = "SEMI_ANNUAL", "نصف سنوي (6 شهور)"
        ANNUAL = "ANNUAL", "سنوي (12 شهر)"
        CUSTOM = "CUSTOM", "مخصص"

    class Status(models.TextChoices):
        PENDING = "PENDING", "قيد الانتظار"
        ACTIVE = "ACTIVE", "نشط"
        EXPIRED = "EXPIRED", "منتهي"
        CANCELLED = "CANCELLED", "ملغي"

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        limit_choices_to={"role": "CLIENT"},
    )
    plan_type = models.CharField(
        max_length=50,
        choices=PlanType.choices,
        default=PlanType.MONTHLY,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.client.username} - {self.get_status_display()} ({self.get_plan_type_display()})"

    def is_currently_active(self):
        if self.status != self.Status.ACTIVE:
            return False
        today = timezone.localdate()
        if self.start_date and self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        return True
