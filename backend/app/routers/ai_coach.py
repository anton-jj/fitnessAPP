from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from ..database import get_db
from ..models import Workout, FitnessData, TrainingPlan, AthleteProfile
from ..schemas import AISessionRequest, WorkoutOut, WorkoutCreate
from ..services.ai_coach import (
    generate_session, generate_structured_plan, adjust_plan, get_usage,
    get_last_error,
)
from ..services.intervals import push_workout, push_workouts
from ..config import settings
from ..services.fit_workout import generate_workout_fit, workout_filename
from ..services.ics_feed import plan_to_ics
from ..services.compliance import plan_compliance, adapt_remaining_weeks
from ..services import session_auth
import io
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/ai", tags=["ai"])


class PlanRequest(BaseModel):
    sports: list[str] = ["cycling", "running"]
    hours: float = 8
    notes: Optional[str] = None
    week_start: Optional[str] = None  # YYYY-MM-DD, defaults to next Monday


class PlanAction(BaseModel):
    action: str  # "skip" | "swap" | "move"
    details: str  # human-readable description of what changed
    week_number: Optional[int] = None


@router.get("/usage")
async def ai_usage():
    return get_usage()


@router.post("/session", response_model=WorkoutOut)
async def create_ai_session(req: AISessionRequest, db: AsyncSession = Depends(get_db)):
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

    result = await generate_session(
        sport=req.sport,
        session_type=req.session_type,
        duration_minutes=req.duration_minutes,
        ftp=settings.ftp,
        fitness_context=fitness_context,
        notes=req.notes,
    )
    if not result:
        raise HTTPException(500, "AI generation failed. Check AI provider configuration.")

    workout = Workout(
        name=result.get("name", f"{req.session_type} session"),
        description=result.get("description"),
        sport=req.sport,
        workout_type=result.get("workout_type", req.session_type),
        steps=result.get("steps", []),
        duration_seconds=result.get("duration_seconds"),
        tss_estimate=result.get("tss_estimate"),
        source="ai",
    )
    db.add(workout)
    await db.commit()
    await db.refresh(workout)
    return WorkoutOut.model_validate(workout)


@router.post("/plan")
async def create_training_plan(req: PlanRequest, db: AsyncSession = Depends(get_db)):
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

    if req.week_start:
        week_start = req.week_start
    else:
        today = datetime.utcnow()
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        next_monday = today + timedelta(days=days_until_monday)
        week_start = next_monday.strftime("%Y-%m-%d")

    profile_result = await db.execute(select(AthleteProfile).limit(1))
    profile = profile_result.scalar_one_or_none()

    plan_profile = {
        "sports": req.sports,
        "weekly_hours": req.hours,
        "plan_duration_weeks": 1,
        "notes": req.notes,
    }
    if profile:
        for field in ("experience_level", "primary_sport", "goal", "goal_event",
                      "preferred_hard_days", "preferred_rest_days", "has_trainer",
                      "max_sessions_per_day", "weaknesses", "strengths"):
            value = getattr(profile, field, None)
            if value:
                plan_profile[field] = value

    result = await generate_structured_plan(
        profile=plan_profile,
        ftp=settings.ftp,
        fitness_context=fitness_context,
        start_date=week_start,
    )
    if not result:
        raise HTTPException(500, "Plan generation failed. Check AI provider configuration.")

    ws = datetime.strptime(week_start, "%Y-%m-%d")
    iso_week = ws.strftime("%G-W%V")

    existing = await db.execute(
        select(TrainingPlan).where(TrainingPlan.status.in_(["active", "upcoming"]))
    )
    for old in existing.scalars().all():
        old.status = "archived"

    plan = TrainingPlan(
        week=iso_week,
        name=result.get("name", f"Week {iso_week}"),
        description=result.get("description"),
        plan_data=result,
        status="active",
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    return {
        "id": plan.id,
        "week": plan.week,
        "name": plan.name,
        "description": plan.description,
        "plan": result,
        "status": plan.status,
    }


@router.get("/plan")
async def get_current_plan(week: str | None = None, db: AsyncSession = Depends(get_db)):
    if week:
        query = select(TrainingPlan).where(TrainingPlan.week == week)
    else:
        query = select(TrainingPlan).where(TrainingPlan.status == "active").order_by(TrainingPlan.created_at.desc())
    result = await db.execute(query.limit(1))
    plan = result.scalar_one_or_none()
    if not plan:
        return None
    return {
        "id": plan.id,
        "week": plan.week,
        "name": plan.name,
        "description": plan.description,
        "plan": plan.plan_data,
        "status": plan.status,
    }


@router.put("/plan/{plan_id}")
async def update_plan(plan_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    plan.plan_data = data.get("plan", plan.plan_data)
    plan.status = data.get("status", plan.status)
    await db.commit()
    return {"updated": True}


@router.delete("/plan/{plan_id}")
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    await db.delete(plan)
    await db.commit()
    return {"deleted": True}


@router.post("/plan/{plan_id}/adjust")
async def adjust_training_plan(plan_id: int, action: PlanAction, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")

    data = plan.plan_data
    weeks = data.get("weeks", [])

    # A plan can span months; only the affected week is sent to the AI, or the
    # request would blow past the model's output budget and come back truncated.
    target = None
    if weeks:
        target = next(
            (w for w in weeks if w.get("week_number") == action.week_number),
            weeks[0],
        )

    adjusted = await adjust_plan(target or data, action.action, action.details)
    if not adjusted:
        raise HTTPException(500, f"Failed to adjust plan: {get_last_error()}")

    if target is not None:
        weeks[weeks.index(target)] = adjusted
    else:
        data = adjusted

    plan.plan_data = data
    flag_modified(plan, "plan_data")
    await db.commit()
    return {
        "id": plan.id,
        "plan": data,
    }


class MoveWorkoutRequest(BaseModel):
    plan_id: int
    week_number: int
    from_day: str
    from_index: int
    to_day: str


@router.post("/plan/move-workout")
async def move_workout(req: MoveWorkoutRequest, db: AsyncSession = Depends(get_db)):
    """Move a workout from one day to another within a week, then ask AI to rebalance."""
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == req.plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")

    data = plan.plan_data
    weeks = data.get("weeks", [])
    week = None
    for w in weeks:
        if w.get("week_number") == req.week_number:
            week = w
            break
    if not week:
        days_list = data.get("days", [])
        if days_list:
            week = data
        else:
            raise HTTPException(404, "Week not found")

    from_day_data = None
    to_day_data = None
    for d in week.get("days", []):
        if d["day"] == req.from_day:
            from_day_data = d
        if d["day"] == req.to_day:
            to_day_data = d

    if not from_day_data or not to_day_data:
        raise HTTPException(400, "Day not found")

    workouts = from_day_data.get("workouts", [])
    if req.from_index >= len(workouts):
        raise HTTPException(400, "Workout index out of range")

    workout = workouts.pop(req.from_index)
    # A rest day is stored as a placeholder workout; drop it so the moved
    # session does not land next to a "Rest Day" entry.
    target = [w for w in to_day_data.get("workouts", []) if w.get("workout_type") != "rest"]
    target.append(workout)
    to_day_data["workouts"] = target

    if not from_day_data["workouts"]:
        from_day_data["workouts"] = [{
            "name": "Rest Day", "sport": "rest", "workout_type": "rest",
            "duration_minutes": 0, "description": "", "coach_notes": "",
            "target_zone": "Recovery", "tss_estimate": 0,
            "intensity_factor": 0, "priority": "optional",
            "distance_km": 0, "steps": [],
        }]

    plan.plan_data = data
    flag_modified(plan, "plan_data")
    await db.commit()

    advice = await _get_rebalance_advice(week, req.from_day, req.to_day, workout)

    return {
        "moved": True,
        "week": week,
        "advice": advice,
    }


async def _get_rebalance_advice(week: dict, from_day: str, to_day: str, moved_workout: dict) -> str | None:
    from ..services.ai_coach import _generate
    summary_lines = [
        f"A workout was moved from {from_day} to {to_day}:",
        f"  {moved_workout.get('name')} ({moved_workout.get('sport')}, "
        f"{moved_workout.get('workout_type')}, {moved_workout.get('duration_minutes')}min)",
        "",
        "Current week after the move:",
    ]
    for d in week.get("days", []):
        for w in d.get("workouts", []):
            if w.get("workout_type") == "rest":
                continue
            summary_lines.append(
                f"  {d['day']}: {w.get('name')} ({w.get('sport')}, "
                f"{w.get('duration_minutes')}min, {w.get('workout_type')}, "
                f"{w.get('archetype', 'easy')})"
            )

    prompt = "\n".join(summary_lines)
    system = (
        "You are a sports coach reviewing a training week after a workout was moved. "
        "Check if the new arrangement has issues: back-to-back quality days, a quality "
        "session adjacent to a long session in the same discipline, too much volume on "
        "one day, or insufficient recovery. Reply with a short JSON: "
        '{"ok": true/false, "advice": "one sentence suggestion or empty string"}'
    )
    try:
        result = await _generate(system, prompt, tier="light")
        if result and isinstance(result, dict):
            return result.get("advice", "")
    except Exception:
        pass
    return None


class WorkoutPushRequest(BaseModel):
    workout: dict
    date: str  # YYYY-MM-DD


@router.post("/push-to-watch")
async def push_workout_to_watch(req: WorkoutPushRequest, db: AsyncSession = Depends(get_db)):
    result = await push_workout(db, req.workout, req.date)
    if not result.get("ok"):
        raise HTTPException(502, result.get("error", "Push to intervals.icu failed"))
    return {"pushed": True, "count": result.get("pushed", 1)}


class PlanPushRequest(BaseModel):
    plan_id: int
    week_number: Optional[int] = None  # omit to push the whole plan


@router.post("/push-plan")
async def push_plan_to_watch(req: PlanPushRequest, db: AsyncSession = Depends(get_db)):
    """Push a whole week (or the whole block) in one go."""
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == req.plan_id))
    plan = result.scalar_one_or_none()
    if not plan or not plan.plan_data:
        raise HTTPException(404, "Plan not found")

    weeks = plan.plan_data.get("weeks") or [plan.plan_data]
    if req.week_number is not None:
        weeks = [w for w in weeks if w.get("week_number") == req.week_number]
        if not weeks:
            raise HTTPException(404, "Week not found")

    items = [
        {"workout": workout, "date": day["date"]}
        for week in weeks
        for day in week.get("days", [])
        if day.get("date")
        for workout in day.get("workouts", [])
        if workout.get("workout_type") != "rest"
    ]
    if not items:
        raise HTTPException(400, "Nothing to push")

    pushed = await push_workouts(db, items)
    if not pushed.get("ok"):
        raise HTTPException(502, pushed.get("error", "Push to intervals.icu failed"))
    return {"pushed": True, "count": pushed.get("pushed", len(items))}


@router.post("/workout-file")
async def download_workout_file(req: WorkoutPushRequest):
    """Download one session as a .fit workout file.

    Import it into Garmin Connect or the COROS app when you would rather not
    route through intervals.icu, or have no connection set up at all.
    """
    fit = generate_workout_fit(req.workout, ftp=settings.ftp)
    return StreamingResponse(
        io.BytesIO(fit),
        media_type="application/vnd.ant.fit",
        headers={
            "Content-Disposition":
                f'attachment; filename="{workout_filename(req.workout, req.date)}"'
        },
    )


@router.get("/plan/{plan_id}/compliance")
async def plan_compliance_report(plan_id: int, db: AsyncSession = Depends(get_db)):
    """How the finished weeks actually went, and what to do about it."""
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan or not plan.plan_data:
        raise HTTPException(404, "Plan not found")
    return await plan_compliance(db, plan.plan_data)


@router.post("/plan/{plan_id}/adapt")
async def adapt_plan_to_compliance(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Apply the compliance recommendation to the weeks that have not started.

    Deterministic — no model call, so adapting a block is free and instant
    where regenerating one is neither.
    """
    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan or not plan.plan_data:
        raise HTTPException(404, "Plan not found")

    report = await plan_compliance(db, plan.plan_data)
    recommendation = report["recommendation"]
    if recommendation["action"] == "none":
        return {"adapted": False, "reason": recommendation["reason"]}

    plan.plan_data = adapt_remaining_weeks(
        plan.plan_data, recommendation,
        threshold_pace=settings.threshold_pace, css_pace=settings.swim_css_pace,
    )
    flag_modified(plan, "plan_data")
    await db.commit()

    adaptation = plan.plan_data["adaptation"]
    if not adaptation["changed_now"]:
        return {"adapted": False,
                "reason": "The weeks ahead already match this recommendation."}
    return {"adapted": True, **adaptation}


@router.get("/plan/{plan_id}/calendar-url")
async def plan_calendar_url(plan_id: int, request: Request):
    """The subscribable feed URL, key included.

    Behind the session check, so the key only ever reaches someone already
    signed in — the frontend cannot derive it on its own.
    """
    base = str(request.base_url).rstrip("/")
    url = f"{base}/api/ai/plan/{plan_id}/calendar.ics"
    if session_auth.is_enabled():
        url += f"?key={session_auth.feed_key(plan_id)}"
    return {"url": url}


@router.get("/plan/{plan_id}/calendar.ics")
async def plan_calendar_feed(plan_id: int, key: str | None = None,
                             db: AsyncSession = Depends(get_db)):
    """Subscribe to the plan from any calendar app.

    Outside the session check on purpose — calendar clients cannot log in. Once
    a PIN is set the URL carries a key instead, so the feed cannot be reached by
    counting plan ids upward. Treat the URL as the secret it is.
    """
    if not session_auth.verify_feed_key(plan_id, key):
        raise HTTPException(404, "Plan not found")

    result = await db.execute(select(TrainingPlan).where(TrainingPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan or not plan.plan_data:
        raise HTTPException(404, "Plan not found")

    ics = plan_to_ics(plan.plan_data, plan.name or "Training Plan")
    return Response(
        content=ics,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="pulse-plan.ics"'},
    )


@router.get("/workouts", response_model=list[WorkoutOut])
async def list_workouts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Workout).order_by(Workout.created_at.desc()).limit(50)
    )
    return [WorkoutOut.model_validate(w) for w in result.scalars().all()]


@router.get("/workouts/{workout_id}", response_model=WorkoutOut)
async def get_workout(workout_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workout).where(Workout.id == workout_id))
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(404, "Workout not found")
    return WorkoutOut.model_validate(workout)


@router.post("/workouts", response_model=WorkoutOut)
async def create_workout(data: WorkoutCreate, db: AsyncSession = Depends(get_db)):
    workout = Workout(**data.model_dump())
    db.add(workout)
    await db.commit()
    await db.refresh(workout)
    return WorkoutOut.model_validate(workout)


@router.delete("/workouts/{workout_id}")
async def delete_workout(workout_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workout).where(Workout.id == workout_id))
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(404, "Workout not found")
    await db.delete(workout)
    await db.commit()
    return {"deleted": True}
