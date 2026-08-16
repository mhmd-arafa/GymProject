from django.urls import path
from .views import MyWorkoutPlansView, WorkoutPlanCreateView
from .views import AddExercisesView

urlpatterns = [
    path("my-plan/", MyWorkoutPlansView.as_view(), name="my-workout-plan"),
    path("plans/add/", WorkoutPlanCreateView.as_view(), name="workout-plan-add"),
    path("days/<int:pk>/add-exercises/", AddExercisesView.as_view(), name="add-exercises"),
]