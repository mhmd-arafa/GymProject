# pyrefly: ignore [missing-import]
from datetime import date, timedelta
from decimal import Decimal

# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .charts import build_line_chart, measurement_chart
from .models import BodyMeasurement, CheckIn, ProgressPhoto

User = get_user_model()

#: Smallest valid PNG, so tests never depend on a fixture file on disk.
ONE_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_image(name="test.png"):
    return SimpleUploadedFile(name, ONE_PIXEL_PNG, content_type="image/png")


class ProgressFixtureMixin:
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )


class ConsentTests(ProgressFixtureMixin, TestCase):
    """The consent flag is only real if the public page actually filters on it."""

    def test_public_results_excludes_photos_without_consent(self):
        ProgressPhoto.objects.create(
            client=self.client_user,
            image=make_image("private1.png"),
            date=date(2026, 1, 1),
            consent_public=False,
        )
        ProgressPhoto.objects.create(
            client=self.client_user,
            image=make_image("private2.png"),
            date=date(2026, 2, 1),
            consent_public=False,
        )

        response = self.client.get(reverse("public-results"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["photos"]), 0)
        self.assertNotContains(response, "private1")
        self.assertNotContains(response, "private2")

    def test_public_results_includes_only_the_consented_photo(self):
        ProgressPhoto.objects.create(
            client=self.client_user,
            image=make_image("secret.png"),
            date=date(2026, 1, 1),
            consent_public=False,
        )
        shared = ProgressPhoto.objects.create(
            client=self.client_user,
            image=make_image("shared.png"),
            date=date(2026, 2, 1),
            consent_public=True,
        )

        response = self.client.get(reverse("public-results"))

        photos = list(response.context["photos"])
        self.assertEqual(photos, [shared])
        self.assertNotContains(response, "secret")

    def test_consent_defaults_to_off(self):
        photo = ProgressPhoto.objects.create(
            client=self.client_user, image=make_image()
        )
        self.assertFalse(photo.consent_public)
        self.assertIsNone(photo.consent_given_at)

    def test_consent_timestamp_is_recorded_and_cleared(self):
        photo = ProgressPhoto.objects.create(
            client=self.client_user, image=make_image(), consent_public=True
        )
        self.assertIsNotNone(photo.consent_given_at)

        photo.consent_public = False
        photo.save()
        self.assertIsNone(photo.consent_given_at)

    def test_client_can_only_change_consent_on_their_own_photo(self):
        photo = ProgressPhoto.objects.create(
            client=self.client_user, image=make_image()
        )
        intruder = User.objects.create_user(
            username="intruder", password="password123", role=User.Role.CLIENT
        )
        self.client.force_login(intruder)

        response = self.client.post(
            reverse("photo-consent", args=[photo.pk]), {"consent_public": "on"}
        )

        self.assertEqual(response.status_code, 404)
        photo.refresh_from_db()
        self.assertFalse(photo.consent_public)

    def test_client_can_withdraw_consent(self):
        photo = ProgressPhoto.objects.create(
            client=self.client_user, image=make_image(), consent_public=True
        )
        self.client.login(username="client1", password="password123")

        self.client.post(reverse("photo-consent", args=[photo.pk]), {})

        photo.refresh_from_db()
        self.assertFalse(photo.consent_public)


class BodyMeasurementTests(ProgressFixtureMixin, TestCase):
    def test_create_and_str(self):
        entry = BodyMeasurement.objects.create(
            client=self.client_user, date=date(2026, 3, 1), weight_kg=Decimal("82.50")
        )
        self.assertIn("client1", str(entry))

    def test_client_can_add_measurements(self):
        self.client.login(username="client1", password="password123")
        response = self.client.post(
            reverse("measurement-add"),
            {"date": "2026-03-01", "weight_kg": "82.5", "waist_cm": "88"},
        )
        self.assertRedirects(response, reverse("my-progress"))
        self.assertEqual(self.client_user.measurements.count(), 1)

    def test_measurements_are_scoped_to_their_owner(self):
        other = User.objects.create_user(
            username="other", password="password123", role=User.Role.CLIENT
        )
        BodyMeasurement.objects.create(
            client=other, date=date(2026, 3, 1), weight_kg=Decimal("99")
        )
        BodyMeasurement.objects.create(
            client=self.client_user, date=date(2026, 3, 1), weight_kg=Decimal("82")
        )

        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("my-progress"))

        self.assertEqual(len(response.context["measurements"]), 1)


class CheckInTests(ProgressFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.checkin = CheckIn.objects.create(
            client=self.client_user, due_date=timezone.localdate()
        )

    def test_submission_stamps_and_queues_for_review(self):
        self.client.login(username="client1", password="password123")

        response = self.client.post(
            reverse("checkin-submit", args=[self.checkin.pk]),
            {
                "weight_kg": "81.2",
                "energy_rating": "4",
                "sleep_rating": "3",
                "adherence_rating": "5",
                "note": "Good week",
            },
        )

        self.assertRedirects(response, reverse("my-checkins"))
        self.checkin.refresh_from_db()
        self.assertIsNotNone(self.checkin.submitted_at)
        self.assertTrue(self.checkin.is_submitted)
        self.assertFalse(self.checkin.reviewed)

    def test_coach_reply_marks_reviewed(self):
        self.checkin.submitted_at = timezone.now()
        self.checkin.save()
        self.client.login(username="coach", password="password123")

        response = self.client.post(
            reverse("checkin-reply", args=[self.checkin.pk]),
            {"trainer_reply": "Add 2.5kg to your squat."},
        )

        self.assertRedirects(response, reverse("checkin-queue"))
        self.checkin.refresh_from_db()
        self.assertTrue(self.checkin.reviewed)
        self.assertIsNotNone(self.checkin.replied_at)

    def test_editing_a_reviewed_checkin_reopens_it(self):
        """A client's edit should land back in the coach's queue, not vanish."""
        self.checkin.submitted_at = timezone.now()
        self.checkin.reviewed = True
        self.checkin.save()

        self.client.login(username="client1", password="password123")
        self.client.post(
            reverse("checkin-submit", args=[self.checkin.pk]),
            {"weight_kg": "80.0", "note": "Corrected"},
        )

        self.checkin.refresh_from_db()
        self.assertFalse(self.checkin.reviewed)

    def test_queue_shows_only_submitted_unreviewed(self):
        submitted = CheckIn.objects.create(
            client=self.client_user,
            due_date=timezone.localdate() - timedelta(days=7),
            submitted_at=timezone.now(),
        )
        CheckIn.objects.create(
            client=self.client_user,
            due_date=timezone.localdate() - timedelta(days=14),
            submitted_at=timezone.now(),
            reviewed=True,
        )

        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("checkin-queue"))

        self.assertEqual(list(response.context["checkins"]), [submitted])

    def test_client_cannot_submit_another_clients_checkin(self):
        intruder = User.objects.create_user(
            username="intruder", password="password123", role=User.Role.CLIENT
        )
        self.client.force_login(intruder)
        response = self.client.post(
            reverse("checkin-submit", args=[self.checkin.pk]), {"note": "hi"}
        )
        self.assertEqual(response.status_code, 404)

    def test_client_cannot_reach_the_coach_queue(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("checkin-queue"))
        self.assertIn(response.status_code, (302, 403))

    def test_overdue_detection(self):
        overdue = CheckIn.objects.create(
            client=self.client_user, due_date=timezone.localdate() - timedelta(days=1)
        )
        self.assertTrue(overdue.is_overdue)

        overdue.submitted_at = timezone.now()
        overdue.save()
        self.assertFalse(overdue.is_overdue)


class ChartTests(TestCase):
    def test_returns_none_for_a_single_point(self):
        """One dot is not a trend; the template should say so instead."""
        self.assertIsNone(build_line_chart([(date(2026, 1, 1), 80)]))

    def test_returns_none_for_no_points(self):
        self.assertIsNone(build_line_chart([]))

    def test_builds_polyline_for_two_points(self):
        chart = build_line_chart(
            [(date(2026, 1, 1), 80), (date(2026, 2, 1), 84)], label="Weight"
        )

        self.assertIsNotNone(chart)
        self.assertEqual(len(chart["points"]), 2)
        self.assertEqual(chart["min_value"], 80)
        self.assertEqual(chart["max_value"], 84)
        self.assertEqual(chart["change"], 4)
        self.assertIn(",", chart["polyline"])

    def test_higher_value_sits_higher_on_screen(self):
        """SVG y grows downward, so the larger value needs the smaller y."""
        chart = build_line_chart([(date(2026, 1, 1), 80), (date(2026, 2, 1), 90)])
        first, last = chart["points"]
        self.assertLess(last["y"], first["y"])

    def test_flat_series_does_not_divide_by_zero(self):
        chart = build_line_chart([(date(2026, 1, 1), 80), (date(2026, 2, 1), 80)])
        self.assertIsNotNone(chart)
        self.assertEqual(chart["change"], 0)

    def test_ignores_none_values(self):
        chart = build_line_chart(
            [(date(2026, 1, 1), 80), (date(2026, 2, 1), None), (date(2026, 3, 1), 82)]
        )
        self.assertEqual(len(chart["points"]), 2)

    def test_measurement_chart_sorts_by_date(self):
        user = User.objects.create_user(
            username="c", password="p", role=User.Role.CLIENT
        )
        BodyMeasurement.objects.create(
            client=user, date=date(2026, 3, 1), weight_kg=Decimal("80")
        )
        BodyMeasurement.objects.create(
            client=user, date=date(2026, 1, 1), weight_kg=Decimal("85")
        )

        chart = measurement_chart(list(user.measurements.all()), "weight_kg")

        self.assertEqual(chart["points"][0]["value"], 85.0)
        self.assertEqual(chart["points"][-1]["value"], 80.0)


class ProgressAdminTests(TestCase):
    def test_models_registered(self):
        from django.contrib import admin

        self.assertIn(ProgressPhoto, admin.site._registry)
        self.assertIn(CheckIn, admin.site._registry)
        self.assertIn(BodyMeasurement, admin.site._registry)
