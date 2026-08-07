from sqlalchemy.ext.asyncio import AsyncSession
from . import strava, intervals, merger
from ..models import Setting
from ..database import async_session
from sqlalchemy import select
from datetime import datetime
import logging

log = logging.getLogger(__name__)

_sync_in_progress = False
_last_sync: str | None = None


def is_syncing() -> bool:
    return _sync_in_progress


def last_sync_time() -> str | None:
    return _last_sync


async def run_sync(days: int = 90):
    global _sync_in_progress, _last_sync
    if _sync_in_progress:
        return

    _sync_in_progress = True
    log.info("Starting sync...")

    try:
        async with async_session() as db:
            strava_raw = await strava.fetch_activities(db, days=days)
            strava_parsed = [strava.parse_strava_activity(a) for a in strava_raw]
            log.info(f"Fetched {len(strava_parsed)} activities from Strava")

            intervals_raw = await intervals.fetch_activities(db, days=days)
            intervals_parsed = [intervals.parse_intervals_activity(a) for a in intervals_raw]
            log.info(f"Fetched {len(intervals_parsed)} activities from intervals.icu")

            await merger.merge_activities(db, strava_parsed, intervals_parsed)
            log.info("Activities merged")

            fitness_data = await intervals.fetch_fitness_data(db, days=days)
            if fitness_data:
                await merger.merge_fitness_data(db, fitness_data)
                log.info(f"Merged {len(fitness_data)} fitness data points")

            wellness_data = await intervals.fetch_wellness(db, days=days)
            if wellness_data:
                await merger.merge_wellness_data(db, wellness_data)
                log.info(f"Merged {len(wellness_data)} wellness data points")

            _last_sync = datetime.utcnow().isoformat()
            setting = await db.execute(select(Setting).where(Setting.key == "last_sync"))
            s = setting.scalar_one_or_none()
            if s:
                s.value = _last_sync
            else:
                db.add(Setting(key="last_sync", value=_last_sync))
            await db.commit()

    except Exception as e:
        log.error(f"Sync failed: {e}", exc_info=True)
    finally:
        _sync_in_progress = False
        log.info("Sync complete")
