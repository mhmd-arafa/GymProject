from django.contrib import admin
from .models import WorkoutPlan, WorkoutDay, Exercise


class ExerciseInline(admin.TabularInline):
    model = Exercise
    extra = 1


class WorkoutDayInline(admin.TabularInline):
    model = WorkoutDay
    extra = 1


@admin.register(WorkoutPlan)
class WorkoutPlanAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "created_at")
    list_filter = ("client",)
    inlines = [WorkoutDayInline]


@admin.register(WorkoutDay)
class WorkoutDayAdmin(admin.ModelAdmin):
    list_display = ("day_name", "plan")
    inlines = [ExerciseInline]