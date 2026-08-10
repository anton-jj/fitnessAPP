"""
Constraint-based training plan builder.

Training planning is treated as a constrained optimization problem.
The goal: maximize long-term fitness while respecting available time,
recovery capacity, injury risk, and event requirements.

Training distribution emerges from the athlete's constraints —
not from a predefined methodology. The guiding question:
"What is the minimum intensity needed to achieve the necessary
training stimulus while remaining sustainable?"

Volume is the preferred adaptation driver (less fatigue per unit of
fitness). Intensity compensates only when volume cannot increase.

The plan builder computes the ENVELOPE — duration targets, quality
session slots, sport distribution, recovery scheduling, safety bounds.
The AI coach fills in workout design, progression, and coaching rationale.

Two rules drive most of the shape of a week:

  Frequency follows volume. Extra hours buy extra sessions, not longer
  ones — roughly 1 session per discipline below 5h/week, 2 by 5-9h,
  3 by 9-14h, 4+ beyond that. Spreading 12 hours over seven single
  sessions gives 100-minute averages and only two swims; the same hours
  as ten sessions gives a triathlete 3-3-3 at sane lengths.

  Added frequency goes to the cheapest discipline first. Swimming and
  cycling absorb extra sessions without much orthopedic cost, so they
  grow before running does.
"""
from datetime import datetime, timedelta

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# --- Zone & speed reference tables ---

ZONE_DEFINITIONS = {
    "recovery": {"pct_ftp": (0.40, 0.55), "rpe": "1-2", "zone": "Zone 1"},
    "endurance": {"pct_ftp": (0.56, 0.75), "rpe": "2-3", "zone": "Zone 2"},
    "tempo": {"pct_ftp": (0.76, 0.87), "rpe": "4-5", "zone": "Zone 3"},
    "sweetspot": {"pct_ftp": (0.88, 0.94), "rpe": "5-6", "zone": "Zone 3-4"},
    "threshold": {"pct_ftp": (0.95, 1.05), "rpe": "6-7", "zone": "Zone 4"},
    "vo2max": {"pct_ftp": (1.06, 1.20), "rpe": "8-9", "zone": "Zone 5"},
    "anaerobic": {"pct_ftp": (1.21, 1.50), "rpe": "9-10", "zone": "Zone 6"},
}

SPORT_SPEEDS = {
    "cycling": {
        "endurance": 28, "tempo": 30, "sweetspot": 31, "threshold": 33,
        "vo2max": 28, "anaerobic": 25, "recovery": 24, "easy": 26,
    },
    "running": {
        "endurance": 10.5, "tempo": 12.0, "sweetspot": 12.5, "threshold": 13.5,
        "vo2max": 11.0, "anaerobic": 10.0, "recovery": 9.0, "easy": 10.0,
    },
    "swimming": {
        "endurance": 2.8, "tempo": 3.0, "sweetspot": 3.1, "threshold": 3.3,
        "vo2max": 3.0, "anaerobic": 2.8, "recovery": 2.5, "easy": 2.6,
    },
}

IF_TABLE = {
    "recovery": 0.55, "endurance": 0.65, "tempo": 0.82, "sweetspot": 0.90,
    "threshold": 0.98, "vo2max": 0.95, "anaerobic": 0.85, "easy": 0.60,
    "strength": 0.50, "rest": 0.0,
}

# --- Sport cost model ---
# Running: highest orthopedic stress — increase cautiously, protect key sessions
# Cycling: lowest stress — primary method to add aerobic volume
# Swimming: technique-limited — frequency > duration
# Strength: adds fatigue — heavy lower-body must not precede key run sessions

SPORT_PROPERTIES = {
    "running": {
        "stress_factor": 1.0,
        "max_session_minutes": 150,
        "max_easy_minutes": 90,
        "max_long_minutes": 150,
        "max_weekly_increase_pct": 0.12,
        "typical_endurance_minutes": 60,
        "session_weight": 1.0,
        "volume_weight": 0.95,
        "max_weekly_sessions": 7,
        "frequency_notes": "protect key sessions, cautious volume increases",
    },
    "cycling": {
        "stress_factor": 0.4,
        "max_session_minutes": 300,
        "max_easy_minutes": 150,
        "max_long_minutes": 240,
        "max_weekly_increase_pct": 0.20,
        "typical_endurance_minutes": 105,
        # The bike carries the block. Extra hours buy extra rides first, and
        # each ride is a little longer than the others — but frequency leads,
        # so most of the share comes from session_weight, not volume_weight.
        "session_weight": 1.35,
        "volume_weight": 1.2,
        "max_weekly_sessions": 10,
        "frequency_notes": "primary volume expander, handles long sessions well",
    },
    "swimming": {
        "stress_factor": 0.2,
        "max_session_minutes": 75,
        "max_easy_minutes": 60,
        "max_long_minutes": 75,
        "max_weekly_increase_pct": 0.20,
        "typical_endurance_minutes": 45,
        "session_weight": 1.0,
        "volume_weight": 0.80,
        "max_weekly_sessions": 6,
        "frequency_priority": True,
        "frequency_notes": "frequency is more valuable than long sessions",
    },
    "strength": {
        "stress_factor": 0.5,
        "max_session_minutes": 45,
        "max_easy_minutes": 45,
        "max_long_minutes": 45,
        "avoid_before_key_run": True,
        "frequency_notes": "heavy lower-body should not interfere with key run workouts",
    },
}

# --- Event requirements ---
# As race distance increases:
#   - required durability & volume increases
#   - ability to substitute volume with intensity decreases
# The planner must recognize when event requirements exceed available time
# instead of compensating with excessive intensity.

EVENT_REQUIREMENTS = {
    "5k": {
        "typical_weekly_hours": 5,
        "min_viable_hours": 3,
        "intensity_substitution": 0.40,
        "long_session_essential": False,
        "volume_priority": 0.4,
    },
    "10k": {
        "typical_weekly_hours": 6,
        "min_viable_hours": 4,
        "intensity_substitution": 0.30,
        "long_session_essential": False,
        "volume_priority": 0.5,
    },
    "half_marathon": {
        "typical_weekly_hours": 8,
        "min_viable_hours": 5,
        "intensity_substitution": 0.20,
        "long_session_essential": True,
        "volume_priority": 0.6,
    },
    "marathon": {
        "typical_weekly_hours": 10,
        "min_viable_hours": 7,
        "intensity_substitution": 0.10,
        "long_session_essential": True,
        "volume_priority": 0.8,
    },
    "olympic_triathlon": {
        "typical_weekly_hours": 10,
        "min_viable_hours": 7,
        "intensity_substitution": 0.15,
        "long_session_essential": True,
        "volume_priority": 0.7,
    },
    "ironman_70.3": {
        "typical_weekly_hours": 12,
        "min_viable_hours": 8,
        "intensity_substitution": 0.10,
        "long_session_essential": True,
        "volume_priority": 0.8,
    },
    "ironman": {
        "typical_weekly_hours": 16,
        "min_viable_hours": 12,
        "intensity_substitution": 0.05,
        "long_session_essential": True,
        "volume_priority": 0.95,
    },
    "sprint_triathlon": {
        "typical_weekly_hours": 6,
        "min_viable_hours": 4,
        "intensity_substitution": 0.30,
        "long_session_essential": False,
        "volume_priority": 0.5,
    },
    "general_fitness": {
        "typical_weekly_hours": 5,
        "min_viable_hours": 3,
        "intensity_substitution": 0.30,
        "long_session_essential": False,
        "volume_priority": 0.5,
    },
}


# --- Core computations ---

def compute_capacity_assessment(weekly_hours: float, event: str,
                                sports: list[str],
                                experience: str = "intermediate") -> dict:
    """Compute the stimulus gap and capacity assessment.

    Returns a dict describing whether the athlete's available time is
    sufficient, marginal, or insufficient for their goal — and how
    training density should be adjusted accordingly.
    """
    event_reqs = EVENT_REQUIREMENTS.get(event, EVENT_REQUIREMENTS["general_fitness"])
    typical = event_reqs["typical_weekly_hours"]
    min_viable = event_reqs["min_viable_hours"]

    capacity_ratio = weekly_hours / typical if typical > 0 else 1.0

    if weekly_hours >= typical:
        strategy = "surplus"
        density_note = (
            "Training capacity exceeds requirements. Increase easy volume, "
            "keep intensity conservative, progress gradually, prioritize consistency."
        )
    elif weekly_hours >= min_viable:
        gap_severity = 1.0 - (weekly_hours - min_viable) / (typical - min_viable)
        strategy = "tight" if gap_severity > 0.5 else "manageable"
        density_note = (
            "Training time is limited. Maintain appropriate volume, "
            "increase training density moderately, add threshold or "
            "race-specific work. Keep recovery adequate."
        )
    else:
        strategy = "insufficient"
        density_note = (
            "Available training time is insufficient for this goal. "
            "Do NOT compensate with excessive intensity. "
            "Recommend more training time, longer preparation, or adjusted expectations."
        )

    sport_stress = sum(
        SPORT_PROPERTIES.get(s, {}).get("stress_factor", 0.5)
        for s in sports if s != "strength"
    ) / max(1, len([s for s in sports if s != "strength"]))

    return {
        "capacity_ratio": round(capacity_ratio, 2),
        "strategy": strategy,
        "density_note": density_note,
        "typical_hours_for_event": typical,
        "min_viable_hours": min_viable,
        "intensity_substitution": event_reqs["intensity_substitution"],
        "long_session_essential": event_reqs["long_session_essential"],
        "volume_priority": event_reqs["volume_priority"],
        "avg_sport_stress": round(sport_stress, 2),
    }


# Average endurance session length across a week, used to turn available hours
# into a session count. Sessions get longer as volume grows — a 4h athlete
# trains in 50-minute blocks, a 16h athlete in 90-minute ones — so this is not
# a constant.
def _average_session_hours(weekly_hours: float) -> float:
    # Interpolated rather than banded: a step function makes 14h produce fewer
    # sessions than 13h, which is not something a plan should ever do.
    low_h, low_len = 4.0, 0.85
    high_h, high_len = 18.0, 1.35
    if weekly_hours <= low_h:
        return low_len
    if weekly_hours >= high_h:
        return high_len
    span = (weekly_hours - low_h) / (high_h - low_h)
    return low_len + span * (high_len - low_len)


def compute_session_target(weekly_hours: float, n_sports: int, n_days: int,
                           max_sessions_per_day: int = 1) -> int:
    """How many endurance sessions the week should contain.

    Frequency has to follow volume, not the calendar. Spreading 12 hours over
    seven days gives 100-minute averages and only two swims; the same hours as
    nine or ten sessions gives a triathlete 3-3-3 with sane session lengths.

    Roughly:  <5h -> 1 per sport,  5-9h -> 2 per sport,
              9-14h -> 3 per sport,  14h+ -> 4+ per sport
    """
    target = round(weekly_hours / _average_session_hours(weekly_hours))
    target = max(target, n_sports)
    return min(target, n_days * max(1, max_sessions_per_day))


# How much the athlete's main discipline outranks the others when sessions are
# shared out. Large enough that a marathoner runs more than they ride, even
# though the bike is the cheaper place to put volume.
PRIMARY_SESSION_BONUS = 1.40


def _sport_ceiling(sport: str, limits: dict | None = None) -> int:
    """Weekly session ceiling for a discipline, athlete's limit taking priority."""
    default = SPORT_PROPERTIES.get(sport, {}).get("max_weekly_sessions", 7)
    stated = (limits or {}).get(sport, {}).get("max_sessions")
    return min(default, stated) if stated else default


def _allocate_sport_sessions(real_sports: list[str], total_sessions: int,
                             primary_sport: str | None,
                             limits: dict | None = None) -> dict[str, int]:
    """Split the week's sessions across disciplines.

    Everyone gets one, then the rest are dealt round-robin starting with the
    primary sport and then the least orthopedically costly one. That keeps the
    common case even (3-3-3 for a triathlete) while sending any odd session to
    swimming and cycling — the disciplines that can absorb extra frequency
    without extra injury risk.
    """
    counts = {s: 1 for s in real_sports}
    remaining = total_sessions - len(real_sports)
    if remaining <= 0:
        return counts

    # Extras are shared by session weight, not evenly: the bike absorbs the
    # most because a ride costs less recovery than a run of the same length,
    # and swimming outranks running because frequency is what it needs.
    # Take the stronger of the two claims rather than multiplying them: for a
    # triathlete cycling is both the volume engine and the primary sport, and
    # stacking the bonuses buries swimming and running.
    weights = {
        sport: max(
            SPORT_PROPERTIES.get(sport, {}).get("session_weight", 1.0),
            PRIMARY_SESSION_BONUS if sport == primary_sport else 0.0,
        )
        for sport in real_sports
    }
    total_weight = sum(weights.values()) or 1.0

    exact = {s: remaining * w / total_weight for s, w in weights.items()}
    extra = {s: int(v) for s, v in exact.items()}
    leftover = remaining - sum(extra.values())
    for sport in sorted(exact, key=lambda s: exact[s] - extra[s], reverse=True):
        if leftover <= 0:
            break
        extra[sport] += 1
        leftover -= 1

    for sport, n in extra.items():
        counts[sport] += n

    # Respect per-sport ceilings, pushing any overflow to whoever has room.
    def ceiling(sport: str) -> int:
        return _sport_ceiling(sport, limits)

    overflow = 0
    for sport in real_sports:
        if counts[sport] > ceiling(sport):
            overflow += counts[sport] - ceiling(sport)
            counts[sport] = ceiling(sport)

    order = sorted(real_sports, key=lambda s: -weights[s])
    while overflow > 0:
        placed = False
        for sport in order:
            if counts[sport] < ceiling(sport):
                counts[sport] += 1
                overflow -= 1
                placed = True
                break
        if not placed:
            break

    return counts


def compute_quality_sessions(weekly_hours: float, experience: str,
                             capacity_strategy: str) -> int:
    """Quality sessions stay roughly constant regardless of volume.

    More hours → more easy volume, NOT more quality sessions.
    This is a fundamental principle: absolute quality work changes
    only modestly as volume increases.

    5h/wk  → 2 quality sessions
    8h/wk  → 2 quality sessions
    15h/wk → still around 2-3 quality sessions
    """
    if capacity_strategy == "insufficient":
        return 1 if experience == "beginner" else 2

    if experience == "beginner":
        return 1 if weekly_hours < 4 else 2

    if weekly_hours < 10:
        return 2
    return 3


def compute_training_density(weekly_hours: float,
                             quality_sessions: int) -> dict:
    """Compute how training time is split between easy and quality.

    The distribution emerges from the constraints, not from a fixed
    methodology. More hours → lower density (more easy). Fewer hours →
    higher density (relatively more quality per hour).

    Examples:
      5h/wk, 2 quality: ~40% quality, 60% easy
      8h/wk, 2 quality: ~25% quality, 75% easy
     15h/wk, 3 quality: ~20% quality, 80% easy
    """
    quality_minutes_per_session = 65
    total_quality = quality_sessions * quality_minutes_per_session
    total_minutes = weekly_hours * 60
    quality_fraction = min(0.45, total_quality / max(total_minutes, 1))
    easy_fraction = 1.0 - quality_fraction

    return {
        "quality_fraction": round(quality_fraction, 2),
        "easy_fraction": round(easy_fraction, 2),
        "quality_minutes_total": total_quality,
        "easy_minutes_total": round(total_minutes - total_quality),
    }


def compute_recovery_schedule(total_weeks: int,
                              experience: str) -> list[str]:
    """Plan recovery weeks with a 20-40% volume reduction.

    Beginners: every 4 weeks (3 build + 1 recovery)
    Intermediate: every 5 weeks (4 build + 1 recovery)
    Advanced: every 6 weeks (5 build + 1 recovery)

    Cutting back every third week costs more fitness than it saves for anyone
    past their first season — the point of a recovery week is to absorb
    accumulated load, and at moderate volume that load takes longer to build.
    """
    if experience == "beginner":
        build_count = 3
    elif experience == "advanced":
        build_count = 5
    else:
        build_count = 4

    cycle = build_count + 1
    week_types = []
    for i in range(total_weeks):
        pos_in_cycle = i % cycle
        if pos_in_cycle >= build_count:
            week_types.append("recovery")
        else:
            week_types.append("build")

    return week_types


# --- Where the block starts ---

def _resolve_starting_volume(profile: dict) -> tuple[float | None, str]:
    """Pick the opening volume, and say where the number came from.

    An explicit answer wins — the athlete may know something the data does
    not, like a block of travel ahead. Otherwise observed history wins over a
    default, because what someone actually trained last month predicts next
    month better than a slider they moved once during onboarding.
    """
    stated = profile.get("current_weekly_hours")
    observed = profile.get("observed_weekly_hours")

    if stated:
        return float(stated), "stated"
    if observed:
        return float(observed), "observed"
    return None, "default"


# Training Stress Balance: negative means carrying fatigue, positive means
# fresh. These thresholds are deliberately wide — TSB swings a lot day to day
# and only a clear signal should change how a block opens.
TSB_BURIED = -25
TSB_TIRED = -10
TSB_VERY_FRESH = 15


def compute_readiness(fitness_context: dict | None) -> dict:
    """Adjust the opening week for how the athlete is actually turning up.

    Starting a build block on top of deep fatigue is how people get injured or
    quit in week two. If the athlete arrives buried, the block opens easier and
    the ramp catches up later.
    """
    if not fitness_context:
        return {"state": "unknown", "multiplier": 1.0, "note": ""}

    tsb = fitness_context.get("tsb")
    ctl = fitness_context.get("ctl")

    if tsb is None:
        return {"state": "unknown", "multiplier": 1.0, "note": ""}

    if tsb <= TSB_BURIED:
        return {
            "state": "fatigued",
            "multiplier": 0.90,
            "note": (
                f"Starting {round((1 - 0.85) * 100)}% easier than planned: your form "
                f"(TSB {tsb:.0f}) says you are carrying real fatigue into this block. "
                "The ramp catches up once you have absorbed it."
            ),
        }
    if tsb <= TSB_TIRED:
        return {
            "state": "tired",
            "multiplier": 0.95,
            "note": (
                f"Opening slightly easier — TSB {tsb:.0f} suggests you are still "
                "carrying fatigue from recent training."
            ),
        }
    if tsb >= TSB_VERY_FRESH and ctl is not None and ctl < 40:
        return {
            "state": "detrained",
            "multiplier": 1.0,
            "note": (
                f"Your fitness (CTL {ctl:.0f}) is low and you are well rested, so "
                "this block is about rebuilding consistency before intensity."
            ),
        }
    return {"state": "ready", "multiplier": 1.0, "note": ""}


def _assess_progression(multipliers: list[float], week_types: list[str],
                        weekly_hours: float, current_hours: float | None,
                        experience: str) -> dict:
    """Describe the block's volume ramp, and say so when it cannot reach the top.

    Progressing faster than the safe weekly increase is not an option, so a
    block that is too short to bridge the gap should say that plainly rather
    than quietly under-delivering on the athlete's stated hours.
    """
    build = [m for m, t in zip(multipliers, week_types) if t not in ("recovery", "taper")]
    if not build:
        return {}

    start_hours = round(build[0] * weekly_hours, 1)
    peak_hours = round(max(build) * weekly_hours, 1)
    assessment = {
        "start_hours": start_hours,
        "peak_hours": peak_hours,
        "build_weeks": len(build),
        "weekly_increase_pct": round(
            ((build[1] / build[0] - 1) * 100) if len(build) > 1 else 0, 1
        ),
        "reaches_target": max(build) >= 0.98,
    }

    if not assessment["reaches_target"]:
        weeks_needed = 0
        level = build[0]
        step = MAX_WEEKLY_INCREASE.get(experience, DEFAULT_MAX_INCREASE)
        while level < 0.98 and weeks_needed < 100:
            level *= 1 + step
            weeks_needed += 1
        # Build weeks are roughly 3 in every 4 once recovery weeks are added back.
        assessment["note"] = (
            f"This block ramps from {start_hours}h to {peak_hours}h/week. Going from "
            f"{start_hours}h to the full {weekly_hours}h safely needs about "
            f"{round(weeks_needed * 4 / 3)} weeks of training — extend the plan if "
            f"reaching {weekly_hours}h matters, rather than progressing faster."
        )
    return assessment


def compute_volume_reduction(week_type: str, experience: str) -> float:
    """Recovery week reduction: 20-40% depending on experience."""
    if week_type == "recovery":
        if experience == "beginner":
            return 0.60
        elif experience == "advanced":
            return 0.70
        else:
            return 0.65
    elif week_type == "taper":
        return 0.50
    return 1.0


MAX_WEEKLY_INCREASE = {"beginner": 0.08, "advanced": 0.12}
DEFAULT_MAX_INCREASE = 0.10

# Never open a block below this fraction of the athlete's stated hours. They
# told us the time is available; starting much lower wastes the block.
MIN_START_FRACTION = 0.85


def compute_volume_progression(week_types: list[str], experience: str,
                               start_fraction: float | None = None) -> list[float]:
    """Progressive overload across the block.

    The athlete's stated weekly hours is the time they actually have, so it is
    a ceiling the peak build week reaches — never a midpoint to ramp past.

    The ramp is fitted to the block: the starting level and the weekly step are
    solved so that the LAST build week lands on the ceiling. A fixed step would
    either top out in week 5 of a 20-week plan and then repeat the same week
    fourteen times, or never reach the athlete's hours at all in a 4-week block.
    """
    build_weeks = sum(1 for w in week_types if w not in ("recovery", "taper"))
    max_step = MAX_WEEKLY_INCREASE.get(experience, DEFAULT_MAX_INCREASE)

    if start_fraction is not None:
        start = min(max(start_fraction, 0.4), 1.0)
    elif build_weeks > 1:
        # Lowest start that still reaches the ceiling without exceeding the
        # safe weekly increase, floored so we do not start absurdly easy.
        start = max(MIN_START_FRACTION, 1.0 / (1 + max_step) ** (build_weeks - 1))
    else:
        start = 1.0

    if build_weeks > 1:
        step = min(max_step, (1.0 / start) ** (1 / (build_weeks - 1)) - 1)
    else:
        step = 0.0

    level = start
    multipliers = []
    for week_type in week_types:
        if week_type in ("recovery", "taper"):
            multipliers.append(round(level * compute_volume_reduction(week_type, experience), 3))
        else:
            multipliers.append(round(level, 3))
            level = min(level * (1 + step), 1.0)
    return multipliers


# --- Week construction ---

MIN_ENDURANCE_DURATION = 45
MIN_SESSION_DURATION = 30

STRENGTH_SESSION_MINUTES = 30
MAX_STRENGTH_SESSIONS = 2


def _round_duration(minutes: float) -> int:
    return max(20, round(minutes / 5) * 5)


def compute_tss(duration_minutes: float, intensity_factor: float) -> float:
    return (duration_minutes * 60 * intensity_factor ** 2) / 36


def _estimate_distance(sport: str, workout_type: str, duration_minutes: int,
                       threshold_pace: int = 300, css_pace: int = 105) -> float:
    """Distance implied by the prescribed pace, so it matches the workout."""
    if sport == "running":
        pace = run_pace_seconds(workout_type, threshold_pace)
        return round(duration_minutes * 60 / pace, 1)
    if sport == "swimming":
        pace = swim_pace_seconds(workout_type, css_pace)
        return round(duration_minutes * 60 / pace / 10, 2)
    speeds = SPORT_SPEEDS.get(sport, SPORT_SPEEDS["cycling"])
    speed = speeds.get(workout_type, speeds.get("endurance", 28))
    return round(speed * duration_minutes / 60, 1)


# Which discipline anchors the week when the athlete has not said. Triathlon
# events point at the bike: it carries the most race time and the most
# trainable volume per unit of fatigue.
EVENT_PRIMARY_SPORT = {
    "5k": "running",
    "10k": "running",
    "half_marathon": "running",
    "marathon": "running",
    "sprint_triathlon": "cycling",
    "olympic_triathlon": "cycling",
    "ironman_70.3": "cycling",
    "ironman": "cycling",
}


def _build_sport_schedule(sports: list[str], quality_days: list[str],
                          easy_days: list[str], primary_sport: str | None,
                          total_sessions: int,
                          max_sessions_per_day: int = 1,
                          limits: dict | None = None) -> list[dict]:
    """Place every session of the week on a day.

    Returns a flat list of {day, sport} slots — more than one per day once the
    volume calls for it. Session counts come from the frequency model, so this
    only decides placement: quality days go to different disciplines, weekend
    days to whichever sport carries the longest session, and second sessions
    land on the lightest non-quality days in a different sport from the first.
    """
    real_sports = [s for s in sports if s != "strength"]
    if not real_sports:
        real_sports = ["cycling"]

    training_days = list(quality_days) + list(easy_days)
    if not training_days:
        return []

    remaining = _allocate_sport_sessions(real_sports, total_sessions,
                                         primary_sport, limits)
    slots: list[dict] = []
    day_sports: dict[str, set[str]] = {}

    def allowed(sport: str, day: str) -> bool:
        """A discipline the athlete can only do on certain days — pool hours,
        a club session, a shared turbo — must never be scheduled elsewhere."""
        days = (limits or {}).get(sport, {}).get("days")
        return not days or day in days

    def usable(day: str) -> list[str]:
        return [s for s in real_sports if remaining[s] > 0 and allowed(s, day)]

    def place(sport: str, day: str) -> None:
        slots.append({"day": day, "sport": sport})
        day_sports.setdefault(day, set()).add(sport)
        remaining[sport] -= 1

    # 1. Quality days — one per discipline where possible.
    quality_used: set[str] = set()
    for day in quality_days:
        available = usable(day)
        if not available:
            continue
        fresh = [s for s in available if s not in quality_used] or available
        pick = max(fresh, key=lambda s: (remaining[s], s == primary_sport))
        quality_used.add(pick)
        place(pick, day)

    # 2. Weekends carry the long sessions.
    leftover = [d for d in easy_days if d not in day_sports]
    weekend_used: set[str] = set()
    for day in ("saturday", "sunday"):
        if day not in leftover:
            continue
        available = usable(day)
        if not available:
            continue
        fresh = [s for s in available if s not in weekend_used] or available
        pick = max(fresh, key=lambda s: (
            s == primary_sport,
            SPORT_PROPERTIES.get(s, {}).get("max_long_minutes", 0),
        ))
        weekend_used.add(pick)
        place(pick, day)
        leftover.remove(day)

    # 3. One session on each remaining day, avoiding the same sport two days
    #    running.
    for day in leftover:
        available = usable(day)
        if not available:
            continue
        previous = day_sports.get(DAY_ORDER[(DAY_ORDER.index(day) - 1) % 7], set())
        spaced = [s for s in available if s not in previous] or available
        place(max(spaced, key=lambda s: remaining[s]), day)

    # 4. Anything still owed becomes a second session. These go on the days
    #    carrying the least so far, and never double up the same discipline.
    if max_sessions_per_day > 1:
        guard = 0
        while any(n > 0 for n in remaining.values()) and guard < 50:
            guard += 1
            candidates = [
                d for d in training_days
                if len(day_sports.get(d, set())) < max_sessions_per_day
                and d not in quality_days
            ] or [
                d for d in training_days
                if len(day_sports.get(d, set())) < max_sessions_per_day
            ]
            if not candidates:
                break
            day = min(candidates, key=lambda d: len(day_sports.get(d, set())))
            available = [s for s in usable(day)
                         if s not in day_sports.get(day, set())]
            if not available:
                # Nothing new can go on the emptiest day; retire it and retry.
                day_sports.setdefault(day, set()).update(real_sports)
                continue
            place(max(available, key=lambda s: remaining[s]), day)

    slots.sort(key=lambda s: DAY_ORDER.index(s["day"]))
    return slots


def _assign_archetypes(schedule: list[dict], quality_days: list[str],
                       long_session_essential: bool) -> list[dict]:
    """Tag each placed session with its archetype.

    Only the first session of a quality day is a quality session — a second
    session that day is there to add easy volume, not more intensity.
    """
    slots = []
    quality_taken: set[str] = set()
    for entry in schedule:
        is_quality = entry["day"] in quality_days and entry["day"] not in quality_taken
        if is_quality:
            quality_taken.add(entry["day"])
        slots.append({
            "day": entry["day"],
            "sport": entry["sport"],
            "archetype": "quality" if is_quality else "easy",
        })

    by_sport: dict[str, list[dict]] = {}
    for slot in slots:
        by_sport.setdefault(slot["sport"], []).append(slot)

    for sport, sport_slots in by_sport.items():
        # Swimming gains more from frequency than from one long swim.
        if SPORT_PROPERTIES.get(sport, {}).get("frequency_priority"):
            continue
        easy_slots = [s for s in sport_slots if s["archetype"] == "easy"]
        if not easy_slots:
            continue
        if len(easy_slots) == 1 and not long_session_essential:
            continue
        weekend = [s for s in easy_slots if s["day"] in ("saturday", "sunday")]
        (weekend[-1] if weekend else easy_slots[-1])["archetype"] = "long"

    return slots


def _slot_cap(slot: dict, week_type: str = "build") -> int:
    props = SPORT_PROPERTIES.get(slot["sport"], {})
    key = "max_long_minutes" if slot["archetype"] == "long" else "max_easy_minutes"
    cap = props.get(key, 90)
    if week_type in ("recovery", "taper"):
        cap = round(cap * 0.7)
    return cap


def _slot_floor(slot: dict, week_type: str = "build") -> int:
    """Smallest duration at which this session is still worth doing.

    Recovery weeks accept shorter sessions: keeping frequency matters more
    than session length when volume is deliberately cut. A long session
    claims a higher floor so that a week which cannot afford both frequency
    and a real long session gives up a frequency day rather than the long one.
    """
    props = SPORT_PROPERTIES.get(slot["sport"], {})
    base = MIN_SESSION_DURATION if week_type in ("recovery", "taper") else MIN_ENDURANCE_DURATION

    if props.get("frequency_priority"):
        # A short technique swim is worth doing; holding swimming to the same
        # floor as a run is what makes it the first thing cut from a thin week.
        base = MIN_SESSION_DURATION
    else:
        # Otherwise scale the floor to what a session of that sport normally
        # looks like. An hour on the bike is a short ride; an hour running is
        # not a short run. Weighting only the surplus above a shared floor
        # leaves every discipline the same size at low volume.
        base = max(base, round(props.get("typical_endurance_minutes", 60) * 0.6))

    if slot["archetype"] == "long":
        base = round(base * 1.5)
    return min(base, _slot_cap(slot, week_type))


def _allocate_slot_durations(slots: list[dict], total_minutes: float,
                             week_type: str) -> tuple[list[dict], int]:
    """Size each session. Returns (surviving slots, minutes that would not fit).

    Quality sessions are sized first: they are bounded by what an athlete can
    absorb, not by how much time is available, and by their share of a small
    week. Every surviving endurance session then gets a floor that makes it
    worth doing, and only the surplus above those floors is distributed
    proportionally — overflow past a session's cap goes into the long sessions
    before it is given up on.
    """
    quality = [s for s in slots if s["archetype"] == "quality"]
    endurance = [s for s in slots if s["archetype"] != "quality"]

    # Quality scales with the week rather than splitting a fixed budget, so a
    # cut-back week gets shorter quality sessions instead of a harder one.
    ceiling = 50 if week_type in ("recovery", "taper") else 75
    target = min(total_minutes * 0.18, ceiling)
    if quality and target * len(quality) > total_minutes * 0.45:
        target = total_minutes * 0.45 / len(quality)
    for slot in quality:
        cap = min(ceiling, SPORT_PROPERTIES.get(slot["sport"], {}).get("max_session_minutes", 75))
        slot["duration"] = _round_duration(max(MIN_SESSION_DURATION, min(target, cap)))

    pool = total_minutes - sum(s["duration"] for s in quality)
    if not endurance:
        return quality, max(0, round(pool))

    active = list(endurance)

    def floors() -> int:
        return sum(_slot_floor(s, week_type) for s in active)

    # A long session reserves 1.5x the normal floor. On a thin week two of them
    # can claim the entire budget, so give up the long designation before
    # giving up sessions — more appropriately sized sessions beat fewer
    # oversized ones.
    longs = sorted((s for s in active if s["archetype"] == "long"),
                   key=lambda s: -_slot_floor(s, week_type))
    for slot in longs:
        if floors() <= pool:
            break
        slot["archetype"] = "easy"

    # Whatever still does not fit gets dropped, easy sessions first and taken
    # from whichever discipline currently has the most — otherwise a thin week
    # deletes a whole sport while another keeps three sessions.
    while active and floors() > pool:
        droppable = [s for s in active if s["archetype"] == "easy"] or active
        per_sport: dict[str, int] = {}
        for slot in active:
            per_sport[slot["sport"]] = per_sport.get(slot["sport"], 0) + 1
        active.remove(max(droppable, key=lambda s: (per_sport[s["sport"]],
                                                    DAY_ORDER.index(s["day"]))))

    if not active:
        return quality, max(0, round(pool))

    for slot in active:
        slot["duration"] = float(_slot_floor(slot, week_type))
        props = SPORT_PROPERTIES.get(slot["sport"], {})
        slot["_weight"] = (
            props.get("typical_endurance_minutes", 60)
            * props.get("volume_weight", 1.0)
            * (1.7 if slot["archetype"] == "long" else 1.0)
        )

    surplus = pool - sum(s["duration"] for s in active)
    open_slots = [s for s in active if s["duration"] < _slot_cap(s, week_type)]

    while surplus >= 1 and open_slots:
        total_weight = sum(s["_weight"] for s in open_slots)
        if total_weight <= 0:
            break
        overflow = 0.0
        still_open = []
        for slot in open_slots:
            cap = _slot_cap(slot, week_type)
            value = slot["duration"] + surplus * slot["_weight"] / total_weight
            if value > cap:
                overflow += value - cap
                slot["duration"] = float(cap)
            else:
                slot["duration"] = value
                still_open.append(slot)
        surplus = overflow
        longs = [s for s in still_open if s["archetype"] == "long"]
        open_slots = longs or still_open

    for slot in active:
        slot["duration"] = _round_duration(slot["duration"])
        slot.pop("_weight", None)

    _demote_undersized_long_sessions(active)

    return quality + active, round(max(0, surplus))


def _demote_undersized_long_sessions(slots: list[dict]) -> None:
    """A session is only 'long' if it is actually longer than the easy ones.

    On tight weeks the long slot can end up the same size as every other
    endurance session, and calling it a long ride misleads the athlete.
    """
    for slot in slots:
        if slot["archetype"] != "long":
            continue
        peers = [
            s["duration"] for s in slots
            if s["sport"] == slot["sport"] and s["archetype"] == "easy"
        ]
        if peers and slot["duration"] < max(peers) * 1.2:
            slot["archetype"] = "easy"


QUALITY_TYPE_ROTATION = ["threshold", "sweetspot", "vo2max", "tempo"]


def _pick_quality_types(n_quality: int, week_num: int) -> list[str]:
    """Vary quality session types across weeks. Max 1 of each type per week."""
    offset = (week_num - 1) % len(QUALITY_TYPE_ROTATION)
    types = []
    for i in range(n_quality):
        types.append(QUALITY_TYPE_ROTATION[(offset + i) % len(QUALITY_TYPE_ROTATION)])
    return types



# --- Workout step building (defaults; AI can override) ---

INTERVAL_VARIATIONS = {
    "threshold": [
        {"block": 8, "rest": 4, "power": 0.96, "cadence": 90, "name": "classic 8min threshold"},
        {"block": 10, "rest": 5, "power": 0.95, "cadence": 88, "name": "long 10min threshold"},
        {"block": 6, "rest": 3, "power": 0.97, "cadence": 92, "name": "6min punchy threshold"},
        {"block": 12, "rest": 5, "power": 0.94, "cadence": 85, "name": "12min sustained threshold"},
        {"block": 20, "rest": 5, "power": 0.93, "cadence": 88, "name": "20min sustained threshold"},
    ],
    "sweetspot": [
        {"block": 10, "rest": 3, "power": 0.90, "cadence": 90, "name": "10min sweet spot"},
        {"block": 15, "rest": 3, "power": 0.89, "cadence": 88, "name": "15min sweet spot"},
        {"block": 8, "rest": 2, "power": 0.91, "cadence": 92, "name": "8min sweet spot"},
        {"block": 20, "rest": 5, "power": 0.88, "cadence": 85, "name": "20min sweet spot"},
    ],
    "tempo": [
        {"block": 10, "rest": 3, "power": 0.82, "cadence": 88, "name": "10min tempo"},
        {"block": 15, "rest": 3, "power": 0.80, "cadence": 85, "name": "15min tempo"},
        {"block": 20, "rest": 5, "power": 0.78, "cadence": 85, "name": "20min sustained tempo"},
        {"block": 8, "rest": 2, "power": 0.84, "cadence": 90, "name": "8min brisk tempo"},
    ],
    "vo2max": [
        {"block": 4, "rest": 4, "power": 1.12, "cadence": 95, "name": "4min VO2max"},
        {"block": 3, "rest": 3, "power": 1.15, "cadence": 100, "name": "3min sharp VO2max"},
        {"block": 5, "rest": 5, "power": 1.10, "cadence": 92, "name": "5min VO2max"},
        {"block": 2, "rest": 2, "power": 1.18, "cadence": 100, "name": "2min VO2max bursts"},
    ],
}


# Running is prescribed against threshold pace the way cycling is prescribed
# against FTP. Values are fractions of threshold SPEED — pace is the inverse,
# so an easy run at 0.78 of threshold speed is 1/0.78 = 1.28x the pace number.
RUN_SPEED_FRACTIONS = {
    "recovery": 0.70,
    "endurance": 0.78,
    "easy": 0.78,
    "tempo": 0.88,
    "sweetspot": 0.93,
    "threshold": 1.00,
    "vo2max": 1.06,
    "anaerobic": 1.15,
}


def run_pace_seconds(workout_type: str, threshold_pace: int) -> int:
    """Target pace in seconds per km for a given run intensity."""
    fraction = RUN_SPEED_FRACTIONS.get(workout_type, RUN_SPEED_FRACTIONS["endurance"])
    return int(round(threshold_pace / fraction))


def format_pace(seconds_per_km: float) -> str:
    minutes, seconds = divmod(int(round(seconds_per_km)), 60)
    return f"{minutes}:{seconds:02d}/km"


def swim_pace_seconds(workout_type: str, css_pace: int) -> int:
    """Target pace in seconds per 100m against the athlete's CSS."""
    fraction = RUN_SPEED_FRACTIONS.get(workout_type, RUN_SPEED_FRACTIONS["endurance"])
    return int(round(css_pace / fraction))


def format_swim_pace(seconds_per_100: float) -> str:
    minutes, seconds = divmod(int(round(seconds_per_100)), 60)
    return f"{minutes}:{seconds:02d}/100m"


RUN_EFFORT_CUES = {
    "endurance": "conversational pace — you should be able to speak in full sentences",
    "tempo": "comfortably hard, marathon-to-half-marathon effort (RPE 5-6)",
    "sweetspot": "just below threshold, ~half-marathon effort (RPE 6)",
    "threshold": "10K-to-hour race effort — controlled discomfort (RPE 7)",
    "vo2max": "3K-to-5K race effort — hard, breathing heavy (RPE 8-9)",
    "anaerobic": "near-maximal, form-focused sprints (RPE 10)",
    "recovery": "very easy shakeout — slower than it feels natural",
}


def _run_note(workout_type: str, base: str = "") -> str:
    """Runners pace by effort, not by watts."""
    cue = RUN_EFFORT_CUES.get(workout_type, "steady effort")
    return f"{base} — {cue}" if base else cue


def _run_step(workout_type: str, duration_secs: int, threshold_pace: int,
              step_type: str = "steady", extra_note: str = "") -> dict:
    """A running step targets a pace, not a share of FTP."""
    pace = run_pace_seconds(workout_type, threshold_pace)
    cue = RUN_EFFORT_CUES.get(workout_type, "steady effort")

    if step_type in ("warmup", "cooldown", "rest"):
        # These already say what to do; the effort cue would just repeat it.
        label = extra_note or step_type.title()
        note = f"{extra_note} @ {format_pace(pace)}" if extra_note else format_pace(pace)
    else:
        label = extra_note or cue
        note = (f"{extra_note} @ {format_pace(pace)} — {cue}" if extra_note
                else f"{format_pace(pace)} — {cue}")

    return {
        "type": step_type,
        "duration": duration_secs,
        "pace": pace,
        "pace_pct": round(RUN_SPEED_FRACTIONS.get(workout_type, 0.78), 2),
        # The pace is carried as a structured target, so the step name on the
        # watch is the coaching cue rather than a repeat of the number.
        "label": label,
        "notes": note,
    }


def _build_workout_steps(workout_type: str, duration: int, ftp: int,
                         has_trainer: bool, variation_seed: int = 0,
                         sport: str = "cycling",
                         threshold_pace: int = 300, css_pace: int = 105) -> list[dict]:
    if sport == "swimming":
        return _build_swim_steps(workout_type, duration, variation_seed, css_pace)
    if sport == "strength":
        return _build_strength_steps(duration, variation_seed)
    if sport == "running":
        return _build_run_steps(workout_type, duration, variation_seed, threshold_pace)

    warmup_mins = min(15, max(5, duration // 6))
    cooldown_mins = min(10, max(5, duration // 8))
    main_mins = duration - warmup_mins - cooldown_mins

    steps = [
        {"type": "warmup", "duration": warmup_mins * 60,
         "power": 0.55, "power_end": 0.70, "cadence": 90,
         "notes": "progressive warmup"},
    ]

    if workout_type == "endurance":
        steps.append({
            "type": "steady", "duration": main_mins * 60,
            "power": 0.68, "cadence": 85,
            "notes": "zone 2 — conversational pace, nose breathing",
        })
    elif workout_type in INTERVAL_VARIATIONS:
        variants = INTERVAL_VARIATIONS[workout_type]
        v = variants[variation_seed % len(variants)]
        block_mins = v["block"]
        rest_mins = v["rest"]
        reps = max(2, main_mins // (block_mins + rest_mins))
        rest_power = 0.45 if workout_type == "vo2max" else 0.55
        steps.append({
            "type": "interval", "duration": block_mins * 60,
            "power": v["power"], "cadence": v["cadence"], "repeat": reps,
            "rest": {"type": "rest", "duration": rest_mins * 60,
                     "power": rest_power, "cadence": 85, "notes": "easy spin"},
            "notes": v["name"],
        })
    elif workout_type == "anaerobic":
        block_secs = 30
        rest_secs = 150
        reps = max(4, (main_mins * 60) // (block_secs + rest_secs))
        steps.append({
            "type": "interval", "duration": block_secs,
            "power": 1.50, "cadence": 110, "repeat": reps,
            "rest": {"type": "rest", "duration": rest_secs, "power": 0.45, "cadence": 80},
            "notes": "max efforts — full recovery between",
        })
    else:
        steps.append({
            "type": "steady", "duration": main_mins * 60,
            "power": 0.65, "cadence": 85, "notes": "easy effort",
        })

    steps.append({
        "type": "cooldown", "duration": cooldown_mins * 60,
        "power": 0.50, "cadence": 80, "notes": "spin down",
    })

    return steps


def _build_run_steps(workout_type: str, duration: int, variation_seed: int,
                     threshold_pace: int) -> list[dict]:
    """Runs are prescribed in pace, never in watts.

    A runner reads 5:42/km, not 68% FTP — and a running watch cannot follow a
    power target unless the athlete owns a running power meter.
    """
    warmup_mins = min(15, max(5, duration // 6))
    cooldown_mins = min(10, max(5, duration // 8))
    main_mins = duration - warmup_mins - cooldown_mins

    steps = [
        _run_step("recovery", warmup_mins * 60, threshold_pace, "warmup",
                  "Easy jog, build gradually"),
    ]

    if workout_type in INTERVAL_VARIATIONS:
        v = INTERVAL_VARIATIONS[workout_type][variation_seed % len(INTERVAL_VARIATIONS[workout_type])]
        block_mins, rest_mins = v["block"], v["rest"]
        reps = max(2, main_mins // (block_mins + rest_mins))
        work = _run_step(workout_type, block_mins * 60, threshold_pace, "interval",
                         f"{reps}x{block_mins}min")
        work["repeat"] = reps
        work["rest"] = _run_step("recovery", rest_mins * 60, threshold_pace, "rest",
                                 "Jog recovery")
        steps.append(work)
    elif workout_type == "anaerobic":
        block_secs, rest_secs = 30, 150
        reps = max(4, (main_mins * 60) // (block_secs + rest_secs))
        work = _run_step("anaerobic", block_secs, threshold_pace, "interval",
                         f"{reps}x30s strides")
        work["repeat"] = reps
        work["rest"] = _run_step("recovery", rest_secs, threshold_pace, "rest",
                                 "Walk or very easy jog")
        steps.append(work)
    else:
        steps.append(_run_step(workout_type, main_mins * 60, threshold_pace, "steady"))

    steps.append(
        _run_step("recovery", cooldown_mins * 60, threshold_pace, "cooldown",
                  "Easy jog, then stretch")
    )
    return steps


SWIM_DRILLS = [
    "catch-up drill", "fingertip drag", "single-arm freestyle",
    "kickboard", "pull buoy", "fist drill", "6-kick switch",
    "sculling", "side-kick drill", "zipper drill",
]

SWIM_MAIN_SETS = [
    {"dist": 100, "rest_sec": 15, "pace": "threshold", "label": "threshold pace"},
    {"dist": 200, "rest_sec": 20, "pace": "threshold", "label": "threshold pace"},
    {"dist": 150, "rest_sec": 15, "pace": "tempo", "label": "steady"},
    {"dist": 50, "rest_sec": 10, "pace": "vo2max", "label": "fast"},
    {"dist": 100, "rest_sec": 20, "pace": "tempo", "label": "build (easy to fast)"},
    {"dist": 300, "rest_sec": 30, "pace": "tempo", "label": "steady"},
]


def _swim_metres(minutes: float, pace: str = "endurance") -> int:
    """Distance covered swimming for a given time, rounded to the pool length."""
    metres_per_min = SPORT_SPEEDS["swimming"].get(pace, 2.8) * 1000 / 60
    return int(round(minutes * metres_per_min / 25) * 25)


def _build_swim_steps(workout_type: str, duration: int, variation_seed: int = 0,
                      css_pace: int = 105) -> list[dict]:
    """Swim sets are prescribed in metres.

    Every step carries an explicit distance. Sending time plus a pace target
    instead makes the consumer derive the distance itself, and intervals.icu
    derived a 16km, six-hour recovery swim from a 35-minute one.
    """
    warmup_mins = min(10, max(5, duration // 6))
    cooldown_mins = min(5, max(3, duration // 10))
    drill_mins = min(8, max(3, duration // 8))
    main_mins = duration - warmup_mins - cooldown_mins - drill_mins

    drill = SWIM_DRILLS[variation_seed % len(SWIM_DRILLS)]
    warmup_m = _swim_metres(warmup_mins)
    cooldown_m = _swim_metres(cooldown_mins, "recovery")
    drill_m = _swim_metres(drill_mins, "recovery")

    steps = [
        {"type": "warmup", "duration": warmup_mins * 60, "distance_m": warmup_m,
         "pace": swim_pace_seconds("endurance", css_pace),
         "notes": f"{warmup_m}m easy freestyle, mix in backstroke"},
        {"type": "steady", "duration": drill_mins * 60, "distance_m": drill_m,
         "notes": f"Technique: {drill} — {drill_m}m of drill work, form over speed"},
    ]

    if workout_type in ("threshold", "vo2max", "sweetspot", "tempo"):
        main_set = SWIM_MAIN_SETS[variation_seed % len(SWIM_MAIN_SETS)]
        pace_per_100 = swim_pace_seconds(main_set["pace"], css_pace)
        rep_secs = int(round(pace_per_100 * main_set["dist"] / 100 / 5) * 5)
        reps = max(2, (main_mins * 60) // (rep_secs + main_set["rest_sec"]))
        steps.append({
            "type": "interval",
            "duration": rep_secs,
            "distance_m": main_set["dist"],
            "repeat": reps,
            "pace": pace_per_100,
            "rest": {"type": "rest", "duration": main_set["rest_sec"],
                     "notes": f"{main_set['rest_sec']}s rest"},
            "notes": f"{reps}x{main_set['dist']}m @ {format_swim_pace(pace_per_100)} "
                     f"({main_set['label']}), {main_set['rest_sec']}s rest",
        })
    else:
        main_m = _swim_metres(main_mins)
        steps.append({
            "type": "steady", "duration": main_mins * 60, "distance_m": main_m,
            "pace": swim_pace_seconds("endurance", css_pace),
            "notes": f"Continuous swim — {main_m}m at easy, relaxed pace",
        })

    steps.append({
        "type": "cooldown", "duration": cooldown_mins * 60, "distance_m": cooldown_m,
        "notes": f"{cooldown_m}m easy choice stroke, focus on long glide",
    })
    return steps


STRENGTH_BLOCKS = [
    {
        "name": "Max Strength — Bilateral",
        "focus": "Heavy compound work for force production. Leave 2-3 reps in reserve.",
        "exercises": [
            {"name": "Back Squat", "sets": 4, "reps": 5, "category": 28, "rest": 120,
             "cue": "Heavy but controlled — stop 2 reps short of failure"},
            {"name": "Romanian Deadlift", "sets": 3, "reps": 6, "category": 8, "rest": 90,
             "cue": "Hinge at the hip, feel the hamstrings load"},
            {"name": "Weighted Step-up", "sets": 3, "reps": 8, "category": 17, "rest": 75,
             "per_side": True, "cue": "Drive through the heel, no push off the back foot"},
            {"name": "Standing Calf Raise", "sets": 3, "reps": 12, "category": 1, "rest": 45,
             "cue": "Full range, slow lowering"},
            {"name": "Pallof Press", "sets": 3, "reps": 10, "category": 5, "rest": 45,
             "per_side": True, "cue": "Resist the rotation, ribs down"},
        ],
    },
    {
        "name": "Single-Leg & Posterior Chain",
        "focus": "Unilateral strength and hip stability — where running durability comes from.",
        "exercises": [
            {"name": "Bulgarian Split Squat", "sets": 3, "reps": 8, "category": 17, "rest": 90,
             "per_side": True, "cue": "Front shin vertical, torso tall"},
            {"name": "Barbell Hip Thrust", "sets": 4, "reps": 8, "category": 10, "rest": 90,
             "cue": "Squeeze at the top, chin tucked"},
            {"name": "Single-leg Deadlift", "sets": 3, "reps": 8, "category": 8, "rest": 75,
             "per_side": True, "cue": "Hips square, slow and balanced"},
            {"name": "Copenhagen Plank", "sets": 3, "reps": 20, "category": 19, "rest": 45,
             "per_side": True, "cue": "Adductor work — count seconds as reps"},
            {"name": "Single-leg Calf Raise", "sets": 3, "reps": 12, "category": 1, "rest": 45,
             "per_side": True, "cue": "Full extension, controlled down"},
        ],
    },
    {
        "name": "Power & Trunk",
        "focus": "Rate of force development plus trunk stiffness for efficient running.",
        "exercises": [
            {"name": "Trap Bar Deadlift", "sets": 4, "reps": 4, "category": 8, "rest": 120,
             "cue": "Move the bar fast — speed is the point, not grinding"},
            {"name": "Box Jump", "sets": 4, "reps": 5, "category": 20, "rest": 90,
             "cue": "Step down, never jump down"},
            {"name": "Walking Lunge", "sets": 3, "reps": 10, "category": 17, "rest": 75,
             "per_side": True, "cue": "Long stride, controlled knee"},
            {"name": "Suitcase Carry", "sets": 3, "reps": 30, "category": 3, "rest": 60,
             "per_side": True, "cue": "Heavy, stay square — count seconds as reps"},
            {"name": "Dead Bug", "sets": 3, "reps": 10, "category": 5, "rest": 45,
             "per_side": True, "cue": "Lower back stays flat on the floor"},
        ],
    },
    {
        "name": "Maintenance Circuit",
        "focus": "In-season upkeep. Moderate load, nothing that leaves you sore for key sessions.",
        "exercises": [
            {"name": "Goblet Squat", "sets": 3, "reps": 10, "category": 28, "rest": 60,
             "cue": "Upright chest, sit between the hips"},
            {"name": "Glute Bridge", "sets": 3, "reps": 12, "category": 10, "rest": 45,
             "cue": "Drive through the heels"},
            {"name": "Single-arm Row", "sets": 3, "reps": 10, "category": 23, "rest": 60,
             "per_side": True, "cue": "Pull to the hip, no shrug"},
            {"name": "Push-up", "sets": 3, "reps": 12, "category": 22, "rest": 45,
             "cue": "Full range, body in one line"},
            {"name": "Side Plank", "sets": 2, "reps": 30, "category": 19, "rest": 45,
             "per_side": True, "cue": "Count seconds as reps, hips high"},
        ],
    },
]

# Roughly how long one rep takes, used only to estimate session length.
SECONDS_PER_REP = 4


def _pick_strength_days(slots: list[dict],
                        max_sessions: int = MAX_STRENGTH_SESSIONS) -> set[str]:
    """Strength rides along with easy days, never the day before a key run."""
    by_day: dict[str, list[dict]] = {}
    for slot in slots:
        by_day.setdefault(slot["day"], []).append(slot)

    chosen: list[str] = []
    for slot in slots:
        if slot["archetype"] != "easy" or not slot["duration"]:
            continue
        index = DAY_ORDER.index(slot["day"])
        next_day = by_day.get(DAY_ORDER[(index + 1) % 7], [])
        if any(s["sport"] == "running" and s["archetype"] in ("quality", "long")
               for s in next_day):
            continue
        if chosen and index - DAY_ORDER.index(chosen[-1]) < 2:
            continue
        chosen.append(slot["day"])
        if len(chosen) >= max_sessions:
            break
    return set(chosen)


def _build_strength_session(seed: int) -> dict:
    block = _strength_block(seed)
    steps = _build_strength_steps(0, seed)
    duration = estimate_strength_minutes(block)
    return {
        "name": block["name"],
        "sport": "strength",
        "workout_type": "strength",
        "archetype": "supporting",
        "duration_minutes": duration,
        "description": block["focus"],
        "coach_notes": "",
        "target_zone": "Strength work",
        "tss_estimate": round(duration * 0.8),
        "intensity_factor": IF_TABLE["strength"],
        "priority": "supporting",
        "distance_km": 0,
        "steps": steps,
    }


def _strength_block(variation_seed: int = 0) -> dict:
    return STRENGTH_BLOCKS[variation_seed % len(STRENGTH_BLOCKS)]


def estimate_strength_minutes(block: dict) -> int:
    """Time the prescribed sets actually take, rather than a fixed guess."""
    seconds = 0
    for exercise in block["exercises"]:
        sides = 2 if exercise.get("per_side") else 1
        work = exercise["reps"] * SECONDS_PER_REP * sides
        seconds += exercise["sets"] * (work + exercise["rest"])
    return round(seconds / 60)


def _build_strength_steps(duration: int, variation_seed: int = 0) -> list[dict]:
    """Strength as sets and reps, not a stopwatch.

    A watch step of "Bulgarian Split Squat, 5:00 steady" is not how anyone
    lifts. FIT has a rep-based duration type and an exercise taxonomy, so each
    set is prescribed as reps and each rest as time, wrapped in a repeat for
    the set count.
    """
    block = _strength_block(variation_seed)

    steps: list[dict] = [{
        "type": "warmup", "duration": 300, "exercise_category": 31,
        "notes": "Dynamic warmup: leg swings, hip circles, bodyweight squats",
    }]

    for exercise in block["exercises"]:
        sides = " each side" if exercise.get("per_side") else ""
        steps.append({
            "type": "interval",
            "reps": exercise["reps"],
            "sets": exercise["sets"],
            "repeat": exercise["sets"],
            "exercise": exercise["name"],
            "exercise_category": exercise["category"],
            "per_side": bool(exercise.get("per_side")),
            # `notes` is what a watch shows on the step, so it repeats the
            # scheme. The UI has those as fields already and shows `cue`.
            "cue": exercise["cue"],
            "notes": (f"{exercise['sets']}x{exercise['reps']}{sides} — "
                      f"{exercise['cue']}"),
            "rest": {
                "type": "rest",
                "duration": exercise["rest"],
                "notes": f"Rest {exercise['rest']}s",
            },
        })

    steps.append({
        "type": "cooldown", "duration": 180,
        "notes": "Stretch hip flexors, quads and calves",
    })
    return steps


SWIM_ZONE_LABELS = {
    "endurance": "Easy aerobic pace",
    "tempo": "Steady pace",
    "sweetspot": "Steady-to-threshold pace",
    "threshold": "Threshold pace (CSS)",
    "vo2max": "Fast pace, short reps",
    "recovery": "Very easy, technique focus",
}


def _target_zone(sport: str, workout_type: str, threshold_pace: int = 300,
                 css_pace: int = 105) -> str:
    """Zone label in the units the sport actually uses.

    Cycling gets watts, running a pace per km, swimming a pace per 100m.
    """
    if sport == "strength":
        return "Strength work"

    zone = ZONE_DEFINITIONS.get(workout_type, ZONE_DEFINITIONS["endurance"])

    if sport == "swimming":
        label = SWIM_ZONE_LABELS.get(workout_type, "Aerobic pace")
        return f"{label} — {format_swim_pace(swim_pace_seconds(workout_type, css_pace))}"

    if sport == "running":
        pace = run_pace_seconds(workout_type, threshold_pace)
        return f"{zone['zone']} — {format_pace(pace)} (RPE {zone['rpe']})"

    return (f"{zone['zone']} ({zone['pct_ftp'][0]*100:.0f}-"
            f"{zone['pct_ftp'][1]*100:.0f}% FTP, RPE {zone['rpe']})")


def _build_session(slot: dict, ftp: int, has_trainer: bool, seed: int,
                   threshold_pace: int = 300, css_pace: int = 105) -> dict:
    sport = slot["sport"]
    duration = int(slot["duration"])
    archetype = slot["archetype"]
    workout_type = slot.get("workout_type", "endurance")

    if_val = IF_TABLE.get(workout_type, 0.65)
    km = _estimate_distance(sport, workout_type, duration, threshold_pace, css_pace)
    suffix = " (long)" if archetype == "long" else ""

    return {
        "name": _workout_name(workout_type, sport, duration) + suffix,
        "sport": sport,
        "workout_type": workout_type,
        "archetype": archetype,
        "duration_minutes": duration,
        "description": "",
        "coach_notes": "",
        "target_zone": _target_zone(sport, workout_type, threshold_pace, css_pace),
        "tss_estimate": round(compute_tss(duration, if_val)),
        "intensity_factor": if_val,
        "priority": "key" if archetype == "quality" else "supporting",
        "distance_km": km,
        "steps": _build_workout_steps(workout_type, duration, ftp, has_trainer,
                                      seed, sport=sport,
                                      threshold_pace=threshold_pace, css_pace=css_pace),
    }


def _workout_name(workout_type: str, sport: str, duration: int) -> str:
    type_names = {
        "endurance": "Endurance Ride" if sport == "cycling" else "Easy Run" if sport == "running" else "Steady Swim",
        "tempo": "Tempo Blocks",
        "sweetspot": "Sweet Spot Intervals",
        "threshold": "Threshold Intervals",
        "vo2max": "VO2max Repeats",
        "anaerobic": "Sprint Intervals",
        "recovery": "Recovery Spin" if sport == "cycling" else "Recovery Jog",
        "easy": "Easy Session",
    }
    name = type_names.get(workout_type, f"{workout_type.capitalize()} Session")
    return f"{duration}min {name}"


# --- Safety validation ---

def validate_plan(plan: dict, profile: dict) -> list[str]:
    """Check plan against safety constraints. Returns list of warnings."""
    warnings = []
    weeks = plan.get("weeks", [])
    n_disciplines = len([s for s in profile.get("sports", ["cycling"]) if s != "strength"]) or 1
    max_quality_per_sport = 1 if n_disciplines > 1 else 2

    # Recovery weeks must be present every 3-5 weeks
    build_streak = 0
    for week in weeks:
        if week["week_type"] == "recovery":
            build_streak = 0
        else:
            build_streak += 1
        if build_streak > 5:
            warnings.append(f"No recovery week for {build_streak} consecutive build weeks")

    for week in weeks:
        days = week.get("days", [])
        wn = week["week_number"]
        prev_hard = False
        archetype_counts: dict[tuple[str, str], int] = {}

        for i, day in enumerate(days):
            workouts = day.get("workouts", [])
            is_hard = any(w.get("archetype") == "quality" for w in workouts)
            if is_hard and prev_hard:
                warnings.append(
                    f"Week {wn}: consecutive quality days "
                    f"({days[i-1]['day']}, {day['day']})"
                )
            prev_hard = is_hard

            for wo in workouts:
                sport = wo.get("sport", "")
                archetype = wo.get("archetype")
                if archetype in ("quality", "long"):
                    key = (sport, archetype)
                    archetype_counts[key] = archetype_counts.get(key, 0) + 1

                duration = wo.get("duration_minutes", 0)
                sport_max = SPORT_PROPERTIES.get(sport, {}).get("max_session_minutes", 300)
                if duration > sport_max:
                    warnings.append(
                        f"Week {wn}, {day['day']}: "
                        f"{sport} session {duration}min exceeds max {sport_max}min"
                    )

        for (sport, archetype), count in archetype_counts.items():
            allowed = 1 if archetype == "long" else max_quality_per_sport
            if count > allowed:
                warnings.append(
                    f"Week {wn}: {count} {archetype} {sport} sessions — "
                    f"at most {allowed} per discipline per week"
                )

    return warnings


# --- Main entry point ---

def build_plan(profile: dict, ftp: int,
               fitness_context: dict | None = None,
               start_date: str = "",
               threshold_pace: int = 300, css_pace: int = 105,
               first_week_from: str = "") -> dict:
    """Build a training plan using constraint-based optimization.

    Computes the training envelope (duration targets, quality slots,
    sport distribution, recovery weeks) and fills in default workouts.
    The AI coach can then override workout design with coaching intelligence.

    `first_week_from` starts a block mid-week: days before that date carry no
    sessions and week one's budget shrinks to the days that are actually left,
    so a Thursday start is a three-day week rather than seven days of training
    squeezed into three.
    """
    experience = profile.get("experience_level", "intermediate")
    total_weeks = profile.get("plan_duration_weeks", 8)
    weekly_hours = profile.get("weekly_hours", 8.0)
    sports = profile.get("sports", ["cycling"])
    event = profile.get("goal_event", profile.get("goal", "general_fitness"))
    preferred_hard_days = profile.get("preferred_hard_days", [])
    preferred_rest_days = profile.get("preferred_rest_days", [])
    has_trainer = profile.get("has_trainer", False)
    max_sessions_per_day = profile.get("max_sessions_per_day") or 1

    start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.now()

    capacity = compute_capacity_assessment(weekly_hours, event, sports, experience)
    n_quality = compute_quality_sessions(weekly_hours, experience, capacity["strategy"])
    density = compute_training_density(weekly_hours, n_quality)
    week_types = compute_recovery_schedule(total_weeks, experience)

    # Race week is a taper. The week before it only becomes an extra recovery
    # week if the regular cycle has not already put one nearby — otherwise the
    # block ends with three consecutive easy weeks and the athlete detrains.
    if profile.get("goal_event") and total_weeks > 4:
        week_types[-1] = "taper"
        # Only add a pre-race cutback if the regular cycle has not put one in
        # the run-in already — otherwise the block ends recovery, one build
        # week, recovery, taper, which is mostly rest.
        if total_weeks >= 6 and "recovery" not in week_types[-4:-1]:
            week_types[-2] = "recovery"

    rest_days = set(d.lower() for d in preferred_rest_days) if preferred_rest_days else set()
    hard_days_pref = set(d.lower() for d in preferred_hard_days) if preferred_hard_days else {"tuesday", "thursday", "saturday"}

    training_days = [d for d in DAY_ORDER if d not in rest_days]
    quality_days = [d for d in training_days if d in hard_days_pref][:n_quality]
    easy_days = [d for d in training_days if d not in quality_days]

    primary_sport = profile.get("primary_sport") or EVENT_PRIMARY_SPORT.get(event)
    real_sports = [s for s in sports if s != "strength"] or ["cycling"]
    # Hard constraints the athlete gave us: pool days, an injured knee capping
    # run frequency. These bound the planner rather than nudging it.
    sport_limits = profile.get("sport_limits") or {}

    # Where the ramp starts. Synced history beats the onboarding slider, and an
    # explicit answer from the athlete beats both.
    current_hours, volume_source = _resolve_starting_volume(profile)
    start_fraction = (
        current_hours / weekly_hours
        if current_hours and weekly_hours > 0 else None
    )

    readiness = compute_readiness(fitness_context)
    if start_fraction is not None:
        start_fraction *= readiness["multiplier"]

    week_multipliers = compute_volume_progression(week_types, experience, start_fraction)
    progression = _assess_progression(week_multipliers, week_types, weekly_hours,
                                      current_hours, experience)
    progression["volume_source"] = volume_source
    if current_hours:
        progression["current_hours"] = round(current_hours, 1)
    if readiness.get("note"):
        progression["readiness_note"] = readiness["note"]
    progression["readiness"] = readiness["state"]

    weeks = []
    for week_idx in range(total_weeks):
        week_num = week_idx + 1
        week_type = week_types[week_idx]
        week_date = start + timedelta(weeks=week_idx)

        week_quality = n_quality
        if week_type == "recovery":
            week_quality = max(1, n_quality - 1)
        elif week_type == "taper":
            week_quality = 1

        # A block can start mid-week; the days already gone carry no sessions
        # and the week's budget shrinks to match what is left.
        week_training_days = training_days
        week_easy_days = easy_days
        week_quality_days = quality_days[:week_quality]
        partial_factor = 1.0

        if first_week_from and week_idx == 0:
            cutoff = datetime.strptime(first_week_from, "%Y-%m-%d")
            still_ahead = {
                day for i, day in enumerate(DAY_ORDER)
                if week_date + timedelta(days=i) >= cutoff
            }
            week_training_days = [d for d in training_days if d in still_ahead]
            week_easy_days = [d for d in easy_days if d in still_ahead]
            week_quality_days = [d for d in week_quality_days if d in still_ahead]
            if training_days:
                partial_factor = len(week_training_days) / len(training_days)

        week_minutes = weekly_hours * 60 * week_multipliers[week_idx] * partial_factor
        # Strength costs the athlete time like anything else, so it comes out of
        # the weekly budget rather than being bolted on top of it. Reserve what
        # the prescribed sets actually take, not a flat guess — the blocks vary
        # from about half an hour to three quarters.
        strength_seeds = (
            [week_num + n for n in range(MAX_STRENGTH_SESSIONS)]
            if "strength" in sports else []
        )
        strength_cost = sum(
            estimate_strength_minutes(_strength_block(seed)) for seed in strength_seeds
        )
        # Never let supporting work claim more than a fifth of the week.
        week_minutes -= min(strength_cost, week_minutes * 0.20)

        # Frequency follows this week's volume, not the plan's headline hours.
        # An early ramp week is a smaller week and should carry fewer sessions
        # rather than the same number squeezed under their useful minimum.
        if not week_training_days:
            weeks.append({
                "week_number": week_num, "week_type": week_type,
                "focus": "Block starts later this week",
                "target_hours": 0, "target_tss": 0, "distance_km": {},
                "days": [_rest_day(d, week_date + timedelta(days=i))
                         for i, d in enumerate(DAY_ORDER)],
            })
            continue

        session_target = compute_session_target(
            week_minutes / 60, len(real_sports), len(week_training_days),
            max_sessions_per_day,
        )
        sport_schedule = _build_sport_schedule(
            sports, week_quality_days, week_easy_days, primary_sport,
            session_target, max_sessions_per_day, sport_limits,
        )
        base_slots = _assign_archetypes(
            sport_schedule, week_quality_days, capacity["long_session_essential"],
        )
        slots, unfitted = _allocate_slot_durations(base_slots, week_minutes, week_type)

        quality_types = _pick_quality_types(week_quality, week_num)
        for idx, slot in enumerate(s for s in slots if s["archetype"] == "quality"):
            slot["workout_type"] = (
                quality_types[idx] if idx < len(quality_types) else "threshold"
            )

        strength_days = _pick_strength_days(slots) if "strength" in sports else set()
        by_day: dict[str, list[dict]] = {}
        for slot in slots:
            by_day.setdefault(slot["day"], []).append(slot)

        days = []
        total_tss = 0.0
        total_distance: dict[str, float] = {}
        strength_index = 0

        for i, day_name in enumerate(DAY_ORDER):
            day_date = week_date + timedelta(days=i)
            day_slots = [s for s in by_day.get(day_name, []) if s["duration"]]

            if not day_slots:
                days.append(_rest_day(day_name, day_date))
                continue

            day_workouts = []
            for slot in day_slots:
                workout = _build_session(slot, ftp, has_trainer, week_num + i,
                                         threshold_pace, css_pace)
                total_tss += workout["tss_estimate"]
                total_distance[slot["sport"]] = (
                    total_distance.get(slot["sport"], 0) + workout["distance_km"]
                )
                day_workouts.append(workout)

            if day_name in strength_days:
                seed = strength_seeds[strength_index % len(strength_seeds)]
                strength_index += 1
                strength = _build_strength_session(seed)
                day_workouts.append(strength)
                total_tss += strength["tss_estimate"]

            days.append({
                "day": day_name,
                "date": day_date.strftime("%Y-%m-%d"),
                "workouts": day_workouts,
            })

        scheduled_minutes = sum(
            w["duration_minutes"] for d in days for w in d["workouts"]
        )

        week = {
            "week_number": week_num,
            "week_type": week_type,
            "focus": _week_focus(week_type, capacity["strategy"]),
            "target_hours": round(scheduled_minutes / 60, 1),
            "target_tss": round(total_tss),
            "distance_km": {s: round(d, 1) for s, d in total_distance.items()},
            "days": days,
        }
        # Recovery and taper weeks are deliberately short, so leftover minutes
        # there are the point, not a problem worth surfacing.
        if unfitted >= 30 and week_type == "build":
            remedy = (
                "free up a rest day" if rest_days
                else "allow a second session on some days"
                if max_sessions_per_day < 2 else "accept the lower volume"
            )
            week["volume_note"] = (
                f"{unfitted} min of this week's {round(week_minutes / 60, 1)}h target "
                f"did not fit within safe session limits — {remedy}."
            )
        weeks.append(week)

    plan_name = _plan_name(event, total_weeks, sports)
    total_dist: dict[str, float] = {}
    for w in weeks:
        for s, d in w["distance_km"].items():
            total_dist[s] = total_dist.get(s, 0) + d

    plan = {
        "name": plan_name,
        "description": "",
        "total_weeks": total_weeks,
        "total_distance_km": {s: round(d) for s, d in total_dist.items()},
        "capacity_assessment": capacity,
        "training_density": density,
        "progression_assessment": progression,
        "weeks": weeks,
        "progression_notes": "",
    }

    safety_warnings = validate_plan(plan, profile)
    if safety_warnings:
        plan["safety_warnings"] = safety_warnings

    return plan


def _rest_day(day_name: str, day_date: datetime) -> dict:
    return {
        "day": day_name,
        "date": day_date.strftime("%Y-%m-%d"),
        "workouts": [{
            "name": "Rest Day",
            "sport": "rest",
            "workout_type": "rest",
            "duration_minutes": 0,
            "description": "",
            "coach_notes": "",
            "target_zone": "Recovery",
            "tss_estimate": 0,
            "intensity_factor": 0,
            "priority": "optional",
            "distance_km": 0,
            "steps": [],
        }],
    }


def _week_focus(week_type: str, capacity_strategy: str) -> str:
    if week_type == "recovery":
        return "Recovery & adaptation — reduce volume 20-40%, maintain some quality"
    if week_type == "taper":
        return "Taper — reduce volume significantly, maintain sharpness"

    focus_map = {
        "surplus": "Aerobic development — build easy volume, conservative intensity",
        "manageable": "Balanced training — appropriate volume with moderate density",
        "tight": "Efficient training — maintain volume, focused quality sessions",
        "insufficient": "Priority training — focus on key sessions, protect recovery",
    }
    return focus_map.get(capacity_strategy, "Build")


def _plan_name(event: str, weeks: int, sports: list[str]) -> str:
    event_labels = {
        "general_fitness": "General Fitness",
        "5k": "5K Preparation",
        "10k": "10K Preparation",
        "half_marathon": "Half Marathon",
        "marathon": "Marathon",
        "olympic_triathlon": "Olympic Triathlon",
        "sprint_triathlon": "Sprint Triathlon",
        "ironman_70.3": "Ironman 70.3",
        "ironman": "Ironman",
    }
    sport_str = " & ".join(s.capitalize() for s in sports if s != "strength")
    return f"{event_labels.get(event, 'Training')} — {sport_str} ({weeks}wk)"
