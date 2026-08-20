"""Checks on the base template and vendored assets.

These are cheap guards against regressions that are easy to introduce and
annoying to notice: a CDN sneaking back in, or the htmx file going missing so
the set logger silently loses its no-reload behaviour.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

HTMX_FILENAME = "htmx-2.0.4.min.js"


class VendoredAssetTests(TestCase):
    def test_htmx_is_vendored_on_disk(self):
        """The in-gym logger must not depend on a third-party host."""
        candidates = [Path(d) / "vendor" / HTMX_FILENAME for d in settings.STATICFILES_DIRS]
        found = [path for path in candidates if path.exists()]
        self.assertTrue(found, f"{HTMX_FILENAME} not found in {settings.STATICFILES_DIRS}")
        # Guard against an empty or truncated file being committed.
        self.assertGreater(found[0].stat().st_size, 40_000)

    def test_vendored_htmx_is_really_htmx(self):
        path = next(
            Path(d) / "vendor" / HTMX_FILENAME
            for d in settings.STATICFILES_DIRS
            if (Path(d) / "vendor" / HTMX_FILENAME).exists()
        )
        content = path.read_text(encoding="utf-8", errors="replace")
        self.assertIn("var htmx=", content)
        self.assertIn('version:"2.0.4"', content)


class BaseTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )

    def test_pages_load_htmx_from_our_own_host(self):
        self.client.login(username="client1", password="password123")
        body = self.client.get(reverse("client-home")).content.decode()

        self.assertIn(HTMX_FILENAME, body)
        self.assertIn(settings.STATIC_URL, body)

    def test_no_external_script_or_style_hosts(self):
        """A CDN reference would reintroduce the gym-wifi failure mode."""
        self.client.login(username="client1", password="password123")

        pages = [
            "client-home",
            "my-workout-plan",
            "my-nutrition-plan",
            "my-progress",
            "my-checkins",
            "my-subscription",
        ]
        for name in pages:
            with self.subTest(page=name):
                body = self.client.get(reverse(name)).content.decode()
                for host in ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com",
                             "ajax.googleapis.com", "fonts.googleapis.com"):
                    self.assertNotIn(host, body)
