"""Server-rendered chart geometry.

Returns plain dicts of pre-computed SVG coordinates so templates can draw a
polyline without a JavaScript charting library. Keeping this in Python means the
charts render identically in a print/PDF view, where JS never runs.
"""

VIEWBOX_WIDTH = 600
VIEWBOX_HEIGHT = 200
PADDING = 30


def build_line_chart(pairs, label="", width=VIEWBOX_WIDTH, height=VIEWBOX_HEIGHT):
    """Turn ``[(date, value), ...]`` into SVG-ready coordinates.

    Returns None for fewer than two usable points, since a single dot is not a
    trend and the template should say "not enough data" instead of drawing.
    """
    cleaned = [(d, float(v)) for d, v in pairs if v is not None]
    if len(cleaned) < 2:
        return None

    values = [v for _, v in cleaned]
    lowest, highest = min(values), max(values)
    value_range = highest - lowest

    # A flat series would divide by zero; centre it instead.
    if value_range == 0:
        lowest -= 1
        highest += 1
        value_range = highest - lowest

    plot_width = width - 2 * PADDING
    plot_height = height - 2 * PADDING
    step = plot_width / (len(cleaned) - 1)

    points = []
    for index, (date, value) in enumerate(cleaned):
        x = PADDING + index * step
        # SVG y grows downward, so invert the normalised value.
        y = PADDING + plot_height * (1 - (value - lowest) / value_range)
        points.append(
            {"x": round(x, 2), "y": round(y, 2), "date": date, "value": value}
        )

    return {
        "label": label,
        "points": points,
        "polyline": " ".join(f"{p['x']},{p['y']}" for p in points),
        "width": width,
        "height": height,
        "min_value": round(lowest, 2),
        "max_value": round(highest, 2),
        "first": points[0],
        "last": points[-1],
        "baseline_y": height - PADDING,
        "change": round(values[-1] - values[0], 2),
    }


def measurement_chart(measurements, field="weight_kg", label=""):
    """Line chart for one field across a client's measurement history."""
    pairs = [
        (m.date, getattr(m, field))
        for m in sorted(measurements, key=lambda m: m.date)
        if getattr(m, field) is not None
    ]
    return build_line_chart(pairs, label=label)
