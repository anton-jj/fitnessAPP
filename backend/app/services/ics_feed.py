"""iCalendar feed for the training plan.

Subscribing to a plan from a normal calendar app is the one sharing feature
every training platform has, and it costs nothing to support: any calendar
client can poll a URL, so the plan shows up next to the rest of the athlete's
week without another app or another login.
"""
from datetime import datetime, timedelta, timezone

PRODID = "-//Pulse//Training Plan//EN"


def _escape(text: str) -> str:
    """Escape per RFC 5545: backslash, semicolon, comma, newline."""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 caps lines at 75 octets; continuations start with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    chunks, start = [], 0
    while start < len(raw):
        end = min(start + (75 if not chunks else 74), len(raw))
        # Never split inside a multi-byte character: back up off any
        # continuation byte (10xxxxxx) so each chunk decodes on its own.
        while end < len(raw) and (raw[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(raw[start:end].decode("utf-8"))
        start = end
    return "\r\n ".join(chunks)


def _describe(workout: dict) -> str:
    parts = []
    if workout.get("description"):
        parts.append(workout["description"])
    if workout.get("target_zone"):
        parts.append(f"Target: {workout['target_zone']}")

    for step in workout.get("steps") or []:
        if not isinstance(step, dict):
            continue
        minutes = round((step.get("duration") or 0) / 60)
        repeat = step.get("repeat") or 1
        label = step.get("notes") or step.get("type", "")
        parts.append(f"{repeat}x {minutes}min — {label}" if repeat > 1
                     else f"{minutes}min — {label}")

    if workout.get("coach_notes"):
        parts.append(f"Coach: {workout['coach_notes']}")
    if workout.get("tss_estimate"):
        parts.append(f"~{round(workout['tss_estimate'])} TSS")
    return "\n".join(parts)


def plan_to_ics(plan_data: dict, plan_name: str = "Training Plan") -> str:
    """Render a stored plan as an iCalendar document."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(plan_name)}",
        # Hint to clients that this feed changes; most poll far less often.
        "X-PUBLISHED-TTL:PT1H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
    ]

    weeks = plan_data.get("weeks") or ([plan_data] if plan_data.get("days") else [])
    for week in weeks:
        for day in week.get("days", []):
            date = day.get("date")
            if not date:
                continue
            try:
                start = datetime.strptime(date, "%Y-%m-%d")
            except (ValueError, TypeError):
                continue

            for index, workout in enumerate(day.get("workouts", [])):
                if workout.get("workout_type") == "rest":
                    continue
                duration = int(workout.get("duration_minutes") or 60)
                # All-day-ish block starting at 06:00 local; a planned session
                # has no real clock time, but a timed event sorts better than
                # an all-day one in most calendar apps.
                begin = start.replace(hour=6) + timedelta(minutes=index * duration)
                end = begin + timedelta(minutes=duration)
                uid = f"pulse-{date}-{index}-{workout.get('sport', 'session')}"

                lines += [
                    "BEGIN:VEVENT",
                    f"UID:{uid}@pulse",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART:{begin.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
                    _fold(f"SUMMARY:{_escape(workout.get('name', 'Training'))}"),
                    _fold(f"DESCRIPTION:{_escape(_describe(workout))}"),
                    f"CATEGORIES:{_escape(workout.get('sport', 'training').title())}",
                    "END:VEVENT",
                ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
