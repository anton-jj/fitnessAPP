from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db, async_session
from ..models import AthleteProfile, FitnessData, TrainingPlan
from ..services.ai_coach import generate_structured_plan, get_last_error
from ..services.training_history import recent_training_volume
from ..config import settings
from datetime import datetime, timedelta
import asyncio
import logging
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger(__name__)

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
    sport_limits: Optional[dict] = None
    recovery_mode: Optional[str] = None
    recovery_cycle_weeks: Optional[int] = None
    volume_progression_mode: Optional[str] = None
    training_style: Optional[str] = None
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


# Generating a block is minutes of model time. Holding an HTTP connection open
# that long is fragile — proxies time out, phones sleep, tabs get closed — so
# the request starts a job and the client polls for the result.
_generation: dict = {"status": "idle", "error": None, "plan_id": None,
                     "started_at": None, "finished_at": None, "detail": None}

# asyncio only holds a weak reference to running tasks, so a fire-and-forget
# task can be garbage collected mid-run. Keep a strong reference until it ends.
_background_tasks: set = set()


def _generation_state() -> dict:
    return dict(_generation)


async def _run_generation(profile_dict: dict, fitness_context: dict | None,
                          start_date: str, first_week_from: str = "") -> None:
    global _generation
    try:
        plan_result = await generate_structured_plan(
            profile=profile_dict,
            ftp=settings.ftp,
            fitness_context=fitness_context,
            start_date=start_date,
            first_week_from=first_week_from,
        )
        if not plan_result:
            raise RuntimeError(get_last_error() or "Plan generation failed")

        async with async_session() as db:
            existing = await db.execute(
                select(TrainingPlan).where(TrainingPlan.status.in_(["active", "upcoming"]))
            )
            for old in existing.scalars().all():
                old.status = "archived"

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
            plan_id = plan.id

        _generation.update({
            "status": "done", "plan_id": plan_id, "error": None,
            "finished_at": datetime.utcnow().isoformat(),
            "detail": f"{plan_result.get('total_weeks')} weeks",
        })
        log.info(f"Plan generation finished: plan {plan_id}")
    except Exception as exc:
        log.exception("Plan generation failed")
        _generation.update({
            "status": "error", "error": str(exc),
            "finished_at": datetime.utcnow().isoformat(),
        })


class GeneratePlanRequest(BaseModel):
    # "next_week" starts on the coming Monday; "this_week" starts today and
    # runs the rest of the current week as a short first week.
    start: str = "next_week"


@router.post("/generate-plan")
async def generate_full_plan(req: GeneratePlanRequest | None = None,
                             db: AsyncSession = Depends(get_db)):
    """Kick off generation and return immediately. Poll /generate-plan/status."""
    if _generation["status"] == "running":
        return {"status": "running", "started_at": _generation["started_at"],
                "message": "A plan is already being generated"}

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

    # What the athlete has actually been training, so the ramp starts from
    # reality rather than from whatever they set during onboarding.
    observed = await recent_training_volume(db)

    today = datetime.utcnow()
    start_this_week = (req.start if req else "next_week") == "this_week"

    if start_this_week:
        # Anchor to this week's Monday so the calendar lines up, but start
        # training today — the days already gone stay empty.
        monday = today - timedelta(days=today.weekday())
        start_date = monday.strftime("%Y-%m-%d")
        first_week_from = today.strftime("%Y-%m-%d")
    else:
        days_until_monday = (7 - today.weekday()) % 7 or 7
        start_date = (today + timedelta(days=days_until_monday)).strftime("%Y-%m-%d")
        first_week_from = ""

    profile_dict = _serialize(profile)
    if observed:
        profile_dict["observed_weekly_hours"] = observed["weekly_hours"]
        profile_dict["observed_history"] = observed

    _generation.update({
        "status": "running", "error": None, "plan_id": None,
        "started_at": datetime.utcnow().isoformat(), "finished_at": None,
        "detail": f"{profile.plan_duration_weeks or 8} weeks, starting "
                  + ("today" if start_this_week else start_date),
    })
    task = asyncio.create_task(
        _run_generation(profile_dict, fitness_context, start_date, first_week_from)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "running", "started_at": _generation["started_at"]}


@router.get("/generate-plan/status")
async def generate_plan_status():
    return _generation_state()


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
        "sport_limits": profile.sport_limits or {},
        "recovery_mode": profile.recovery_mode or "auto",
        "recovery_cycle_weeks": profile.recovery_cycle_weeks,
        "volume_progression_mode": profile.volume_progression_mode or "ramp",
        "training_style": profile.training_style or "standard",
        "auto_push": profile.auto_push,
        "notes": profile.notes,
        "onboarding_complete": profile.onboarding_complete,
    }
