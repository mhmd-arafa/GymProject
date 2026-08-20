from django.contrib import admin

from .models import (
    Exercise,
    ExerciseCatalog,
    PersonalRecord,
    SetLog,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
)


class ExerciseInline(admin.TabularInline):
    model = Exercise
    extra = 1
    autocomplete_fields = ["catalog_exercise"]


class WorkoutDayInline(admin.TabularInline):
    model = WorkoutDay
    extra = 1


class SetLogInline(admin.TabularInline):
    model = SetLog
    extra = 0
    fields = ("exercise", "set_number", "weight_kg", "reps", "rpe", "is_warmup")


@admin.register(ExerciseCatalog)
class ExerciseCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "muscle_group", "equipment", "is_active")
    list_filter = ("muscle_group", "equipment", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(WorkoutPlan)
class WorkoutPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "is_template", "created_at")
    list_filter = ("is_template", "client")
    search_fields = ("title",)
    inlines = [WorkoutDayInline]


@admin.register(WorkoutDay)
class WorkoutDayAdmin(admin.ModelAdmin):
    list_display = ("day_name", "plan", "order")
    inlines = [ExerciseInline]


@admin.register(WorkoutSession)
class WorkoutSessionAdmin(admin.ModelAdmin):
    list_display = ("client", "day", "started_at", "completed_at", "perceived_effort")
    list_filter = ("client",)
    date_hierarchy = "started_at"
    inlines = [SetLogInline]


@admin.register(SetLog)
class SetLogAdmin(admin.ModelAdmin):
    list_display = (
        "exercise_name",
        "session",
        "set_number",
        "weight_kg",
        "reps",
        "rpe",
        "is_warmup",
    )
    list_filter = ("is_warmup", "catalog_exercise")


@admin.register(PersonalRecord)
class PersonalRecordAdmin(admin.ModelAdmin):
    list_display = ("client", "catalog_exercise", "record_type", "value", "achieved_on")
    list_filter = ("record_type", "catalog_exercise")
