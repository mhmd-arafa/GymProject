"""Deterministic training logic.

Everything here is rules-based and side-effect-light so it can be unit tested
without HTTP: no ML, no heuristics that change between runs.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Max
from django.utils import timezone

from .models import PersonalRecord, SetLog, WorkoutSession

#: Smallest plate jump that is realistic in a commercial gym.
WEIGHT_INCREMENT_KG = Decimal("2.5")

#: Consecutive sessions at the top of the rep range before we suggest more load.
SESSIONS_BEFORE_PROGRESSION = 2


def _working_sets(queryset):
    return queryset.filter(is_warmup=False)


def previous_session_sets(client, catalog_exercise, before_session=None):
    """Sets from the most recent *earlier* session containing this exercise.

    ``before_session`` excludes the session currently in progress, which is what
    makes this show "last time" rather than "just now".
    """
    if catalog_exercise is None:
        return SetLog.objects.none()

    sessions = (
        WorkoutSession.objects.filter(
            client=client, set_logs__catalog_exercise=catalog_exercise
        )
        .distinct()
        .order_by("-started_at")
    )
    if before_session is not None:
        sessions = sessions.exclude(pk=before_session.pk).filter(
            started_at__lte=before_session.started_at
        )

    last_session = sessions.first()
    if last_session is None:
        return SetLog.objects.none()

    return _working_sets(
        last_session.set_logs.filter(catalog_exercise=catalog_exercise)
    ).order_by("set_number")


def last_performance(client, catalog_exercise, before_session=None):
    """Human-readable summary of the previous session, e.g. "80kg x 8, 80kg x 7".

    Returns an empty string when there is no history, so templates can render it
    unconditionally.
    """
    sets = previous_session_sets(client, catalog_exercise, before_session)
    if not sets:
        return ""
    return ", ".join(f"{_trim(s.weight_kg)}kg × {s.reps}" for s in sets)


def _trim(value):
    """Render 80.00 as "80" and 82.50 as "82.5".

    ``normalize()`` alone is not enough: it turns Decimal("80.00") into 8E+1,
    which would show up in the UI as "8E+1kg". Re-quantising whole numbers back
    to an integer exponent keeps them in plain notation.
    """
    normalised = Decimal(value).normalize()
    if normalised == normalised.to_integral_value():
        normalised = normalised.quantize(Decimal(1))
    return str(normalised)


def detect_prs(set_log):
    """Create or update personal records beaten by ``set_log``.

    Returns the list of ``PersonalRecord`` rows that were newly set, so the view
    can show "new best on Bench Press". Warm-up sets never count.
    """
    if set_log.is_warmup or set_log.catalog_exercise is None or set_log.reps <= 0:
        return []

    client = set_log.session.client
    exercise = set_log.catalog_exercise
    achieved_on = timezone.localdate(set_log.completed_at)

    candidates = {
        PersonalRecord.RecordType.MAX_WEIGHT: Decimal(set_log.weight_kg),
        PersonalRecord.RecordType.MAX_REPS: Decimal(set_log.reps),
        PersonalRecord.RecordType.MAX_VOLUME: Decimal(set_log.volume_kg),
        PersonalRecord.RecordType.ESTIMATED_1RM: Decimal(
            str(set_log.estimated_1rm_kg or 0)
        ),
    }

    beaten = []
    for record_type, value in candidates.items():
        if value <= 0:
            continue
        existing = PersonalRecord.objects.filter(
            client=client, catalog_exercise=exercise, record_type=record_type
        ).first()

        # Strictly greater: matching your best is not a new record.
        if existing is None:
            beaten.append(
                PersonalRecord.objects.create(
                    client=client,
                    catalog_exercise=exercise,
                    record_type=record_type,
                    value=value,
                    set_log=set_log,
                    achieved_on=achieved_on,
                )
            )
        elif value > existing.value:
            existing.value = value
            existing.set_log = set_log
            existing.achieved_on = achieved_on
            existing.save(update_fields=["value", "set_log", "achieved_on"])
            beaten.append(existing)

    return beaten


def suggest_progression(client, exercise):
    """Suggest a load increase when the client has topped out the rep range.

    Rule: for the last ``SESSIONS_BEFORE_PROGRESSION`` sessions that included
    this exercise, every working set reached the top of the prescribed range.
    Then suggest the heaviest weight used plus one plate increment.

    Returns a dict with ``suggested_weight_kg`` and ``reason``, or None when no
    change is warranted. Purely deterministic -- the same history always gives
    the same answer.
    """
    catalog_exercise = exercise.catalog_exercise
    if catalog_exercise is None:
        return None

    target_reps = exercise.rep_range_top

    recent_sessions = list(
        WorkoutSession.objects.filter(
            client=client,
            completed_at__isnull=False,
            set_logs__catalog_exercise=catalog_exercise,
        )
        .distinct()
        .order_by("-started_at")[:SESSIONS_BEFORE_PROGRESSION]
    )

    if len(recent_sessions) < SESSIONS_BEFORE_PROGRESSION:
        return None

    heaviest = Decimal("0")
    for session in recent_sessions:
        sets = _working_sets(
            session.set_logs.filter(catalog_exercise=catalog_exercise)
        )
        if not sets.exists():
            return None
        if any(s.reps < target_reps for s in sets):
            return None
        session_max = sets.aggregate(top=Max("weight_kg"))["top"] or Decimal("0")
        heaviest = max(heaviest, Decimal(session_max))

    if heaviest <= 0:
        return None

    return {
        "exercise": exercise,
        "current_weight_kg": heaviest,
        "suggested_weight_kg": heaviest + WEIGHT_INCREMENT_KG,
        "increment_kg": WEIGHT_INCREMENT_KG,
        "sessions_at_top": SESSIONS_BEFORE_PROGRESSION,
        "target_reps": target_reps,
    }


def plan_progression_suggestions(client, plan):
    """All progression suggestions across a plan, for the trainer's dashboard."""
    suggestions = []
    for day in plan.days.all():
        for exercise in day.exercises.select_related("catalog_exercise"):
            suggestion = suggest_progression(client, exercise)
            if suggestion:
                suggestions.append(suggestion)
    return suggestions


def adherence(client, days=7, plan=None):
    """Completed sessions vs. sessions expected in the trailing window.

    "Expected" comes from the number of days in the client's active plan, scaled
    to the window. Returns a dict; ``percent`` is None when we cannot tell what
    was expected (no plan), so callers can hide the metric rather than show 0%.
    """
    since = timezone.now() - timedelta(days=days)
    completed = WorkoutSession.objects.filter(
        client=client, completed_at__isnull=False, started_at__gte=since
    ).count()

    if plan is None:
        plan = (
            client.workout_plans.filter(is_template=False)
            .order_by("-created_at")
            .first()
        )

    if plan is None:
        return {"completed": completed, "expected": None, "percent": None, "days": days}

    per_week = plan.days.count()
    expected = round(per_week * days / 7)
    percent = round(completed / expected * 100) if expected else None

    return {
        "completed": completed,
        "expected": expected,
        "percent": percent,
        "days": days,
    }


def exercise_history(client, catalog_exercise, limit=20):
    """Per-session totals for charting: heaviest set, volume, best estimated 1RM."""
    sessions = (
        WorkoutSession.objects.filter(
            client=client, set_logs__catalog_exercise=catalog_exercise
        )
        .distinct()
        .order_by("-started_at")[:limit]
    )

    points = []
    for session in reversed(list(sessions)):
        sets = list(
            _working_sets(session.set_logs.filter(catalog_exercise=catalog_exercise))
        )
        if not sets:
            continue
        estimates = [s.estimated_1rm_kg for s in sets if s.estimated_1rm_kg]
        points.append(
            {
                "date": timezone.localdate(session.started_at),
                "top_weight_kg": max(s.weight_kg for s in sets),
                "volume_kg": sum(s.volume_kg for s in sets),
                "best_1rm_kg": max(estimates) if estimates else None,
                "session": session,
            }
        )
    return points


def clients_without_recent_session(clients, days=10):
    """Clients with no logged session in the trailing window. Feeds the queue."""
    cutoff = timezone.now() - timedelta(days=days)
    active_ids = set(
        WorkoutSession.objects.filter(started_at__gte=cutoff)
        .values_list("client_id", flat=True)
        .distinct()
    )
    return [c for c in clients if c.pk not in active_ids]


#: Standard men's Olympic bar. Women's is 15kg; not modelled yet.
BAR_WEIGHT_KG = Decimal("20")

#: Plates a normal commercial gym actually stocks, heaviest first.
AVAILABLE_PLATES_KG = [
    Decimal("25"),
    Decimal("20"),
    Decimal("15"),
    Decimal("10"),
    Decimal("5"),
    Decimal("2.5"),
    Decimal("1.25"),
]


def plate_breakdown(total_kg, bar_kg=BAR_WEIGHT_KG):
    """How to load ``total_kg`` on a barbell, per side.

    Returns None when the weight is not loadable as a barbell (at or below the
    bar), so the UI can stay silent rather than show a misleading empty rack.
    Otherwise returns the per-side plates heaviest-first plus any remainder that
    the gym's plates cannot make up, e.g. asking for 61kg on a 20kg bar leaves
    0.5kg per side unaccounted for.

    Greedy works here because the plate set is canonical: every plate is a
    multiple of the smallest, so the largest-first choice is always optimal.
    """
    if total_kg is None:
        return None

    total = Decimal(str(total_kg))
    if total <= bar_kg:
        return None

    per_side = (total - bar_kg) / 2
    plates = []
    remaining = per_side

    for plate in AVAILABLE_PLATES_KG:
        while remaining >= plate:
            plates.append(plate)
            remaining -= plate

    return {
        "bar_kg": bar_kg,
        "total_kg": total,
        "per_side_kg": per_side,
        "plates": plates,
        "remainder_kg": remaining if remaining > 0 else None,
    }
