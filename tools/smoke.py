"""End-to-end smoke check against a real database and real HTTP handling.

Unit tests assert pieces; this walks the flows a trainer and client actually
perform, in order, and prints what happened. Run it against a scratch sqlite DB:

    SECRET_KEY=dev DEBUG=1 DB_ENGINE=django.db.backends.sqlite3 \
    DB_NAME=smoke.sqlite3 python tools/smoke.py
"""

import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")

import django  # noqa: E402

django.setup()

from django.test.utils import setup_test_environment  # noqa: E402

# Instruments template rendering so response.context is populated, and adds
# "testserver" to ALLOWED_HOSTS. The test runner normally does this; a
# standalone script has to ask for it.
setup_test_environment()

from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone  # noqa: E402

from accounts.models import IntakeForm, TrainerNote, User  # noqa: E402
from nutrition.models import (  # noqa: E402
    FoodItem,
    MacroTarget,
    Meal,
    MealFoodItem,
    NutritionPlan,
)
from progress.models import CheckIn, ProgressPhoto  # noqa: E402
from subscriptions.models import PaymentProof, Subscription, SubscriptionPlan  # noqa: E402
from subscriptions.services import approve_payment  # noqa: E402
from workouts import services  # noqa: E402
from workouts.models import (  # noqa: E402
    Exercise,
    ExerciseCatalog,
    PersonalRecord,
    SetLog,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
)

PASSWORD = "SmokeTest123!"
failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def reset():
    """Remove anything from a previous run so the script is re-runnable."""
    User.objects.filter(username__startswith="smoke_").delete()
    WorkoutPlan.objects.filter(title__startswith="SMOKE").delete()
    ExerciseCatalog.objects.filter(name__startswith="SMOKE").delete()
    SubscriptionPlan.objects.filter(name__startswith="SMOKE").delete()
    FoodItem.objects.filter(name__startswith="SMOKE").delete()


def main():
    reset()
    print("\n=== 1. Accounts ===")
    coach = User.objects.create_user(
        username="smoke_coach", password=PASSWORD, role=User.Role.ADMIN
    )
    ahmed = User.objects.create_user(
        username="smoke_ahmed", password=PASSWORD, role=User.Role.CLIENT,
        phone="01012345678",
    )
    mona = User.objects.create_user(
        username="smoke_mona", password=PASSWORD, role=User.Role.CLIENT
    )
    check("created coach and two clients", User.objects.filter(
        username__startswith="smoke_").count() == 3)

    coach_client = Client()
    coach_client.force_login(coach)
    ahmed_client = Client()
    ahmed_client.force_login(ahmed)

    print("\n=== 2. Intake questionnaire ===")
    response = ahmed_client.post(reverse("intake"), {
        "goal": IntakeForm.Goal.BUILD_MUSCLE,
        "equipment_access": IntakeForm.Equipment.FULL_GYM,
        "training_days_per_week": "4",
        "injuries": "Left shoulder impingement",
        "allergies": "Peanuts",
        "food_dislikes": "Liver",
        "notes": "",
    })
    check("client submitted intake", response.status_code == 302)
    check("intake stored", IntakeForm.objects.filter(client=ahmed).exists())

    print("\n=== 3. Exercise library + template + clone ===")
    bench = ExerciseCatalog.objects.create(
        name="SMOKE Bench Press", muscle_group="CHEST", equipment="BARBELL",
        video_url="https://example.com/bench",
    )
    check("library seeded by migration", ExerciseCatalog.objects.count() > 40,
          f"{ExerciseCatalog.objects.count()} exercises")

    template = WorkoutPlan.objects.create(
        title="SMOKE PPL Beginner", is_template=True, client=None
    )
    push = WorkoutDay.objects.create(plan=template, day_name="Push", order=1)
    WorkoutDay.objects.create(plan=template, day_name="Pull", order=2)
    Exercise.objects.create(
        day=push, catalog_exercise=bench, name=bench.name,
        sets=3, reps=6, reps_max=8, rest_seconds=120, order=1,
    )

    ahmed_plan = template.clone_for(ahmed)
    mona_plan = template.clone_for(mona)
    check("template cloned to two clients",
          ahmed_plan.pk != mona_plan.pk and ahmed_plan.days.count() == 2)
    check("cloned exercises are independent rows",
          ahmed_plan.days.first().exercises.first().pk
          != mona_plan.days.first().exercises.first().pk)

    response = ahmed_client.get(reverse("my-workout-plan"))
    body = response.content.decode()
    check("client sees their cloned plan", "SMOKE PPL Beginner" in body)
    check("template itself is not listed for the client",
          body.count("SMOKE PPL Beginner") == 1)

    print("\n=== 4. In-gym logging (session 1) ===")
    ahmed_push = ahmed_plan.days.get(day_name="Push")
    ahmed_exercise = ahmed_push.exercises.first()

    response = ahmed_client.post(reverse("session-start", args=[ahmed_push.pk]))
    session1 = WorkoutSession.objects.filter(client=ahmed).first()
    check("session started", session1 is not None and response.status_code == 302)

    log_url = reverse("log-set", args=[session1.pk])
    for set_number in (1, 2, 3):
        response = ahmed_client.post(
            log_url,
            {"exercise": ahmed_exercise.pk, "weight_kg": "80", "reps": "8"},
            headers={"HX-Request": "true"},
        )
        if set_number == 1:
            fragment = response.content.decode()
            check("HTMX POST returns a fragment, not a page",
                  response.status_code == 200 and "<html" not in fragment)
            check("fragment shows the logged set", "80kg" in fragment)
    check("three sets logged", session1.set_logs.count() == 3)

    prs = PersonalRecord.objects.filter(client=ahmed, catalog_exercise=bench)
    check("personal records auto-detected", prs.exists(),
          f"{prs.count()} record types")

    response = ahmed_client.post(
        reverse("session-complete", args=[session1.pk]),
        {"perceived_effort": "8", "notes": "Felt strong"},
    )
    session1.refresh_from_db()
    check("session completed", session1.completed_at is not None)

    # Backdate so session 2 is a genuinely later session.
    WorkoutSession.objects.filter(pk=session1.pk).update(
        started_at=timezone.now() - timedelta(days=3)
    )

    print("\n=== 5. Session 2: 'last time' and progression ===")
    ahmed_client.post(reverse("session-start", args=[ahmed_push.pk]))
    session2 = WorkoutSession.objects.filter(
        client=ahmed, completed_at__isnull=True
    ).first()

    response = ahmed_client.get(reverse("workout-session", args=[session2.pk]))
    body = response.content.decode()
    check("session page shows 'Last time' with real numbers",
          "Last time" in body and "80kg" in body)
    check("weight renders plainly, not as 8E+1", "8E+1" not in body)

    log_url2 = reverse("log-set", args=[session2.pk])
    for _ in range(3):
        ahmed_client.post(log_url2,
                          {"exercise": ahmed_exercise.pk, "weight_kg": "80", "reps": "8"})
    ahmed_client.post(reverse("session-complete", args=[session2.pk]),
                      {"perceived_effort": "8", "notes": ""})

    suggestion = services.suggest_progression(ahmed, ahmed_exercise)
    check("progression suggested after 2 top-of-range sessions",
          suggestion is not None)
    if suggestion:
        check("suggests +2.5kg over 80kg",
              suggestion["suggested_weight_kg"] == Decimal("82.5"),
              f"{suggestion['suggested_weight_kg']}kg")

    response = coach_client.get(reverse("client-detail", args=[ahmed.pk]))
    check("coach sees the suggestion on client detail",
          "82.5" in response.content.decode())

    print("\n=== 6. New PR on a heavier set ===")
    ahmed_client.post(reverse("session-start", args=[ahmed_push.pk]))
    session3 = WorkoutSession.objects.filter(
        client=ahmed, completed_at__isnull=True
    ).first()
    before = PersonalRecord.objects.get(
        client=ahmed, catalog_exercise=bench,
        record_type=PersonalRecord.RecordType.MAX_WEIGHT,
    ).value
    ahmed_client.post(reverse("log-set", args=[session3.pk]),
                      {"exercise": ahmed_exercise.pk, "weight_kg": "90", "reps": "5"})
    after = PersonalRecord.objects.get(
        client=ahmed, catalog_exercise=bench,
        record_type=PersonalRecord.RecordType.MAX_WEIGHT,
    ).value
    check("max-weight PR updated", after > before, f"{before}kg -> {after}kg")

    print("\n=== 7. Nutrition: Egyptian foods compute macros ===")
    foul = FoodItem.objects.filter(name="Foul Medames").first()
    check("Egyptian staples seeded", foul is not None)
    if foul:
        macros = foul.macros_for(200)
        check("200g foul computes macros", macros["calories"] > 0,
              f"{macros['calories']} kcal, {macros['protein']}g protein")

    diet = NutritionPlan.objects.create(client=ahmed, title="SMOKE Cutting Diet")
    breakfast = Meal.objects.create(
        plan=diet, name="Breakfast", calories=0, protein=0, carbs=0, fats=0
    )
    chicken = FoodItem.objects.filter(name="Chicken Breast (grilled)").first()
    MealFoodItem.objects.create(meal=breakfast, food=chicken, grams=150)
    breakfast.recalculate_totals()
    breakfast.refresh_from_db()
    check("macros auto-computed from 150g chicken", breakfast.calories == 248,
          f"{breakfast.calories} kcal")

    Meal.objects.create(
        plan=diet, alternative_of=breakfast, name="Breakfast option B",
        calories=250, protein=45, carbs=2, fats=6,
    )
    totals = diet.daily_totals()
    check("alternatives excluded from daily totals",
          totals["calories"] == breakfast.calories, f"{totals['calories']} kcal")

    MacroTarget.objects.create(
        plan=diet, target_calories=2200, target_protein=180,
        target_carbs=200, target_fats=60,
    )
    comparison = diet.target_comparison()
    check("off-target plan is flagged", comparison["any_off_target"])

    print("\n=== 8. Manual payment verification ===")
    package = SubscriptionPlan.objects.create(
        name="SMOKE 3 Months", duration_days=90, price_egp=Decimal("3000")
    )
    subscription = Subscription.objects.create(client=ahmed, plan=package)
    response = ahmed_client.post(
        reverse("payment-proof-upload", args=[subscription.pk]),
        {"method": PaymentProof.Method.INSTAPAY, "reference_number": "IPN-99881",
         "amount_egp": "3000", "note": ""},
    )
    check("client uploaded payment details", response.status_code == 302)
    proof = subscription.payment_proofs.first()
    check("proof is pending review",
          proof is not None and proof.status == PaymentProof.Status.PENDING)

    response = coach_client.get(reverse("payment-queue"))
    check("proof appears in the coach's review queue",
          "IPN-99881" in response.content.decode())

    coach_client.post(reverse("payment-approve", args=[proof.pk]))
    subscription.refresh_from_db()
    check("subscription activated on approval",
          subscription.status == Subscription.Status.ACTIVE)
    check("end date is start + 90 days",
          subscription.end_date == subscription.start_date + timedelta(days=90),
          f"{subscription.start_date} -> {subscription.end_date}")

    print("\n=== 9. Check-in loop ===")
    checkin = CheckIn.objects.create(client=ahmed, due_date=timezone.localdate())
    ahmed_client.post(reverse("checkin-submit", args=[checkin.pk]), {
        "weight_kg": "81.4", "energy_rating": "4", "sleep_rating": "3",
        "adherence_rating": "5", "note": "Good week, shoulder fine",
    })
    checkin.refresh_from_db()
    check("check-in submitted and unreviewed",
          checkin.is_submitted and not checkin.reviewed)

    response = coach_client.get(reverse("checkin-queue"))
    check("check-in is in the coach queue", "smoke_ahmed" in response.content.decode())

    coach_client.post(reverse("checkin-reply", args=[checkin.pk]),
                      {"trainer_reply": "Push to 82.5kg next week."})
    checkin.refresh_from_db()
    check("coach reply recorded and marked reviewed",
          checkin.reviewed and checkin.replied_at is not None)

    print("\n=== 10. Photo consent gating ===")
    from django.core.files.uploadedfile import SimpleUploadedFile
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08"
        b"\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
        b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    private = ProgressPhoto.objects.create(
        client=ahmed, image=SimpleUploadedFile("smoke_private.png", png, "image/png"),
        consent_public=False,
    )
    ProgressPhoto.objects.create(
        client=ahmed, image=SimpleUploadedFile("smoke_private2.png", png, "image/png"),
        consent_public=False,
    )

    public = Client()
    response = public.get(reverse("public-results"))
    listed = len(response.context["photos"])
    check("public page shows nothing without consent", listed == 0, f"{listed} photos")

    private.consent_public = True
    private.save()
    check("consent timestamp recorded", private.consent_given_at is not None)

    response = public.get(reverse("public-results"))
    photos = list(response.context["photos"])
    check("only the consented photo is public",
          photos == [private], f"{len(photos)} photo(s)")

    print("\n=== 11. Trainer notes stay private ===")
    TrainerNote.objects.create(client=ahmed, author=coach, body="SMOKE_SECRET_NOTE")
    response = coach_client.get(reverse("client-detail", args=[ahmed.pk]))
    check("coach sees the note", "SMOKE_SECRET_NOTE" in response.content.decode())

    leaked = []
    for name in ("client-home", "my-workout-plan", "my-nutrition-plan",
                 "my-progress", "my-checkins", "my-subscription"):
        page = ahmed_client.get(reverse(name)).content.decode()
        if "SMOKE_SECRET_NOTE" in page:
            leaked.append(name)
    check("note leaks on no client-facing page", not leaked, str(leaked))

    response = ahmed_client.get(reverse("client-detail", args=[ahmed.pk]))
    check("client cannot open the client-detail page",
          response.status_code in (302, 403), f"got {response.status_code}")

    print("\n=== 12. Attention queue ===")
    context = coach_client.get(reverse("trainer-dashboard")).context
    check("dashboard renders", context is not None)
    check("mona has no intake yet",
          mona in list(context["without_intake"]))
    check("ahmed completed intake",
          ahmed not in list(context["without_intake"]))
    check("mona has not logged a workout",
          mona in context["inactive_clients"])
    check("ahmed has logged workouts",
          ahmed not in context["inactive_clients"])

    print("\n=== 13. WhatsApp + print/PDF ===")
    from accounts.templatetags.gym_extras import whatsapp_url
    url = whatsapp_url(ahmed.phone, "Your plan is ready")
    check("Egyptian number normalised for wa.me",
          url.startswith("https://wa.me/201012345678?text="), url[:45])
    check("no link when phone is missing", whatsapp_url("", "x") == "")

    response = ahmed_client.get(reverse("workout-plan-print", args=[ahmed_plan.pk]))
    check("client can print their own workout plan", response.status_code == 200)
    response = ahmed_client.get(reverse("nutrition-plan-print", args=[diet.pk]))
    check("client can print their own diet", response.status_code == 200)
    response = ahmed_client.get(reverse("workout-plan-print", args=[mona_plan.pk]))
    check("client cannot print another client's plan",
          response.status_code == 404, f"got {response.status_code}")

    print("\n=== 14. Language switching ===")
    import re

    anon = Client()
    body = anon.get(reverse("login")).content.decode()
    check("English is the default", 'lang="en"' in body and 'dir="ltr"' in body)

    anon.post(reverse("set_language"), {"language": "ar", "next": "/"})
    body = anon.get(reverse("login")).content.decode()
    check("Arabic switches direction to RTL", 'dir="rtl"' in body)
    # Django ships its own Arabic catalogue, so widely-used strings such as
    # "Log in" are already translated; app-specific strings stay English until
    # locale/ar/LC_MESSAGES/django.po is written and compiled.
    check("Django's bundled Arabic strings render",
          len(re.findall(r"[؀-ۿ]", body)) > 0,
          f"{len(re.findall(r'[؀-ۿ]', body))} Arabic codepoints")
    check("app strings still English (catalogue not written yet)",
          "Create an account" in body)

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for name in failures:
            print(f"  - {name}")
        reset()
        sys.exit(1)
    print("ALL SMOKE CHECKS PASSED")
    reset()


if __name__ == "__main__":
    main()
