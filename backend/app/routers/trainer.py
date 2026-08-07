from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import Activity
from ..schemas import TrainerRideData
from ..services.fit_export import generate_fit
from datetime import datetime

router = APIRouter(prefix="/api/trainer", tags=["trainer"])


@router.post("/save")
async def save_trainer_ride(data: TrainerRideData, db: AsyncSession = Depends(get_db)):
    """Save a completed trainer ride as an activity and return a FIT file."""
    now = datetime.utcnow()
    avg_p = data.avg_power or (sum(data.power_data) // len(data.power_data) if data.power_data else 0)
    max_p = max(data.power_data) if data.power_data else 0

    activity = Activity(
        sport_type="cycling",
        name="Indoor Ride",
        start_time=now,
        elapsed_time=data.duration_seconds,
        moving_time=data.duration_seconds,
        avg_power=avg_p,
        max_power=max_p,
        normalized_power=data.normalized_power,
        avg_hr=sum(data.hr_data) / len(data.hr_data) if data.hr_data else None,
        max_hr=max(data.hr_data) if data.hr_data else None,
        avg_cadence=sum(data.cadence_data) / len(data.cadence_data) if data.cadence_data else None,
        streams={
            "time": list(range(len(data.power_data))),
            "power": data.power_data,
            "hr": data.hr_data or [],
            "cadence": data.cadence_data or [],
        },
        source="trainer",
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    return {"activity_id": activity.id, "avg_power": avg_p, "max_power": max_p}


@router.post("/fit")
async def export_fit_file(data: TrainerRideData):
    """Generate a .fit file from trainer ride data for upload to Strava/Coros."""
    now = datetime.utcnow()
    fit_bytes = generate_fit(
        start_time=now,
        duration_seconds=data.duration_seconds,
        power_data=data.power_data,
        hr_data=data.hr_data or None,
        cadence_data=data.cadence_data or None,
        avg_power=data.avg_power,
        normalized_power=data.normalized_power,
        ftp=data.ftp,
    )
    filename = f"pulse_ride_{now.strftime('%Y%m%d_%H%M')}.fit"
    return Response(
        content=fit_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
