from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ..database import get_db
from ..services import strava
from ..services import session_auth
from ..models import Credential
from ..config import settings
from sqlalchemy import select

router = APIRouter(prefix="/api/auth", tags=["auth"])


class PinLogin(BaseModel):
    pin: str


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/session")
async def session_status(request: Request):
    """Whether this browser is signed in, and whether it even needs to be."""
    if not session_auth.is_enabled():
        return {"required": False, "authenticated": True}
    token = request.cookies.get(session_auth.COOKIE_NAME)
    return {
        "required": True,
        "authenticated": session_auth.verify_token(token),
    }


@router.post("/login")
async def login(body: PinLogin, request: Request, response: Response):
    if not session_auth.is_enabled():
        return {"authenticated": True, "required": False}

    client = _client_id(request)
    wait = session_auth.seconds_until_unlocked(client)
    if wait:
        raise HTTPException(
            429, f"Too many attempts. Try again in {wait // 60 + 1} minute(s)."
        )

    if not session_auth.check_pin(body.pin, client):
        raise HTTPException(401, "Incorrect PIN")

    # Secure only over HTTPS — set unconditionally it would break a plain-HTTP
    # LAN or tailnet instance, where the cookie would be dropped silently.
    forwarded = request.headers.get("x-forwarded-proto", "")
    https = request.url.scheme == "https" or forwarded.startswith("https")
    response.set_cookie(
        session_auth.COOKIE_NAME,
        session_auth.issue_token(),
        max_age=session_auth.SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=https,
        path="/",
    )
    return {"authenticated": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(session_auth.COOKIE_NAME, path="/")
    return {"authenticated": False}


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
