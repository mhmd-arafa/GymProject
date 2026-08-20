"""Tests for client-uploaded progress photos.

Covers the three things that would actually hurt if broken: photos reaching the
coach, image processing not falling over on real phone uploads, and the consent
gate holding.
"""

from datetime import timedelta
from decimal import Decimal
import tempfile
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from progress.images import MAX_EDGE_PX, ImageRejected, process_upload
from progress.models import BodyMeasurement, CheckIn, ProgressPhoto

User = get_user_model()

#: Uploads land here instead of the real MEDIA_ROOT. tempfile keeps this
#: correct on Windows, where a hardcoded "/tmp" path does not exist.
TEST_MEDIA = tempfile.mkdtemp(prefix="gym-test-media-")


def make_image(width=800, height=1000, fmt="JPEG", colour=(120, 90, 60), exif=None):
    """An in-memory image file, as a browser would submit it."""
    buffer = BytesIO()
    image = Image.new("RGB", (width, height), colour)
    save_kwargs = {"format": fmt}
    if exif is not None:
        save_kwargs["exif"] = exif
    image.save(buffer, **save_kwargs)
    buffer.seek(0)
    extension = "jpg" if fmt == "JPEG" else fmt.lower()
    content_type = f"image/{'jpeg' if fmt == 'JPEG' else fmt.lower()}"
    return SimpleUploadedFile(f"shot.{extension}", buffer.read(), content_type)


class ImageProcessingTests(TestCase):
    def test_downscales_oversized_photo(self):
        """A 4000px phone photo must not be stored at full size."""
        processed = process_upload(make_image(4000, 3000))
        reopened = Image.open(processed)
        self.assertEqual(max(reopened.size), MAX_EDGE_PX)
        # Aspect ratio preserved: 4000x3000 -> 1600x1200.
        self.assertEqual(reopened.size, (1600, 1200))

    def test_leaves_small_photo_dimensions_alone(self):
        processed = process_upload(make_image(600, 800))
        self.assertEqual(Image.open(processed).size, (600, 800))

    def test_converts_png_with_alpha_to_jpeg(self):
        buffer = BytesIO()
        Image.new("RGBA", (400, 400), (10, 200, 10, 128)).save(buffer, format="PNG")
        buffer.seek(0)
        upload = SimpleUploadedFile("shot.png", buffer.read(), "image/png")

        processed = process_upload(upload)
        self.assertTrue(processed.name.endswith(".jpg"))
        self.assertEqual(Image.open(processed).mode, "RGB")

    def test_strips_metadata(self):
        """Phone photos carry GPS coordinates; a physique photo should not."""
        exif = Image.Exif()
        exif[0x010F] = "TestPhone"
        processed = process_upload(make_image(500, 500, exif=exif.tobytes()))
        self.assertEqual(dict(Image.open(processed).getexif()), {})

    def test_rejects_a_file_that_is_not_an_image(self):
        bogus = SimpleUploadedFile("notes.txt", b"just some text", "text/plain")
        with self.assertRaises(ImageRejected):
            process_upload(bogus)

    def test_rejects_an_oversized_file(self):
        upload = make_image(100, 100)
        upload.size = 40 * 1024 * 1024
        with self.assertRaises(ImageRejected):
            process_upload(upload)

    def test_none_passes_through(self):
        self.assertIsNone(process_upload(None))


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class CheckInPhotoUploadTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach1", password="pw12345678", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="lifter1", password="pw12345678", role=User.Role.CLIENT
        )
        self.other = User.objects.create_user(
            username="lifter2", password="pw12345678", role=User.Role.CLIENT
        )
        self.checkin = CheckIn.objects.create(
            client=self.client_user, due_date=timezone.localdate()
        )
        self.client.login(username="lifter1", password="pw12345678")

    def submit(self, **extra):
        payload = {
            "weight_kg": "81.5",
            "energy_rating": "4",
            "sleep_rating": "3",
            "adherence_rating": "5",
            "note": "Solid week.",
        }
        payload.update(extra)
        return self.client.post(
            reverse("checkin-submit", args=[self.checkin.pk]), payload
        )

    def test_submits_with_no_photos(self):
        """A client with nothing to show must still be able to check in."""
        response = self.submit()
        self.assertEqual(response.status_code, 302)
        self.checkin.refresh_from_db()
        self.assertTrue(self.checkin.is_submitted)
        self.assertEqual(self.checkin.photos.count(), 0)

    def test_uploads_three_poses_with_correct_labels(self):
        self.submit(
            photo_front=make_image(),
            photo_side=make_image(),
            photo_back=make_image(),
        )
        photos = self.checkin.photos.all()
        self.assertEqual(photos.count(), 3)
        self.assertEqual(
            sorted(p.pose for p in photos),
            sorted(
                [
                    ProgressPhoto.Pose.FRONT,
                    ProgressPhoto.Pose.SIDE,
                    ProgressPhoto.Pose.BACK,
                ]
            ),
        )

    def test_photo_joins_the_client_timeline(self):
        """Check-in photos must also appear in the client's own progress album,
        or the before/after comparison would silently miss them."""
        self.submit(photo_front=make_image())
        photo = ProgressPhoto.objects.get(client=self.client_user)
        self.assertEqual(photo.checkin, self.checkin)
        self.assertEqual(photo.date, self.checkin.due_date)

    def test_reuploading_a_pose_replaces_rather_than_duplicates(self):
        self.submit(photo_front=make_image())
        self.submit(photo_front=make_image(colour=(9, 9, 9)))
        self.assertEqual(
            self.checkin.photos.filter(pose=ProgressPhoto.Pose.FRONT).count(), 1
        )

    def test_photos_are_private_unless_consent_given(self):
        self.submit(photo_front=make_image())
        photo = ProgressPhoto.objects.get(client=self.client_user)
        self.assertFalse(photo.consent_public)
        self.assertIsNone(photo.consent_given_at)

    def test_consent_checkbox_applies_to_uploaded_photos(self):
        self.submit(photo_front=make_image(), consent_public="on")
        photo = ProgressPhoto.objects.get(client=self.client_user)
        self.assertTrue(photo.consent_public)
        self.assertIsNotNone(photo.consent_given_at)

    def test_a_non_image_upload_shows_an_error_and_saves_nothing(self):
        response = self.submit(
            photo_front=SimpleUploadedFile("x.txt", b"nope", "text/plain")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProgressPhoto.objects.count(), 0)
        self.checkin.refresh_from_db()
        # The whole submission is rejected rather than half-saved.
        self.assertFalse(self.checkin.is_submitted)

    def test_cannot_submit_another_clients_checkin(self):
        theirs = CheckIn.objects.create(
            client=self.other, due_date=timezone.localdate()
        )
        response = self.client.post(
            reverse("checkin-submit", args=[theirs.pk]), {"weight_kg": "70"}
        )
        self.assertEqual(response.status_code, 404)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class CoachPhotoReviewTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach2", password="pw12345678", role=User.Role.ADMIN
        )
        self.lifter = User.objects.create_user(
            username="lifter3", password="pw12345678", role=User.Role.CLIENT
        )
        today = timezone.localdate()

        self.old = CheckIn.objects.create(
            client=self.lifter,
            due_date=today - timedelta(days=7),
            weight_kg=Decimal("84.0"),
            submitted_at=timezone.now() - timedelta(days=7),
        )
        self.new = CheckIn.objects.create(
            client=self.lifter,
            due_date=today,
            weight_kg=Decimal("82.5"),
            submitted_at=timezone.now(),
        )
        for checkin in (self.old, self.new):
            ProgressPhoto.objects.create(
                client=self.lifter,
                checkin=checkin,
                pose=ProgressPhoto.Pose.FRONT,
                date=checkin.due_date,
                image=make_image(),
            )

        self.client.login(username="coach2", password="pw12345678")

    def test_reply_page_pairs_this_week_against_last(self):
        response = self.client.get(reverse("checkin-reply", args=[self.new.pk]))
        self.assertEqual(response.status_code, 200)

        pairs = response.context["photo_pairs"]
        front = next(p for p in pairs if p["then"] or p["now"])
        self.assertEqual(front["then"].checkin, self.old)
        self.assertEqual(front["now"].checkin, self.new)

    def test_reply_page_shows_weight_change(self):
        response = self.client.get(reverse("checkin-reply", args=[self.new.pk]))
        self.assertEqual(response.context["weight_delta"], Decimal("-1.5"))

    def test_pose_with_only_one_side_still_appears(self):
        """A missing counterpart must render as "no photo", not vanish."""
        ProgressPhoto.objects.create(
            client=self.lifter,
            checkin=self.new,
            pose=ProgressPhoto.Pose.BACK,
            date=self.new.due_date,
            image=make_image(),
        )
        response = self.client.get(reverse("checkin-reply", args=[self.new.pk]))
        back = next(
            p for p in response.context["photo_pairs"] if p["now"]
            and p["now"].pose == ProgressPhoto.Pose.BACK
        )
        self.assertIsNone(back["then"])

    def test_client_cannot_open_the_coach_review_page(self):
        self.client.logout()
        self.client.login(username="lifter3", password="pw12345678")
        response = self.client.get(reverse("checkin-reply", args=[self.new.pk]))
        self.assertIn(response.status_code, (302, 403))


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class PhotoConsentAndDeletionTests(TestCase):
    def setUp(self):
        self.lifter = User.objects.create_user(
            username="lifter4", password="pw12345678", role=User.Role.CLIENT
        )
        self.other = User.objects.create_user(
            username="lifter5", password="pw12345678", role=User.Role.CLIENT
        )
        self.photo = ProgressPhoto.objects.create(
            client=self.lifter, image=make_image(), pose=ProgressPhoto.Pose.FRONT
        )
        self.client.login(username="lifter4", password="pw12345678")

    def test_public_page_excludes_photos_without_consent(self):
        response = self.client.get(reverse("public-results"))
        self.assertEqual(list(response.context["photos"]), [])

    def test_public_page_includes_a_consented_photo(self):
        self.photo.consent_public = True
        self.photo.save()
        response = self.client.get(reverse("public-results"))
        self.assertEqual(list(response.context["photos"]), [self.photo])

    def test_withdrawing_consent_clears_the_timestamp_and_hides_it(self):
        self.photo.consent_public = True
        self.photo.save()
        self.assertIsNotNone(self.photo.consent_given_at)

        self.client.post(reverse("photo-consent", args=[self.photo.pk]), {})
        self.photo.refresh_from_db()
        self.assertFalse(self.photo.consent_public)
        self.assertIsNone(self.photo.consent_given_at)

        response = self.client.get(reverse("public-results"))
        self.assertEqual(list(response.context["photos"]), [])

    def test_client_can_delete_their_own_photo_and_the_file_goes(self):
        path = self.photo.image.path
        import os

        self.assertTrue(os.path.exists(path))

        response = self.client.post(reverse("photo-delete", args=[self.photo.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProgressPhoto.objects.filter(pk=self.photo.pk).exists())
        self.assertFalse(os.path.exists(path))

    def test_cannot_delete_another_clients_photo(self):
        theirs = ProgressPhoto.objects.create(
            client=self.other, image=make_image(), pose=ProgressPhoto.Pose.FRONT
        )
        response = self.client.post(reverse("photo-delete", args=[theirs.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProgressPhoto.objects.filter(pk=theirs.pk).exists())

    def test_cannot_change_consent_on_another_clients_photo(self):
        theirs = ProgressPhoto.objects.create(
            client=self.other, image=make_image(), pose=ProgressPhoto.Pose.FRONT
        )
        response = self.client.post(
            reverse("photo-consent", args=[theirs.pk]), {"consent_public": "on"}
        )
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertFalse(theirs.consent_public)


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class ProgressTimelineTests(TestCase):
    def setUp(self):
        self.lifter = User.objects.create_user(
            username="lifter6", password="pw12345678", role=User.Role.CLIENT
        )
        today = timezone.localdate()
        for weeks, pose in (
            (8, ProgressPhoto.Pose.FRONT),
            (0, ProgressPhoto.Pose.FRONT),
            (4, ProgressPhoto.Pose.SIDE),
        ):
            ProgressPhoto.objects.create(
                client=self.lifter,
                image=make_image(),
                pose=pose,
                date=today - timedelta(weeks=weeks),
            )
        for weeks, kg in ((8, "86.0"), (0, "82.0")):
            BodyMeasurement.objects.create(
                client=self.lifter,
                date=today - timedelta(weeks=weeks),
                weight_kg=Decimal(kg),
            )
        self.client.login(username="lifter6", password="pw12345678")

    def test_groups_photos_by_pose_and_pairs_only_where_possible(self):
        response = self.client.get(reverse("my-progress"))
        poses = {p["pose_value"]: p for p in response.context["poses"]}

        front = poses[ProgressPhoto.Pose.FRONT]
        self.assertIsNotNone(front["first"])
        self.assertEqual(front["span_days"], 56)

        # One photo is not a comparison.
        side = poses[ProgressPhoto.Pose.SIDE]
        self.assertIsNone(side["first"])

    def test_reports_net_weight_change(self):
        response = self.client.get(reverse("my-progress"))
        self.assertEqual(response.context["weight_change"], Decimal("-4.0"))
