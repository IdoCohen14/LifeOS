"""User-selected calendar occupancy limits, not inferred study effort."""

from datetime import timedelta


def scheduled_minutes(spans, day, zone, check=lambda: None):
    from .assistant import day_boundary

    left = day_boundary(day.isoformat(), zone)
    right = day_boundary((day + timedelta(days=1)).isoformat(), zone)
    clipped = []
    for begin, end in spans:
        check()
        if begin < right and end > left:
            clipped.append((max(begin, left), min(end, right)))
    merged = []
    for begin, end in sorted(clipped):
        check()
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((begin, end))
    return sum((end - begin).total_seconds() / 60 for begin, end in merged)
