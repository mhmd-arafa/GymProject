from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import admin
from .models import WorkoutPlan, WorkoutDay, Exercise
from .forms import WorkoutPlanForm, WorkoutDayFormSet, ExerciseFormSet
from subscriptions.models import Subscription

User = get_user_model()


class WorkoutModelTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )

    def test_workout_plan_day_exercise_str(self):
        plan = WorkoutPlan.objects.create(client=self.client_user, title="Push Pull Legs")
        self.assertEqual(str(plan), "Push Pull Legs - client1")

        day = WorkoutDay.objects.create(plan=plan, day_name="Push Day")
        self.assertEqual(str(day), "Push Day (Push Pull Legs)")

        exercise = Exercise.objects.create(day=day, name="Bench Press", sets=4, reps=8)
        self.assertEqual(str(exercise), "Bench Press (4x8)")


class WorkoutViewTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        Subscription.objects.create(
            client=self.client_user,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
        )
        self.plan = WorkoutPlan.objects.create(client=self.client_user, title="Strength Plan")
        self.day = WorkoutDay.objects.create(plan=self.plan, day_name="Legs")

    def test_my_workout_plans_view_authenticated_active(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("my-workout-plan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Strength Plan")
        self.assertContains(response, "Legs")

    def test_workout_plan_create_view_admin(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("workout-plan-add"))
        self.assertEqual(response.status_code, 200)

    def test_add_exercises_view_admin(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("add-exercises", kwargs={"pk": self.day.pk}))
        self.assertEqual(response.status_code, 200)
