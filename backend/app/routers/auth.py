from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..services import strava
from ..models import Credential
from ..config import settings
from sqlalchemy import select

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/strava")
async def strava_auth():
    if not settings.strava_client_id:
        raise HTTPException(400, "Strava client ID not configured")
    return RedirectResponse(strava.get_auth_url())


@router.get("/strava/callback")
async def strava_callback(code: str, db: AsyncSession = Depends(get_db)):
    try:
        await strava.exchange_token(code, db)
        return RedirectResponse("/settings?strava=connected")
    except Exception as e:
        raise HTTPException(400, f"Failed to connect Strava: {e}")


@router.get("/strava/status")
async def strava_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Credential).where(Credential.provider == "strava"))
    cred = result.scalar_one_or_none()
    return {"connected": cred is not None, "athlete_id": cred.athlete_id if cred else None}


@router.post("/intervals")
async def save_intervals_credentials(api_key: str, athlete_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Credential).where(Credential.provider == "intervals"))
    cred = result.scalar_one_or_none()
    if cred:
        cred.api_key = api_key
        cred.athlete_id = athlete_id
    else:
        cred = Credential(provider="intervals", api_key=api_key, athlete_id=athlete_id)
        db.add(cred)
    await db.commit()
    return {"connected": True}


@router.get("/intervals/status")
async def intervals_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Credential).where(Credential.provider == "intervals"))
    cred = result.scalar_one_or_none()
    has_env = bool(settings.intervals_api_key and settings.intervals_athlete_id)
    return {
        "connected": cred is not None or has_env,
        "athlete_id": (cred.athlete_id if cred else None) or settings.intervals_athlete_id or None,
    }
