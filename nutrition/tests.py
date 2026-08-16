# pyrefly: ignore [missing-import]
from django.test import TestCase
# pyrefly: ignore [missing-import]
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import admin
from .models import NutritionPlan, Meal
from .forms import NutritionPlanForm, MealFormSet

User = get_user_model()


class NutritionModelTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.admin_user = User.objects.create_user(
            username="admin1", password="password123", role=User.Role.ADMIN
        )

    def test_nutrition_plan_creation_and_str(self):
        plan = NutritionPlan.objects.create(
            client=self.client_user,
            title="Bulking Diet",
        )
        self.assertEqual(str(plan), "Bulking Diet - client1")

    def test_meal_creation_and_str(self):
        plan = NutritionPlan.objects.create(
            client=self.client_user,
            title="Cutting Diet",
        )
        meal = Meal.objects.create(
            plan=plan,
            name="Breakfast",
            calories=500,
            protein=40,
            carbs=50,
            fats=15,
            notes="Oats with eggs",
        )
        self.assertEqual(str(meal), "Breakfast (500 kcal)")
        self.assertEqual(plan.meals.count(), 1)
        self.assertEqual(self.client_user.nutrition_plans.count(), 1)


class NutritionFormTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.admin_user = User.objects.create_user(
            username="admin1", password="password123", role=User.Role.ADMIN
        )

    def test_nutrition_plan_form_client_filter(self):
        form = NutritionPlanForm()
        clients_in_form = list(form.fields["client"].queryset)
        self.assertIn(self.client_user, clients_in_form)
        self.assertNotIn(self.admin_user, clients_in_form)


class NutritionViewTests(TestCase):
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
        self.plan1 = NutritionPlan.objects.create(client=self.client1, title="Client1 Plan")
        self.meal1 = Meal.objects.create(
            plan=self.plan1,
            name="Lunch",
            calories=700,
            protein=50,
            carbs=70,
            fats=20,
            notes="Chicken & Rice",
        )
        self.plan2 = NutritionPlan.objects.create(client=self.client2, title="Client2 Plan")

    def test_my_nutrition_plan_view_requires_login(self):
        response = self.client.get(reverse("my-nutrition-plan"))
        self.assertEqual(response.status_code, 302)

    def test_my_nutrition_plan_view_client_isolation(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("my-nutrition-plan"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Client1 Plan")
        self.assertContains(response, "Lunch")
        self.assertContains(response, "700 kcal")
        self.assertNotContains(response, "Client2 Plan")

    def test_nutrition_plan_create_view_admin_access(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("nutrition-plan-add"))
        self.assertEqual(response.status_code, 200)

        data = {
            "client": self.client1.pk,
            "title": "New High Protein Plan",
            "meals-TOTAL_FORMS": "1",
            "meals-INITIAL_FORMS": "0",
            "meals-MIN_NUM_FORMS": "0",
            "meals-MAX_NUM_FORMS": "1000",
            "meals-0-name": "Dinner",
            "meals-0-calories": "600",
            "meals-0-protein": "45",
            "meals-0-carbs": "40",
            "meals-0-fats": "15",
            "meals-0-notes": "Salmon and veggies",
        }
        post_response = self.client.post(reverse("nutrition-plan-add"), data)
        self.assertEqual(post_response.status_code, 302)
        self.assertTrue(NutritionPlan.objects.filter(title="New High Protein Plan").exists())
        created_plan = NutritionPlan.objects.get(title="New High Protein Plan")
        self.assertEqual(created_plan.meals.count(), 1)
        self.assertEqual(created_plan.meals.first().name, "Dinner")

    def test_nutrition_plan_create_view_client_forbidden(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("nutrition-plan-add"))
        # AdminRequiredMixin returns 403 Forbidden or redirect if not admin
        self.assertIn(response.status_code, [302, 403])


class NutritionAdminTests(TestCase):
    def test_nutrition_plan_registered_in_admin(self):
        self.assertIn(NutritionPlan, admin.site._registry)
