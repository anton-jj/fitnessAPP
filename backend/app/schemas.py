from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ActivityOut(BaseModel):
    id: int
    strava_id: Optional[str] = None
    intervals_id: Optional[str] = None
    sport_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    elapsed_time: Optional[int] = None
    moving_time: Optional[int] = None
    distance: Optional[float] = None
    elevation_gain: Optional[float] = None
    calories: Optional[float] = None
    avg_hr: Optional[float] = None
    max_hr: Optional[float] = None
    avg_power: Optional[float] = None
    max_power: Optional[float] = None
    normalized_power: Optional[float] = None
    avg_cadence: Optional[float] = None
    avg_pace: Optional[float] = None
    avg_speed: Optional[float] = None
    tss: Optional[float] = None
    intensity_factor: Optional[float] = None
    training_load: Optional[float] = None
    map_polyline: Optional[str] = None
    streams: Optional[dict] = None
    laps: Optional[list] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class WellnessOut(BaseModel):
    id: int
    date: str
    resting_hr: Optional[float] = None
    hrv: Optional[float] = None
    sleep_hours: Optional[float] = None
    sleep_quality: Optional[float] = None
    weight: Optional[float] = None
    fatigue: Optional[float] = None
    mood: Optional[float] = None
    soreness: Optional[float] = None
    stress: Optional[float] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True


class FitnessDataOut(BaseModel):
    date: str
    ctl: Optional[float] = None
    atl: Optional[float] = None
    tsb: Optional[float] = None
    daily_tss: Optional[float] = None

    class Config:
        from_attributes = True


class DashboardOut(BaseModel):
    fitness_data: list[FitnessDataOut]
    weekly_summary: dict
    recent_activities: list[ActivityOut]
    current_ctl: Optional[float] = None
    current_atl: Optional[float] = None
    current_tsb: Optional[float] = None


class WorkoutStep(BaseModel):
    type: str  # warmup, interval, rest, cooldown, steady
    duration: int  # seconds
    power: Optional[float] = None  # fraction of FTP (e.g. 0.9 = 90%)
    power_start: Optional[float] = None  # for ramp steps
    power_end: Optional[float] = None
    cadence: Optional[int] = None
    repeat: Optional[int] = None
    rest: Optional["WorkoutStep"] = None


class WorkoutOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    sport: str
    workout_type: Optional[str] = None
    steps: list[dict]
    duration_seconds: Optional[int] = None
    tss_estimate: Optional[float] = None
    source: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkoutCreate(BaseModel):
    name: str
    description: Optional[str] = None
    sport: str = "cycling"
    workout_type: Optional[str] = None
    steps: list[dict]
    duration_seconds: Optional[int] = None
    tss_estimate: Optional[float] = None
    source: str = "manual"


class ManualActivityCreate(BaseModel):
    sport_type: str  # swimming, strength, running, cycling, etc.
    name: Optional[str] = None
    duration_minutes: int
    distance_km: Optional[float] = None
    notes: Optional[str] = None
    start_time: Optional[datetime] = None


class WeeklyGoal(BaseModel):
    week: str  # ISO week "2026-W31"
    hours_target: Optional[float] = None
    quality_sessions: list[dict] = []  # [{sport, label, done}]


class TrainerRideData(BaseModel):
    duration_seconds: int
    power_data: list[int]  # power samples (1 per second)
    hr_data: list[int] = []
    cadence_data: list[int] = []
    avg_power: Optional[int] = None
    normalized_power: Optional[int] = None
    ftp: int = 200


class AISessionRequest(BaseModel):
    sport: str = "cycling"
    session_type: str = "intervals"  # intervals, tempo, sweetspot, threshold, endurance, vo2max
    duration_minutes: int = 60
    notes: Optional[str] = None


class SyncStatus(BaseModel):
    strava_connected: bool
    intervals_connected: bool
    last_sync: Optional[str] = None
    activities_count: int
    sync_in_progress: bool


class SettingsUpdate(BaseModel):
    ftp: Optional[int] = None
    threshold_pace: Optional[int] = None  # seconds per km
    swim_css_pace: Optional[int] = None  # seconds per 100m
    sync_interval: Optional[int] = None
    ai_provider: Optional[str] = None
    strava_client_id: Optional[str] = None
    strava_client_secret: Optional[str] = None
    intervals_api_key: Optional[str] = None
    intervals_athlete_id: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model_light: Optional[str] = None
    ollama_model_heavy: Optional[str] = None
    claude_model_light: Optional[str] = None
    claude_model_heavy: Optional[str] = None
    openai_model_light: Optional[str] = None
    openai_model_heavy: Optional[str] = None
