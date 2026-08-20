from django.db import transaction
from django.utils import timezone

from .models import PaymentProof


@transaction.atomic
def approve_payment(proof, reviewer, start=None):
    """Approve a payment proof and activate the subscription behind it.

    Returns the activated ``Subscription``. Idempotent: approving an
    already-approved proof leaves the subscription window untouched, so a
    double-click in the admin cannot silently extend someone's access.
    """
    if proof.status == PaymentProof.Status.APPROVED:
        return proof.subscription

    proof.status = PaymentProof.Status.APPROVED
    proof.reviewed_by = reviewer
    proof.reviewed_at = timezone.now()
    proof.rejection_reason = ""
    proof.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"]
    )

    subscription = proof.subscription
    subscription.activate(start=start)
    subscription.save(update_fields=["status", "start_date", "end_date"])
    return subscription


@transaction.atomic
def reject_payment(proof, reviewer, reason=""):
    """Mark a proof rejected, leaving the subscription pending."""
    proof.status = PaymentProof.Status.REJECTED
    proof.reviewed_by = reviewer
    proof.reviewed_at = timezone.now()
    proof.rejection_reason = reason
    proof.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"]
    )
    return proof


def expire_overdue_subscriptions():
    """Flip ACTIVE subscriptions whose end date has passed to EXPIRED.

    Called from the trainer dashboard so the attention queue never shows a stale
    "active" badge. Cheap enough to run per page load; returns the row count.
    """
    from .models import Subscription

    return Subscription.objects.filter(
        status=Subscription.Status.ACTIVE,
        end_date__lt=timezone.localdate(),
    ).update(status=Subscription.Status.EXPIRED)
