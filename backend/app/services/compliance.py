"""Comparing the plan against what the athlete actually did.

A plan that never looks back is a document, not a coach. Every week of synced
activity is evidence about whether the block is pitched right, and the weeks
still ahead are the only ones that can act on it.

Nothing here calls a model: matching is by date and sport, and the adjustment
is arithmetic. Rewriting a block costs minutes and real money, so adapting one
should not.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Activity
from .plan_builder import (
    IF_TABLE,
    MIN_SESSION_DURATION,
    SPORT_PROPERTIES,
    _estimate_distance,
    _round_duration,
    compute_tss,
)

# A session counts as done if the athlete got most of the way through it.
# Requiring the full duration punishes a session cut ten minutes short.
COMPLETED_FRACTION = 0.70

# How many finished weeks to judge on. One bad week is a bad week; three is
# a signal about the plan.
LOOKBACK_WEEKS = 3

# Only act once there is enough evidence.
MIN_WEEKS_FOR_SIGNAL = 2

# Bounds on a single adjustment, so one holiday cannot gut a block and one
# strong fortnight cannot inflate it.
MIN_VOLUME_FACTOR = 0.70
MAX_VOLUME_FACTOR = 1.15

UNDER_COMPLETING = 0.80
OVER_COMPLETING = 1.10

# A discipline this consistently skipped is one the athlete is not doing.
SPORT_DROP_RATIO = 0.55


def _planned_sessions(week: dict) -> list[dict]:
    return [
        {
            "date": day["date"], "sport": w["sport"],
            "minutes": w.get("duration_minutes", 0), "name": w.get("name", ""),
            # An AM/PM Norwegian double-threshold pair is one logical session
            # for adherence purposes — counting the PM shakeout as its own
            # planned session would make skipping an easy jog look like the
            # discipline is being dropped, when the (harder) AM session still
            # happened. Its minutes still count toward the week's volume.
            "countable": w.get("norwegian") != "shakeout_pm",
        }
        for day in week.get("days", [])
        if day.get("date")
        for w in day.get("workouts", [])
        if w.get("workout_type") != "rest"
    ]


async def _activities_between(db: AsyncSession, start: str, end: str) -> list[Activity]:
    first = datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)
    result = await db.execute(
        select(Activity).where(
            Activity.start_time >= first, Activity.start_time < last
        )
    )
    return list(result.scalars().all())


def _match(planned: list[dict], activities: list[Activity]) -> dict:
    """Pair planned sessions with what was actually recorded.

    Matching is per day and sport, and deliberately forgiving: an athlete who
    moves Tuesday's ride to Wednesday did the training. Only sessions with no
    activity of that sport anywhere in the week count as missed.
    """
    done_minutes: dict[str, float] = {}
    done_count: dict[str, int] = {}
    for activity in activities:
        sport = activity.sport_type or "other"
        seconds = activity.moving_time or activity.elapsed_time or 0
        done_minutes[sport] = done_minutes.get(sport, 0) + seconds / 60
        done_count[sport] = done_count.get(sport, 0) + 1

    planned_minutes: dict[str, float] = {}
    planned_count: dict[str, int] = {}
    for session in planned:
        sport = session["sport"]
        planned_minutes[sport] = planned_minutes.get(sport, 0) + session["minutes"]
        if session.get("countable", True):
            planned_count[sport] = planned_count.get(sport, 0) + 1

    sports = set(planned_minutes) | set(done_minutes)
    by_sport = {
        sport: {
            "planned_minutes": round(planned_minutes.get(sport, 0)),
            "completed_minutes": round(done_minutes.get(sport, 0)),
            "planned_sessions": planned_count.get(sport, 0),
            "completed_sessions": done_count.get(sport, 0),
        }
        for sport in sorted(sports)
    }

    total_planned = sum(planned_minutes.values())
    total_done = sum(done_minutes.values())
    return {
        "by_sport": by_sport,
        "planned_minutes": round(total_planned),
        "completed_minutes": round(total_done),
        "planned_hours": round(total_planned / 60, 1),
        "completed_hours": round(total_done / 60, 1),
        "ratio": round(total_done / total_planned, 2) if total_planned else None,
        "planned_sessions": sum(planned_count.values()),
        "completed_sessions": sum(done_count.values()),
    }


async def plan_compliance(db: AsyncSession, plan_data: dict,
                          today: datetime | None = None) -> dict:
    """Week-by-week planned versus completed, for the weeks that have finished."""
    now = today or datetime.utcnow()
    weeks = plan_data.get("weeks") or []
    report = []

    for week in weeks:
        planned = _planned_sessions(week)
        if not planned:
            continue
        dates = sorted(s["date"] for s in planned)
        start, end = dates[0], dates[-1]

        # A week still in progress cannot be judged on.
        if datetime.strptime(end, "%Y-%m-%d") >= now:
            continue

        summary = _match(planned, await _activities_between(db, start, end))
        summary.update({
            "week_number": week.get("week_number"),
            "week_type": week.get("week_type"),
            "start": start, "end": end,
        })
        report.append(summary)

    recent = report[-LOOKBACK_WEEKS:]
    ratios = [w["ratio"] for w in recent if w["ratio"] is not None]

    return {
        "weeks": report,
        "weeks_assessed": len(recent),
        # The median, matching what the recommendation reasons about — a
        # headline figure that disagrees with the advice under it is worse
        # than no headline at all.
        "typical_ratio": round(_median(ratios), 2) if ratios else None,
        "recommendation": _recommend(recent),
    }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _recommend(recent: list[dict]) -> dict:
    """Turn recent compliance into a concrete change, or explain why not.

    Judged on the median rather than the mean: one week lost to illness or
    travel should not rescale a whole block, and the mean cannot tell that
    week apart from a plan that is genuinely too hard.
    """
    ratios = [w["ratio"] for w in recent if w["ratio"] is not None]
    if len(ratios) < MIN_WEEKS_FOR_SIGNAL:
        return {
            "action": "none",
            "volume_factor": 1.0,
            "drop_sports": [],
            "reason": (
                f"Only {len(ratios)} finished week(s) of data — not enough to "
                "judge the plan on yet."
            ),
        }

    average = _median(ratios)
    drop_sports = _consistently_skipped(recent)

    if average < UNDER_COMPLETING:
        factor = max(MIN_VOLUME_FACTOR, round(average, 2))
        reason = (
            f"You have completed {average:.0%} of the planned load over "
            f"{len(ratios)} weeks. The remaining weeks scale to {factor:.0%} so "
            "the plan matches the training you are actually doing."
        )
        if drop_sports:
            reason += (
                " " + ", ".join(s.title() for s in drop_sports)
                + " is being skipped often enough to drop a session a week."
            )
        return {"action": "reduce", "volume_factor": factor,
                "drop_sports": drop_sports, "reason": reason}

    if average > OVER_COMPLETING:
        factor = min(MAX_VOLUME_FACTOR, round(average, 2))
        return {
            "action": "increase", "volume_factor": factor, "drop_sports": [],
            "reason": (
                f"You have been training {average:.0%} of what was planned over "
                f"{len(ratios)} weeks. The remaining weeks scale to {factor:.0%}."
            ),
        }

    if drop_sports:
        return {
            "action": "rebalance", "volume_factor": 1.0, "drop_sports": drop_sports,
            "reason": (
                "Overall volume is on track, but "
                + ", ".join(s.title() for s in drop_sports)
                + " is being skipped consistently — dropping a session a week "
                "and keeping the hours in the disciplines you are doing."
            ),
        }

    return {
        "action": "none", "volume_factor": 1.0, "drop_sports": [],
        "reason": (
            f"You are completing {average:.0%} of the plan — it is pitched about "
            "right, so nothing needs to change."
        ),
    }


def _consistently_skipped(recent: list[dict]) -> list[str]:
    skipped = []
    for sport in {s for w in recent for s in w["by_sport"]}:
        planned = sum(w["by_sport"].get(sport, {}).get("planned_sessions", 0) for w in recent)
        done = sum(w["by_sport"].get(sport, {}).get("completed_sessions", 0) for w in recent)
        if planned >= 2 * len(recent) and done / max(planned, 1) < SPORT_DROP_RATIO:
            skipped.append(sport)
    return sorted(skipped)


def adapt_remaining_weeks(plan_data: dict, recommendation: dict,
                          today: datetime | None = None,
                          threshold_pace: int = 300, css_pace: int = 105) -> dict:
    """Apply a recommendation to the weeks that have not started yet.

    Weeks already underway are left alone — rewriting a session the athlete
    may have already done today is worse than leaving it slightly wrong.
    """
    now = today or datetime.utcnow()
    factor = recommendation.get("volume_factor", 1.0)
    drop_sports = set(recommendation.get("drop_sports") or [])
    changed_weeks = 0

    for week in plan_data.get("weeks", []):
        dates = [d["date"] for d in week.get("days", []) if d.get("date")]
        if not dates or datetime.strptime(min(dates), "%Y-%m-%d") <= now:
            continue

        # Adaptation is relative to the original plan, not to the last
        # adaptation. Without this, pressing adapt twice scales the same weeks
        # twice and a 70% recommendation quietly becomes 49%.
        already = week.get("volume_factor_applied", 1.0)
        delta = factor / already if already else factor

        dropped = _drop_one_session_per_sport(week, drop_sports) if drop_sports else False
        if abs(delta - 1.0) > 0.01:
            _scale_week(week, delta, threshold_pace, css_pace)
            week["volume_factor_applied"] = round(factor, 3)
        elif not dropped:
            continue

        _recount_week(week)
        changed_weeks += 1

    # `weeks_changed` is the durable record of the adaptation that actually
    # took effect; `changed_now` is what this particular call did. A no-op
    # re-check must report zero without erasing the earlier record.
    if changed_weeks or "adaptation" not in plan_data:
        plan_data["adaptation"] = {
            "applied_at": now.isoformat(),
            "volume_factor": factor,
            "dropped_sports": sorted(drop_sports),
            "weeks_changed": changed_weeks,
            "reason": recommendation.get("reason", ""),
        }
    plan_data["adaptation"]["last_checked"] = now.isoformat()
    plan_data["adaptation"]["changed_now"] = changed_weeks
    return plan_data


def _drop_one_session_per_sport(week: dict, sports: set[str]) -> bool:
    """Remove the least important session of each skipped discipline.

    Returns whether anything was actually removed, so a repeated adaptation
    does not report a change it did not make.
    """
    removed = False
    already = set(week.get("sports_trimmed") or [])
    for sport in sports:
        if sport in already:
            continue
        candidates = [
            (day, workout)
            for day in week.get("days", [])
            for workout in day.get("workouts", [])
            if workout.get("sport") == sport
            and workout.get("archetype") not in ("quality", "long")
        ]
        if len(candidates) <= 1:
            continue  # never drop a discipline out of the week entirely
        day, workout = candidates[-1]
        day["workouts"].remove(workout)
        if not day["workouts"]:
            day["workouts"] = [_rest_placeholder()]
        already.add(sport)
        removed = True

    week["sports_trimmed"] = sorted(already)
    return removed


def _scale_week(week: dict, factor: float, threshold_pace: int, css_pace: int) -> None:
    for day in week.get("days", []):
        for workout in day.get("workouts", []):
            if workout.get("workout_type") in ("rest", "strength"):
                continue

            sport = workout.get("sport", "cycling")
            props = SPORT_PROPERTIES.get(sport, {})
            cap = props.get(
                "max_long_minutes" if workout.get("archetype") == "long"
                else "max_easy_minutes", 120)

            scaled = _round_duration(workout.get("duration_minutes", 0) * factor)
            workout["duration_minutes"] = max(MIN_SESSION_DURATION, min(scaled, cap))

            _rescale_steps(workout, factor)

            workout_type = workout.get("workout_type", "endurance")
            if_val = IF_TABLE.get(workout_type, 0.65)
            workout["tss_estimate"] = round(
                compute_tss(workout["duration_minutes"], if_val))
            workout["distance_km"] = _estimate_distance(
                sport, workout_type, workout["duration_minutes"],
                threshold_pace, css_pace)


def _rescale_steps(workout: dict, factor: float) -> None:
    """Keep the steps consistent with the new duration.

    Only the steady and interval work scales — warmups and cooldowns are
    already short, and rep counts belong to the exercise, not the budget.
    """
    for step in workout.get("steps") or []:
        if not isinstance(step, dict) or step.get("reps"):
            continue
        if step.get("type") in ("warmup", "cooldown", "rest"):
            continue
        if step.get("duration"):
            step["duration"] = max(30, int(step["duration"] * factor))
        if step.get("distance_m"):
            step["distance_m"] = max(25, int(round(step["distance_m"] * factor / 25) * 25))


def _recount_week(week: dict) -> None:
    minutes = tss = 0.0
    distance: dict[str, float] = {}
    for day in week.get("days", []):
        for workout in day.get("workouts", []):
            if workout.get("workout_type") == "rest":
                continue
            minutes += workout.get("duration_minutes", 0)
            tss += workout.get("tss_estimate", 0)
            if workout.get("distance_km"):
                distance[workout["sport"]] = (
                    distance.get(workout["sport"], 0) + workout["distance_km"])

    week["target_hours"] = round(minutes / 60, 1)
    week["target_tss"] = round(tss)
    if distance:
        week["distance_km"] = {s: round(d, 1) for s, d in distance.items()}


def _rest_placeholder() -> dict:
    return {
        "name": "Rest Day", "sport": "rest", "workout_type": "rest",
        "duration_minutes": 0, "description": "", "coach_notes": "",
        "target_zone": "Recovery", "tss_estimate": 0, "intensity_factor": 0,
        "priority": "optional", "distance_km": 0, "steps": [],
    }
