# pyrefly: ignore [missing-import]
from datetime import timedelta
from decimal import Decimal

# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from progress.models import CheckIn
from subscriptions.models import PaymentProof, Subscription, SubscriptionPlan
from workouts.models import WorkoutPlan, WorkoutSession

from .models import IntakeForm, TrainerNote
from .templatetags.gym_extras import normalise_egyptian_phone, whatsapp_url

User = get_user_model()


class AccountsFixtureMixin:
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )


class TrainerNoteTests(AccountsFixtureMixin, TestCase):
    """Private notes must never reach a client through any route."""

    def test_coach_can_add_a_note(self):
        self.client.login(username="coach", password="password123")
        response = self.client.post(
            reverse("trainer-note-add", args=[self.client_user.pk]),
            {"body": "Bad left knee - no deep lunges."},
        )
        self.assertRedirects(
            response, reverse("client-detail", args=[self.client_user.pk])
        )
        note = TrainerNote.objects.get()
        self.assertEqual(note.author, self.coach)
        self.assertEqual(note.client, self.client_user)

    def test_note_shows_on_the_admin_only_client_detail_page(self):
        TrainerNote.objects.create(
            client=self.client_user, author=self.coach, body="Injury note here"
        )
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("client-detail", args=[self.client_user.pk]))
        self.assertContains(response, "Injury note here")

    def test_client_cannot_open_the_page_that_renders_notes(self):
        TrainerNote.objects.create(
            client=self.client_user, author=self.coach, body="Secret injury note"
        )
        self.client.login(username="client1", password="password123")

        response = self.client.get(reverse("client-detail", args=[self.client_user.pk]))

        self.assertIn(response.status_code, (302, 403))

    def test_client_cannot_post_a_note(self):
        self.client.login(username="client1", password="password123")
        response = self.client.post(
            reverse("trainer-note-add", args=[self.client_user.pk]),
            {"body": "self-written"},
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(TrainerNote.objects.exists())

    def test_note_text_never_appears_on_any_client_facing_page(self):
        TrainerNote.objects.create(
            client=self.client_user, author=self.coach, body="ZZUNIQUENOTEZZ"
        )
        self.client.login(username="client1", password="password123")

        for name in (
            "client-home",
            "my-workout-plan",
            "my-nutrition-plan",
            "my-progress",
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertNotContains(response, "ZZUNIQUENOTEZZ")


class IntakeFormTests(AccountsFixtureMixin, TestCase):
    def test_client_can_submit_intake(self):
        self.client.login(username="client1", password="password123")
        response = self.client.post(
            reverse("intake"),
            {
                "goal": IntakeForm.Goal.BUILD_MUSCLE,
                "equipment_access": IntakeForm.Equipment.FULL_GYM,
                "training_days_per_week": "4",
                "injuries": "Left shoulder",
                "allergies": "Peanuts",
                "food_dislikes": "Liver",
                "notes": "",
            },
        )
        self.assertRedirects(response, reverse("client-home"))
        intake = IntakeForm.objects.get()
        self.assertEqual(intake.client, self.client_user)
        self.assertEqual(intake.training_days_per_week, 4)

    def test_second_visit_redirects_to_edit(self):
        IntakeForm.objects.create(client=self.client_user)
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("intake"))
        self.assertRedirects(response, reverse("intake-edit"))

    def test_training_days_are_validated(self):
        from .forms import IntakeFormForm

        form = IntakeFormForm(
            data={
                "goal": IntakeForm.Goal.GENERAL,
                "equipment_access": IntakeForm.Equipment.FULL_GYM,
                "training_days_per_week": "9",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("training_days_per_week", form.errors)


class DashboardRoutingTests(AccountsFixtureMixin, TestCase):
    def test_admin_lands_on_the_attention_queue(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("dashboard-home"))
        self.assertRedirects(response, reverse("trainer-dashboard"))

    def test_client_lands_on_their_home(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("dashboard-home"))
        self.assertRedirects(response, reverse("client-home"))

    def test_client_cannot_open_the_dashboard(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("trainer-dashboard"))
        self.assertIn(response.status_code, (302, 403))


class AttentionQueueTests(AccountsFixtureMixin, TestCase):
    """Each queue card must pick up exactly the clients it claims to."""

    def setUp(self):
        super().setUp()
        self.client.login(username="coach", password="password123")
        self.package = SubscriptionPlan.objects.create(
            name="Monthly", duration_days=30, price_egp=Decimal("1000")
        )

    def _dashboard(self):
        return self.client.get(reverse("trainer-dashboard")).context

    def test_client_without_a_plan_is_listed(self):
        context = self._dashboard()
        self.assertIn(self.client_user, list(context["without_plan"]))

    def test_client_with_a_plan_is_not_listed(self):
        WorkoutPlan.objects.create(client=self.client_user, title="Plan")
        context = self._dashboard()
        self.assertNotIn(self.client_user, list(context["without_plan"]))

    def test_template_only_does_not_count_as_an_assigned_plan(self):
        """A template is not an assignment, so the client still needs one."""
        WorkoutPlan.objects.create(client=None, is_template=True, title="Template")
        context = self._dashboard()
        self.assertIn(self.client_user, list(context["without_plan"]))

    def test_inactive_client_is_listed(self):
        context = self._dashboard()
        self.assertIn(self.client_user, context["inactive_clients"])

    def test_recently_active_client_is_not_listed(self):
        WorkoutSession.objects.create(client=self.client_user)
        context = self._dashboard()
        self.assertNotIn(self.client_user, context["inactive_clients"])

    def test_expiring_subscription_is_listed(self):
        subscription = Subscription.objects.create(
            client=self.client_user,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=3),
        )
        context = self._dashboard()
        self.assertIn(subscription, list(context["expiring_soon"]))

    def test_distant_expiry_is_not_listed(self):
        Subscription.objects.create(
            client=self.client_user,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=60),
        )
        context = self._dashboard()
        self.assertEqual(len(context["expiring_soon"]), 0)

    def test_unreviewed_checkin_is_listed(self):
        checkin = CheckIn.objects.create(
            client=self.client_user,
            due_date=timezone.localdate(),
            submitted_at=timezone.now(),
        )
        context = self._dashboard()
        self.assertIn(checkin, list(context["unreviewed_checkins"]))

    def test_reviewed_checkin_is_not_listed(self):
        CheckIn.objects.create(
            client=self.client_user,
            due_date=timezone.localdate(),
            submitted_at=timezone.now(),
            reviewed=True,
        )
        context = self._dashboard()
        self.assertEqual(len(context["unreviewed_checkins"]), 0)

    def test_pending_payment_is_listed(self):
        subscription = Subscription.objects.create(
            client=self.client_user, plan=self.package
        )
        proof = PaymentProof.objects.create(
            subscription=subscription,
            method=PaymentProof.Method.INSTAPAY,
            amount_egp=Decimal("1000"),
        )
        context = self._dashboard()
        self.assertIn(proof, list(context["pending_payments"]))

    def test_client_without_intake_is_listed(self):
        context = self._dashboard()
        self.assertIn(self.client_user, list(context["without_intake"]))

        IntakeForm.objects.create(client=self.client_user)
        context = self._dashboard()
        self.assertNotIn(self.client_user, list(context["without_intake"]))

    def test_dashboard_expires_stale_subscriptions_on_load(self):
        subscription = Subscription.objects.create(
            client=self.client_user,
            plan=self.package,
            status=Subscription.Status.ACTIVE,
            end_date=timezone.localdate() - timedelta(days=1),
        )
        self._dashboard()
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, Subscription.Status.EXPIRED)


class WhatsAppHelperTests(TestCase):
    """Egyptian numbers are written locally; wa.me needs a country code."""

    def test_local_mobile_gets_country_code(self):
        self.assertEqual(normalise_egyptian_phone("01012345678"), "201012345678")

    def test_plus_prefixed_number_is_kept(self):
        self.assertEqual(normalise_egyptian_phone("+201012345678"), "201012345678")

    def test_double_zero_prefix_is_stripped(self):
        self.assertEqual(normalise_egyptian_phone("00201012345678"), "201012345678")

    def test_spaces_and_dashes_are_ignored(self):
        self.assertEqual(normalise_egyptian_phone("010 1234-5678"), "201012345678")

    def test_bare_mobile_without_trunk_zero(self):
        self.assertEqual(normalise_egyptian_phone("1012345678"), "201012345678")

    def test_empty_input_returns_empty(self):
        self.assertEqual(normalise_egyptian_phone(""), "")
        self.assertEqual(normalise_egyptian_phone(None), "")
        self.assertEqual(normalise_egyptian_phone("not a phone"), "")

    def test_url_is_built_and_text_encoded(self):
        url = whatsapp_url("01012345678", "Hello there")
        self.assertTrue(url.startswith("https://wa.me/201012345678?text="))
        self.assertIn("Hello%20there", url)

    def test_url_is_empty_without_a_usable_phone(self):
        """An empty string lets the template hide the button entirely."""
        self.assertEqual(whatsapp_url("", "hi"), "")

    def test_url_without_text(self):
        self.assertEqual(whatsapp_url("01012345678"), "https://wa.me/201012345678")


class ProfileTests(AccountsFixtureMixin, TestCase):
    def test_client_can_set_phone_and_language(self):
        self.client.login(username="client1", password="password123")
        response = self.client.post(
            reverse("profile-edit"),
            {
                "first_name": "Ahmed",
                "last_name": "",
                "email": "a@example.com",
                "phone": "01012345678",
                "language": "ar",
            },
        )
        self.assertRedirects(response, reverse("client-home"))
        self.client_user.refresh_from_db()
        self.assertEqual(self.client_user.phone, "01012345678")
        self.assertEqual(self.client_user.language, "ar")

    def test_registration_accepts_a_phone(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "newclient",
                "email": "new@example.com",
                "phone": "01098765432",
                "password1": "SuperSecret123",
                "password2": "SuperSecret123",
            },
        )
        self.assertRedirects(response, reverse("login"))
        user = User.objects.get(username="newclient")
        self.assertEqual(user.role, User.Role.CLIENT)
        self.assertEqual(user.phone, "01098765432")


class LanguageTests(AccountsFixtureMixin, TestCase):
    def test_english_is_the_default(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'lang="en"')
        self.assertContains(response, 'dir="ltr"')

    def test_arabic_flips_direction_to_rtl(self):
        self.client.post(reverse("set_language"), {"language": "ar", "next": "/"})
        response = self.client.get(reverse("login"))
        self.assertContains(response, 'dir="rtl"')


class ClientListTests(AccountsFixtureMixin, TestCase):
    def test_only_clients_are_listed(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("client-list"))
        usernames = [c.username for c in response.context["clients"]]
        self.assertIn("client1", usernames)
        self.assertNotIn("coach", usernames)

    def test_client_cannot_list_clients(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("client-list"))
        self.assertIn(response.status_code, (302, 403))


class AccountsAdminTests(TestCase):
    def test_models_registered(self):
        from django.contrib import admin

        self.assertIn(TrainerNote, admin.site._registry)
        self.assertIn(IntakeForm, admin.site._registry)
