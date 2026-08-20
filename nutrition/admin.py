from django.contrib import admin

from .models import (
    FoodItem,
    MacroTarget,
    Meal,
    MealFoodItem,
    NutritionPlan,
    Supplement,
    SupplementSchedule,
)


class MealFoodItemInline(admin.TabularInline):
    model = MealFoodItem
    extra = 1
    autocomplete_fields = ["food"]


class MealInline(admin.TabularInline):
    model = Meal
    extra = 1
    fields = ("name", "alternative_of", "calories", "protein", "carbs", "fats")


class MacroTargetInline(admin.StackedInline):
    model = MacroTarget
    extra = 0


class SupplementScheduleInline(admin.TabularInline):
    model = SupplementSchedule
    extra = 1


@admin.register(FoodItem)
class FoodItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "calories_per_100g",
        "protein_per_100g",
        "carbs_per_100g",
        "fats_per_100g",
        "is_egyptian_staple",
    )
    list_filter = ("category", "is_egyptian_staple")
    search_fields = ("name",)


@admin.register(NutritionPlan)
class NutritionPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "created_at")
    list_filter = ("client",)
    inlines = [MacroTargetInline, MealInline, SupplementScheduleInline]


@admin.register(Meal)
class MealAdmin(admin.ModelAdmin):
    list_display = ("name", "plan", "alternative_of", "calories", "protein")
    list_filter = ("plan",)
    inlines = [MealFoodItemInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Keep stored macros in step with the weighed foods edited inline.
        form.instance.recalculate_totals()


@admin.register(Supplement)
class SupplementAdmin(admin.ModelAdmin):
    list_display = ("name", "notes")
    search_fields = ("name",)


@admin.register(MacroTarget)
class MacroTargetAdmin(admin.ModelAdmin):
    list_display = (
        "plan",
        "target_calories",
        "target_protein",
        "target_carbs",
        "target_fats",
        "water_ml",
    )
