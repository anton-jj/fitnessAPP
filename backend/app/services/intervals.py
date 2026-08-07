import httpx
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Credential
from ..config import settings
import logging
import base64

log = logging.getLogger(__name__)

INTERVALS_API = "https://intervals.icu/api/v1"


def _get_auth_headers(api_key: str) -> dict:
    encoded = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


async def _get_credentials(db: AsyncSession) -> tuple[str, str] | None:
    result = await db.execute(select(Credential).where(Credential.provider == "intervals"))
    cred = result.scalar_one_or_none()
    if cred and cred.api_key and cred.athlete_id:
        return cred.api_key, cred.athlete_id

    if settings.intervals_api_key and settings.intervals_athlete_id:
        return settings.intervals_api_key, settings.intervals_athlete_id
    return None


async def fetch_activities(db: AsyncSession, days: int = 90) -> list[dict]:
    creds = await _get_credentials(db)
    if not creds:
        return []
    api_key, athlete_id = creds

    oldest = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.utcnow().strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{INTERVALS_API}/athlete/{athlete_id}/activities",
            headers=_get_auth_headers(api_key),
            params={"oldest": oldest, "newest": newest},
            timeout=30,
        )
        if resp.status_code != 200:
            log.error(f"intervals.icu activities fetch failed: {resp.text}")
            return []
        return resp.json()


async def fetch_activity_streams(db: AsyncSession, activity_id: str) -> dict | None:
    creds = await _get_credentials(db)
    if not creds:
        return None
    api_key, athlete_id = creds

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{INTERVALS_API}/activity/{activity_id}/streams",
            headers=_get_auth_headers(api_key),
            params={"types": "time,heartrate,watts,cadence,altitude,velocity_smooth"},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()

    streams = {}
    key_map = {
        "time": "time",
        "heartrate": "hr",
        "watts": "power",
        "cadence": "cadence",
        "altitude": "altitude",
        "velocity_smooth": "speed",
    }
    for item in data:
        if item.get("type") in key_map:
            streams[key_map[item["type"]]] = item.get("data", [])
    return streams


async def fetch_fitness_data(db: AsyncSession, days: int = 90) -> list[dict]:
    creds = await _get_credentials(db)
    if not creds:
        return []
    api_key, athlete_id = creds

    oldest = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.utcnow().strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{INTERVALS_API}/athlete/{athlete_id}/fitness",
            headers=_get_auth_headers(api_key),
            params={"oldest": oldest, "newest": newest},
            timeout=30,
        )
        if resp.status_code != 200:
            log.error(f"intervals.icu fitness fetch failed: {resp.text}")
            return []
        return resp.json()


async def fetch_wellness(db: AsyncSession, days: int = 90) -> list[dict]:
    creds = await _get_credentials(db)
    if not creds:
        return []
    api_key, athlete_id = creds

    oldest = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    newest = datetime.utcnow().strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{INTERVALS_API}/athlete/{athlete_id}/wellness",
            headers=_get_auth_headers(api_key),
            params={"oldest": oldest, "newest": newest},
            timeout=30,
        )
        if resp.status_code != 200:
            log.error(f"intervals.icu wellness fetch failed: {resp.text}")
            return []
        return resp.json()


SPORT_MAP = {
    "Ride": "cycling",
    "VirtualRide": "cycling",
    "Run": "running",
    "VirtualRun": "running",
    "Swim": "swimming",
    "WeightTraining": "strength",
    "Workout": "strength",
    "Hike": "hiking",
    "Walk": "walking",
    "NordicSki": "xcski",
    "Rowing": "rowing",
    "Yoga": "yoga",
}


SPORT_TO_INTERVALS = {
    "cycling": "Ride",
    "running": "Run",
    "swimming": "Swim",
    "strength": "WeightTraining",
}


def _to_icu_step(step: dict, sport: str) -> dict:
    """Convert one plan step into an intervals.icu workout_doc step.

    Each sport is sent in the units its watch can actually follow: watts for
    cycling, pace for running and swimming. Sending %FTP to a running watch
    prescribes a target the athlete has no way to read.
    """
    icu: dict = {"type": step.get("type", "steady").capitalize()}
    if step.get("duration"):
        icu["duration"] = {"value": step["duration"], "units": "s"}

    if sport == "cycling":
        if step.get("power") is not None:
            icu["power"] = {"value": int(step["power"] * 100), "units": "%ftp"}
            if step.get("power_end") is not None:
                icu["powerEnd"] = {"value": int(step["power_end"] * 100), "units": "%ftp"}
        if step.get("cadence"):
            icu["cadence"] = {"value": step["cadence"], "units": "rpm"}
    elif sport == "running" and step.get("pace"):
        icu["pace"] = {"value": step["pace"], "units": "secs_per_km"}
    elif sport == "swimming" and step.get("pace"):
        icu["pace"] = {"value": step["pace"], "units": "secs_per_100m"}

    if step.get("notes"):
        icu["text"] = step["notes"]
    return icu


async def push_workout(db: AsyncSession, workout_data: dict, date: str) -> dict:
    """Push a structured workout to intervals.icu for watch sync (Coros/Garmin).

    Returns {"ok": True, "workout": ...} or {"ok": False, "error": "..."} —
    the caller needs the reason to tell the athlete what to fix.
    """
    creds = await _get_credentials(db)
    if not creds:
        return {"ok": False, "error":
                "No intervals.icu credentials. Add your API key and athlete ID in Settings."}
    api_key, athlete_id = creds

    sport = workout_data.get("sport", "cycling")

    icu_steps = []
    for step in workout_data.get("steps", []):
        if step.get("repeat") and step.get("rest"):
            work = _to_icu_step(step, sport)
            work["type"] = "Interval"
            rest = _to_icu_step(step["rest"], sport)
            rest["type"] = "Rest"
            icu_steps.append({
                "type": "Repeat",
                "count": step["repeat"],
                "steps": [work, rest],
            })
        else:
            icu_steps.append(_to_icu_step(step, sport))

    payload = {
        "athlete_id": athlete_id,
        "name": workout_data.get("name", "Pulse Workout"),
        "description": workout_data.get("description", ""),
        "type": SPORT_TO_INTERVALS.get(sport, "Ride"),
        "date": date,
        "moving_time": (workout_data.get("duration_minutes") or 0) * 60 or None,
    }
    if icu_steps:
        payload["workout_doc"] = {"steps": icu_steps}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{INTERVALS_API}/athlete/{athlete_id}/workouts",
                headers=_get_auth_headers(api_key),
                json=payload,
                timeout=30,
            )
    except httpx.HTTPError as exc:
        log.error(f"intervals.icu workout push failed: {exc}")
        return {"ok": False, "error": f"Could not reach intervals.icu: {exc}"}

    if resp.status_code in (401, 403):
        return {"ok": False, "error": "intervals.icu rejected the API key. Check it in Settings."}
    if resp.status_code not in (200, 201):
        log.error(f"intervals.icu workout push failed [{resp.status_code}]: {resp.text}")
        return {"ok": False,
                "error": f"intervals.icu returned {resp.status_code}: {resp.text[:200]}"}

    return {"ok": True, "workout": resp.json()}


def parse_intervals_activity(raw: dict) -> dict:
    sport = SPORT_MAP.get(raw.get("type", ""), raw.get("type", "other").lower())

    start = None
    if raw.get("start_date_local"):
        try:
            start = datetime.fromisoformat(raw["start_date_local"].replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    pace = None
    if raw.get("average_speed") and sport == "running" and raw["average_speed"] > 0:
        pace = (1000 / raw["average_speed"]) / 60

    return {
        "intervals_id": str(raw.get("id", "")),
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
        "avg_power": raw.get("icu_average_watts") or raw.get("average_watts"),
        "max_power": raw.get("max_watts"),
        "normalized_power": raw.get("icu_weighted_avg_watts"),
        "avg_cadence": raw.get("average_cadence"),
        "avg_speed": raw.get("average_speed"),
        "avg_pace": pace,
        "tss": raw.get("icu_training_load"),
        "intensity_factor": raw.get("icu_intensity"),
        "training_load": raw.get("icu_training_load"),
        "source": "intervals",
    }
