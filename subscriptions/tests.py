# pyrefly: ignore [missing-import]
from datetime import timedelta
from decimal import Decimal

# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import PaymentProof, Subscription, SubscriptionPlan

User = get_user_model()


class SubscriptionFixtureMixin:
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.plan = SubscriptionPlan.objects.create(
            name="3 Months Coaching", duration_days=90, price_egp=Decimal("3000")
        )

    def make_subscription(self, status=Subscription.Status.PENDING):
        return Subscription.objects.create(
            client=self.client_user, plan=self.plan, status=status
        )

    def make_proof(self, subscription=None, status=PaymentProof.Status.PENDING):
        return PaymentProof.objects.create(
            subscription=subscription or self.make_subscription(),
            method=PaymentProof.Method.INSTAPAY,
            reference_number="REF123456",
            amount_egp=Decimal("3000"),
            status=status,
        )


class ApprovePaymentTests(SubscriptionFixtureMixin, TestCase):
    def test_approval_activates_and_computes_end_date(self):
        proof = self.make_proof()
        today = timezone.localdate()

        subscription = services.approve_payment(proof, self.coach)

        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)
        self.assertEqual(subscription.start_date, today)
        self.assertEqual(subscription.end_date, today + timedelta(days=90))
        self.assertTrue(subscription.is_active)

        proof.refresh_from_db()
        self.assertEqual(proof.status, PaymentProof.Status.APPROVED)
        self.assertEqual(proof.reviewed_by, self.coach)
        self.assertIsNotNone(proof.reviewed_at)

    def test_approval_is_idempotent(self):
        """A double-click must not silently extend someone's access."""
        proof = self.make_proof()
        first = services.approve_payment(proof, self.coach)
        original_end = first.end_date

        again = services.approve_payment(proof, self.coach)

        self.assertEqual(again.end_date, original_end)

    def test_approval_honours_an_explicit_start_date(self):
        proof = self.make_proof()
        start = timezone.localdate() - timedelta(days=10)

        subscription = services.approve_payment(proof, self.coach, start=start)

        self.assertEqual(subscription.start_date, start)
        self.assertEqual(subscription.end_date, start + timedelta(days=90))

    def test_rejection_leaves_subscription_pending(self):
        proof = self.make_proof()
        services.reject_payment(proof, self.coach, reason="Wrong amount")

        proof.refresh_from_db()
        self.assertEqual(proof.status, PaymentProof.Status.REJECTED)
        self.assertEqual(proof.rejection_reason, "Wrong amount")
        self.assertEqual(proof.subscription.status, Subscription.Status.PENDING)
        self.assertFalse(proof.subscription.is_active)


class SubscriptionModelTests(SubscriptionFixtureMixin, TestCase):
    def test_days_remaining_is_none_without_end_date(self):
        subscription = self.make_subscription()
        self.assertIsNone(subscription.days_remaining)
        self.assertFalse(subscription.is_active)

    def test_days_remaining_counts_down(self):
        subscription = self.make_subscription(status=Subscription.Status.ACTIVE)
        subscription.start_date = timezone.localdate()
        subscription.end_date = timezone.localdate() + timedelta(days=5)
        subscription.save()

        self.assertEqual(subscription.days_remaining, 5)
        self.assertTrue(subscription.is_active)

    def test_expired_window_is_not_active(self):
        """A past end date must not read as active even if the status lags."""
        subscription = self.make_subscription(status=Subscription.Status.ACTIVE)
        subscription.end_date = timezone.localdate() - timedelta(days=1)
        subscription.save()
        self.assertFalse(subscription.is_active)

    def test_expire_overdue_flips_status(self):
        subscription = self.make_subscription(status=Subscription.Status.ACTIVE)
        subscription.end_date = timezone.localdate() - timedelta(days=1)
        subscription.save()

        count = services.expire_overdue_subscriptions()

        subscription.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(subscription.status, Subscription.Status.EXPIRED)

    def test_expire_leaves_current_subscriptions_alone(self):
        subscription = self.make_subscription(status=Subscription.Status.ACTIVE)
        subscription.end_date = timezone.localdate() + timedelta(days=3)
        subscription.save()

        services.expire_overdue_subscriptions()

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.ACTIVE)


class PaymentProofFormTests(SubscriptionFixtureMixin, TestCase):
    def test_digital_transfer_needs_reference_or_screenshot(self):
        from .forms import PaymentProofForm

        form = PaymentProofForm(
            data={
                "method": PaymentProof.Method.INSTAPAY,
                "amount_egp": "3000",
                "reference_number": "",
            }
        )
        self.assertFalse(form.is_valid())

    def test_cash_needs_neither(self):
        from .forms import PaymentProofForm

        form = PaymentProofForm(
            data={
                "method": PaymentProof.Method.CASH,
                "amount_egp": "3000",
                "reference_number": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)


class PaymentViewTests(SubscriptionFixtureMixin, TestCase):
    def test_client_can_upload_a_proof(self):
        subscription = self.make_subscription()
        self.client.login(username="client1", password="password123")

        response = self.client.post(
            reverse("payment-proof-upload", args=[subscription.pk]),
            {
                "method": PaymentProof.Method.VODAFONE_CASH,
                "reference_number": "VC998877",
                "amount_egp": "3000",
                "note": "",
            },
        )

        self.assertRedirects(response, reverse("my-subscription"))
        self.assertTrue(subscription.payment_proofs.exists())

    def test_client_cannot_upload_to_another_clients_subscription(self):
        subscription = self.make_subscription()
        intruder = User.objects.create_user(
            username="intruder", password="password123", role=User.Role.CLIENT
        )
        self.client.force_login(intruder)

        response = self.client.get(
            reverse("payment-proof-upload", args=[subscription.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_approve_view_requires_admin(self):
        proof = self.make_proof()
        self.client.login(username="client1", password="password123")

        response = self.client.post(reverse("payment-approve", args=[proof.pk]))

        self.assertIn(response.status_code, (302, 403))
        proof.refresh_from_db()
        self.assertEqual(proof.status, PaymentProof.Status.PENDING)

    def test_coach_approves_through_the_view(self):
        proof = self.make_proof()
        self.client.login(username="coach", password="password123")

        response = self.client.post(reverse("payment-approve", args=[proof.pk]))

        self.assertRedirects(response, reverse("payment-queue"))
        proof.refresh_from_db()
        self.assertEqual(proof.status, PaymentProof.Status.APPROVED)
        self.assertEqual(proof.subscription.status, Subscription.Status.ACTIVE)

    def test_coach_rejects_with_a_reason(self):
        proof = self.make_proof()
        self.client.login(username="coach", password="password123")

        self.client.post(
            reverse("payment-reject", args=[proof.pk]),
            {"rejection_reason": "Screenshot unreadable"},
        )

        proof.refresh_from_db()
        self.assertEqual(proof.status, PaymentProof.Status.REJECTED)
        self.assertEqual(proof.rejection_reason, "Screenshot unreadable")

    def test_queue_requires_admin(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("payment-queue"))
        self.assertIn(response.status_code, (302, 403))

    def test_client_sees_only_their_own_subscriptions(self):
        self.make_subscription()
        other = User.objects.create_user(
            username="other", password="password123", role=User.Role.CLIENT
        )
        other_plan = SubscriptionPlan.objects.create(
            name="Other Package", duration_days=30, price_egp=Decimal("1000")
        )
        Subscription.objects.create(client=other, plan=other_plan)

        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("my-subscription"))

        self.assertContains(response, "3 Months Coaching")
        # The other client's package appears only in the "available" list, never
        # as one of their own subscriptions, so check the history section count.
        self.assertEqual(len(response.context["subscriptions"]), 1)


class SubscriptionAdminTests(TestCase):
    def test_models_registered(self):
        from django.contrib import admin

        self.assertIn(Subscription, admin.site._registry)
        self.assertIn(PaymentProof, admin.site._registry)
        self.assertIn(SubscriptionPlan, admin.site._registry)
