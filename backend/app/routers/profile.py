from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models import AthleteProfile, FitnessData, TrainingPlan
from ..services.ai_coach import generate_structured_plan, get_last_error
from ..config import settings
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileUpdate(BaseModel):
    experience_level: Optional[str] = None
    primary_sport: Optional[str] = None
    goal: Optional[str] = None
    goal_event: Optional[str] = None
    goal_date: Optional[str] = None
    weaknesses: Optional[list[str]] = None
    strengths: Optional[list[str]] = None
    sports: Optional[list[str]] = None
    weekly_hours: Optional[float] = None
    current_weekly_hours: Optional[float] = None
    preferred_hard_days: Optional[list[str]] = None
    preferred_rest_days: Optional[list[str]] = None
    plan_duration_weeks: Optional[int] = None
    has_trainer: Optional[bool] = None
    has_power_meter: Optional[bool] = None
    has_hr_monitor: Optional[bool] = None
    max_sessions_per_day: Optional[int] = None
    auto_push: Optional[bool] = None
    notes: Optional[str] = None
    onboarding_complete: Optional[bool] = None


@router.get("")
async def get_profile(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AthleteProfile).limit(1))
    profile = result.scalar_one_or_none()
    if not profile:
        return None
    return _serialize(profile)


@router.put("")
async def update_profile(data: ProfileUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AthleteProfile).limit(1))
    profile = result.scalar_one_or_none()
    if not profile:
        profile = AthleteProfile()
        db.add(profile)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return _serialize(profile)


@router.post("/generate-plan")
async def generate_full_plan(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AthleteProfile).limit(1))
    profile = result.scalar_one_or_none()
    if not profile or not profile.onboarding_complete:
        raise HTTPException(400, "Complete onboarding first")

    fitness_result = await db.execute(
        select(FitnessData).order_by(FitnessData.date.desc()).limit(1)
    )
    latest_fitness = fitness_result.scalar_one_or_none()
    fitness_context = None
    if latest_fitness:
        fitness_context = {
            "ctl": latest_fitness.ctl,
            "atl": latest_fitness.atl,
            "tsb": latest_fitness.tsb,
        }

    today = datetime.utcnow()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    start_date = (today + timedelta(days=days_until_monday)).strftime("%Y-%m-%d")

    profile_dict = _serialize(profile)
    plan_result = await generate_structured_plan(
        profile=profile_dict,
        ftp=settings.ftp,
        fitness_context=fitness_context,
        start_date=start_date,
    )
    if not plan_result:
        detail = get_last_error() or "Plan generation failed"
        raise HTTPException(500, f"Plan generation failed: {detail}")

    existing = await db.execute(
        select(TrainingPlan).where(TrainingPlan.status.in_(["active", "upcoming"]))
    )
    for old in existing.scalars().all():
        old.status = "archived"

    weeks = plan_result.get("weeks", [])
    plan = TrainingPlan(
        week=datetime.strptime(start_date, "%Y-%m-%d").strftime("%G-W%V"),
        name=plan_result.get("name", "Training Plan"),
        description=plan_result.get("description"),
        plan_data=plan_result,
        status="active",
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    return {
        "plan_id": plan.id,
        "plan_name": plan_result.get("name"),
        "total_weeks": plan_result.get("total_weeks"),
        "description": plan_result.get("description"),
        "weeks_created": len(weeks),
        "progression_notes": plan_result.get("progression_notes"),
    }


def _serialize(profile: AthleteProfile) -> dict:
    return {
        "id": profile.id,
        "experience_level": profile.experience_level,
        "primary_sport": profile.primary_sport,
        "goal": profile.goal,
        "goal_event": profile.goal_event,
        "goal_date": profile.goal_date,
        "weaknesses": profile.weaknesses or [],
        "strengths": profile.strengths or [],
        "sports": profile.sports or [],
        "weekly_hours": profile.weekly_hours,
        "current_weekly_hours": profile.current_weekly_hours,
        "preferred_hard_days": profile.preferred_hard_days or [],
        "preferred_rest_days": profile.preferred_rest_days or [],
        "plan_duration_weeks": profile.plan_duration_weeks,
        "has_trainer": profile.has_trainer,
        "has_power_meter": profile.has_power_meter,
        "has_hr_monitor": profile.has_hr_monitor,
        "max_sessions_per_day": profile.max_sessions_per_day or 1,
        "auto_push": profile.auto_push,
        "notes": profile.notes,
        "onboarding_complete": profile.onboarding_complete,
    }
