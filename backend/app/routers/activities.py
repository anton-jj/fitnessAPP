from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database import get_db
from ..models import Activity
from ..schemas import ActivityOut, ManualActivityCreate
from datetime import datetime, timedelta
import csv
import io
import json

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("", response_model=list[ActivityOut])
async def list_activities(
    sport: str | None = None,
    days: int = 90,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = select(Activity).where(Activity.start_time >= cutoff)
    if sport:
        query = query.where(Activity.sport_type == sport)
    query = query.order_by(Activity.start_time.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return [ActivityOut.model_validate(a) for a in result.scalars().all()]


@router.post("", response_model=ActivityOut)
async def log_manual_activity(data: ManualActivityCreate, db: AsyncSession = Depends(get_db)):
    start = data.start_time or datetime.utcnow()
    elapsed = data.duration_minutes * 60
    distance = (data.distance_km or 0) * 1000

    activity = Activity(
        sport_type=data.sport_type,
        name=data.name or f"{data.sport_type.title()} session",
        description=data.notes,
        start_time=start,
        elapsed_time=elapsed,
        moving_time=elapsed,
        distance=distance if distance > 0 else None,
        source="manual",
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return ActivityOut.model_validate(activity)


@router.get("/sports")
async def list_sports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Activity.sport_type, func.count(Activity.id))
        .group_by(Activity.sport_type)
        .order_by(func.count(Activity.id).desc())
    )
    return [{"sport": r[0], "count": r[1]} for r in result.all() if r[0]]


@router.get("/calendar")
async def calendar_data(
    year: int | None = None,
    month: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    y = year or now.year
    m = month or now.month
    start = datetime(y, m, 1)
    if m == 12:
        end = datetime(y + 1, 1, 1)
    else:
        end = datetime(y, m + 1, 1)

    result = await db.execute(
        select(Activity)
        .where(Activity.start_time >= start, Activity.start_time < end)
        .order_by(Activity.start_time)
    )
    activities = result.scalars().all()

    by_day: dict[str, list] = {}
    for a in activities:
        day = a.start_time.strftime("%Y-%m-%d")
        by_day.setdefault(day, []).append(ActivityOut.model_validate(a).model_dump())

    return by_day


@router.get("/export/{fmt}")
async def export_activities(
    fmt: str,
    days: int = 365,
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Activity).where(Activity.start_time >= cutoff).order_by(Activity.start_time.desc())
    )
    activities = result.scalars().all()

    fields = [
        "id", "sport_type", "name", "start_time", "elapsed_time", "moving_time",
        "distance", "elevation_gain", "calories", "avg_hr", "max_hr",
        "avg_power", "max_power", "normalized_power", "avg_cadence",
        "avg_pace", "avg_speed", "tss", "intensity_factor", "source",
    ]

    if fmt == "json":
        data = []
        for a in activities:
            row = {}
            for f in fields:
                val = getattr(a, f)
                if isinstance(val, datetime):
                    val = val.isoformat()
                row[f] = val
            data.append(row)
        content = json.dumps(data, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=pulse_activities.json"},
        )

    elif fmt == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for a in activities:
            row = {}
            for f in fields:
                val = getattr(a, f)
                if isinstance(val, datetime):
                    val = val.isoformat()
                row[f] = val
            writer.writerow(row)
        content = output.getvalue()
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=pulse_activities.csv"},
        )

    raise HTTPException(400, "Format must be 'csv' or 'json'")


@router.get("/{activity_id}", response_model=ActivityOut)
async def get_activity(activity_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Activity).where(Activity.id == activity_id))
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(404, "Activity not found")
    return ActivityOut.model_validate(activity)
