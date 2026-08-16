from django.contrib import admin
from .models import NutritionPlan, Meal


class MealInline(admin.TabularInline):
    model = Meal
    extra = 1


@admin.register(NutritionPlan)
class NutritionPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "created_at")
    list_filter = ("client",)
    inlines = [MealInline]
