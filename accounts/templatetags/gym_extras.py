"""Template helpers shared across apps."""

from urllib.parse import quote

from django import template
from django.utils.translation import gettext as _

register = template.Library()

#: Egypt's country calling code, without the leading "+".
EGYPT_COUNTRY_CODE = "20"


def normalise_egyptian_phone(phone):
    """Convert a locally written Egyptian mobile into wa.me digits.

    wa.me needs a country code and digits only. Egyptians write their mobile as
    ``01012345678``, which has to become ``201012345678``.

    Handles ``+20…``, ``0020…``, ``20…``, ``010…`` and numbers containing spaces
    or dashes. Returns "" when there is nothing usable, so callers can hide the
    button rather than render a broken link.
    """
    if not phone:
        return ""

    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if not digits:
        return ""

    # 00 international prefix -> drop it.
    if digits.startswith("00"):
        digits = digits[2:]

    # Already country-coded, e.g. 201012345678.
    if digits.startswith(EGYPT_COUNTRY_CODE) and len(digits) >= 11:
        return digits

    # National trunk prefix, e.g. 01012345678 -> 201012345678.
    if digits.startswith("0"):
        return EGYPT_COUNTRY_CODE + digits[1:]

    # Bare mobile without the trunk zero, e.g. 1012345678.
    if digits.startswith("1") and len(digits) == 10:
        return EGYPT_COUNTRY_CODE + digits

    return digits


@register.simple_tag
def whatsapp_url(phone, text=""):
    """Build a wa.me deep link. Empty string when the phone is unusable."""
    number = normalise_egyptian_phone(phone)
    if not number:
        return ""
    if text:
        return f"https://wa.me/{number}?text={quote(str(text))}"
    return f"https://wa.me/{number}"


@register.simple_tag(takes_context=True)
def workout_plan_whatsapp_text(context, plan):
    """A plain-text plan summary short enough for a WhatsApp message."""
    lines = [f"*{plan.title}*"]
    for day in plan.days.all():
        lines.append(f"\n{day.day_name}:")
        for exercise in day.exercises.all():
            lines.append(
                f"- {exercise.name}: {exercise.sets} × {exercise.rep_range_display}"
            )
    request = context.get("request")
    if request is not None:
        lines.append("\n" + request.build_absolute_uri("/dashboard/home/"))
    return "\n".join(lines)


@register.simple_tag(takes_context=True)
def nutrition_plan_whatsapp_text(context, plan):
    """A plain-text nutrition summary for WhatsApp."""
    lines = [f"*{plan.title}*"]
    for meal in plan.meals.filter(alternative_of__isnull=True):
        lines.append(
            f"- {meal.name}: {meal.calories} kcal "
            f"(P{meal.protein} C{meal.carbs} F{meal.fats})"
        )
    totals = plan.daily_totals()
    lines.append(
        _("Daily total: %(calories)s kcal, protein %(protein)sg")
        % {"calories": totals["calories"], "protein": totals["protein"]}
    )
    request = context.get("request")
    if request is not None:
        lines.append("\n" + request.build_absolute_uri("/dashboard/home/"))
    return "\n".join(lines)


@register.filter
def rating_stars(value):
    """Render a 1-5 rating as filled/empty stars, or an em dash when unset."""
    if not value:
        return "—"
    value = int(value)
    return "★" * value + "☆" * (5 - value)


@register.filter
def trim_decimal(value):
    """80.00 -> "80", 82.50 -> "82.5". Keeps weights readable."""
    if value is None:
        return ""
    text = f"{value}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


#: Plate weight -> chip size bucket. Mirrors real plate diameters, so the strip
#: reads like a loaded bar rather than a list of numbers.
_PLATE_SIZES = {
    "25": "xl",
    "20": "xl",
    "15": "l",
    "10": "l",
    "5": "m",
    "2.5": "s",
    "1.25": "s",
}


@register.simple_tag
def plate_loading(weight_kg, equipment=""):
    """Per-side barbell loading for ``weight_kg``, ready for the template.

    Returns None unless this is a barbell lift with a loadable weight, so the
    strip stays hidden for dumbbells, machines and bodyweight work rather than
    showing nonsense.
    """
    if str(equipment).upper() != "BARBELL":
        return None

    from workouts.services import plate_breakdown

    breakdown = plate_breakdown(weight_kg)
    if not breakdown or not breakdown["plates"]:
        return None

    chips = []
    for plate in breakdown["plates"]:
        label = trim_decimal(plate)
        chips.append({"label": label, "size": _PLATE_SIZES.get(label, "m")})

    return {
        "bar_kg": trim_decimal(breakdown["bar_kg"]),
        "chips": chips,
        "remainder": trim_decimal(breakdown["remainder_kg"])
        if breakdown["remainder_kg"]
        else None,
    }
