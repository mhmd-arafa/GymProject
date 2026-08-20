# pyrefly: ignore [missing-import]
from datetime import timedelta
from decimal import Decimal

# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import (
    Exercise,
    ExerciseCatalog,
    PersonalRecord,
    SetLog,
    WorkoutDay,
    WorkoutPlan,
    WorkoutSession,
)

User = get_user_model()


class WorkoutFixtureMixin:
    """Shared setup: a coach, a client, and a catalog exercise."""

    def setUp(self):
        self.coach = User.objects.create_user(
            username="coach", password="password123", role=User.Role.ADMIN
        )
        self.client_user = User.objects.create_user(
            username="client1", password="password123", role=User.Role.CLIENT
        )
        self.bench = ExerciseCatalog.objects.create(
            name="Test Bench Press", muscle_group="CHEST", equipment="BARBELL"
        )

    def make_plan(self, client=None, is_template=False, title="Plan"):
        return WorkoutPlan.objects.create(
            client=client, is_template=is_template, title=title
        )

    def make_exercise(self, day, sets=3, reps=8, reps_max=None):
        return Exercise.objects.create(
            day=day,
            catalog_exercise=self.bench,
            name=self.bench.name,
            sets=sets,
            reps=reps,
            reps_max=reps_max,
        )

    def log_session(self, exercise, sets, completed=True, started_at=None):
        """Create a session with the given (weight, reps) working sets."""
        session = WorkoutSession.objects.create(
            client=self.client_user, plan=exercise.day.plan, day=exercise.day
        )
        for index, (weight, reps) in enumerate(sets, start=1):
            SetLog.objects.create(
                session=session,
                exercise=exercise,
                set_number=index,
                weight_kg=Decimal(str(weight)),
                reps=reps,
            )
        if completed:
            session.completed_at = timezone.now()
            session.save(update_fields=["completed_at"])
        if started_at is not None:
            # auto_now_add ignores assignment, so write the column directly.
            WorkoutSession.objects.filter(pk=session.pk).update(started_at=started_at)
            session.refresh_from_db()
        return session


class TemplateAndCloneTests(WorkoutFixtureMixin, TestCase):
    def test_template_requires_null_client(self):
        """The check constraint makes an invalid template unrepresentable."""
        with self.assertRaises(IntegrityError):
            WorkoutPlan.objects.create(
                client=self.client_user, is_template=True, title="Bad"
            )

    def test_assigned_plan_requires_client(self):
        with self.assertRaises(IntegrityError):
            WorkoutPlan.objects.create(client=None, is_template=False, title="Bad")

    def test_clone_for_deep_copies_days_and_exercises(self):
        template = self.make_plan(is_template=True, title="PPL Beginner")
        day = WorkoutDay.objects.create(plan=template, day_name="Push", order=1)
        self.make_exercise(day, sets=4, reps=6, reps_max=8)

        clone = template.clone_for(self.client_user)

        self.assertEqual(clone.client, self.client_user)
        self.assertFalse(clone.is_template)
        self.assertEqual(clone.title, "PPL Beginner")
        self.assertEqual(clone.days.count(), 1)

        cloned_day = clone.days.first()
        self.assertNotEqual(cloned_day.pk, day.pk)
        self.assertEqual(cloned_day.day_name, "Push")

        cloned_exercise = cloned_day.exercises.first()
        self.assertEqual(cloned_exercise.sets, 4)
        self.assertEqual(cloned_exercise.reps, 6)
        self.assertEqual(cloned_exercise.reps_max, 8)
        self.assertEqual(cloned_exercise.catalog_exercise, self.bench)

    def test_clone_does_not_alias_original(self):
        """Editing a clone must not reach back into the template."""
        template = self.make_plan(is_template=True, title="Template")
        day = WorkoutDay.objects.create(plan=template, day_name="Push")
        original = self.make_exercise(day, sets=3)

        clone = template.clone_for(self.client_user)
        cloned_exercise = clone.days.first().exercises.first()
        cloned_exercise.sets = 99
        cloned_exercise.save()

        original.refresh_from_db()
        self.assertEqual(original.sets, 3)
        self.assertEqual(template.days.count(), 1)

    def test_clone_accepts_custom_title(self):
        template = self.make_plan(is_template=True, title="Generic")
        clone = template.clone_for(self.client_user, title="Ahmed Block 1")
        self.assertEqual(clone.title, "Ahmed Block 1")

    def test_cloning_to_many_clients_is_independent(self):
        template = self.make_plan(is_template=True, title="PPL")
        day = WorkoutDay.objects.create(plan=template, day_name="Push")
        self.make_exercise(day)
        second_client = User.objects.create_user(
            username="client2", password="password123", role=User.Role.CLIENT
        )

        first = template.clone_for(self.client_user)
        second = template.clone_for(second_client)

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.days.first().exercises.count(), 1)
        self.assertEqual(second.days.first().exercises.count(), 1)
        self.assertNotEqual(
            first.days.first().exercises.first().pk,
            second.days.first().exercises.first().pk,
        )


class TemplateIsolationTests(WorkoutFixtureMixin, TestCase):
    def test_templates_never_appear_in_client_plan_list(self):
        """Templates have client=None, so they must not leak to any client."""
        self.make_plan(is_template=True, title="Secret Template")
        self.make_plan(client=self.client_user, title="My Real Plan")

        self.client.login(username="client1", password="password123")
        response = self.client.get(reverse("my-workout-plan"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Real Plan")
        self.assertNotContains(response, "Secret Template")


class SetLogTests(WorkoutFixtureMixin, TestCase):
    def test_catalog_exercise_denormalised_on_save(self):
        plan = self.make_plan(client=self.client_user)
        day = WorkoutDay.objects.create(plan=plan, day_name="Push")
        exercise = self.make_exercise(day)
        session = WorkoutSession.objects.create(
            client=self.client_user, plan=plan, day=day
        )

        set_log = SetLog.objects.create(
            session=session, exercise=exercise, weight_kg=Decimal("80"), reps=8
        )

        self.assertEqual(set_log.catalog_exercise, self.bench)
        self.assertEqual(set_log.exercise_name, self.bench.name)

    def test_history_survives_plan_deletion(self):
        """The whole point of denormalising: deleting a plan keeps the history."""
        plan = self.make_plan(client=self.client_user)
        day = WorkoutDay.objects.create(plan=plan, day_name="Push")
        exercise = self.make_exercise(day)
        session = WorkoutSession.objects.create(
            client=self.client_user, plan=plan, day=day
        )
        SetLog.objects.create(
            session=session, exercise=exercise, weight_kg=Decimal("80"), reps=8
        )

        plan.delete()

        set_log = SetLog.objects.get()
        self.assertEqual(set_log.exercise_name, self.bench.name)
        self.assertEqual(set_log.catalog_exercise, self.bench)
        self.assertIsNone(set_log.exercise)

    def test_volume_and_estimated_1rm(self):
        plan = self.make_plan(client=self.client_user)
        day = WorkoutDay.objects.create(plan=plan, day_name="Push")
        exercise = self.make_exercise(day)
        session = WorkoutSession.objects.create(
            client=self.client_user, plan=plan, day=day
        )

        set_log = SetLog.objects.create(
            session=session, exercise=exercise, weight_kg=Decimal("100"), reps=10
        )

        self.assertEqual(set_log.volume_kg, Decimal("1000"))
        # Epley: 100 * (1 + 10/30) = 133.33
        self.assertAlmostEqual(set_log.estimated_1rm_kg, 133.33, places=2)

    def test_single_rep_1rm_is_the_weight(self):
        plan = self.make_plan(client=self.client_user)
        day = WorkoutDay.objects.create(plan=plan, day_name="Push")
        exercise = self.make_exercise(day)
        session = WorkoutSession.objects.create(
            client=self.client_user, plan=plan, day=day
        )
        set_log = SetLog.objects.create(
            session=session, exercise=exercise, weight_kg=Decimal("120"), reps=1
        )
        self.assertEqual(set_log.estimated_1rm_kg, 120.0)


class LastPerformanceTests(WorkoutFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plan = self.make_plan(client=self.client_user)
        self.day = WorkoutDay.objects.create(plan=self.plan, day_name="Push")
        self.exercise = self.make_exercise(self.day)

    def test_no_history_returns_empty_string(self):
        self.assertEqual(services.last_performance(self.client_user, self.bench), "")

    def test_formats_previous_session_sets(self):
        self.log_session(self.exercise, [(80, 8), (80, 7)])
        result = services.last_performance(self.client_user, self.bench)
        self.assertEqual(result, "80kg × 8, 80kg × 7")

    def test_excludes_the_session_in_progress(self):
        """'Last time' must mean last time, not the set just logged."""
        old = timezone.now() - timedelta(days=3)
        self.log_session(self.exercise, [(80, 8)], started_at=old)
        current = self.log_session(self.exercise, [(90, 5)], completed=False)

        result = services.last_performance(
            self.client_user, self.bench, before_session=current
        )
        self.assertEqual(result, "80kg × 8")

    def test_ignores_warmup_sets(self):
        session = self.log_session(self.exercise, [(80, 8)])
        SetLog.objects.create(
            session=session,
            exercise=self.exercise,
            set_number=2,
            weight_kg=Decimal("20"),
            reps=15,
            is_warmup=True,
        )
        result = services.last_performance(self.client_user, self.bench)
        self.assertEqual(result, "80kg × 8")

    def test_trims_trailing_zeros(self):
        self.log_session(self.exercise, [("82.50", 5)])
        self.assertEqual(
            services.last_performance(self.client_user, self.bench), "82.5kg × 5"
        )


class PersonalRecordTests(WorkoutFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plan = self.make_plan(client=self.client_user)
        self.day = WorkoutDay.objects.create(plan=self.plan, day_name="Push")
        self.exercise = self.make_exercise(self.day)
        self.session = WorkoutSession.objects.create(
            client=self.client_user, plan=self.plan, day=self.day
        )

    def _log(self, weight, reps, is_warmup=False):
        return SetLog.objects.create(
            session=self.session,
            exercise=self.exercise,
            weight_kg=Decimal(str(weight)),
            reps=reps,
            is_warmup=is_warmup,
        )

    def test_first_set_creates_records(self):
        records = services.detect_prs(self._log(80, 8))
        types = {record.record_type for record in records}
        self.assertIn(PersonalRecord.RecordType.MAX_WEIGHT, types)
        self.assertIn(PersonalRecord.RecordType.MAX_VOLUME, types)

    def test_heavier_set_beats_max_weight(self):
        services.detect_prs(self._log(80, 8))
        records = services.detect_prs(self._log(85, 5))

        beaten = {r.record_type for r in records}
        self.assertIn(PersonalRecord.RecordType.MAX_WEIGHT, beaten)

        record = PersonalRecord.objects.get(
            client=self.client_user,
            catalog_exercise=self.bench,
            record_type=PersonalRecord.RecordType.MAX_WEIGHT,
        )
        self.assertEqual(record.value, Decimal("85.00"))

    def test_matching_your_best_is_not_a_record(self):
        """Equalling a best must stay silent, or every session claims a PR."""
        services.detect_prs(self._log(80, 8))
        records = services.detect_prs(self._log(80, 8))
        self.assertEqual(records, [])

    def test_warmup_never_sets_a_record(self):
        self.assertEqual(services.detect_prs(self._log(200, 1, is_warmup=True)), [])
        self.assertFalse(PersonalRecord.objects.exists())

    def test_records_are_unique_per_exercise_and_type(self):
        services.detect_prs(self._log(80, 8))
        services.detect_prs(self._log(85, 8))
        self.assertEqual(
            PersonalRecord.objects.filter(
                record_type=PersonalRecord.RecordType.MAX_WEIGHT
            ).count(),
            1,
        )


class ProgressionSuggestionTests(WorkoutFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plan = self.make_plan(client=self.client_user)
        self.day = WorkoutDay.objects.create(plan=self.plan, day_name="Push")
        # Rep range 6-8: the top is 8.
        self.exercise = self.make_exercise(self.day, sets=2, reps=6, reps_max=8)

    def test_no_suggestion_without_enough_history(self):
        self.log_session(self.exercise, [(80, 8), (80, 8)])
        self.assertIsNone(services.suggest_progression(self.client_user, self.exercise))

    def test_suggests_after_two_sessions_at_top_of_range(self):
        old = timezone.now() - timedelta(days=4)
        self.log_session(self.exercise, [(80, 8), (80, 8)], started_at=old)
        self.log_session(self.exercise, [(80, 8), (80, 8)])

        suggestion = services.suggest_progression(self.client_user, self.exercise)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["current_weight_kg"], Decimal("80.00"))
        self.assertEqual(suggestion["suggested_weight_kg"], Decimal("82.5"))
        self.assertEqual(suggestion["target_reps"], 8)

    def test_no_suggestion_when_a_set_misses_the_top(self):
        old = timezone.now() - timedelta(days=4)
        self.log_session(self.exercise, [(80, 8), (80, 8)], started_at=old)
        self.log_session(self.exercise, [(80, 8), (80, 7)])
        self.assertIsNone(services.suggest_progression(self.client_user, self.exercise))

    def test_incomplete_sessions_do_not_count(self):
        old = timezone.now() - timedelta(days=4)
        self.log_session(self.exercise, [(80, 8), (80, 8)], started_at=old)
        self.log_session(self.exercise, [(80, 8), (80, 8)], completed=False)
        self.assertIsNone(services.suggest_progression(self.client_user, self.exercise))

    def test_fixed_rep_target_uses_reps_when_no_upper_bound(self):
        fixed = self.make_exercise(self.day, sets=1, reps=5, reps_max=None)
        old = timezone.now() - timedelta(days=4)
        self.log_session(fixed, [(100, 5)], started_at=old)
        self.log_session(fixed, [(100, 5)])

        suggestion = services.suggest_progression(self.client_user, fixed)
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["target_reps"], 5)

    def test_exercise_without_catalog_link_gets_no_suggestion(self):
        unlinked = Exercise.objects.create(
            day=self.day, name="Freehand thing", sets=3, reps=8
        )
        self.assertIsNone(services.suggest_progression(self.client_user, unlinked))


class AdherenceTests(WorkoutFixtureMixin, TestCase):
    def test_percent_is_none_without_a_plan(self):
        result = services.adherence(self.client_user)
        self.assertIsNone(result["percent"])
        self.assertIsNone(result["expected"])

    def test_counts_completed_sessions_against_plan_days(self):
        plan = self.make_plan(client=self.client_user)
        for name in ("Push", "Pull", "Legs", "Upper"):
            WorkoutDay.objects.create(plan=plan, day_name=name)
        day = plan.days.first()
        exercise = self.make_exercise(day)

        self.log_session(exercise, [(80, 8)])
        self.log_session(exercise, [(80, 8)])
        self.log_session(exercise, [(80, 8)])

        result = services.adherence(self.client_user, days=7, plan=plan)
        self.assertEqual(result["completed"], 3)
        self.assertEqual(result["expected"], 4)
        self.assertEqual(result["percent"], 75)

    def test_incomplete_sessions_are_not_counted(self):
        plan = self.make_plan(client=self.client_user)
        WorkoutDay.objects.create(plan=plan, day_name="Push")
        exercise = self.make_exercise(plan.days.first())
        self.log_session(exercise, [(80, 8)], completed=False)

        result = services.adherence(self.client_user, days=7, plan=plan)
        self.assertEqual(result["completed"], 0)


class LogSetViewTests(WorkoutFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plan = self.make_plan(client=self.client_user)
        self.day = WorkoutDay.objects.create(plan=self.plan, day_name="Push")
        self.exercise = self.make_exercise(self.day)
        self.session = WorkoutSession.objects.create(
            client=self.client_user, plan=self.plan, day=self.day
        )
        self.client.login(username="client1", password="password123")
        self.url = reverse("log-set", args=[self.session.pk])
        self.payload = {"exercise": self.exercise.pk, "weight_kg": "80", "reps": "8"}

    def test_htmx_request_returns_a_partial(self):
        response = self.client.post(
            self.url, self.payload, headers={"HX-Request": "true"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "80kg")
        # A fragment, not a full page.
        self.assertNotContains(response, "<html")

    def test_plain_post_redirects_back_to_the_session(self):
        """Progressive enhancement: works when the HTMX script never loads."""
        response = self.client.post(self.url, self.payload)
        self.assertRedirects(
            response, reverse("workout-session", args=[self.session.pk])
        )
        self.assertEqual(SetLog.objects.count(), 1)

    def test_set_number_auto_increments(self):
        self.client.post(self.url, self.payload)
        self.client.post(self.url, {**self.payload, "set_number": ""})
        self.assertEqual(
            list(
                SetLog.objects.order_by("set_number").values_list(
                    "set_number", flat=True
                )
            ),
            [1, 2],
        )

    def test_invalid_set_returns_400_for_htmx(self):
        response = self.client.post(
            self.url,
            {"exercise": self.exercise.pk, "weight_kg": "80", "reps": "0"},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SetLog.objects.exists())

    def test_cannot_log_into_another_clients_session(self):
        intruder = User.objects.create_user(
            username="intruder", password="password123", role=User.Role.CLIENT
        )
        self.client.force_login(intruder)
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SetLog.objects.exists())

    def test_cannot_log_to_a_completed_session(self):
        self.session.completed_at = timezone.now()
        self.session.save(update_fields=["completed_at"])
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 404)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, 302)


class SessionFlowTests(WorkoutFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plan = self.make_plan(client=self.client_user)
        self.day = WorkoutDay.objects.create(plan=self.plan, day_name="Push")
        self.exercise = self.make_exercise(self.day)
        self.client.login(username="client1", password="password123")

    def test_start_creates_a_session(self):
        response = self.client.post(reverse("session-start", args=[self.day.pk]))
        session = WorkoutSession.objects.get()
        self.assertRedirects(response, reverse("workout-session", args=[session.pk]))

    def test_start_reuses_an_open_session(self):
        """Reopening the page mid-workout must not start a second session."""
        self.client.post(reverse("session-start", args=[self.day.pk]))
        self.client.post(reverse("session-start", args=[self.day.pk]))
        self.assertEqual(WorkoutSession.objects.count(), 1)

    def test_cannot_start_another_clients_day(self):
        other = User.objects.create_user(
            username="other", password="password123", role=User.Role.CLIENT
        )
        self.client.force_login(other)
        response = self.client.post(reverse("session-start", args=[self.day.pk]))
        self.assertEqual(response.status_code, 404)

    def test_session_page_shows_last_time(self):
        old = timezone.now() - timedelta(days=4)
        self.log_session(self.exercise, [(80, 8)], started_at=old)
        current = WorkoutSession.objects.create(
            client=self.client_user, plan=self.plan, day=self.day
        )

        response = self.client.get(reverse("workout-session", args=[current.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "80kg")

    def test_complete_marks_the_session_done(self):
        session = WorkoutSession.objects.create(
            client=self.client_user, plan=self.plan, day=self.day
        )
        response = self.client.post(
            reverse("session-complete", args=[session.pk]),
            {"perceived_effort": "8", "notes": "Felt strong"},
        )
        self.assertRedirects(response, reverse("workout-history"))
        session.refresh_from_db()
        self.assertIsNotNone(session.completed_at)
        self.assertEqual(session.perceived_effort, 8)

    def test_delete_set_removes_it(self):
        session = WorkoutSession.objects.create(
            client=self.client_user, plan=self.plan, day=self.day
        )
        set_log = SetLog.objects.create(
            session=session, exercise=self.exercise, weight_kg=Decimal("80"), reps=8
        )
        response = self.client.post(reverse("delete-set", args=[set_log.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(SetLog.objects.exists())


class AdminAccessTests(WorkoutFixtureMixin, TestCase):
    """Every new trainer-only view must reject clients."""

    def test_client_cannot_reach_trainer_views(self):
        self.client.login(username="client1", password="password123")
        for name in (
            "plan-template-list",
            "plan-template-add",
            "exercise-catalog",
            "exercise-catalog-add",
            "workout-plan-add",
        ):
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertIn(response.status_code, (302, 403))

    def test_coach_can_reach_trainer_views(self):
        self.client.login(username="coach", password="password123")
        for name in ("plan-template-list", "exercise-catalog"):
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_clone_requires_admin(self):
        template = self.make_plan(is_template=True, title="T")
        self.client.login(username="client1", password="password123")
        response = self.client.post(
            reverse("plan-template-clone", args=[template.pk]),
            {"client": self.client_user.pk},
        )
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(WorkoutPlan.objects.filter(is_template=False).exists())

    def test_coach_can_clone_via_the_view(self):
        template = self.make_plan(is_template=True, title="PPL")
        WorkoutDay.objects.create(plan=template, day_name="Push")
        self.client.login(username="coach", password="password123")

        response = self.client.post(
            reverse("plan-template-clone", args=[template.pk]),
            {"client": self.client_user.pk},
        )

        self.assertRedirects(
            response, reverse("client-detail", args=[self.client_user.pk])
        )
        self.assertTrue(
            WorkoutPlan.objects.filter(
                client=self.client_user, is_template=False
            ).exists()
        )


class ExerciseModelTests(WorkoutFixtureMixin, TestCase):
    def test_rep_range_display(self):
        plan = self.make_plan(client=self.client_user)
        day = WorkoutDay.objects.create(plan=plan, day_name="Push")

        ranged = self.make_exercise(day, reps=6, reps_max=8)
        fixed = self.make_exercise(day, reps=5)

        self.assertEqual(ranged.rep_range_display, "6-8")
        self.assertEqual(ranged.rep_range_top, 8)
        self.assertEqual(fixed.rep_range_display, "5")
        self.assertEqual(fixed.rep_range_top, 5)

    def test_name_falls_back_to_catalog(self):
        plan = self.make_plan(client=self.client_user)
        day = WorkoutDay.objects.create(plan=plan, day_name="Push")
        exercise = Exercise.objects.create(
            day=day, catalog_exercise=self.bench, name="", sets=3, reps=8
        )
        self.assertEqual(exercise.name, self.bench.name)

    def test_catalog_slug_autogenerated(self):
        item = ExerciseCatalog.objects.create(
            name="Romanian Deadlift Variant", muscle_group="HAMSTRINGS"
        )
        self.assertEqual(item.slug, "romanian-deadlift-variant")


class SeedDataTests(TestCase):
    def test_exercise_library_is_seeded(self):
        """The seed migration must actually populate the library."""
        self.assertGreaterEqual(ExerciseCatalog.objects.count(), 40)
        self.assertTrue(
            ExerciseCatalog.objects.filter(name="Barbell Bench Press").exists()
        )
