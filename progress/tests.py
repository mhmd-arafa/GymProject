import tempfile
from decimal import Decimal
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import admin
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io

from .models import ProgressLog
from .forms import ProgressLogForm
from subscriptions.models import Subscription

User = get_user_model()


def get_test_image():
    file = io.BytesIO()
    image = Image.new("RGBA", size=(50, 50), color=(256, 0, 0))
    image.save(file, "png")
    file.name = "test.png"
    file.seek(0)
    return SimpleUploadedFile(file.name, file.read(), content_type="image/png")


class ProgressModelTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )

    def test_progress_log_creation_and_str(self):
        log = ProgressLog.objects.create(
            client=self.client_user,
            weight=Decimal("78.50"),
            notes="Feeling great and high energy",
        )
        self.assertIn("client1", str(log))
        self.assertIn("78.5", str(log))


@override_settings(MEDIA_ROOT=tempfile.gettempdir())
class ProgressViewTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client1 = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.client2 = User.objects.create_user(
            username="client2", password="password123", role=User.Role.CLIENT
        )
        # Give client1 an active subscription
        Subscription.objects.create(
            client=self.client1,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
        )

        self.log1 = ProgressLog.objects.create(
            client=self.client1,
            date=timezone.localdate() - timezone.timedelta(days=7),
            weight=Decimal("80.00"),
            notes="Week 1 start",
        )
        self.log2 = ProgressLog.objects.create(
            client=self.client1,
            date=timezone.localdate(),
            weight=Decimal("78.50"),
            notes="Week 2 check-in",
        )

        # Log for client2 (inactive subscription)
        self.log_client2 = ProgressLog.objects.create(
            client=self.client2,
            weight=Decimal("90.00"),
        )

    def test_my_progress_view_active_client(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("my-progress"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "80.00")
        self.assertContains(response, "78.50")
        self.assertContains(response, "Week 1 start")
        self.assertNotContains(response, "90.00")  # client2 log isolated
        # Check context stats
        self.assertEqual(response.context["start_weight"], Decimal("80.00"))
        self.assertEqual(response.context["latest_weight"], Decimal("78.50"))
        self.assertEqual(response.context["weight_diff"], Decimal("-1.50"))

    def test_my_progress_view_inactive_client_redirected(self):
        self.client.login(username="client2", password="password123")
        response = self.client.get(reverse("my-progress"))
        self.assertRedirects(response, reverse("no-active-subscription"))

    def test_progress_create_view_with_photo(self):
        self.client.login(username="client1", password="password123")
        image = get_test_image()
        data = {
            "date": timezone.localdate().strftime("%Y-%m-%d"),
            "weight": "77.80",
            "photo": image,
            "notes": "Week 3 - visible abs",
        }
        response = self.client.post(reverse("progress-add"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProgressLog.objects.filter(client=self.client1, weight=Decimal("77.80")).exists())
        new_log = ProgressLog.objects.get(client=self.client1, weight=Decimal("77.80"))
        self.assertTrue(bool(new_log.photo))

    def test_client_progress_admin_view(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("client-progress-admin", kwargs={"client_id": self.client1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "client1")
        self.assertContains(response, "78.50")

    def test_client_cannot_access_client_progress_admin(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("client-progress-admin", kwargs={"client_id": self.client2.pk}))
        self.assertIn(response.status_code, [302, 403])


class ProgressAdminTests(TestCase):
    def test_progress_log_registered_in_admin(self):
        self.assertIn(ProgressLog, admin.site._registry)
