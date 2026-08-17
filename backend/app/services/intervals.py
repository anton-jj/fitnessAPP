import httpx
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Credential
from ..config import settings
from .fit_workout import generate_workout_fit, workout_filename
from .plan_builder import format_pace, format_swim_pace
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


def _dsl_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds or 0), 60)
    if minutes and secs:
        return f"{minutes}m{secs}s"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def _dsl_target(step: dict, sport: str) -> str:
    """intervals.icu's own workout syntax target token for one step.

    Cycling: "90%" (of FTP), optionally "+90rpm" for cadence. Running/
    swimming: a pace token like "5:00/km Pace" or "1:45/100m Pace" — their
    parser accepts pace natively, it's not FTP-percent-only.
    """
    power = step.get("power")
    if sport == "cycling" and isinstance(power, (int, float)):
        token = f"{power * 100:.0f}%"
        if step.get("cadence"):
            token += f" {int(step['cadence'])}rpm"
        return token
    pace = step.get("pace")
    if isinstance(pace, (int, float)) and pace > 0:
        formatted = format_swim_pace(pace) if sport == "swimming" else format_pace(pace)
        return f"{formatted} Pace"
    return ""


_DSL_SECTION_LABEL = {
    "warmup": "Warmup",
    "cooldown": "Cooldown",
    "rest": "Recovery",
    "recovery": "Recovery",
}


def _dsl_description(workout: dict) -> str:
    """Structured description in intervals.icu's own plain-text workout
    syntax (section header, blank line, dash-prefixed steps) — this is what
    intervals.icu actually parses into real power/pace targets on its own
    calendar and analysis pages. A FIT attachment alone doesn't get this:
    intervals.icu's FIT re-import path has documented quirks (dropped rest,
    unexpected paces on swim files) that the native syntax sidesteps.
    Cycling/running/swimming only — strength has no equivalent, see
    _strength_description.
    """
    sport = workout.get("sport", "cycling")
    sections = []
    for step in workout.get("steps") or []:
        if not isinstance(step, dict):
            continue
        seconds = step.get("duration")
        if not seconds:
            continue
        repeat = step.get("repeat") or 1
        label = _DSL_SECTION_LABEL.get((step.get("type") or "").lower(), "Main Set")
        header = f"{label} {repeat}x" if repeat > 1 else label

        lines = [f"- {_dsl_duration(seconds)} {_dsl_target(step, sport)}".rstrip()]
        rest = step.get("rest")
        if isinstance(rest, dict) and rest.get("duration"):
            lines.append(f"- {_dsl_duration(rest['duration'])} {_dsl_target(rest, sport)}".rstrip())

        sections.append(header + "\n" + "\n".join(lines))

    return "\n\n".join(sections)


def _strength_description(workout: dict) -> str:
    """Readable exercise/sets/reps/rest text for a gym session.

    intervals.icu has no structured format for strength — sets, reps and
    rest aren't representable in either the workout syntax or a FIT file it
    will parse (confirmed platform limitation, not a Pulse gap: it shows
    strength FIT steps as a plain note at best). A clean text list is the
    most it can faithfully display.
    """
    parts = []
    if workout.get("description"):
        parts.append(workout["description"])

    lines = []
    for step in workout.get("steps") or []:
        if not isinstance(step, dict):
            continue
        name = step.get("exercise") or step.get("type", "Exercise")
        reps = step.get("reps")
        sets = step.get("sets") or step.get("repeat") or 1
        rest = step.get("rest") or {}
        rest_sec = rest.get("duration")

        line = f"- {name}"
        if reps:
            line += f": {sets}x{reps}" if sets and sets > 1 else f": {reps} reps"
        if rest_sec:
            line += f", {int(rest_sec)}s rest"
        if step.get("notes"):
            line += f" — {step['notes']}"
        lines.append(line)
    if lines:
        parts.append("\n".join(lines))

    if workout.get("coach_notes"):
        parts.append(f"Coach: {workout['coach_notes']}")
    return "\n\n".join(parts)


def _event_payload(workout: dict, date: str, ftp: int) -> dict:
    """One intervals.icu calendar event.

    Planned sessions are calendar *events* with category WORKOUT — the
    /workouts endpoint is the reusable workout library and never reaches the
    athlete's calendar or their watch. Endurance sports get a description in
    intervals.icu's own structured workout syntax (parsed into real targets
    on their side) plus a FIT attachment for device forwarding. Strength
    gets neither structure intervals.icu can use — see _strength_description
    — so it's plain text and no FIT attachment.
    """
    sport = workout.get("sport", "cycling")
    duration = int(workout.get("duration_minutes") or 0) * 60
    name = workout.get("name", "Pulse Workout")
    is_strength = sport == "strength"

    payload = {
        "category": "WORKOUT",
        "start_date_local": f"{date}T00:00:00",
        "type": SPORT_TO_INTERVALS.get(sport, "Ride"),
        "name": name,
        "description": (
            _strength_description(workout) if is_strength
            else (_dsl_description(workout) or workout.get("description", ""))
        ),
        # Stable id so re-pushing the same session updates it instead of
        # stacking duplicates on the calendar.
        "external_id": f"pulse-{date}-{sport}-{abs(hash(name)) % 100000}",
    }
    if duration:
        payload["moving_time"] = duration

    if workout.get("steps") and not is_strength:
        fit = generate_workout_fit(workout, ftp=ftp, rep_steps=False)
        payload["filename"] = workout_filename(workout, date)
        payload["file_contents_base64"] = base64.b64encode(fit).decode()

    return payload


async def push_workouts(db: AsyncSession, items: list[dict]) -> dict:
    """Push planned sessions to the intervals.icu calendar.

    `items` is a list of {"workout": dict, "date": "YYYY-MM-DD"}. From there
    intervals.icu forwards them to whichever device the athlete has connected
    — Garmin, COROS, Wahoo, Polar or Suunto — which is why Pulse does not
    need a partner API of its own.
    """
    creds = await _get_credentials(db)
    if not creds:
        return {"ok": False, "error":
                "No intervals.icu credentials. Add your API key and athlete ID in Settings."}
    api_key, athlete_id = creds

    events = [
        _event_payload(item["workout"], item["date"], settings.ftp)
        for item in items
        if item.get("workout", {}).get("workout_type") != "rest"
    ]
    if not events:
        return {"ok": False, "error": "Nothing to push — no non-rest sessions selected."}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{INTERVALS_API}/athlete/{athlete_id}/events/bulk",
                headers=_get_auth_headers(api_key),
                params={"upsert": "true"},
                json=events,
                timeout=60,
            )
    except httpx.HTTPError as exc:
        log.error(f"intervals.icu push failed: {exc}")
        return {"ok": False, "error": f"Could not reach intervals.icu: {exc}"}

    if resp.status_code in (401, 403):
        return {"ok": False, "error":
                "intervals.icu rejected the API key. Check it in Settings."}
    if resp.status_code not in (200, 201):
        log.error(f"intervals.icu push failed [{resp.status_code}]: {resp.text[:300]}")
        return {"ok": False,
                "error": f"intervals.icu returned {resp.status_code}: {resp.text[:200]}"}

    log.info(f"Pushed {len(events)} workout(s) to intervals.icu")
    return {"ok": True, "pushed": len(events), "workout": resp.json()}


async def push_workout(db: AsyncSession, workout_data: dict, date: str) -> dict:
    return await push_workouts(db, [{"workout": workout_data, "date": date}])


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
