import httpx
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Credential, Activity
from ..config import settings
import logging

log = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API = "https://www.strava.com/api/v3"

SPORT_MAP = {
    "Run": "running",
    "Ride": "cycling",
    "Swim": "swimming",
    "WeightTraining": "strength",
    "Workout": "strength",
    "Hike": "hiking",
    "Walk": "walking",
    "NordicSki": "xcski",
    "CrossCountrySkiing": "xcski",
    "VirtualRide": "cycling",
    "VirtualRun": "running",
    "TrailRun": "running",
    "GravelRide": "cycling",
    "MountainBikeRide": "cycling",
    "Rowing": "rowing",
    "Yoga": "yoga",
}


def get_auth_url() -> str:
    return (
        f"{STRAVA_AUTH_URL}?client_id={settings.strava_client_id}"
        f"&response_type=code&redirect_uri={settings.strava_redirect_uri}"
        f"&scope=read,activity:read_all"
    )


async def exchange_token(code: str, db: AsyncSession) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(STRAVA_TOKEN_URL, data={
            "client_id": settings.strava_client_id,
            "client_secret": settings.strava_client_secret,
            "code": code,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        data = resp.json()

    cred = await db.execute(select(Credential).where(Credential.provider == "strava"))
    cred = cred.scalar_one_or_none()
    if cred:
        cred.access_token = data["access_token"]
        cred.refresh_token = data["refresh_token"]
        cred.expires_at = data["expires_at"]
        cred.athlete_id = str(data["athlete"]["id"])
    else:
        cred = Credential(
            provider="strava",
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=data["expires_at"],
            athlete_id=str(data["athlete"]["id"]),
        )
        db.add(cred)
    await db.commit()
    return data


async def _ensure_token(db: AsyncSession) -> str | None:
    result = await db.execute(select(Credential).where(Credential.provider == "strava"))
    cred = result.scalar_one_or_none()
    if not cred:
        return None

    if cred.expires_at and cred.expires_at < datetime.utcnow().timestamp():
        async with httpx.AsyncClient() as client:
            resp = await client.post(STRAVA_TOKEN_URL, data={
                "client_id": settings.strava_client_id,
                "client_secret": settings.strava_client_secret,
                "refresh_token": cred.refresh_token,
                "grant_type": "refresh_token",
            })
            if resp.status_code != 200:
                log.error(f"Strava token refresh failed: {resp.text}")
                return None
            data = resp.json()
            cred.access_token = data["access_token"]
            cred.refresh_token = data["refresh_token"]
            cred.expires_at = data["expires_at"]
            await db.commit()

    return cred.access_token


async def fetch_activities(db: AsyncSession, days: int = 90) -> list[dict]:
    token = await _ensure_token(db)
    if not token:
        return []

    after = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    all_activities = []
    page = 1

    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"{STRAVA_API}/athlete/activities",
                headers={"Authorization": f"Bearer {token}"},
                params={"after": after, "per_page": 100, "page": page},
            )
            if resp.status_code != 200:
                log.error(f"Strava activities fetch failed: {resp.text}")
                break
            batch = resp.json()
            if not batch:
                break
            all_activities.extend(batch)
            page += 1

    return all_activities


async def fetch_activity_streams(db: AsyncSession, activity_id: int) -> dict | None:
    token = await _ensure_token(db)
    if not token:
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_API}/activities/{activity_id}/streams",
            headers={"Authorization": f"Bearer {token}"},
            params={"keys": "time,heartrate,watts,cadence,altitude,velocity_smooth,latlng"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()

    streams = {}
    for stream in data:
        key_map = {
            "time": "time",
            "heartrate": "hr",
            "watts": "power",
            "cadence": "cadence",
            "altitude": "altitude",
            "velocity_smooth": "speed",
            "latlng": "latlng",
        }
        if stream["type"] in key_map:
            streams[key_map[stream["type"]]] = stream["data"]
    return streams


def parse_strava_activity(raw: dict) -> dict:
    sport = SPORT_MAP.get(raw.get("type", ""), raw.get("type", "other").lower())
    start = datetime.fromisoformat(raw["start_date"].replace("Z", "+00:00"))

    pace = None
    if raw.get("average_speed") and sport == "running" and raw["average_speed"] > 0:
        pace = (1000 / raw["average_speed"]) / 60  # min/km

    return {
        "strava_id": str(raw["id"]),
        "sport_type": sport,
        "name": raw.get("name", ""),
        "description": raw.get("description"),
        "start_time": start,
        "elapsed_time": raw.get("elapsed_time"),
        "moving_time": raw.get("moving_time"),
        "distance": raw.get("distance"),
        "elevation_gain": raw.get("total_elevation_gain"),
        "calories": raw.get("calories"),
        "avg_hr": raw.get("average_heartrate"),
        "max_hr": raw.get("max_heartrate"),
        "avg_power": raw.get("average_watts"),
        "max_power": raw.get("max_watts"),
        "avg_cadence": raw.get("average_cadence"),
        "avg_speed": raw.get("average_speed"),
        "avg_pace": pace,
        "tss": raw.get("suffer_score"),
        "map_polyline": raw.get("map", {}).get("summary_polyline"),
        "source": "strava",
    }
