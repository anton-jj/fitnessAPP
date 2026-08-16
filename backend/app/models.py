from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, JSON
from .database import Base
from datetime import datetime


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    strava_id = Column(String, index=True)
    intervals_id = Column(String, index=True)
    coros_id = Column(String, index=True)

    sport_type = Column(String, index=True)
    name = Column(String)
    description = Column(Text)
    start_time = Column(DateTime, index=True)
    elapsed_time = Column(Integer)  # seconds
    moving_time = Column(Integer)
    distance = Column(Float)  # meters
    elevation_gain = Column(Float)
    calories = Column(Float)

    avg_hr = Column(Float)
    max_hr = Column(Float)
    avg_power = Column(Float)
    max_power = Column(Float)
    normalized_power = Column(Float)
    avg_cadence = Column(Float)
    avg_pace = Column(Float)  # min/km
    avg_speed = Column(Float)  # m/s

    tss = Column(Float)
    intensity_factor = Column(Float)
    training_load = Column(Float)

    map_polyline = Column(Text)
    streams = Column(JSON)  # {time:[], hr:[], power:[], cadence:[], altitude:[], pace:[]}
    laps = Column(JSON)
    source = Column(String)  # comma-separated: "strava,intervals"

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Wellness(Base):
    __tablename__ = "wellness"

    id = Column(Integer, primary_key=True)
    date = Column(String, unique=True, index=True)  # YYYY-MM-DD
    resting_hr = Column(Float)
    hrv = Column(Float)
    sleep_hours = Column(Float)
    sleep_quality = Column(Float)
    weight = Column(Float)
    fatigue = Column(Float)
    mood = Column(Float)
    soreness = Column(Float)
    stress = Column(Float)
    source = Column(String)


class FitnessData(Base):
    __tablename__ = "fitness_data"

    id = Column(Integer, primary_key=True)
    date = Column(String, unique=True, index=True)
    ctl = Column(Float)  # chronic training load (fitness)
    atl = Column(Float)  # acute training load (fatigue)
    tsb = Column(Float)  # training stress balance (form)
    daily_tss = Column(Float)


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True)
    provider = Column(String, unique=True)  # strava, intervals, coros
    access_token = Column(String)
    refresh_token = Column(String)
    expires_at = Column(Integer)
    athlete_id = Column(String)
    api_key = Column(String)
    extra = Column(JSON)


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(Text)
    sport = Column(String, default="cycling")
    workout_type = Column(String)  # intervals, sweetspot, threshold, endurance, etc.
    steps = Column(JSON)  # structured workout steps
    duration_seconds = Column(Integer)
    tss_estimate = Column(Float)
    source = Column(String, default="manual")  # manual, ai, imported
    created_at = Column(DateTime, default=datetime.utcnow)


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id = Column(Integer, primary_key=True)
    week = Column(String, index=True)  # "2026-W31"
    name = Column(String)
    description = Column(Text)
    plan_data = Column(JSON)  # full plan JSON from AI
    status = Column(String, default="active")  # active, completed, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WeeklyGoal(Base):
    __tablename__ = "weekly_goals"

    id = Column(Integer, primary_key=True)
    week = Column(String, unique=True, index=True)  # "2026-W31"
    hours_target = Column(Float)
    quality_sessions = Column(JSON, default=list)  # [{sport, label, done}]
    notes = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AthleteProfile(Base):
    __tablename__ = "athlete_profile"

    id = Column(Integer, primary_key=True)
    experience_level = Column(String)  # beginner, intermediate, advanced
    primary_sport = Column(String)  # cycling, running, triathlon, etc.
    goal = Column(String)  # general_fitness, event, performance, weight_loss
    goal_event = Column(String)  # event name/type if applicable
    goal_date = Column(String)  # YYYY-MM-DD target date
    weaknesses = Column(JSON)  # ["vo2max", "endurance", "sprint", "threshold", "climbing"]
    strengths = Column(JSON)  # same options
    sports = Column(JSON)  # ["cycling", "running", "swimming", "strength"]
    weekly_hours = Column(Float, default=8)  # hours available per week (the ceiling)
    current_weekly_hours = Column(Float)  # what they train now — the ramp's starting point
    preferred_hard_days = Column(JSON)  # ["tuesday", "thursday", "saturday"]
    preferred_rest_days = Column(JSON)  # ["monday", "friday"]
    plan_duration_weeks = Column(Integer, default=8)
    has_trainer = Column(Boolean, default=False)
    has_power_meter = Column(Boolean, default=False)
    has_hr_monitor = Column(Boolean, default=True)
    max_sessions_per_day = Column(Integer, default=1)
    # Hard limits per discipline, e.g. {"swimming": {"max_sessions": 2,
    # "days": ["tuesday", "thursday"]}} for an athlete whose pool is only open
    # on those days. Constraints, not preferences — the planner must not
    # schedule training the athlete cannot physically do.
    sport_limits = Column(JSON)
    # Recovery-week cadence: "auto" (experience-derived cycle), "extended"
    # (athlete-chosen cycle length, see recovery_cycle_weeks), or "off" (no
    # periodic recovery week — the consecutive-build-week ceiling in
    # plan_builder still forces one, this only disables the regular cadence).
    recovery_mode = Column(String, default="auto")
    recovery_cycle_weeks = Column(Integer)  # only used when recovery_mode == "extended"
    # "ramp": progressive overload to the stated weekly_hours (default).
    # "steady": ramp in briefly, then hold volume flat — see
    # plan_builder.compute_volume_progression for the history-relative cap.
    volume_progression_mode = Column(String, default="ramp")
    # "standard" (methodology-agnostic, the default) or "norwegian"
    # (double-threshold days named and coached explicitly).
    training_style = Column(String, default="standard")
    auto_push = Column(Boolean, default=False)  # auto-push workouts to watch daily
    notes = Column(Text)
    onboarding_complete = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text)
