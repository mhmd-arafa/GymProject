from django.urls import path

from .views import (
    ActiveSessionView,
    AddExercisesView,
    DeleteSetView,
    ExerciseCatalogCreateView,
    ExerciseCatalogListView,
    ExerciseHistoryView,
    LogSetView,
    MyWorkoutPlansView,
    PlanCloneView,
    PlanTemplateCreateView,
    PlanTemplateListView,
    SessionCompleteView,
    SessionHistoryView,
    SessionStartView,
    WorkoutPlanCreateView,
    WorkoutPlanPrintView,
)

urlpatterns = [
    path("my-plan/", MyWorkoutPlansView.as_view(), name="my-workout-plan"),
    path("plans/add/", WorkoutPlanCreateView.as_view(), name="workout-plan-add"),
    path("plans/<int:pk>/print/", WorkoutPlanPrintView.as_view(), name="workout-plan-print"),
    path("days/<int:pk>/add-exercises/", AddExercisesView.as_view(), name="add-exercises"),

    # Exercise library
    path("library/", ExerciseCatalogListView.as_view(), name="exercise-catalog"),
    path("library/add/", ExerciseCatalogCreateView.as_view(), name="exercise-catalog-add"),
    path("library/<slug:slug>/history/", ExerciseHistoryView.as_view(), name="exercise-history"),

    # Templates
    path("templates/", PlanTemplateListView.as_view(), name="plan-template-list"),
    path("templates/add/", PlanTemplateCreateView.as_view(), name="plan-template-add"),
    path("templates/<int:pk>/clone/", PlanCloneView.as_view(), name="plan-template-clone"),

    # In-gym logging
    path("days/<int:day_pk>/start/", SessionStartView.as_view(), name="session-start"),
    path("sessions/<int:pk>/", ActiveSessionView.as_view(), name="workout-session"),
    path("sessions/<int:session_pk>/log-set/", LogSetView.as_view(), name="log-set"),
    path("sets/<int:pk>/delete/", DeleteSetView.as_view(), name="delete-set"),
    path("sessions/<int:pk>/complete/", SessionCompleteView.as_view(), name="session-complete"),
    path("history/", SessionHistoryView.as_view(), name="workout-history"),
]
