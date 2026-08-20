from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class FoodItem(models.Model):
    """A food with per-100g macros.

    Seeded with Egyptian staples, which is the gap international apps leave: the
    trainer types "150g foul" instead of looking up and retyping macros.
    """

    class Category(models.TextChoices):
        PROTEIN = "PROTEIN", _("Protein")
        CARB = "CARB", _("Carbohydrate")
        FAT = "FAT", _("Fat")
        VEGETABLE = "VEGETABLE", _("Vegetable")
        FRUIT = "FRUIT", _("Fruit")
        DAIRY = "DAIRY", _("Dairy")
        COMPOSITE = "COMPOSITE", _("Prepared dish")
        DRINK = "DRINK", _("Drink")
        OTHER = "OTHER", _("Other")

    name = models.CharField(_("name"), max_length=100, unique=True)
    category = models.CharField(
        _("category"), max_length=10, choices=Category.choices, default=Category.OTHER
    )
    calories_per_100g = models.DecimalField(
        _("calories per 100g"), max_digits=6, decimal_places=1
    )
    protein_per_100g = models.DecimalField(
        _("protein per 100g"), max_digits=5, decimal_places=1
    )
    carbs_per_100g = models.DecimalField(
        _("carbs per 100g"), max_digits=5, decimal_places=1
    )
    fats_per_100g = models.DecimalField(
        _("fats per 100g"), max_digits=5, decimal_places=1
    )
    is_egyptian_staple = models.BooleanField(_("Egyptian staple"), default=False)

    class Meta:
        ordering = ["name"]
        verbose_name = _("food item")
        verbose_name_plural = _("food items")

    def __str__(self):
        return f"{self.name} ({self.calories_per_100g} kcal/100g)"

    def macros_for(self, grams):
        """Macros for an arbitrary gram amount, rounded to whole numbers.

        ROUND_HALF_UP is explicit because Decimal defaults to banker's rounding,
        which would turn 46.5g of protein into 46 -- correct but surprising to
        anyone checking the arithmetic by hand.
        """
        factor = Decimal(grams) / Decimal(100)
        whole = Decimal("1")
        return {
            "calories": int(
                (self.calories_per_100g * factor).quantize(whole, rounding=ROUND_HALF_UP)
            ),
            "protein": int(
                (self.protein_per_100g * factor).quantize(whole, rounding=ROUND_HALF_UP)
            ),
            "carbs": int(
                (self.carbs_per_100g * factor).quantize(whole, rounding=ROUND_HALF_UP)
            ),
            "fats": int(
                (self.fats_per_100g * factor).quantize(whole, rounding=ROUND_HALF_UP)
            ),
        }


class NutritionPlan(models.Model):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nutrition_plans",
        limit_choices_to={"role": "CLIENT"},
        verbose_name=_("client"),
    )
    title = models.CharField(_("title"), max_length=100)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("nutrition plan")
        verbose_name_plural = _("nutrition plans")

    def __str__(self):
        return f"{self.title} - {self.client.username}"

    def daily_totals(self):
        """Summed macros across primary meals only.

        Alternatives are deliberately excluded: option A and option B are two
        ways to eat the same slot, so counting both would double the day.
        """
        totals = {"calories": 0, "protein": 0, "carbs": 0, "fats": 0}
        for meal in self.meals.filter(alternative_of__isnull=True):
            totals["calories"] += meal.calories
            totals["protein"] += meal.protein
            totals["carbs"] += meal.carbs
            totals["fats"] += meal.fats
        return totals

    def target_comparison(self):
        """Totals vs. target, flagging macros that miss by more than 5%.

        Returns None when no target is set, so the template can stay quiet.
        """
        target = getattr(self, "macro_target", None)
        if target is None:
            return None

        totals = self.daily_totals()
        rows = []
        for key, label, target_value in (
            ("calories", _("Calories"), target.target_calories),
            ("protein", _("Protein (g)"), target.target_protein),
            ("carbs", _("Carbs (g)"), target.target_carbs),
            ("fats", _("Fats (g)"), target.target_fats),
        ):
            actual = totals[key]
            difference = actual - target_value
            tolerance = max(round(target_value * 0.05), 1)
            rows.append(
                {
                    "macro": key,
                    "label": label,
                    "actual": actual,
                    "target": target_value,
                    "difference": difference,
                    "off_target": abs(difference) > tolerance,
                }
            )
        return {"rows": rows, "any_off_target": any(r["off_target"] for r in rows)}


class Meal(models.Model):
    """A meal in a plan, or an alternative to one.

    Real trainers always offer options, so a meal whose ``alternative_of`` points
    at another meal is "Breakfast option B" rather than an extra meal.
    """

    plan = models.ForeignKey(
        NutritionPlan,
        on_delete=models.CASCADE,
        related_name="meals",
        verbose_name=_("plan"),
    )
    alternative_of = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alternatives",
        verbose_name=_("alternative to"),
        help_text=_("Set this to offer the meal as a swap for another meal."),
    )
    name = models.CharField(_("name"), max_length=100)  # e.g. "Breakfast"
    calories = models.PositiveIntegerField(_("calories"))
    protein = models.PositiveIntegerField(_("protein"), help_text=_("in grams"))
    carbs = models.PositiveIntegerField(_("carbs"), help_text=_("in grams"))
    fats = models.PositiveIntegerField(_("fats"), help_text=_("in grams"))
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("meal")
        verbose_name_plural = _("meals")

    def __str__(self):
        return f"{self.name} ({self.calories} kcal)"

    def recalculate_totals(self, commit=True):
        """Recompute stored macros from this meal's food items.

        No-op when the meal has no food items, so hand-entered meals keep the
        numbers the trainer typed. That is why these columns stay non-nullable.
        Returns True when totals were recomputed.
        """
        items = list(self.food_items.select_related("food"))
        if not items:
            return False

        totals = {"calories": 0, "protein": 0, "carbs": 0, "fats": 0}
        for item in items:
            macros = item.food.macros_for(item.grams)
            for key in totals:
                totals[key] += macros[key]

        self.calories = totals["calories"]
        self.protein = totals["protein"]
        self.carbs = totals["carbs"]
        self.fats = totals["fats"]
        if commit:
            self.save(update_fields=["calories", "protein", "carbs", "fats"])
        return True


class MealFoodItem(models.Model):
    """A weighed portion of a food inside a meal."""

    meal = models.ForeignKey(
        Meal,
        on_delete=models.CASCADE,
        related_name="food_items",
        verbose_name=_("meal"),
    )
    food = models.ForeignKey(
        FoodItem,
        on_delete=models.PROTECT,
        related_name="meal_entries",
        verbose_name=_("food"),
    )
    grams = models.PositiveIntegerField(_("grams"))

    class Meta:
        verbose_name = _("meal food item")
        verbose_name_plural = _("meal food items")

    def __str__(self):
        return f"{self.grams}g {self.food.name}"

    @property
    def macros(self):
        return self.food.macros_for(self.grams)


class MacroTarget(models.Model):
    """The daily numbers a plan is supposed to hit."""

    plan = models.OneToOneField(
        NutritionPlan,
        on_delete=models.CASCADE,
        related_name="macro_target",
        verbose_name=_("plan"),
    )
    target_calories = models.PositiveIntegerField(_("target calories"))
    target_protein = models.PositiveIntegerField(_("target protein (g)"))
    target_carbs = models.PositiveIntegerField(_("target carbs (g)"))
    target_fats = models.PositiveIntegerField(_("target fats (g)"))
    water_ml = models.PositiveIntegerField(_("daily water (ml)"), default=2500)

    class Meta:
        verbose_name = _("macro target")
        verbose_name_plural = _("macro targets")

    def __str__(self):
        return f"{self.plan.title} — {self.target_calories} kcal"


class Supplement(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("supplement")
        verbose_name_plural = _("supplements")

    def __str__(self):
        return self.name


class SupplementSchedule(models.Model):
    class Timing(models.TextChoices):
        MORNING = "MORNING", _("Morning")
        PRE_WORKOUT = "PRE_WORKOUT", _("Pre-workout")
        POST_WORKOUT = "POST_WORKOUT", _("Post-workout")
        WITH_MEAL = "WITH_MEAL", _("With a meal")
        BEFORE_BED = "BEFORE_BED", _("Before bed")

    plan = models.ForeignKey(
        NutritionPlan,
        on_delete=models.CASCADE,
        related_name="supplement_schedule",
        verbose_name=_("plan"),
    )
    supplement = models.ForeignKey(
        Supplement,
        on_delete=models.PROTECT,
        related_name="schedules",
        verbose_name=_("supplement"),
    )
    dose = models.CharField(_("dose"), max_length=100)
    timing = models.CharField(
        _("timing"), max_length=15, choices=Timing.choices, default=Timing.MORNING
    )

    class Meta:
        verbose_name = _("supplement schedule")
        verbose_name_plural = _("supplement schedule")

    def __str__(self):
        return f"{self.supplement.name} — {self.dose} ({self.get_timing_display()})"
