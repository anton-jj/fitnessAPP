from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..database import get_db
from ..models import Activity, Credential
from ..services import sync_manager
from ..schemas import SyncStatus
from ..config import settings

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("")
async def trigger_sync(background_tasks: BackgroundTasks, days: int = 90):
    if sync_manager.is_syncing():
        return {"status": "already_syncing"}
    background_tasks.add_task(sync_manager.run_sync, days)
    return {"status": "started"}


@router.get("/status", response_model=SyncStatus)
async def sync_status(db: AsyncSession = Depends(get_db)):
    strava_result = await db.execute(
        select(Credential).where(Credential.provider == "strava")
    )
    intervals_result = await db.execute(
        select(Credential).where(Credential.provider == "intervals")
    )
    count_result = await db.execute(select(func.count(Activity.id)))

    return SyncStatus(
        strava_connected=strava_result.scalar_one_or_none() is not None,
        intervals_connected=(
            intervals_result.scalar_one_or_none() is not None
            or bool(settings.intervals_api_key)
        ),
        last_sync=sync_manager.last_sync_time(),
        activities_count=count_result.scalar() or 0,
        sync_in_progress=sync_manager.is_syncing(),
    )
