from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import Setting
from ..config import settings
from ..schemas import SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Setting))
    db_settings = {s.key: s.value for s in result.scalars().all()}

    return {
        "ftp": int(db_settings.get("ftp", settings.ftp)),
        "threshold_pace": int(db_settings.get("threshold_pace", settings.threshold_pace)),
        "swim_css_pace": int(db_settings.get("swim_css_pace", settings.swim_css_pace)),
        "sync_interval": int(db_settings.get("sync_interval", settings.sync_interval)),
        "ai_provider": db_settings.get("ai_provider", settings.ai_provider),
        "ollama_url": db_settings.get("ollama_url", settings.ollama_url),
        "ollama_model_light": db_settings.get("ollama_model_light", settings.ollama_model_light),
        "ollama_model_heavy": db_settings.get("ollama_model_heavy", settings.ollama_model_heavy),
        "claude_model_light": db_settings.get("claude_model_light", settings.claude_model_light),
        "claude_model_heavy": db_settings.get("claude_model_heavy", settings.claude_model_heavy),
        "claude_skill_id": db_settings.get("claude_skill_id", settings.claude_skill_id),
        "claude_skill_version": db_settings.get("claude_skill_version", settings.claude_skill_version),
        "openai_model_light": db_settings.get("openai_model_light", settings.openai_model_light),
        "openai_model_heavy": db_settings.get("openai_model_heavy", settings.openai_model_heavy),
        "strava_client_id": settings.strava_client_id or db_settings.get("strava_client_id", ""),
        "intervals_athlete_id": settings.intervals_athlete_id or db_settings.get("intervals_athlete_id", ""),
    }


@router.put("")
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
        if hasattr(settings, key):
            setattr(settings, key, value)
    await db.commit()
    return {"updated": list(updates.keys())}
