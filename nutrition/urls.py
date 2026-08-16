from django.urls import path
from .views import MyNutritionPlansView, NutritionPlanCreateView

urlpatterns = [
    path("my-plan/", MyNutritionPlansView.as_view(), name="my-nutrition-plan"),
    path("plans/add/", NutritionPlanCreateView.as_view(), name="nutrition-plan-add"),
]
