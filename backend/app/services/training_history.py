"""What the athlete has actually been doing, as opposed to what they typed.

The onboarding form asks how many hours someone trains. Synced activities know.
Starting a block from observed volume rather than a slider is the difference
between a plan that meets the athlete where they are and one that assumes a
fitness they may not have.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Activity

# Weeks of history to average. Long enough to smooth a missed week, short
# enough to still reflect a recent change in routine.
LOOKBACK_WEEKS = 4

# Below this, the athlete is not training consistently enough for the average
# to mean anything and we should not build a ramp on it.
MIN_SESSIONS_FOR_SIGNAL = 6


async def recent_training_volume(db: AsyncSession,
                                 weeks: int = LOOKBACK_WEEKS) -> dict | None:
    """Average weekly training hours over the recent past.

    Returns None when there is too little history to draw a conclusion from —
    a caller should fall back to whatever the athlete told us rather than
    ramping from a number built out of three rides.
    """
    cutoff = datetime.utcnow() - timedelta(weeks=weeks)
    result = await db.execute(
        select(Activity).where(Activity.start_time >= cutoff)
    )
    activities = result.scalars().all()

    if len(activities) < MIN_SESSIONS_FOR_SIGNAL:
        return None

    total_seconds = 0
    by_sport: dict[str, int] = {}
    sessions_by_sport: dict[str, int] = {}
    for activity in activities:
        seconds = activity.moving_time or activity.elapsed_time or 0
        if not seconds:
            continue
        total_seconds += seconds
        sport = activity.sport_type or "other"
        by_sport[sport] = by_sport.get(sport, 0) + seconds
        sessions_by_sport[sport] = sessions_by_sport.get(sport, 0) + 1

    if not total_seconds:
        return None

    # Only count weeks that actually have training in them, so a fortnight off
    # does not halve the athlete's apparent volume.
    active_weeks = len({
        a.start_time.isocalendar()[:2] for a in activities if a.start_time
    }) or 1

    return {
        "weekly_hours": round(total_seconds / 3600 / active_weeks, 1),
        "weeks_observed": active_weeks,
        "sessions": len(activities),
        "sessions_per_week": round(len(activities) / active_weeks, 1),
        "hours_by_sport": {
            sport: round(secs / 3600 / active_weeks, 1)
            for sport, secs in sorted(by_sport.items(), key=lambda kv: -kv[1])
        },
        "sessions_per_week_by_sport": {
            sport: round(count / active_weeks, 1)
            for sport, count in sessions_by_sport.items()
        },
    }
