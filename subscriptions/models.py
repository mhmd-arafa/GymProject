from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SubscriptionPlan(models.Model):
    """A package the trainer sells, e.g. "3 months online coaching"."""

    name = models.CharField(_("name"), max_length=100)
    duration_days = models.PositiveIntegerField(_("duration in days"), default=30)
    price_egp = models.DecimalField(
        _("price (EGP)"), max_digits=8, decimal_places=2, default=0
    )
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["duration_days"]
        verbose_name = _("subscription plan")
        verbose_name_plural = _("subscription plans")

    def __str__(self):
        return f"{self.name} ({self.duration_days}d)"


class Subscription(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", _("Awaiting payment")
        ACTIVE = "ACTIVE", _("Active")
        EXPIRED = "EXPIRED", _("Expired")
        CANCELLED = "CANCELLED", _("Cancelled")

    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name=_("plan"),
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    start_date = models.DateField(_("start date"), null=True, blank=True)
    end_date = models.DateField(_("end date"), null=True, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")

    def __str__(self):
        return f"{self.client.username} — {self.plan.name} ({self.get_status_display()})"

    def activate(self, start=None):
        """Set the window and mark active. Caller is responsible for saving."""
        self.start_date = start or timezone.localdate()
        self.end_date = self.start_date + timedelta(days=self.plan.duration_days)
        self.status = self.Status.ACTIVE

    @property
    def days_remaining(self):
        """Whole days until expiry, or None when there is no end date yet."""
        if not self.end_date:
            return None
        return (self.end_date - timezone.localdate()).days

    @property
    def is_active(self):
        remaining = self.days_remaining
        return self.status == self.Status.ACTIVE and remaining is not None and remaining >= 0


class PaymentProof(models.Model):
    """Client-uploaded evidence of an InstaPay / Vodafone Cash transfer.

    This is how payment actually works for this trainer today: the client sends
    money and uploads a screenshot plus reference number, and the trainer
    approves it by eye. A payment gateway can later call
    ``subscriptions.services.approve_payment`` on the same model.
    """

    class Method(models.TextChoices):
        INSTAPAY = "INSTAPAY", _("InstaPay")
        VODAFONE_CASH = "VODAFONE_CASH", _("Vodafone Cash")
        BANK_TRANSFER = "BANK_TRANSFER", _("Bank transfer")
        CASH = "CASH", _("Cash in person")

    class Status(models.TextChoices):
        PENDING = "PENDING", _("Pending review")
        APPROVED = "APPROVED", _("Approved")
        REJECTED = "REJECTED", _("Rejected")

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="payment_proofs",
        verbose_name=_("subscription"),
    )
    method = models.CharField(
        _("payment method"), max_length=15, choices=Method.choices
    )
    reference_number = models.CharField(
        _("reference number"),
        max_length=100,
        blank=True,
        help_text=_("The transaction reference shown in your transfer receipt."),
    )
    amount_egp = models.DecimalField(
        _("amount paid (EGP)"), max_digits=8, decimal_places=2
    )
    screenshot = models.ImageField(
        _("transfer screenshot"), upload_to="payment_proofs/%Y/%m/", blank=True
    )
    status = models.CharField(
        _("status"), max_length=10, choices=Status.choices, default=Status.PENDING
    )
    note = models.CharField(_("note"), max_length=255, blank=True)
    submitted_at = models.DateTimeField(_("submitted at"), auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_payments",
        limit_choices_to={"role": "ADMIN"},
        verbose_name=_("reviewed by"),
    )
    reviewed_at = models.DateTimeField(_("reviewed at"), null=True, blank=True)
    rejection_reason = models.CharField(
        _("rejection reason"), max_length=255, blank=True
    )

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = _("payment proof")
        verbose_name_plural = _("payment proofs")

    def __str__(self):
        return f"{self.get_method_display()} {self.amount_egp} EGP — {self.get_status_display()}"
