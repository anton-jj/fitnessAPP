from datetime import datetime
from sqlalchemy import select
from ..database import async_session
from ..models import AthleteProfile, TrainingPlan
from .intervals import push_workout
import logging

log = logging.getLogger(__name__)


def workouts_on(plan_data: dict, date: str) -> list[dict]:
    """Every non-rest workout the plan schedules for one date.

    A plan spans many weeks in one record, so this matches on the date —
    matching on weekday name would push week 1's Monday every Monday of the
    block.
    """
    days = [d for w in plan_data.get("weeks", []) for d in w.get("days", [])]
    days += plan_data.get("days", [])
    return [
        workout
        for day in days if day.get("date") == date
        for workout in day.get("workouts", [])
        if workout.get("workout_type") != "rest"
    ]


async def push_todays_workouts():
    """Daily scheduled job: push today's workouts to intervals.icu for watch sync."""
    async with async_session() as db:
        result = await db.execute(select(AthleteProfile).limit(1))
        profile = result.scalar_one_or_none()
        if not profile or not profile.auto_push:
            return

        # Local time, not UTC: the scheduler fires this at 05:00 local, so
        # asking UTC what day it is would push the wrong day's sessions for
        # anyone far enough from Greenwich.
        today = datetime.now().strftime("%Y-%m-%d")

        plan_result = await db.execute(
            select(TrainingPlan)
            .where(TrainingPlan.status.in_(["active", "upcoming"]))
            .order_by(TrainingPlan.created_at.desc())
        )
        plan = plan_result.scalars().first()
        if not plan or not plan.plan_data:
            log.info("No active plan, skipping auto-push")
            return

        workouts = workouts_on(plan.plan_data, today)
        if not workouts:
            log.info(f"Nothing scheduled for {today}, skipping auto-push")
            return

        pushed = 0
        for workout in workouts:
            result = await push_workout(db, workout, today)
            if result.get("ok"):
                pushed += 1
                log.info(f"Pushed workout '{workout.get('name')}' for {today}")
            else:
                log.warning(
                    f"Failed to push '{workout.get('name')}' for {today}: {result.get('error')}"
                )

        log.info(f"Auto-push complete: {pushed}/{len(workouts)} workouts pushed for {today}")
