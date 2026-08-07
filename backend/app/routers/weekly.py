from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import WeeklyGoal, Activity
from ..schemas import WeeklyGoal as WeeklyGoalSchema
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/weekly", tags=["weekly"])


def _current_iso_week() -> str:
    now = datetime.utcnow()
    return now.strftime("%G-W%V")


def _week_date_range(iso_week: str) -> tuple[datetime, datetime]:
    year, week = iso_week.split("-W")
    start = datetime.strptime(f"{year} {week} 1", "%G %V %u")
    end = start + timedelta(days=7)
    return start, end


@router.get("")
async def get_weekly_overview(week: str | None = None, db: AsyncSession = Depends(get_db)):
    w = week or _current_iso_week()
    start, end = _week_date_range(w)

    result = await db.execute(select(WeeklyGoal).where(WeeklyGoal.week == w))
    goal = result.scalar_one_or_none()

    act_result = await db.execute(
        select(Activity)
        .where(Activity.start_time >= start, Activity.start_time < end)
        .order_by(Activity.start_time)
    )
    activities = act_result.scalars().all()

    total_hours = sum((a.moving_time or a.elapsed_time or 0) for a in activities) / 3600
    total_tss = sum(a.tss or 0 for a in activities)

    by_sport: dict[str, dict] = {}
    for a in activities:
        sport = a.sport_type or "other"
        if sport not in by_sport:
            by_sport[sport] = {"hours": 0, "tss": 0, "count": 0, "distance_km": 0}
        by_sport[sport]["hours"] += (a.moving_time or a.elapsed_time or 0) / 3600
        by_sport[sport]["tss"] += a.tss or 0
        by_sport[sport]["count"] += 1
        by_sport[sport]["distance_km"] += (a.distance or 0) / 1000

    for v in by_sport.values():
        v["hours"] = round(v["hours"], 1)
        v["tss"] = round(v["tss"])
        v["distance_km"] = round(v["distance_km"], 1)

    return {
        "week": w,
        "week_start": start.strftime("%Y-%m-%d"),
        "week_end": (end - timedelta(days=1)).strftime("%Y-%m-%d"),
        "hours_target": goal.hours_target if goal else None,
        "hours_actual": round(total_hours, 1),
        "total_tss": round(total_tss),
        "quality_sessions": goal.quality_sessions if goal else [],
        "by_sport": by_sport,
        "activity_count": len(activities),
    }


@router.put("")
async def update_weekly_goal(data: WeeklyGoalSchema, db: AsyncSession = Depends(get_db)):
    w = data.week or _current_iso_week()
    result = await db.execute(select(WeeklyGoal).where(WeeklyGoal.week == w))
    goal = result.scalar_one_or_none()

    if goal:
        if data.hours_target is not None:
            goal.hours_target = data.hours_target
        goal.quality_sessions = data.quality_sessions
    else:
        goal = WeeklyGoal(
            week=w,
            hours_target=data.hours_target,
            quality_sessions=data.quality_sessions,
        )
        db.add(goal)

    await db.commit()
    return {"updated": True}
