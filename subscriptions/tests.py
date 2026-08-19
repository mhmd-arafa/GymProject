from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import admin
from django.utils import timezone
from .models import Subscription
from .forms import AdminSubscriptionForm, ClientSubscriptionRequestForm
from workouts.models import WorkoutPlan
from nutrition.models import NutritionPlan

User = get_user_model()


class SubscriptionModelTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.today = timezone.localdate()

    def test_subscription_creation_and_str(self):
        sub = Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
        )
        self.assertIn("client1", str(sub))
        self.assertIn("نشط", str(sub))

    def test_is_currently_active_logic(self):
        # 1. PENDING status -> not active
        sub_pending = Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.PENDING,
        )
        self.assertFalse(sub_pending.is_currently_active())

        # 2. ACTIVE status with valid date range -> active
        sub_active = Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
            start_date=self.today - timedelta(days=5),
            end_date=self.today + timedelta(days=25),
        )
        self.assertTrue(sub_active.is_currently_active())

        # 3. ACTIVE status with future start date -> not active yet
        sub_future = Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
            start_date=self.today + timedelta(days=2),
            end_date=self.today + timedelta(days=32),
        )
        self.assertFalse(sub_future.is_currently_active())

        # 4. ACTIVE status with past end date -> expired / not active
        sub_past = Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
            start_date=self.today - timedelta(days=40),
            end_date=self.today - timedelta(days=10),
        )
        self.assertFalse(sub_past.is_currently_active())


class SubscriptionFormTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.admin_user = User.objects.create_user(
            username="admin1", password="password123", role=User.Role.ADMIN
        )

    def test_admin_form_client_filter(self):
        form = AdminSubscriptionForm()
        clients_in_form = list(form.fields["client"].queryset)
        self.assertIn(self.client_user, clients_in_form)
        self.assertNotIn(self.admin_user, clients_in_form)

    def test_client_request_form_valid(self):
        form = ClientSubscriptionRequestForm(
            data={"plan_type": Subscription.PlanType.QUARTERLY, "notes": "Need custom diet"}
        )
        self.assertTrue(form.is_valid())


class SubscriptionViewTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.today = timezone.localdate()

    def test_admin_subscription_list_view(self):
        self.client.login(username="coach", password="password123")
        Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.PENDING,
        )
        response = self.client.get(reverse("subscription-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "client1")
        self.assertContains(response, "قيد الانتظار")

    def test_admin_subscription_create_and_update(self):
        self.client.login(username="coach", password="password123")
        create_data = {
            "client": self.client_user.pk,
            "plan_type": Subscription.PlanType.MONTHLY,
            "status": Subscription.Status.ACTIVE,
            "start_date": self.today.strftime("%Y-%m-%d"),
            "end_date": (self.today + timedelta(days=30)).strftime("%Y-%m-%d"),
            "notes": "First month paid in cash",
        }
        create_response = self.client.post(reverse("subscription-add"), create_data)
        self.assertEqual(create_response.status_code, 302)
        self.assertTrue(Subscription.objects.filter(client=self.client_user, status=Subscription.Status.ACTIVE).exists())

        sub = Subscription.objects.get(client=self.client_user)
        update_data = {
            "client": self.client_user.pk,
            "plan_type": Subscription.PlanType.QUARTERLY,
            "status": Subscription.Status.ACTIVE,
            "start_date": self.today.strftime("%Y-%m-%d"),
            "end_date": (self.today + timedelta(days=90)).strftime("%Y-%m-%d"),
            "notes": "Upgraded to 3 months",
        }
        update_response = self.client.post(reverse("subscription-edit", kwargs={"pk": sub.pk}), update_data)
        self.assertEqual(update_response.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.plan_type, Subscription.PlanType.QUARTERLY)

    def test_client_subscription_request_flow(self):
        self.client.login(username="client1", password="password123")
        response = self.client.post(
            reverse("subscription-request"),
            {"plan_type": Subscription.PlanType.MONTHLY, "notes": "Please activate my plan"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Subscription.objects.filter(client=self.client_user, status=Subscription.Status.PENDING).exists())

    def test_my_subscription_view_displays_history(self):
        self.client.login(username="client1", password="password123")
        Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
            start_date=self.today - timedelta(days=1),
            end_date=self.today + timedelta(days=29),
        )
        response = self.client.get(reverse("my-subscription"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اشتراكك الحالي: نشط")


class ActiveSubscriptionGatingTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.workout_plan = WorkoutPlan.objects.create(client=self.client_user, title="Full Body Plan")
        self.nutrition_plan = NutritionPlan.objects.create(client=self.client_user, title="Diet Plan")
        self.today = timezone.localdate()

    def test_inactive_client_gated_from_workouts_and_nutrition(self):
        self.client.login(username="client1", password="password123")
        
        # Inactive client gets redirected from workout plan to no-active-subscription
        workout_response = self.client.get(reverse("my-workout-plan"))
        self.assertRedirects(workout_response, reverse("no-active-subscription"))

        # Inactive client gets redirected from nutrition plan to no-active-subscription
        nutrition_response = self.client.get(reverse("my-nutrition-plan"))
        self.assertRedirects(nutrition_response, reverse("no-active-subscription"))

        # Inactive notice page is accessible
        notice_response = self.client.get(reverse("no-active-subscription"))
        self.assertEqual(notice_response.status_code, 200)
        self.assertContains(notice_response, "الاشتراك غير نشط")

    def test_active_client_can_access_workouts_and_nutrition(self):
        # Activate subscription for client
        Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
            start_date=self.today - timedelta(days=1),
            end_date=self.today + timedelta(days=29),
        )
        self.client.login(username="client1", password="password123")

        workout_response = self.client.get(reverse("my-workout-plan"))
        self.assertEqual(workout_response.status_code, 200)
        self.assertContains(workout_response, "Full Body Plan")

        nutrition_response = self.client.get(reverse("my-nutrition-plan"))
        self.assertEqual(nutrition_response.status_code, 200)
        self.assertContains(nutrition_response, "Diet Plan")

    def test_admin_always_can_access_admin_and_plans(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("subscription-list"))
        self.assertEqual(response.status_code, 200)


class SubscriptionAdminTests(TestCase):
    def test_subscription_registered_in_admin(self):
        self.assertIn(Subscription, admin.site._registry)
