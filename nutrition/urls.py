from django.urls import path

from .views import (
    FoodItemCreateView,
    FoodItemListView,
    MacroTargetUpdateView,
    MealFoodItemsView,
    MyNutritionPlansView,
    NutritionPlanCreateView,
    NutritionPlanDetailView,
    NutritionPlanPrintView,
    SupplementScheduleView,
)

urlpatterns = [
    path("my-plan/", MyNutritionPlansView.as_view(), name="my-nutrition-plan"),
    path("plans/add/", NutritionPlanCreateView.as_view(), name="nutrition-plan-add"),
    path("plans/<int:pk>/", NutritionPlanDetailView.as_view(), name="nutrition-plan-detail"),
    path("plans/<int:pk>/print/", NutritionPlanPrintView.as_view(), name="nutrition-plan-print"),
    path("plans/<int:plan_pk>/target/", MacroTargetUpdateView.as_view(), name="macro-target-edit"),
    path("plans/<int:pk>/supplements/", SupplementScheduleView.as_view(), name="supplement-schedule"),
    path("meals/<int:pk>/foods/", MealFoodItemsView.as_view(), name="meal-food-items"),
    path("foods/", FoodItemListView.as_view(), name="food-list"),
    path("foods/add/", FoodItemCreateView.as_view(), name="food-add"),
]
