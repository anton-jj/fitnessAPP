from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database import get_db
from ..models import Activity, FitnessData, Wellness
from ..schemas import DashboardOut, ActivityOut, FitnessDataOut
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
async def get_dashboard(days: int = 90, db: AsyncSession = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(days=days)

    fitness_result = await db.execute(
        select(FitnessData)
        .where(FitnessData.date >= cutoff.strftime("%Y-%m-%d"))
        .order_by(FitnessData.date)
    )
    fitness_data = [
        FitnessDataOut.model_validate(f) for f in fitness_result.scalars().all()
    ]

    current_ctl = fitness_data[-1].ctl if fitness_data else None
    current_atl = fitness_data[-1].atl if fitness_data else None
    current_tsb = fitness_data[-1].tsb if fitness_data else None

    recent_result = await db.execute(
        select(Activity)
        .where(Activity.start_time >= cutoff)
        .order_by(Activity.start_time.desc())
        .limit(10)
    )
    recent_activities = [ActivityOut.model_validate(a) for a in recent_result.scalars().all()]

    week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_result = await db.execute(
        select(Activity).where(Activity.start_time >= week_start)
    )
    week_acts = week_result.scalars().all()

    weekly_hours = sum((a.moving_time or a.elapsed_time or 0) for a in week_acts) / 3600
    weekly_tss = sum(a.tss or 0 for a in week_acts)
    weekly_distance = sum(a.distance or 0 for a in week_acts) / 1000
    weekly_count = len(week_acts)

    by_sport: dict[str, dict] = {}
    for a in week_acts:
        sport = a.sport_type or "other"
        if sport not in by_sport:
            by_sport[sport] = {"hours": 0, "tss": 0, "distance_km": 0, "count": 0}
        by_sport[sport]["hours"] += (a.moving_time or a.elapsed_time or 0) / 3600
        by_sport[sport]["tss"] += a.tss or 0
        by_sport[sport]["distance_km"] += (a.distance or 0) / 1000
        by_sport[sport]["count"] += 1

    weekly_summary = {
        "hours": round(weekly_hours, 1),
        "tss": round(weekly_tss),
        "distance_km": round(weekly_distance, 1),
        "count": weekly_count,
        "by_sport": {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in by_sport.items()},
    }

    return DashboardOut(
        fitness_data=fitness_data,
        weekly_summary=weekly_summary,
        recent_activities=recent_activities,
        current_ctl=current_ctl,
        current_atl=current_atl,
        current_tsb=current_tsb,
    )


@router.get("/volume")
async def get_volume_data(weeks: int = 12, db: AsyncSession = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(weeks=weeks)
    result = await db.execute(
        select(Activity).where(Activity.start_time >= cutoff).order_by(Activity.start_time)
    )
    activities = result.scalars().all()

    weekly_data: dict[str, dict] = {}
    for a in activities:
        if not a.start_time:
            continue
        week_key = a.start_time.strftime("%Y-W%W")
        week_start = (a.start_time - timedelta(days=a.start_time.weekday())).strftime("%Y-%m-%d")
        if week_key not in weekly_data:
            weekly_data[week_key] = {"week": week_start, "sports": {}}
        sport = a.sport_type or "other"
        if sport not in weekly_data[week_key]["sports"]:
            weekly_data[week_key]["sports"][sport] = {"hours": 0, "tss": 0, "distance_km": 0}
        weekly_data[week_key]["sports"][sport]["hours"] += (a.moving_time or a.elapsed_time or 0) / 3600
        weekly_data[week_key]["sports"][sport]["tss"] += a.tss or 0
        weekly_data[week_key]["sports"][sport]["distance_km"] += (a.distance or 0) / 1000

    volume = []
    for key in sorted(weekly_data.keys()):
        entry = {"week": weekly_data[key]["week"]}
        for sport, data in weekly_data[key]["sports"].items():
            entry[f"{sport}_hours"] = round(data["hours"], 1)
            entry[f"{sport}_tss"] = round(data["tss"])
            entry[f"{sport}_km"] = round(data["distance_km"], 1)
        volume.append(entry)

    return volume
