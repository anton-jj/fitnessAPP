from datetime import datetime
from sqlalchemy import select
from ..database import async_session
from ..models import AthleteProfile, TrainingPlan
from .intervals import push_workout
import logging

log = logging.getLogger(__name__)


async def push_todays_workouts():
    """Daily scheduled job: push today's workouts to intervals.icu for watch sync."""
    async with async_session() as db:
        result = await db.execute(select(AthleteProfile).limit(1))
        profile = result.scalar_one_or_none()
        if not profile or not profile.auto_push:
            return

        today = datetime.utcnow().strftime("%Y-%m-%d")

        plan_result = await db.execute(
            select(TrainingPlan)
            .where(TrainingPlan.status.in_(["active", "upcoming"]))
            .order_by(TrainingPlan.created_at.desc())
        )
        plan = plan_result.scalars().first()
        if not plan or not plan.plan_data:
            log.info("No active plan, skipping auto-push")
            return

        # A plan spans many weeks in one record, so match on date — matching on
        # weekday name would push week 1's Monday every Monday of the block.
        data = plan.plan_data
        all_days = [d for w in data.get("weeks", []) for d in w.get("days", [])]
        all_days += data.get("days", [])

        workouts = [
            w
            for day in all_days if day.get("date") == today
            for w in day.get("workouts", [])
            if w.get("workout_type") != "rest"
        ]
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
