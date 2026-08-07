from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Activity, Wellness, FitnessData
import logging

log = logging.getLogger(__name__)

MATCH_WINDOW_MINUTES = 5


def _activities_match(a: dict, b: dict) -> bool:
    if not a.get("start_time") or not b.get("start_time"):
        return False
    time_diff = abs((a["start_time"] - b["start_time"]).total_seconds())
    if time_diff > MATCH_WINDOW_MINUTES * 60:
        return False
    sport_a = (a.get("sport_type") or "").lower()
    sport_b = (b.get("sport_type") or "").lower()
    return sport_a == sport_b


def _merge_field(existing, new_val):
    if new_val is not None and new_val != 0:
        return new_val
    return existing


def merge_activity_data(existing: dict, incoming: dict, priority_source: str = "intervals") -> dict:
    """Merge two activity dicts. Fields from priority_source win when both have data."""
    merged = dict(existing)
    is_priority = incoming.get("source") == priority_source

    skip_fields = {"id", "created_at", "updated_at", "source"}
    source_id_fields = {"strava_id", "intervals_id", "coros_id"}

    for key, val in incoming.items():
        if key in skip_fields:
            continue
        if key in source_id_fields:
            if val:
                merged[key] = val
            continue
        if val is None:
            continue
        if merged.get(key) is None or is_priority:
            merged[key] = val

    sources = set()
    if merged.get("strava_id"):
        sources.add("strava")
    if merged.get("intervals_id"):
        sources.add("intervals")
    if merged.get("coros_id"):
        sources.add("coros")
    merged["source"] = ",".join(sorted(sources))

    return merged


async def merge_activities(db: AsyncSession, strava_data: list[dict], intervals_data: list[dict]):
    existing = await db.execute(select(Activity).order_by(Activity.start_time.desc()))
    existing_activities = existing.scalars().all()

    existing_by_strava = {a.strava_id: a for a in existing_activities if a.strava_id}
    existing_by_intervals = {a.intervals_id: a for a in existing_activities if a.intervals_id}
    existing_by_time = {}
    for a in existing_activities:
        if a.start_time and a.sport_type:
            key = (a.start_time.strftime("%Y%m%d%H%M"), a.sport_type)
            existing_by_time[key] = a

    processed_ids = set()

    for sdata in strava_data:
        sid = sdata.get("strava_id")
        if not sid:
            continue

        matched_interval = None
        for idata in intervals_data:
            if _activities_match(sdata, idata):
                matched_interval = idata
                break

        if sid in existing_by_strava:
            record = existing_by_strava[sid]
            merged = merge_activity_data(
                {c.name: getattr(record, c.name) for c in record.__table__.columns},
                sdata,
            )
            if matched_interval:
                merged = merge_activity_data(merged, matched_interval, "intervals")
                processed_ids.add(matched_interval.get("intervals_id"))
            for key, val in merged.items():
                if hasattr(record, key) and key != "id":
                    setattr(record, key, val)
        else:
            merged = dict(sdata)
            if matched_interval:
                merged = merge_activity_data(merged, matched_interval, "intervals")
                processed_ids.add(matched_interval.get("intervals_id"))

            time_key = None
            if merged.get("start_time") and merged.get("sport_type"):
                time_key = (merged["start_time"].strftime("%Y%m%d%H%M"), merged["sport_type"])
            if time_key and time_key in existing_by_time:
                record = existing_by_time[time_key]
                for key, val in merged.items():
                    if hasattr(record, key) and key != "id":
                        setattr(record, key, val)
            else:
                merged.pop("id", None)
                db.add(Activity(**merged))

    for idata in intervals_data:
        iid = idata.get("intervals_id")
        if not iid or iid in processed_ids:
            continue

        if iid in existing_by_intervals:
            record = existing_by_intervals[iid]
            for key, val in idata.items():
                if val is not None and hasattr(record, key) and key != "id":
                    current = getattr(record, key)
                    if current is None:
                        setattr(record, key, val)
        else:
            time_key = None
            if idata.get("start_time") and idata.get("sport_type"):
                time_key = (idata["start_time"].strftime("%Y%m%d%H%M"), idata["sport_type"])
            if time_key and time_key in existing_by_time:
                record = existing_by_time[time_key]
                for key, val in idata.items():
                    if val is not None and hasattr(record, key) and key != "id":
                        current = getattr(record, key)
                        if current is None:
                            setattr(record, key, val)
            else:
                idata.pop("id", None)
                db.add(Activity(**idata))

    await db.commit()


async def merge_fitness_data(db: AsyncSession, fitness_list: list[dict]):
    for item in fitness_list:
        date = item.get("id")
        if not date:
            continue
        result = await db.execute(select(FitnessData).where(FitnessData.date == date))
        existing = result.scalar_one_or_none()
        if existing:
            existing.ctl = item.get("ctl", existing.ctl)
            existing.atl = item.get("atl", existing.atl)
            existing.tsb = item.get("ctl", 0) - item.get("atl", 0) if item.get("ctl") else existing.tsb
            existing.daily_tss = item.get("load", existing.daily_tss)
        else:
            ctl = item.get("ctl")
            atl = item.get("atl")
            db.add(FitnessData(
                date=date,
                ctl=ctl,
                atl=atl,
                tsb=(ctl - atl) if ctl and atl else None,
                daily_tss=item.get("load"),
            ))
    await db.commit()


async def merge_wellness_data(db: AsyncSession, wellness_list: list[dict]):
    for item in wellness_list:
        date = item.get("id")
        if not date:
            continue
        result = await db.execute(select(Wellness).where(Wellness.date == date))
        existing = result.scalar_one_or_none()

        sleep_secs = item.get("sleepTime")
        sleep_hours = round(sleep_secs / 3600, 1) if sleep_secs else None

        if existing:
            existing.resting_hr = item.get("restingHR") or existing.resting_hr
            existing.hrv = item.get("hrv") or existing.hrv
            existing.sleep_hours = sleep_hours or existing.sleep_hours
            existing.sleep_quality = item.get("sleepQuality") or existing.sleep_quality
            existing.weight = item.get("weight") or existing.weight
            existing.fatigue = item.get("fatigue") or existing.fatigue
            existing.mood = item.get("mood") or existing.mood
            existing.soreness = item.get("soreness") or existing.soreness
            existing.stress = item.get("stress") or existing.stress
            existing.source = "intervals"
        else:
            db.add(Wellness(
                date=date,
                resting_hr=item.get("restingHR"),
                hrv=item.get("hrv"),
                sleep_hours=sleep_hours,
                sleep_quality=item.get("sleepQuality"),
                weight=item.get("weight"),
                fatigue=item.get("fatigue"),
                mood=item.get("mood"),
                soreness=item.get("soreness"),
                stress=item.get("stress"),
                source="intervals",
            ))
    await db.commit()
