from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib import admin
from .models import NutritionPlan, Meal
from .forms import NutritionPlanForm, MealFormSet
from subscriptions.models import Subscription

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
        # Give client1 active subscription so they can access plans
        Subscription.objects.create(
            client=self.client1,
            plan_type=Subscription.PlanType.MONTHLY,
            status=Subscription.Status.ACTIVE,
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
        self.assertIn(response.status_code, [302, 403])


class NutritionAdminTests(TestCase):
    def test_nutrition_plan_registered_in_admin(self):
        self.assertIn(NutritionPlan, admin.site._registry)


# ---------------------------------------------------------------------------
# Food database, meal alternatives and macro targets
# ---------------------------------------------------------------------------

from decimal import Decimal  # noqa: E402

from .models import FoodItem, MacroTarget, MealFoodItem  # noqa: E402


class FoodItemTests(TestCase):
    def setUp(self):
        self.chicken = FoodItem.objects.create(
            name="Test Chicken Breast",
            category=FoodItem.Category.PROTEIN,
            calories_per_100g=Decimal("165"),
            protein_per_100g=Decimal("31"),
            carbs_per_100g=Decimal("0"),
            fats_per_100g=Decimal("3.6"),
        )

    def test_macros_scale_with_grams(self):
        """The whole point: type grams, get macros."""
        macros = self.chicken.macros_for(150)
        self.assertEqual(macros["calories"], 248)  # 165 * 1.5 = 247.5 -> 248
        self.assertEqual(macros["protein"], 47)  # 31 * 1.5 = 46.5 -> 47 (half up)
        self.assertEqual(macros["carbs"], 0)
        self.assertEqual(macros["fats"], 5)  # 3.6 * 1.5 = 5.4 -> 5

    def test_exactly_100g_matches_the_per_100g_values(self):
        macros = self.chicken.macros_for(100)
        self.assertEqual(macros["calories"], 165)
        self.assertEqual(macros["protein"], 31)

    def test_egyptian_staples_are_seeded(self):
        """Seed migration must ship the local foods, not just generic ones."""
        for name in ("Foul Medames", "Koshari", "Baladi Bread", "Taameya (Egyptian Falafel)"):
            with self.subTest(food=name):
                self.assertTrue(FoodItem.objects.filter(name=name).exists())
        self.assertGreaterEqual(
            FoodItem.objects.filter(is_egyptian_staple=True).count(), 15
        )


class MealRecalculationTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.plan = NutritionPlan.objects.create(
            client=self.client_user, title="Test Plan"
        )
        self.meal = Meal.objects.create(
            plan=self.plan, name="Lunch", calories=0, protein=0, carbs=0, fats=0
        )
        self.rice = FoodItem.objects.create(
            name="Test White Rice",
            category=FoodItem.Category.CARB,
            calories_per_100g=Decimal("130"),
            protein_per_100g=Decimal("2.7"),
            carbs_per_100g=Decimal("28"),
            fats_per_100g=Decimal("0.3"),
        )
        self.chicken = FoodItem.objects.create(
            name="Test Chicken",
            category=FoodItem.Category.PROTEIN,
            calories_per_100g=Decimal("165"),
            protein_per_100g=Decimal("31"),
            carbs_per_100g=Decimal("0"),
            fats_per_100g=Decimal("3.6"),
        )

    def test_totals_match_hand_computed_macros(self):
        MealFoodItem.objects.create(meal=self.meal, food=self.chicken, grams=150)
        MealFoodItem.objects.create(meal=self.meal, food=self.rice, grams=200)

        changed = self.meal.recalculate_totals()

        self.meal.refresh_from_db()
        self.assertTrue(changed)
        # chicken 150g: 248 kcal / 47 P ; rice 200g: 260 kcal / 5 P / 56 C
        self.assertEqual(self.meal.calories, 248 + 260)
        self.assertEqual(self.meal.protein, 47 + 5)
        self.assertEqual(self.meal.carbs, 0 + 56)

    def test_hand_entered_meal_is_left_alone(self):
        """A meal with no food items keeps whatever the trainer typed."""
        manual = Meal.objects.create(
            plan=self.plan, name="Manual", calories=700, protein=50, carbs=70, fats=20
        )
        changed = manual.recalculate_totals()

        manual.refresh_from_db()
        self.assertFalse(changed)
        self.assertEqual(manual.calories, 700)

    def test_view_recalculates_on_save(self):
        coach = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client.force_login(coach)

        response = self.client.post(
            reverse("meal-food-items", args=[self.meal.pk]),
            {
                "food_items-TOTAL_FORMS": "1",
                "food_items-INITIAL_FORMS": "0",
                "food_items-MIN_NUM_FORMS": "0",
                "food_items-MAX_NUM_FORMS": "1000",
                "food_items-0-food": self.chicken.pk,
                "food_items-0-grams": "150",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.meal.refresh_from_db()
        self.assertEqual(self.meal.calories, 248)


class MealAlternativeTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.plan = NutritionPlan.objects.create(
            client=self.client_user, title="Options Plan"
        )
        self.breakfast = Meal.objects.create(
            plan=self.plan, name="Breakfast", calories=500, protein=40, carbs=50, fats=15
        )

    def test_alternative_links_to_its_primary_meal(self):
        option_b = Meal.objects.create(
            plan=self.plan,
            alternative_of=self.breakfast,
            name="Breakfast option B",
            calories=490,
            protein=38,
            carbs=52,
            fats=14,
        )
        self.assertIn(option_b, self.breakfast.alternatives.all())

    def test_alternatives_are_excluded_from_daily_totals(self):
        """Option A and B are one slot, so counting both would double the day."""
        Meal.objects.create(
            plan=self.plan,
            alternative_of=self.breakfast,
            name="Breakfast option B",
            calories=490,
            protein=38,
            carbs=52,
            fats=14,
        )
        totals = self.plan.daily_totals()
        self.assertEqual(totals["calories"], 500)

    def test_deleting_the_primary_removes_its_alternatives(self):
        Meal.objects.create(
            plan=self.plan,
            alternative_of=self.breakfast,
            name="Option B",
            calories=1,
            protein=1,
            carbs=1,
            fats=1,
        )
        self.breakfast.delete()
        self.assertEqual(Meal.objects.filter(plan=self.plan).count(), 0)


class MacroTargetTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.plan = NutritionPlan.objects.create(
            client=self.client_user, title="Target Plan"
        )
        Meal.objects.create(
            plan=self.plan, name="All day", calories=2000, protein=150, carbs=200, fats=60
        )

    def test_no_target_returns_none(self):
        self.assertIsNone(self.plan.target_comparison())

    def test_on_target_plan_raises_no_warning(self):
        MacroTarget.objects.create(
            plan=self.plan,
            target_calories=2000,
            target_protein=150,
            target_carbs=200,
            target_fats=60,
        )
        comparison = self.plan.target_comparison()
        self.assertFalse(comparison["any_off_target"])

    def test_plan_that_misses_the_target_is_flagged(self):
        MacroTarget.objects.create(
            plan=self.plan,
            target_calories=2600,
            target_protein=200,
            target_carbs=250,
            target_fats=70,
        )
        comparison = self.plan.target_comparison()

        self.assertTrue(comparison["any_off_target"])
        calories_row = next(r for r in comparison["rows"] if r["macro"] == "calories")
        self.assertEqual(calories_row["difference"], -600)
        self.assertTrue(calories_row["off_target"])

    def test_small_difference_is_within_tolerance(self):
        """A 1% miss is not worth warning a trainer about."""
        MacroTarget.objects.create(
            plan=self.plan,
            target_calories=2010,
            target_protein=150,
            target_carbs=200,
            target_fats=60,
        )
        comparison = self.plan.target_comparison()
        self.assertFalse(comparison["any_off_target"])


class NutritionAccessTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.plan = NutritionPlan.objects.create(
            client=self.client_user, title="Client Plan"
        )

    def test_client_cannot_reach_trainer_nutrition_views(self):
        self.client.login(username="client1", password="password123")
        for name, args in (
            ("food-list", []),
            ("food-add", []),
            ("nutrition-plan-detail", [self.plan.pk]),
            ("macro-target-edit", [self.plan.pk]),
        ):
            with self.subTest(view=name):
                response = self.client.get(reverse(name, args=args))
                self.assertIn(response.status_code, (302, 403))

    def test_client_can_print_their_own_plan(self):
        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("nutrition-plan-print", args=[self.plan.pk]))
        self.assertEqual(response.status_code, 200)

    def test_client_cannot_print_another_clients_plan(self):
        other = User.objects.create_user(
            username="other", password="password123", role=User.Role.CLIENT
        )
        other_plan = NutritionPlan.objects.create(client=other, title="Other Plan")

        self.client.login(username="client1", password="password123")
        response = self.client.get(
            reverse("nutrition-plan-print", args=[other_plan.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_coach_can_print_any_plan(self):
        self.client.login(username="coach", password="password123")
        response = self.client.get(reverse("nutrition-plan-print", args=[self.plan.pk]))
        self.assertEqual(response.status_code, 200)

