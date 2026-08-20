"""Populate a scratch database with believable data for design review.

Screenshots of empty states tell you nothing about a design, so this builds a
coach with several clients in different situations: one training well with
history, one gone quiet, one waiting on payment approval, one never set up.

    SECRET_KEY=dev DEBUG=1 DB_ENGINE=django.db.backends.sqlite3 \
    DB_NAME=demo.sqlite3 python tools/seed_demo.py
"""

import os
import sys
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

import django  # noqa: E402

django.setup()

from django.core.files.base import ContentFile  # noqa: E402
from django.utils import timezone  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from accounts.models import IntakeForm, TrainerNote, User  # noqa: E402
from nutrition.models import (  # noqa: E402
    FoodItem,
    MacroTarget,
    Meal,
    MealFoodItem,
    NutritionPlan,
    Supplement,
    SupplementSchedule,
)
from progress.models import BodyMeasurement, CheckIn, ProgressPhoto  # noqa: E402
from subscriptions.models import PaymentProof, Subscription, SubscriptionPlan  # noqa: E402
from workouts.models import (  # noqa: E402
    Exercise,
    ExerciseCatalog,
    SetLog,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
)
from workouts.services import detect_prs  # noqa: E402

PASSWORD = "demo12345"


def wipe():
    User.objects.filter(username__in=[
        "coach", "ahmed", "mona", "youssef", "salma"
    ]).delete()
    WorkoutPlan.objects.filter(title__startswith="Push/Pull/Legs").delete()
    SubscriptionPlan.objects.filter(name__in=["3 months", "1 month"]).delete()

def main():
    wipe()
    today = timezone.localdate()

    coach = User.objects.create_user(
        username="coach", password=PASSWORD, role=User.Role.ADMIN,
        first_name="Kareem", email="kareem@example.com",
    )

    ahmed = User.objects.create_user(
        username="ahmed", password=PASSWORD, role=User.Role.CLIENT,
        phone="01012345678", email="ahmed@example.com",
    )
    mona = User.objects.create_user(
        username="mona", password=PASSWORD, role=User.Role.CLIENT,
        phone="01198765432", email="mona@example.com",
    )
    youssef = User.objects.create_user(
        username="youssef", password=PASSWORD, role=User.Role.CLIENT,
        phone="01234567890",
    )
    salma = User.objects.create_user(
        username="salma", password=PASSWORD, role=User.Role.CLIENT,
        phone="01555512345",
    )

    IntakeForm.objects.create(
        client=ahmed, goal=IntakeForm.Goal.BUILD_MUSCLE,
        equipment_access=IntakeForm.Equipment.FULL_GYM,
        training_days_per_week=4, injuries="Left shoulder impingement",
        allergies="Peanuts",
    )
    IntakeForm.objects.create(
        client=mona, goal=IntakeForm.Goal.LOSE_FAT,
        equipment_access=IntakeForm.Equipment.HOME_BASIC,
        training_days_per_week=3,
    )
    IntakeForm.objects.create(
        client=youssef, goal=IntakeForm.Goal.STRENGTH,
        equipment_access=IntakeForm.Equipment.FULL_GYM,
        training_days_per_week=5,
    )

    TrainerNote.objects.create(
        client=ahmed, author=coach,
        body="Shoulder flares up on flat bench. Keep incline work light.",
    )

    # --- Plan, cloned from a template like the trainer really would ---------
    template = WorkoutPlan.objects.create(
        title="Push/Pull/Legs — intermediate", is_template=True, client=None,
        description="Three days, barbell-led, 6-8 rep range on the main lifts.",
    )

    def lift(day, name, sets, reps, reps_max, weight, rest, order):
        catalog = ExerciseCatalog.objects.filter(name=name).first()
        return Exercise.objects.create(
            day=day, catalog_exercise=catalog, name=name, sets=sets, reps=reps,
            reps_max=reps_max, target_weight_kg=weight, rest_seconds=rest,
            order=order,
        )

    push = WorkoutDay.objects.create(plan=template, day_name="Push", order=1)
    lift(push, "Barbell Bench Press", 4, 6, 8, Decimal("80"), 150, 1)
    lift(push, "Overhead Press", 3, 6, 8, Decimal("45"), 120, 2)
    lift(push, "Incline Dumbbell Press", 3, 8, 12, Decimal("24"), 90, 3)
    lift(push, "Triceps Rope Pushdown", 3, 10, 15, Decimal("30"), 60, 4)

    pull = WorkoutDay.objects.create(plan=template, day_name="Pull", order=2)
    lift(pull, "Deadlift", 3, 4, 6, Decimal("120"), 180, 1)
    lift(pull, "Barbell Row", 4, 6, 8, Decimal("70"), 120, 2)
    lift(pull, "Lat Pulldown", 3, 10, 12, Decimal("55"), 90, 3)

    legs = WorkoutDay.objects.create(plan=template, day_name="Legs", order=3)
    lift(legs, "Back Squat", 4, 5, 8, Decimal("100"), 180, 1)
    lift(legs, "Romanian Deadlift", 3, 8, 10, Decimal("80"), 120, 2)
    lift(legs, "Standing Calf Raise", 4, 12, 15, Decimal("60"), 60, 3)

    ahmed_plan = template.clone_for(ahmed)
    template.clone_for(mona)
    template.clone_for(youssef)
    # salma deliberately gets no plan, so the queue has something to show.

    # --- Ahmed's training history ------------------------------------------
    ahmed_push = ahmed_plan.days.get(day_name="Push")
    bench = ahmed_push.exercises.get(name="Barbell Bench Press")
    ohp = ahmed_push.exercises.get(name="Overhead Press")

    # Two completed sessions at the top of the rep range, which is exactly what
    # earns a progression suggestion on the third.
    for days_ago, load in ((10, Decimal("77.5")), (6, Decimal("80")), (3, Decimal("80"))):
        session = WorkoutSession.objects.create(
            client=ahmed, plan=ahmed_plan, day=ahmed_push
        )
        for set_number in (1, 2, 3, 4):
            log = SetLog.objects.create(
                session=session, exercise=bench, set_number=set_number,
                weight_kg=load, reps=8, rpe=Decimal("8"),
            )
            detect_prs(log)
        for set_number in (1, 2, 3):
            log = SetLog.objects.create(
                session=session, exercise=ohp, set_number=set_number,
                weight_kg=Decimal("45"), reps=8,
            )
            detect_prs(log)
        WorkoutSession.objects.filter(pk=session.pk).update(
            started_at=timezone.now() - timedelta(days=days_ago),
            completed_at=timezone.now() - timedelta(days=days_ago),
            perceived_effort=8,
        )

    # An open session for the screenshot: one warm-up and two working sets in.
    live = WorkoutSession.objects.create(
        client=ahmed, plan=ahmed_plan, day=ahmed_push
    )
    SetLog.objects.create(
        session=live, exercise=bench, set_number=1,
        weight_kg=Decimal("60"), reps=10, is_warmup=True,
    )
    detect_prs(
        SetLog.objects.create(
            session=live, exercise=bench, set_number=1,
            weight_kg=Decimal("82.5"), reps=8, rpe=Decimal("8"),
        )
    )
    detect_prs(
        SetLog.objects.create(
            session=live, exercise=bench, set_number=2,
            weight_kg=Decimal("82.5"), reps=7, rpe=Decimal("9"),
        )
    )

    for weeks_ago, weight, waist in ((6, "84.2", "88"), (4, "83.1", "87"),
                                     (2, "82.4", "86"), (0, "81.6", "85")):
        BodyMeasurement.objects.create(
            client=ahmed, date=today - timedelta(weeks=weeks_ago),
            weight_kg=Decimal(weight), waist_cm=Decimal(waist),
        )

    # --- Progress photos ----------------------------------------------------
    # Placeholder images: a labelled gradient per pose and date, so the
    # comparison views have something distinguishable to show without shipping
    # real photos of anyone.
    def placeholder(label, shade):
        image = Image.new("RGB", (900, 1200), shade)
        draw = ImageDraw.Draw(image)
        # A crude figure outline, enough to read as a body silhouette.
        lighter = tuple(min(255, c + 26) for c in shade)
        draw.ellipse((390, 130, 510, 250), fill=lighter)
        draw.rounded_rectangle((330, 270, 570, 720), 40, fill=lighter)
        draw.rounded_rectangle((355, 730, 440, 1090), 30, fill=lighter)
        draw.rounded_rectangle((460, 730, 545, 1090), 30, fill=lighter)
        draw.text((40, 40), label, fill=(240, 240, 240))
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=80)
        buffer.seek(0)
        return ContentFile(buffer.read(), name=f"{label.replace(' ', '_')}.jpg")

    # Two rounds eight weeks apart, all three poses, so every "then vs now"
    # pair on both the client and coach pages is populated.
    photo_rounds = [
        (8, 96),   # earlier, darker
        (0, 126),  # latest, lighter
    ]
    for weeks_ago, base in photo_rounds:
        date = today - timedelta(weeks=weeks_ago)
        for index, pose in enumerate(
            [ProgressPhoto.Pose.FRONT, ProgressPhoto.Pose.SIDE, ProgressPhoto.Pose.BACK]
        ):
            shade = (base, base - 14 + index * 8, base - 30 + index * 6)
            ProgressPhoto.objects.create(
                client=ahmed, date=date, pose=pose,
                image=placeholder(f"{pose} {date}", shade),
                # Left private on purpose: the public results page should be
                # empty until a client explicitly opts in.
                consent_public=False,
            )

    # --- Nutrition ----------------------------------------------------------
    # Built from the seeded Egyptian food database so macros are computed, not
    # typed -- which is the whole point of that table.
    diet = NutritionPlan.objects.create(client=ahmed, title="Cutting — 2,200 kcal")
    MacroTarget.objects.create(
        plan=diet, target_calories=2200, target_protein=180,
        target_carbs=200, target_fats=65, water_ml=3000,
    )

    def build_meal(name, foods, notes="", alternative_of=None):
        """Create a meal and compute its macros from weighed foods."""
        meal = Meal.objects.create(
            plan=diet, name=name, calories=0, protein=0, carbs=0, fats=0,
            notes=notes, alternative_of=alternative_of,
        )
        for food_name, grams in foods:
            food = FoodItem.objects.filter(name=food_name).first()
            if food:
                MealFoodItem.objects.create(meal=meal, food=food, grams=grams)
        meal.recalculate_totals()
        return meal

    breakfast = build_meal("Breakfast", [
        ("Foul Medames", 200),
        ("Baladi Bread", 60),
        ("Whole Egg (boiled)", 100),
    ], notes="Skip the extra oil on the foul.")
    build_meal("Breakfast — option B", [
        ("Oats (dry)", 60),
        ("Skimmed Milk", 250),
        ("Banana", 100),
        ("Peanut Butter", 15),
    ], alternative_of=breakfast)

    lunch = build_meal("Lunch", [
        ("Chicken Breast (grilled)", 200),
        ("White Rice (cooked)", 200),
        ("Green Salad (mixed)", 150),
        ("Olive Oil", 10),
    ])
    build_meal("Lunch — option B", [
        ("Tilapia (grilled)", 220),
        ("Sweet Potato (baked)", 200),
        ("Broccoli (steamed)", 150),
    ], alternative_of=lunch)

    build_meal("Snack", [
        ("Greek Yoghurt (plain)", 200),
        ("Almonds", 20),
    ])
    build_meal("Dinner", [
        ("Beef Mince (lean, cooked)", 150),
        ("Molokhia (cooked)", 200),
        ("Rice with Vermicelli", 150),
    ])

    for supp_name, dose, timing in (
        ("Whey Protein", "1 scoop", SupplementSchedule.Timing.POST_WORKOUT),
        ("Creatine Monohydrate", "5 g", SupplementSchedule.Timing.MORNING),
        ("Vitamin D3", "2000 IU", SupplementSchedule.Timing.WITH_MEAL),
    ):
        supplement = Supplement.objects.filter(name=supp_name).first()
        if supplement:
            SupplementSchedule.objects.create(
                plan=diet, supplement=supplement, dose=dose, timing=timing
            )

    NutritionPlan.objects.create(client=mona, title="Maintenance — 1,800 kcal")

    # --- Subscriptions ------------------------------------------------------
    quarter = SubscriptionPlan.objects.create(
        name="3 months", duration_days=90, price_egp=Decimal("3000")
    )
    monthly = SubscriptionPlan.objects.create(
        name="1 month", duration_days=30, price_egp=Decimal("1200")
    )

    # Ahmed: active, expiring inside the renewal window.
    active = Subscription.objects.create(
        client=ahmed, plan=quarter, status=Subscription.Status.ACTIVE,
        start_date=today - timedelta(days=85), end_date=today + timedelta(days=5),
    )

    # Mona: paid, waiting on the coach to approve.
    pending = Subscription.objects.create(client=mona, plan=quarter)
    proof = PaymentProof.objects.create(
        subscription=pending, method=PaymentProof.Method.INSTAPAY,
        reference_number="IPN-4471902", amount_egp=Decimal("3000"),
    )
    PaymentProof.objects.filter(pk=proof.pk).update(
        submitted_at=timezone.now() - timedelta(days=2)
    )

    # Youssef: another payment waiting, different method.
    pending2 = Subscription.objects.create(client=youssef, plan=monthly)
    proof2 = PaymentProof.objects.create(
        subscription=pending2, method=PaymentProof.Method.VODAFONE_CASH,
        reference_number="VF-88213", amount_egp=Decimal("1200"),
    )
    PaymentProof.objects.filter(pk=proof2.pk).update(
        submitted_at=timezone.now() - timedelta(hours=6)
    )

    # --- Check-ins ----------------------------------------------------------
    # Ahmed has an earlier answered check-in with photos, and a new unanswered
    # one with photos, so the coach's "last vs this week" pairing has both sides.
    previous_checkin = CheckIn.objects.create(
        client=ahmed, due_date=today - timedelta(days=8),
        weight_kg=Decimal("82.4"), energy_rating=3, sleep_rating=3,
        adherence_rating=4, note="Busy week but got all four sessions in.",
        trainer_reply="Good work. Keep bench at 80 for one more week.",
        reviewed=True,
    )
    CheckIn.objects.filter(pk=previous_checkin.pk).update(
        submitted_at=timezone.now() - timedelta(days=8),
        replied_at=timezone.now() - timedelta(days=7),
    )

    submitted = CheckIn.objects.create(
        client=ahmed, due_date=today - timedelta(days=1),
        weight_kg=Decimal("81.6"), energy_rating=4, sleep_rating=3,
        adherence_rating=5, note="Good week. Shoulder held up on incline.",
    )
    CheckIn.objects.filter(pk=submitted.pk).update(
        submitted_at=timezone.now() - timedelta(hours=20)
    )

    # Link the two photo rounds to those check-ins so the coach sees a pair.
    for checkin, weeks_ago in ((previous_checkin, 8), (submitted, 0)):
        ProgressPhoto.objects.filter(
            client=ahmed, date=today - timedelta(weeks=weeks_ago)
        ).update(checkin=checkin)

    submitted2 = CheckIn.objects.create(
        client=mona, due_date=today - timedelta(days=2),
        weight_kg=Decimal("68.9"), energy_rating=2, sleep_rating=2,
        adherence_rating=3, note="Travelled for work, missed two sessions.",
    )
    CheckIn.objects.filter(pk=submitted2.pk).update(
        submitted_at=timezone.now() - timedelta(days=1, hours=4)
    )

    # Overdue and never submitted.
    CheckIn.objects.create(client=youssef, due_date=today - timedelta(days=4))

    # An open check-in for Ahmed so the photo-upload form is reachable, and it
    # shows last round's shots as framing references.
    upcoming = CheckIn.objects.create(client=ahmed, due_date=today + timedelta(days=6))

    print("Seeded.")
    print(f"  coach / {PASSWORD}   (ADMIN)")
    print(f"  ahmed / {PASSWORD}   (CLIENT)")
    print("")
    print("  client progress ....... /progress/me/")
    print(f"  send a check-in ....... /progress/checkins/{upcoming.pk}/submit/")
    print(f"  live workout .......... /workouts/sessions/{live.pk}/")
    print("  coach dashboard ....... /dashboard/")
    print(f"  coach reviews photos .. /progress/checkins/{submitted.pk}/reply/")
    print(f"  coach sees progress ... /progress/clients/{ahmed.pk}/")
    print(f"  active sub ends ....... {active.end_date}")


if __name__ == "__main__":
    main()
