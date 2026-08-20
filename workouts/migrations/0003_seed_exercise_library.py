"""Seed the exercise library with common lifts.

Named exercises are what let per-exercise history and charts work at all, so the
library ships populated rather than leaving the trainer to type 40 rows.
"""

from django.db import migrations
from django.utils.text import slugify

# (name, muscle_group, equipment)
EXERCISES = [
    # Chest
    ("Barbell Bench Press", "CHEST", "BARBELL"),
    ("Incline Barbell Bench Press", "CHEST", "BARBELL"),
    ("Dumbbell Bench Press", "CHEST", "DUMBBELL"),
    ("Incline Dumbbell Press", "CHEST", "DUMBBELL"),
    ("Cable Chest Fly", "CHEST", "CABLE"),
    ("Machine Chest Press", "CHEST", "MACHINE"),
    ("Push-Up", "CHEST", "BODYWEIGHT"),
    # Back
    ("Deadlift", "BACK", "BARBELL"),
    ("Barbell Row", "BACK", "BARBELL"),
    ("Pull-Up", "BACK", "BODYWEIGHT"),
    ("Lat Pulldown", "BACK", "CABLE"),
    ("Seated Cable Row", "BACK", "CABLE"),
    ("Dumbbell Row", "BACK", "DUMBBELL"),
    ("T-Bar Row", "BACK", "MACHINE"),
    # Shoulders
    ("Overhead Press", "SHOULDERS", "BARBELL"),
    ("Dumbbell Shoulder Press", "SHOULDERS", "DUMBBELL"),
    ("Lateral Raise", "SHOULDERS", "DUMBBELL"),
    ("Rear Delt Fly", "SHOULDERS", "DUMBBELL"),
    ("Face Pull", "SHOULDERS", "CABLE"),
    # Arms
    ("Barbell Curl", "BICEPS", "BARBELL"),
    ("Dumbbell Curl", "BICEPS", "DUMBBELL"),
    ("Hammer Curl", "BICEPS", "DUMBBELL"),
    ("Preacher Curl", "BICEPS", "MACHINE"),
    ("Close-Grip Bench Press", "TRICEPS", "BARBELL"),
    ("Triceps Rope Pushdown", "TRICEPS", "CABLE"),
    ("Overhead Triceps Extension", "TRICEPS", "DUMBBELL"),
    ("Triceps Dip", "TRICEPS", "BODYWEIGHT"),
    # Legs
    ("Back Squat", "QUADS", "BARBELL"),
    ("Front Squat", "QUADS", "BARBELL"),
    ("Leg Press", "QUADS", "MACHINE"),
    ("Bulgarian Split Squat", "QUADS", "DUMBBELL"),
    ("Leg Extension", "QUADS", "MACHINE"),
    ("Romanian Deadlift", "HAMSTRINGS", "BARBELL"),
    ("Lying Leg Curl", "HAMSTRINGS", "MACHINE"),
    ("Hip Thrust", "GLUTES", "BARBELL"),
    ("Glute Bridge", "GLUTES", "BODYWEIGHT"),
    ("Standing Calf Raise", "CALVES", "MACHINE"),
    ("Seated Calf Raise", "CALVES", "MACHINE"),
    # Core and conditioning
    ("Plank", "CORE", "BODYWEIGHT"),
    ("Hanging Leg Raise", "CORE", "BODYWEIGHT"),
    ("Cable Crunch", "CORE", "CABLE"),
    ("Russian Twist", "CORE", "OTHER"),
    ("Kettlebell Swing", "FULL_BODY", "KETTLEBELL"),
    ("Treadmill Run", "CARDIO", "MACHINE"),
    ("Stationary Bike", "CARDIO", "MACHINE"),
    ("Rowing Machine", "CARDIO", "MACHINE"),
]


def seed_exercises(apps, schema_editor):
    ExerciseCatalog = apps.get_model("workouts", "ExerciseCatalog")
    for name, muscle_group, equipment in EXERCISES:
        # get_or_create keeps this safe to re-run and non-destructive if the
        # trainer has already added an exercise by the same name.
        ExerciseCatalog.objects.get_or_create(
            name=name,
            defaults={
                "slug": slugify(name)[:120],
                "muscle_group": muscle_group,
                "equipment": equipment,
                "is_active": True,
            },
        )


def unseed_exercises(apps, schema_editor):
    ExerciseCatalog = apps.get_model("workouts", "ExerciseCatalog")
    # Only remove rows that are not referenced by a plan or a logged set, so
    # reversing the migration cannot destroy real training history.
    names = [name for name, _group, _equipment in EXERCISES]
    ExerciseCatalog.objects.filter(
        name__in=names, plan_exercises__isnull=True, set_logs__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("workouts", "0002_exercisecatalog_personalrecord_setlog_workoutsession_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_exercises, unseed_exercises),
    ]
