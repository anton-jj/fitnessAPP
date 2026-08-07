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
        "max_weekly_increase_pct": 0.10,
        "typical_endurance_minutes": 60,
        "frequency_notes": "protect key sessions, cautious volume increases",
    },
    "cycling": {
        "stress_factor": 0.4,
        "max_session_minutes": 240,
        "max_easy_minutes": 120,
        "max_long_minutes": 180,
        "max_weekly_increase_pct": 0.15,
        "typical_endurance_minutes": 90,
        "frequency_notes": "primary volume expander, handles long sessions well",
    },
    "swimming": {
        "stress_factor": 0.2,
        "max_session_minutes": 75,
        "max_easy_minutes": 60,
        "max_long_minutes": 75,
        "max_weekly_increase_pct": 0.15,
        "typical_endurance_minutes": 45,
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

    if weekly_hours < 4:
        return 2
    elif weekly_hours < 12:
        return 2
    else:
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
    """Plan recovery weeks every 3-5 weeks with 20-40% volume reduction.

    Beginners: every 3 weeks (2 build + 1 recovery)
    Intermediate: every 4 weeks (3 build + 1 recovery)
    Advanced: every 4-5 weeks (3-4 build + 1 recovery)
    """
    if experience == "beginner":
        build_count = 2
    elif experience == "advanced":
        build_count = 4
    else:
        build_count = 3

    cycle = build_count + 1
    week_types = []
    for i in range(total_weeks):
        pos_in_cycle = i % cycle
        if pos_in_cycle >= build_count:
            week_types.append("recovery")
        else:
            week_types.append("build")

    return week_types


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


MAX_WEEKLY_INCREASE = {"beginner": 0.06, "advanced": 0.10}
DEFAULT_MAX_INCREASE = 0.08

# Never open a block below this fraction of the athlete's stated hours. They
# told us the time is available; starting much lower wastes the block.
MIN_START_FRACTION = 0.70


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


EVENT_PRIMARY_SPORT = {
    "5k": "running", "10k": "running", "half_marathon": "running",
    "marathon": "running",
}


def _allocate_sport_days(real_sports: list[str], n_days: int,
                        primary_sport: str | None) -> dict[str, int]:
    """Decide how many sessions each discipline gets before choosing days.

    Dealing days out round-robin starves whichever sport sorts last, which is
    always swimming — the one discipline whose value comes from frequency
    rather than session length. Session counts are allocated first so a
    triathlete gets to swim more than once a week.
    """
    weights: dict[str, float] = {}
    for sport in real_sports:
        props = SPORT_PROPERTIES.get(sport, {})
        weight = 1.0
        if props.get("frequency_priority"):
            weight *= 1.15
        if sport == primary_sport:
            weight *= 1.35
        weights[sport] = weight

    total_weight = sum(weights.values()) or 1.0
    exact = {s: n_days * w / total_weight for s, w in weights.items()}
    counts = {s: int(v) for s, v in exact.items()}

    # Largest-remainder so the counts add up to exactly the days available.
    leftover = n_days - sum(counts.values())
    for sport in sorted(exact, key=lambda s: exact[s] - counts[s], reverse=True):
        if leftover <= 0:
            break
        counts[sport] += 1
        leftover -= 1

    # Every discipline in the plan should appear at least once, and a
    # frequency-priority sport needs at least two touches to be worth doing.
    for sport in real_sports:
        floor = 2 if SPORT_PROPERTIES.get(sport, {}).get("frequency_priority") else 1
        floor = min(floor, max(1, n_days // len(real_sports)))
        while counts[sport] < floor:
            donor = max(counts, key=lambda s: counts[s] - (
                2 if SPORT_PROPERTIES.get(s, {}).get("frequency_priority") else 1))
            if donor == sport or counts[donor] <= 1:
                break
            counts[donor] -= 1
            counts[sport] += 1

    return counts


def _build_sport_schedule(sports: list[str], quality_days: list[str],
                          easy_days: list[str],
                          primary_sport: str | None = None) -> dict[str, str]:
    """Assign a discipline to every training day.

    Session counts come first (see _allocate_sport_days), then days are chosen:
    quality days go to the disciplines the athlete does most, weekend days to
    whichever remaining sport carries the longest sessions, and the rest are
    spread so the same sport avoids back-to-back days.
    """
    real_sports = [s for s in sports if s != "strength"]
    if not real_sports:
        return {d: "cycling" for d in DAY_ORDER}
    if len(real_sports) == 1:
        return {d: real_sports[0] for d in DAY_ORDER}

    training_days = list(quality_days) + list(easy_days)
    remaining = _allocate_sport_days(real_sports, len(training_days), primary_sport)
    schedule: dict[str, str] = {}

    def take(sport: str, day: str) -> None:
        schedule[day] = sport
        remaining[sport] -= 1

    # Quality goes to the disciplines with the most sessions — that is where
    # the athlete has the base to absorb it — but each discipline gets at most
    # one hard day, so a second quality slot moves to another sport.
    quality_used: set[str] = set()
    for day in quality_days:
        available = [s for s in real_sports if remaining[s] > 0]
        if not available:
            break
        fresh = [s for s in available if s not in quality_used] or available
        pick = max(fresh, key=lambda s: (remaining[s], s == primary_sport))
        quality_used.add(pick)
        take(pick, day)

    leftover_days = [d for d in easy_days if d not in schedule]

    # Weekends suit the long session, so give them to the sports that can use
    # the time — primary sport first, and not the same sport twice.
    weekend_used: set[str] = set()
    for day in ("saturday", "sunday"):
        if day not in leftover_days:
            continue
        available = [s for s in real_sports if remaining[s] > 0]
        if not available:
            break
        fresh = [s for s in available if s not in weekend_used] or available
        pick = max(fresh, key=lambda s: (
            s == primary_sport,
            SPORT_PROPERTIES.get(s, {}).get("max_long_minutes", 0),
        ))
        weekend_used.add(pick)
        take(pick, day)
        leftover_days.remove(day)

    # Spread what is left, avoiding the same sport on consecutive days.
    for day in leftover_days:
        available = [s for s in real_sports if remaining[s] > 0]
        if not available:
            break
        previous = schedule.get(DAY_ORDER[(DAY_ORDER.index(day) - 1) % 7])
        spaced = [s for s in available if s != previous] or available
        take(max(spaced, key=lambda s: remaining[s]), day)

    for day in DAY_ORDER:
        schedule.setdefault(day, real_sports[0])

    return schedule


# --- Session archetypes ---
#
# Each discipline gets at most one session of each archetype per week:
#   quality — structured intensity (0 or 1)
#   long    — the single longest endurance session for that sport
#   easy    — one or more aerobic sessions
#
# When several schedules satisfy the weekly volume target, prefer the one
# that uses appropriately sized sessions over fewer oversized ones, and
# routes surplus endurance volume into the designated long session.

def _assign_archetypes(sport_schedule: dict[str, str], training_days: list[str],
                       quality_days: list[str],
                       long_session_essential: bool) -> list[dict]:
    slots = [
        {
            "day": day,
            "sport": sport_schedule.get(day, "cycling"),
            "archetype": "quality" if day in quality_days else "easy",
        }
        for day in training_days
    ]

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
    base = MIN_SESSION_DURATION if week_type in ("recovery", "taper") else MIN_ENDURANCE_DURATION
    if SPORT_PROPERTIES.get(slot["sport"], {}).get("frequency_priority"):
        # A short technique swim is worth doing; holding swimming to the same
        # floor as a run is what makes it the first thing cut from a thin week.
        base = MIN_SESSION_DURATION
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
        slot["_weight"] = props.get("typical_endurance_minutes", 60) * (
            1.7 if slot["archetype"] == "long" else 1.0
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


def _add_second_sessions(slots: list[dict], unfitted: int, sports: list[str],
                         quality_days: list[str],
                         max_sessions_per_day: int) -> tuple[list[dict], int]:
    """Absorb leftover volume as second sessions rather than oversized ones.

    Beyond roughly 10h/week the volume stops fitting into one session per day.
    Splitting it into a short second session is what the extra time actually
    buys — lengthening the existing sessions past their caps is not.
    """
    if max_sessions_per_day < 2 or unfitted < MIN_ENDURANCE_DURATION:
        return slots, unfitted

    low_stress = sorted(
        (s for s in sports if s != "strength"),
        key=lambda s: SPORT_PROPERTIES.get(s, {}).get("stress_factor", 1.0),
    )
    if not low_stress:
        return slots, unfitted

    per_day: dict[str, float] = {}
    sports_on_day: dict[str, set[str]] = {}
    for slot in slots:
        per_day[slot["day"]] = per_day.get(slot["day"], 0) + slot["duration"]
        sports_on_day.setdefault(slot["day"], set()).add(slot["sport"])

    candidates = sorted(
        (d for d in per_day if d not in quality_days),
        key=lambda d: per_day[d],
    )

    added = []
    for i, day in enumerate(candidates):
        if unfitted < MIN_ENDURANCE_DURATION:
            break
        # A second session should add a different stimulus, not repeat the day's
        # sport — two swims on one Monday is worse than a swim and a spin.
        fresh = [s for s in low_stress if s not in sports_on_day.get(day, set())]
        sport = (fresh or low_stress)[i % len(fresh or low_stress)]
        sports_on_day.setdefault(day, set()).add(sport)
        duration = _round_duration(min(unfitted, SPORT_PROPERTIES.get(sport, {})
                                       .get("max_easy_minutes", 60), 60))
        added.append({
            "day": day,
            "sport": sport,
            "archetype": "easy",
            "duration": duration,
            "workout_type": "recovery",
        })
        unfitted -= duration

    return slots + added, max(0, unfitted)


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
    if step_type in ("warmup", "cooldown", "rest"):
        # These already say what to do; the effort cue would just repeat it.
        note = f"{extra_note} @ {format_pace(pace)}" if extra_note else format_pace(pace)
    else:
        cue = RUN_EFFORT_CUES.get(workout_type, "steady effort")
        note = (f"{extra_note} @ {format_pace(pace)} — {cue}" if extra_note
                else f"{format_pace(pace)} — {cue}")
    return {
        "type": step_type,
        "duration": duration_secs,
        "pace": pace,
        "pace_pct": round(RUN_SPEED_FRACTIONS.get(workout_type, 0.78), 2),
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
    warmup_mins = min(10, max(5, duration // 6))
    cooldown_mins = min(5, max(3, duration // 10))
    drill_mins = min(8, max(3, duration // 8))
    main_mins = duration - warmup_mins - cooldown_mins - drill_mins

    drill = SWIM_DRILLS[variation_seed % len(SWIM_DRILLS)]

    steps = [
        {"type": "warmup", "duration": warmup_mins * 60,
         "notes": f"{_swim_metres(warmup_mins)}m easy freestyle, mix in backstroke"},
        {"type": "steady", "duration": drill_mins * 60,
         "notes": f"Technique: {drill} — focus on form, not speed"},
    ]

    if workout_type in ("threshold", "vo2max", "sweetspot", "tempo"):
        main_set = SWIM_MAIN_SETS[variation_seed % len(SWIM_MAIN_SETS)]
        pace_per_100 = swim_pace_seconds(main_set["pace"], css_pace)
        rep_secs = int(round(pace_per_100 * main_set["dist"] / 100 / 5) * 5)
        reps = max(2, (main_mins * 60) // (rep_secs + main_set["rest_sec"]))
        steps.append({
            "type": "interval", "duration": rep_secs, "repeat": reps,
            "pace": pace_per_100,
            "rest": {"type": "rest", "duration": main_set["rest_sec"]},
            "notes": f"{reps}x{main_set['dist']}m @ {format_swim_pace(pace_per_100)} "
                     f"({main_set['label']}), {main_set['rest_sec']}s rest",
        })
    else:
        steps.append({
            "type": "steady", "duration": main_mins * 60,
            "notes": f"Continuous swim — {_swim_metres(main_mins)}m at easy, relaxed pace",
        })

    steps.append({
        "type": "cooldown", "duration": cooldown_mins * 60,
        "notes": f"{_swim_metres(cooldown_mins, 'recovery')}m easy choice stroke, "
                 "focus on long glide",
    })
    return steps


STRENGTH_EXERCISES = [
    [
        {"name": "Squat", "sets": 3, "reps": "8-10"},
        {"name": "Romanian Deadlift", "sets": 3, "reps": "8-10"},
        {"name": "Step-ups", "sets": 2, "reps": "10 each"},
        {"name": "Plank", "sets": 3, "reps": "30-45s"},
        {"name": "Single-leg Calf Raise", "sets": 2, "reps": "12 each"},
    ],
    [
        {"name": "Bulgarian Split Squat", "sets": 3, "reps": "8 each"},
        {"name": "Hip Thrust", "sets": 3, "reps": "10-12"},
        {"name": "Single-leg Deadlift", "sets": 2, "reps": "8 each"},
        {"name": "Side Plank", "sets": 2, "reps": "30s each"},
        {"name": "Calf Raise", "sets": 3, "reps": "15"},
    ],
    [
        {"name": "Goblet Squat", "sets": 3, "reps": "10-12"},
        {"name": "Glute Bridge", "sets": 3, "reps": "12-15"},
        {"name": "Lunges", "sets": 2, "reps": "10 each"},
        {"name": "Dead Bug", "sets": 3, "reps": "10 each"},
        {"name": "Band Walk", "sets": 2, "reps": "12 each"},
    ],
]


def _build_strength_steps(duration: int, variation_seed: int = 0) -> list[dict]:
    exercises = STRENGTH_EXERCISES[variation_seed % len(STRENGTH_EXERCISES)]
    warmup_mins = 5
    main_mins = duration - warmup_mins

    steps = [
        {"type": "warmup", "duration": warmup_mins * 60,
         "notes": "Dynamic stretching: leg swings, hip circles, bodyweight squats"},
    ]

    per_exercise = max(3, main_mins // len(exercises))
    for ex in exercises:
        steps.append({
            "type": "steady", "duration": per_exercise * 60,
            "notes": f"{ex['name']}: {ex['sets']}x{ex['reps']}",
        })

    return steps


def _pick_strength_days(slots: list[dict],
                        max_sessions: int = MAX_STRENGTH_SESSIONS) -> set[str]:
    """Strength rides along with easy days, never the day before a key run."""
    by_day = {s["day"]: s for s in slots}
    chosen: list[str] = []
    for slot in slots:
        if slot["archetype"] != "easy" or not slot["duration"]:
            continue
        idx = DAY_ORDER.index(slot["day"])
        next_slot = by_day.get(DAY_ORDER[(idx + 1) % 7])
        if (next_slot and next_slot["sport"] == "running"
                and next_slot["archetype"] in ("quality", "long")):
            continue
        if chosen and idx - DAY_ORDER.index(chosen[-1]) < 2:
            continue
        chosen.append(slot["day"])
        if len(chosen) >= max_sessions:
            break
    return set(chosen)


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

    Cycling gets watts, running gets a pace, swimming gets a pace per 100m.
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


def _build_strength_session(seed: int) -> dict:
    duration = STRENGTH_SESSION_MINUTES
    return {
        "name": "Strength Session",
        "sport": "strength",
        "workout_type": "strength",
        "archetype": "supporting",
        "duration_minutes": duration,
        "description": "",
        "coach_notes": "",
        "target_zone": "Strength work",
        "tss_estimate": 25,
        "intensity_factor": IF_TABLE["strength"],
        "priority": "supporting",
        "distance_km": 0,
        "steps": _build_strength_steps(duration, seed),
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
               threshold_pace: int = 300, css_pace: int = 105) -> dict:
    """Build a training plan using constraint-based optimization.

    Computes the training envelope (duration targets, quality slots,
    sport distribution, recovery weeks) and fills in default workouts.
    The AI coach can then override workout design with coaching intelligence.
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
        if total_weeks >= 6 and "recovery" not in week_types[-3:-1]:
            week_types[-2] = "recovery"

    rest_days = set(d.lower() for d in preferred_rest_days) if preferred_rest_days else set()
    hard_days_pref = set(d.lower() for d in preferred_hard_days) if preferred_hard_days else {"tuesday", "thursday", "saturday"}

    training_days = [d for d in DAY_ORDER if d not in rest_days]
    quality_days = [d for d in training_days if d in hard_days_pref][:n_quality]
    easy_days = [d for d in training_days if d not in quality_days]

    primary_sport = profile.get("primary_sport") or EVENT_PRIMARY_SPORT.get(event)
    sport_schedule = _build_sport_schedule(sports, quality_days, easy_days, primary_sport)

    # If the athlete told us what they are training now, start there rather than
    # at a guess — ramping from their actual current load is the whole point.
    current_hours = profile.get("current_weekly_hours")
    start_fraction = (
        current_hours / weekly_hours
        if current_hours and weekly_hours > 0 else None
    )
    week_multipliers = compute_volume_progression(week_types, experience, start_fraction)
    progression = _assess_progression(week_multipliers, week_types, weekly_hours,
                                      current_hours, experience)

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

        week_quality_days = quality_days[:week_quality]
        base_slots = _assign_archetypes(
            sport_schedule, training_days, week_quality_days,
            capacity["long_session_essential"],
        )
        week_minutes = weekly_hours * 60 * week_multipliers[week_idx]
        # Strength costs the athlete time like anything else, so it comes out of
        # the weekly budget rather than being bolted on top of it.
        week_minutes -= STRENGTH_SESSION_MINUTES * MAX_STRENGTH_SESSIONS if "strength" in sports else 0
        slots, unfitted = _allocate_slot_durations(base_slots, week_minutes, week_type)
        slots, unfitted = _add_second_sessions(
            slots, unfitted, sports, week_quality_days, max_sessions_per_day,
        )

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
                strength = _build_strength_session(week_num + i)
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
