import asyncio
import httpx
from ..config import settings
from .plan_builder import (
    build_plan, validate_plan, compute_tss, IF_TABLE, _target_zone,
    format_pace, format_swim_pace,
)
import logging
import json
from datetime import datetime

log = logging.getLogger(__name__)

# How many weeks are written concurrently. Enough to keep a 12-week plan fast
# without tripping the provider's rate limits.
WEEK_CONCURRENCY = 4

# Token usage tracking
_usage = {
    "total_calls": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_tokens": 0,
    "estimated_cost": 0.0,
    "provider": settings.ai_provider,
    "calls": [],  # last 50 calls
}

# Cost per 1M tokens (input/output) — keyed by model name
COST_TABLE = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-fable-5": {"input": 3.00, "output": 15.00},
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


def _track_usage(provider: str, model: str, tier: str,
                 input_tokens: int, output_tokens: int):
    total = input_tokens + output_tokens
    costs = COST_TABLE.get(model, {"input": 0, "output": 0})
    cost = (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000

    _usage["total_calls"] += 1
    _usage["total_input_tokens"] += input_tokens
    _usage["total_output_tokens"] += output_tokens
    _usage["total_tokens"] += total
    _usage["estimated_cost"] += cost
    _usage["provider"] = provider
    _usage["calls"].append({
        "time": datetime.utcnow().isoformat(),
        "provider": provider,
        "model": model,
        "tier": tier,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": round(cost, 6),
    })
    _usage["calls"] = _usage["calls"][-50:]


def get_usage() -> dict:
    return {
        "total_calls": _usage["total_calls"],
        "total_tokens": _usage["total_tokens"],
        "total_input_tokens": _usage["total_input_tokens"],
        "total_output_tokens": _usage["total_output_tokens"],
        "estimated_cost": round(_usage["estimated_cost"], 4),
        "provider": _usage["provider"],
        "recent_calls": _usage["calls"][-10:],
    }


SESSION_PROMPT = """You are an expert endurance sports coach writing structured training sessions.
You write detailed, professional workout prescriptions similar to TrainingPeaks.

Output a JSON object with these fields:
- name: descriptive session name (e.g. "4x8 Sweet Spot with Cadence Builds")
- description: 2-3 sentence coaching description. Explain the PURPOSE of the workout, what energy system it targets, how it should feel, and any execution cues. Example: "This session develops your ability to sustain power at the upper end of your aerobic zone. The 8-minute blocks build muscular endurance while staying below threshold. Focus on smooth pedaling and keeping your upper body relaxed."
- workout_type: the type (intervals, sweetspot, threshold, tempo, endurance, vo2max, sprint)
- coach_notes: 1-2 sentences of execution tips (cadence targets, breathing, when to bail)
- warmup_notes: brief warmup guidance ("include 2x30s high-cadence spins")
- target_zone: primary training zone description (e.g. "Zone 3-4, 86-95% FTP")
- steps: array of step objects, each with:
  - type: "warmup" | "interval" | "rest" | "cooldown" | "steady"
  - duration: seconds
  - power: fraction of FTP (e.g. 0.88 = 88% FTP), or null for rest
  - power_start: for ramp intervals, starting power fraction
  - power_end: for ramp intervals, ending power fraction
  - cadence: target RPM or null
  - repeat: number of repetitions (for interval blocks)
  - rest: a rest step object (used with repeat)
  - notes: brief step-level cue (e.g. "seated, smooth" or "build effort gradually")
- duration_seconds: total workout duration
- tss_estimate: estimated TSS
- intensity_factor: estimated IF (NP/FTP)

Return ONLY the JSON object, no markdown fences or explanation."""


PLAN_PROMPT = """You are an expert endurance sports coach building structured training plans.
Write professional plans with detailed workout descriptions similar to TrainingPeaks.

Rules:
- Respect the total hours budget
- Place hard sessions when TSB allows (not when heavily fatigued)
- Don't stack two hard sessions on consecutive days unless fitness supports it
- Include at least 1 rest day per week
- Each workout gets a detailed description explaining purpose, feel, and execution cues
- Periodize within the week: hard/easy pattern, build toward key sessions
- Swapping two workouts on the same day has no consequence
- If a workout is skipped, reduce remaining week load proportionally

Output a JSON object:
{
  "name": "Descriptive plan name",
  "description": "2-3 sentence coaching rationale for the week. What's the focus, why this load?",
  "week_focus": "aerobic base|threshold development|vo2max block|recovery|race prep|strength",
  "days": [
    {
      "day": "monday",
      "date": "2026-08-04",
      "workouts": [
        {
          "name": "Descriptive session name",
          "sport": "cycling|running|swimming|strength",
          "workout_type": "endurance|sweetspot|threshold|tempo|vo2max|intervals|easy|rest|strength",
          "duration_minutes": 60,
          "description": "2-3 sentence description: purpose, target zone, feel, execution cues. Like a TrainingPeaks workout description.",
          "coach_notes": "Execution tips: cadence, RPE, when to back off",
          "target_zone": "Zone description and power/pace range",
          "tss_estimate": 50,
          "intensity_factor": 0.70,
          "priority": "key|supporting|optional",
          "steps": [...]
        }
      ]
    },
    ...for all 7 days (monday through sunday)
  ],
  "total_hours": 8.5,
  "total_tss": 450,
  "notes": "Weekly coaching summary and things to watch for"
}

Return ONLY the JSON object."""


# The philosophy is shared by both coaching calls below.
TRAINING_PHILOSOPHY = """## TRAINING PHILOSOPHY

Training distribution should emerge from the athlete's constraints, NOT from a predefined
methodology (not "Norwegian", not "polarized", not "pyramidal"). Ask: "Given this athlete's
goals, available time, recovery, and fitness — what is the minimum intensity required to achieve
the necessary training stimulus while remaining sustainable?"

### Volume vs Intensity
- Volume is the preferred adaptation driver (less fatigue per unit of fitness).
- Intensity compensates only when volume cannot be increased.
- More hours -> lower training density -> more easy volume.
- Fewer hours -> higher density -> relatively more quality per hour.
- But ABSOLUTE quality work changes only modestly:
    5h/wk -> 2 quality sessions
    8h/wk -> 2 quality sessions
    15h/wk -> still around 2-3 quality sessions
- Higher-volume athletes mainly gain additional easy training, not more intervals.

### Frequency Follows Volume
Extra hours buy extra SESSIONS, not longer ones. Roughly, per discipline:
    <5h/wk   -> 1 session
    5-9h/wk  -> 2 sessions
    9-14h/wk -> 3 sessions
    14h+/wk  -> 4+ sessions
When hours increase, add frequency to the low-stress disciplines first
(swimming and cycling); running frequency grows last because it carries the
most orthopedic cost. The envelope already reflects this — describe it, do
not fight it.

### Sport-Specific Cost
- Running: highest orthopedic stress. Increase cautiously. Protect key run sessions.
- Cycling: lowest orthopedic stress. THE volume engine — for a multi-sport
  athlete the bike should carry the largest share of weekly hours (roughly
  45-60%), and it is where additional volume goes first as hours grow.
- Swimming: technique-limited. Frequency > long sessions.
- Strength: adds fatigue. Heavy lower-body should not interfere with key run workouts.

### Event Specificity
As race distance increases:
- Required durability and volume increase
- Ability to substitute volume with intensity decreases
- 5K: intensity can replace some volume
- Marathon: long runs become essential
- Ironman: large aerobic volume cannot be replaced with intervals

### Session Archetypes
Each discipline should generally contain at most one session of each archetype per week:
- one long session
- zero or one quality session
- one or more easy sessions
- optional recovery session

Every session in the envelope is tagged with its archetype. Respect those tags.
When multiple designs satisfy the required weekly volume, prefer the one that:
1. Uses appropriately sized sessions rather than fewer oversized ones.
2. Places most additional endurance volume into the designated long session.
3. Maintains realistic recovery between key workouts.

### Progression Rules
- Only increase one major variable at a time (volume, frequency, intensity, duration)
- Include recovery weeks every 3-5 weeks (20-40% volume reduction)
- Never increase multiple variables simultaneously

### Safety Constraints (MUST follow)
- Never prescribe excessive intensity for the available volume
- Never increase running load too rapidly
- Never omit recovery weeks
- Never schedule unnecessary consecutive hard days
- Never overemphasize one discipline without event-specific justification"""


# Used only when the athlete has explicitly opted into training_style ==
# "norwegian" — plan_builder has already applied the hard guards (minimum
# weekly hours, no cutback weeks, no stacking on an active ramp) and
# restructured up to two quality days into AM sub-threshold / PM shakeout
# pairs, tagging the AM session's workout_type "sub_threshold". Unlike
# TRAINING_PHILOSOPHY above, this block names the method explicitly — the
# athlete chose it and wants it coached as such, not described generically.
NORWEGIAN_TRAINING_PHILOSOPHY = """## TRAINING PHILOSOPHY: NORWEGIAN DOUBLE-THRESHOLD METHOD

This athlete has opted into Norwegian-style double-threshold training. Unlike the
generic methodology-agnostic approach, name the method explicitly and coach to it —
the athlete chose this style and expects it, not a euphemism for it.

### The Method
- Up to two days a week carry a double session: a controlled AM sub-threshold
  session (~90-95% FTP / threshold pace, RPE 5-6) followed by an easy PM shakeout
  in a lower-stress discipline (never a second run the same day).
- Sub-threshold work is intentionally SHORT rest between reps (about a minute) so
  the athlete stays just under threshold rather than recovering enough to push
  over it — the point is high-quality time near threshold with low accumulated
  fatigue, not maximal single efforts.
- The AM session's `workout_type` is already "sub_threshold" in the envelope —
  write intervals that hold that effort steady and controlled, not building to a
  crescendo like a normal threshold set.
- The PM shakeout is genuinely easy (recovery pace/power) — its only job is
  circulation and technique, never intensity. Keep it short and low-key.
- The other quality/easy/long sessions in the week follow the same volume,
  frequency and sport-cost principles below — double-threshold days replace some
  of the week's quality slots, they do not add new methodology on top of them.

### Volume vs Intensity
- Volume is still the preferred adaptation driver — double-threshold days control
  how much QUALITY time near threshold the athlete can absorb without excess
  fatigue, they do not replace easy volume elsewhere in the week.
- Higher-volume athletes mainly gain additional easy training, not more doubles.

### Sport-Specific Cost
- Running: highest orthopedic stress. Increase cautiously. Protect key run sessions.
- Cycling: lowest orthopedic stress. THE volume engine — for a multi-sport athlete
  the bike should carry the largest share of weekly hours (roughly 45-60%).
- Swimming: technique-limited. Frequency > long sessions.
- Strength: adds fatigue. Heavy lower-body should not interfere with key run workouts.

### Event Specificity
As race distance increases, required durability and volume increase and the
ability to substitute volume with intensity decreases — double-threshold days
sharpen threshold-adjacent fitness, they do not substitute for race-specific
long-session volume.

### Session Archetypes
Every session in the envelope is tagged with its archetype (quality/easy/long).
Respect those tags, including the AM/PM pairing on double-threshold days.

### Progression Rules
- Only increase one major variable at a time (volume, frequency, intensity, duration)
- Include recovery weeks every 3-5 weeks (20-40% volume reduction) — double-threshold
  days are never scheduled in a recovery or taper week
- Never increase multiple variables simultaneously

### Safety Constraints (MUST follow)
- Never turn the PM shakeout into a second hard session
- Never schedule double-threshold days back to back or adjacent to the long session
- Never increase running load too rapidly
- Never omit recovery weeks
- Never overemphasize one discipline without event-specific justification"""


def _philosophy_block(training_style: str) -> str:
    return NORWEGIAN_TRAINING_PHILOSOPHY if training_style == "norwegian" else TRAINING_PHILOSOPHY


STRATEGY_PROMPT_HEAD = """You are an expert endurance sports coach setting the direction for a training block.

The plan builder has already computed the TRAINING ENVELOPE — weekly hours, session
durations, quality/easy slots, sport distribution and recovery weeks. You are NOT
writing individual workouts here. You are deciding the BLOCK STRATEGY that a second
pass will use to write each week.

"""

STRATEGY_PROMPT_TAIL = """

## WHAT TO RETURN

Return a JSON object and nothing else:
{
  "description": "2-3 sentence coaching rationale for the whole block",
  "progression_notes": "How the block builds week to week, and what changes when",
  "capacity_feedback": "If the athlete's time is a poor fit for the goal, say what to consider (more time, longer preparation, adjusted expectations). Empty string if the plan is well matched.",
  "weeks": [
    {
      "week": 1,
      "intent": "One sentence: what this week is for",
      "quality": [
        {"day": "tuesday", "workout_type": "threshold|sweetspot|tempo|vo2max", "focus": "short phrase, e.g. 'long cruise intervals, build duration'"}
      ]
    }
  ]
}

Include an entry for EVERY week in the envelope, and one "quality" entry for each
quality session that week. Vary the workout types across weeks so each energy system
is developed, and progress them deliberately rather than at random. Return ONLY JSON."""


def _strategy_prompt(training_style: str = "standard") -> str:
    return STRATEGY_PROMPT_HEAD + _philosophy_block(training_style) + STRATEGY_PROMPT_TAIL


# Kept as a module-level constant too — some tests/tools may still import it
# directly, and the standard style is the default.
STRATEGY_PROMPT = _strategy_prompt("standard")


WEEK_PROMPT_HEAD = """You are an expert endurance sports coach writing one week of a training plan.

You are given the block strategy and the ENVELOPE for a single week: every session's
day, sport, archetype and duration. Write the actual workouts for that week only.

"""

WEEK_PROMPT_TAIL = """

## HOW TO WRITE STEPS PER SPORT

Steps are pushed to the athlete's watch, so they must be executable as written.

- CYCLING: use `power` as a fraction of FTP (0.68 = 68% FTP) plus `cadence`.
- RUNNING: no power. Set `pace` in SECONDS PER KM against the athlete's run
  threshold pace given above, and repeat the target plus an RPE cue in `notes`
  (e.g. "5:42/km — conversational"). Never use watts or %FTP for a run.
- SWIMMING: no power. Set `pace` in SECONDS PER 100M against the athlete's CSS,
  and put the set in `notes` (e.g. "8x100m @ 1:45/100m, 15s rest"). Always
  include a technique/drill block. Never reference FTP or watts for a swim.
- STRENGTH: no power and NO timed blocks. Each exercise is a step with `reps`
  (repetitions per set) and `sets`, plus a `rest` step in seconds between sets.
  Never prescribe an exercise as a duration — "Split Squat, 5 minutes" is not
  how anyone lifts. Keep the envelope's exercises and set/rep scheme unless you
  have a reason to change them; you may rewrite names, cues and coach notes.
  Bias toward heavy-ish low-rep single-leg, posterior chain and trunk work.

## WHAT TO RETURN

Write one entry for EVERY session listed in the week envelope, using the exact `day`
and `workout_index` given. Use the quality workout types from the block strategy.
Keep each workout's total step duration within +/-2 minutes of the envelope duration —
those durations are the athlete's real available time, not a suggestion.

Return a JSON object and nothing else:
{
  "workouts": [
    {
      "day": "tuesday",
      "workout_index": 0,
      "name": "Specific workout name (e.g. 4x8 Threshold w/ Cadence Builds)",
      "workout_type": "threshold|sweetspot|tempo|vo2max|endurance",
      "description": "2-3 sentence coaching description: purpose, energy system, feel, execution cues",
      "coach_notes": "Key execution tip (1 sentence)",
      "steps": [{"type": "warmup|interval|steady|cooldown", "duration": 600, "power": 0.68, "cadence": 90, "repeat": 4, "rest": {"type": "rest", "duration": 180, "power": 0.55}, "notes": "cue"}]
    }
  ]
}

Do not include rest days. Return ONLY JSON."""


def _week_prompt(training_style: str = "standard") -> str:
    return WEEK_PROMPT_HEAD + _philosophy_block(training_style) + WEEK_PROMPT_TAIL


# Kept as a module-level constant too, for the same reason as STRATEGY_PROMPT.
WEEK_PROMPT = _week_prompt("standard")


def _build_user_prompt(sport: str, session_type: str, duration_minutes: int,
                       ftp: int, fitness_context: dict | None, notes: str | None) -> str:
    parts = [
        f"Write a {duration_minutes}-minute {session_type} session for {sport}.",
        f"Athlete FTP: {ftp}W.",
    ]
    if fitness_context:
        if fitness_context.get("ctl"):
            parts.append(f"Current CTL (fitness): {fitness_context['ctl']:.0f}")
        if fitness_context.get("atl"):
            parts.append(f"Current ATL (fatigue): {fitness_context['atl']:.0f}")
        if fitness_context.get("tsb"):
            parts.append(f"Current TSB (form): {fitness_context['tsb']:.0f}")
    if notes:
        parts.append(f"Additional notes: {notes}")
    return " ".join(parts)


async def generate_session(sport: str, session_type: str, duration_minutes: int,
                           ftp: int, fitness_context: dict | None = None,
                           notes: str | None = None) -> dict | None:
    user_prompt = _build_user_prompt(sport, session_type, duration_minutes, ftp, fitness_context, notes)
    return await _generate(SESSION_PROMPT, user_prompt, tier="light")


async def generate_structured_plan(profile: dict, ftp: int,
                                   fitness_context: dict | None = None,
                                   start_date: str = "",
                                   first_week_from: str = "") -> dict | None:
    """Generate a multi-week periodized plan.

    The plan builder computes the training envelope (duration targets,
    quality/easy slots, sport distribution, recovery scheduling).
    The AI makes coaching decisions: workout types, interval design,
    progression, and coaching rationale.
    Falls back to algorithmic defaults if AI is unavailable.
    """
    plan = build_plan(profile=profile, ftp=ftp,
                      fitness_context=fitness_context, start_date=start_date,
                      threshold_pace=settings.threshold_pace,
                      css_pace=settings.swim_css_pace,
                      first_week_from=first_week_from)

    # Norwegian style is named and coached explicitly rather than through the
    # methodology-agnostic philosophy — see NORWEGIAN_TRAINING_PHILOSOPHY.
    training_style = profile.get("training_style", "standard")
    strategy_prompt = _strategy_prompt(training_style)
    week_prompt = _week_prompt(training_style)

    strategy = await _generate(
        strategy_prompt,
        _build_strategy_summary(plan, profile, ftp, fitness_context),
        tier="heavy",
    )
    if not strategy:
        log.warning(f"Plan strategy call failed: {get_last_error()}")
        plan["description"] = _fallback_description(profile)
        plan["progression_notes"] = _fallback_progression(plan)
        return plan

    plan["description"] = strategy.get("description", "")
    plan["progression_notes"] = strategy.get("progression_notes", "")
    if strategy.get("capacity_feedback"):
        plan["capacity_feedback"] = strategy["capacity_feedback"]

    week_strategies = {w.get("week"): w for w in strategy.get("weeks", [])}

    # One call per week. A whole block in a single response runs past the model's
    # output limit and comes back as truncated JSON, which parses to nothing —
    # per-week calls stay well inside the budget and run concurrently.
    semaphore = asyncio.Semaphore(WEEK_CONCURRENCY)

    async def write_week(week: dict) -> tuple[dict, dict | None]:
        async with semaphore:
            summary = _build_week_summary(
                week, week_strategies.get(week["week_number"]), plan, profile, ftp,
                fitness_context,
            )
            return week, await _generate(week_prompt, summary, tier="heavy")

    results = await asyncio.gather(
        *(write_week(w) for w in plan["weeks"]), return_exceptions=True,
    )

    written = 0
    for result in results:
        if isinstance(result, BaseException):
            log.warning(f"Week generation raised: {result}")
            continue
        week, payload = result
        if not payload:
            log.warning(f"Week {week['week_number']} not customized: {get_last_error()}")
            continue
        _apply_week_workouts(week, payload.get("workouts", []))
        written += 1

    log.info(f"AI wrote {written}/{len(plan['weeks'])} weeks")
    if not written:
        plan["description"] = _fallback_description(profile)
        plan["progression_notes"] = _fallback_progression(plan)

    plan["safety_warnings"] = validate_plan(plan, profile)
    return plan


def _apply_week_workouts(week: dict, workouts: list) -> None:
    """Merge the AI's workouts into one week's envelope."""
    by_day = {d["day"]: d for d in week.get("days", [])}
    for wd in workouts:
        if not isinstance(wd, dict):
            continue
        day = by_day.get(wd.get("day", ""))
        idx = wd.get("workout_index", 0)
        if not day or not isinstance(idx, int) or idx >= len(day["workouts"]):
            continue

        wo = day["workouts"][idx]
        if wo.get("workout_type") == "rest":
            continue
        if wd.get("name"):
            wo["name"] = wd["name"]
        # Strength keeps its type — the AI relabelling one as "endurance" would
        # push it to the watch as a ride and skew its TSS.
        if wd.get("workout_type") and wo["sport"] != "strength":
            wo["workout_type"] = wd["workout_type"]
        if wd.get("description"):
            wo["description"] = wd["description"]
        if wd.get("coach_notes"):
            wo["coach_notes"] = wd["coach_notes"]
        if wd.get("steps") and isinstance(wd["steps"], list):
            wo["steps"] = wd["steps"]
        _reconcile_workout(wo)

    _recompute_week_totals(week)


def _recompute_week_totals(week: dict) -> None:
    """Refresh the week header after the AI has rewritten its workouts.

    Hours and TSS are computed from the envelope before the AI runs; if its
    workouts land even slightly off, the header would keep advertising the
    old numbers.
    """
    minutes = 0
    tss = 0.0
    distance: dict[str, float] = {}
    for day in week.get("days", []):
        for wo in day.get("workouts", []):
            if wo.get("workout_type") == "rest":
                continue
            minutes += wo.get("duration_minutes", 0)
            tss += wo.get("tss_estimate", 0)
            if wo.get("distance_km"):
                distance[wo["sport"]] = distance.get(wo["sport"], 0) + wo["distance_km"]

    week["target_hours"] = round(minutes / 60, 1)
    week["target_tss"] = round(tss)
    if distance:
        week["distance_km"] = {s: round(d, 1) for s, d in distance.items()}


def _reconcile_workout(workout: dict) -> None:
    """Keep a workout's headline numbers consistent with its actual steps.

    The AI writes the steps, so duration, TSS and zone have to be recomputed
    from what it wrote — otherwise the plan advertises a 60-minute session
    that is 85 minutes of intervals once it reaches the athlete's watch.
    """
    steps = workout.get("steps") or []
    seconds = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        repeat = step.get("repeat") or 1
        rest = step.get("rest") or {}
        seconds += repeat * (step.get("duration", 0) + rest.get("duration", 0))

    if seconds:
        workout["duration_minutes"] = max(1, round(seconds / 60))

    workout_type = workout.get("workout_type", "endurance")
    if_val = IF_TABLE.get(workout_type, workout.get("intensity_factor", 0.65))
    workout["intensity_factor"] = if_val
    workout["tss_estimate"] = round(compute_tss(workout["duration_minutes"], if_val))

    workout["target_zone"] = _target_zone(
        workout["sport"], workout_type, settings.threshold_pace, settings.swim_css_pace,
    )


def _build_athlete_context(profile: dict, ftp: int,
                           fitness_context: dict | None = None) -> list[str]:
    """The athlete facts both coaching calls need."""
    lines = [
        f"Athlete FTP: {ftp}W (cycling)",
        f"Run threshold pace: {format_pace(settings.threshold_pace)}",
        f"Swim CSS pace: {format_swim_pace(settings.swim_css_pace)}",
        f"Experience: {profile.get('experience_level', 'intermediate')}",
        f"Goal: {profile.get('goal', 'general_fitness')}",
        f"Sports: {', '.join(profile.get('sports', ['cycling']))}",
        f"Weekly hours: {profile.get('weekly_hours', 8)}h",
    ]

    history = profile.get("observed_history")
    if history:
        by_sport = ", ".join(
            f"{sport} {hours}h" for sport, hours in history["hours_by_sport"].items()
        )
        lines.append(
            f"ACTUALLY TRAINING (last {history['weeks_observed']} weeks of synced "
            f"data): {history['weekly_hours']}h/week across "
            f"{history['sessions_per_week']} sessions — {by_sport}"
        )

    optional = [
        ("goal_event", "Target event"),
        ("goal_event_distance", "Event distance"),
        ("goal_date", "Event date"),
        ("goal_performance", "Target performance"),
        ("current_weekly_hours", "Current training volume (h/week)"),
        ("recovery_capacity", "Recovery capacity"),
        ("injury_notes", "Injury history"),
    ]
    for key, label in optional:
        if profile.get(key):
            lines.append(f"{label}: {profile[key]}")

    if profile.get("weaknesses"):
        lines.append(f"Weaknesses to address: {', '.join(profile['weaknesses'])}")
    if profile.get("strengths"):
        lines.append(f"Strengths: {', '.join(profile['strengths'])}")
    if profile.get("has_trainer"):
        lines.append("Has smart trainer (ERG mode available)")
    if profile.get("has_power_meter"):
        lines.append("Has outdoor power meter")
    if profile.get("notes"):
        lines.append(f"Athlete notes: {profile['notes']}")

    if fitness_context:
        parts = [
            f"{k.upper()}={fitness_context[k]:.0f}"
            for k in ("ctl", "atl", "tsb") if fitness_context.get(k)
        ]
        if parts:
            lines.append(f"Current fitness: {', '.join(parts)}")

    return lines


def _build_strategy_summary(plan: dict, profile: dict, ftp: int,
                            fitness_context: dict | None = None) -> str:
    """Block-level context. Week shapes only — no individual sessions."""
    lines = [f"Plan: {plan['name']} ({plan['total_weeks']} weeks)"]
    lines += _build_athlete_context(profile, ftp, fitness_context)

    cap = plan.get("capacity_assessment", {})
    if cap:
        lines.append("\n--- CAPACITY ASSESSMENT ---")
        lines.append(f"Strategy: {cap.get('strategy', 'unknown')}")
        lines.append(f"Capacity ratio: {cap.get('capacity_ratio', 'N/A')} "
                     f"(athlete hours / typical hours for event)")
        lines.append(f"Intensity substitution allowed: {cap.get('intensity_substitution', 'N/A')}")
        lines.append(f"Long sessions essential: {cap.get('long_session_essential', False)}")
        lines.append(f"Assessment: {cap.get('density_note', '')}")

    density = plan.get("training_density", {})
    if density:
        lines.append("\n--- TRAINING DENSITY ---")
        lines.append(f"Quality fraction: {density.get('quality_fraction', 'N/A')} "
                     f"({density.get('quality_minutes_total', 0)}min quality / week)")
        lines.append(f"Easy fraction: {density.get('easy_fraction', 'N/A')} "
                     f"({density.get('easy_minutes_total', 0)}min easy / week)")

    prog = plan.get("progression_assessment", {})
    if prog:
        lines.append("\n--- VOLUME RAMP ---")
        lines.append(
            f"Ramps {prog['start_hours']}h -> {prog['peak_hours']}h/week over "
            f"{prog['build_weeks']} build weeks (+{prog['weekly_increase_pct']}%/build week)."
        )
        source = {
            "observed": "the athlete's actual synced training volume",
            "stated": "what the athlete reported they are currently training",
            "default": "a default, since there is no history to go on",
        }.get(prog.get("volume_source", "default"))
        lines.append(f"The starting point comes from {source}.")
        if prog.get("readiness_note"):
            lines.append(f"Readiness: {prog['readiness_note']}")
        if prog.get("note"):
            lines.append(f"Shortfall: {prog['note']}")

    targets = plan.get("session_targets", {})
    if targets.get("requested"):
        lines.append("\n--- STATED WEEKLY FREQUENCY ---")
        lines.append(
            "The athlete asked for these session counts per week: "
            + ", ".join(f"{sport} {n}x" for sport, n in sorted(targets["requested"].items()))
            + ". These are their own decision, already built into the schedule. Do "
            "not argue with them or suggest different frequencies."
        )
        if targets.get("note"):
            lines.append(
                f"Not all of it fit ({targets['note']}) — the schedule below is what "
                "was actually possible. You may mention this once in capacity_feedback."
            )

    lines.append("\n--- WEEK SHAPES ---")
    lines.append(
        "Weekly volume is already fixed and cannot be changed — it ramps to the "
        "athlete's available hours at the last build week. Describe this ramp "
        "accurately in progression_notes; your progression decisions are about "
        "INTENSITY and workout type, not hours. The volume ramp is already "
        "reported to the athlete separately — do NOT repeat it in "
        "capacity_feedback, which is only for time-vs-goal mismatches."
    )
    for week in plan["weeks"]:
        quality = [
            f"{d['day']} ({w['sport']})"
            for d in week["days"] for w in d["workouts"]
            if w.get("archetype") == "quality"
        ]
        lines.append(
            f"Week {week['week_number']} ({week['week_type']}): "
            f"{week['target_hours']}h, {week['target_tss']} TSS — "
            f"quality slots: {', '.join(quality) if quality else 'none'}"
        )
        if week.get("volume_note"):
            lines.append(f"  note: {week['volume_note']}")

    return "\n".join(lines)


def _build_week_summary(week: dict, week_strategy: dict | None, plan: dict,
                        profile: dict, ftp: int,
                        fitness_context: dict | None = None) -> str:
    """Envelope for a single week, plus the block strategy for it."""
    lines = [
        f"Plan: {plan['name']} — writing week {week['week_number']} "
        f"of {plan['total_weeks']}",
    ]
    lines += _build_athlete_context(profile, ftp, fitness_context)

    if plan.get("progression_notes"):
        lines.append(f"\nBlock progression: {plan['progression_notes']}")

    if week_strategy:
        lines.append("\n--- STRATEGY FOR THIS WEEK ---")
        if week_strategy.get("intent"):
            lines.append(f"Intent: {week_strategy['intent']}")
        for q in week_strategy.get("quality", []):
            lines.append(
                f"Quality session on {q.get('day')}: {q.get('workout_type')} "
                f"— {q.get('focus', '')}"
            )

    lines.append(
        f"\n--- WEEK {week['week_number']} ENVELOPE ({week['week_type']}): "
        f"{week['focus']} — {week['target_hours']}h, {week['target_tss']} TSS ---"
    )
    for day in week["days"]:
        for i, w in enumerate(day["workouts"]):
            if w["workout_type"] == "rest":
                continue
            lines.append(
                f"  day={day['day']} workout_index={i} | {w['sport']} | "
                f"archetype={w.get('archetype', 'easy')} | "
                f"default_type={w['workout_type']} | "
                f"duration={w['duration_minutes']}min"
            )
            steps_summary = _summarize_steps(w.get("steps", []))
            if steps_summary:
                lines.append(f"    default steps: {steps_summary}")

    return "\n".join(lines)


def _summarize_steps(steps: list[dict]) -> str:
    """One-line summary of workout steps for AI context.

    Swim and strength steps carry notes instead of power targets.
    """
    parts = []
    for s in steps:
        stype = s.get("type", "?")
        dur = s.get("duration", 0)
        pwr = s.get("power")
        reps = s.get("repeat")
        intensity = f"@{pwr:.0%}" if isinstance(pwr, (int, float)) else ""

        if stype == "warmup":
            parts.append(f"warmup {dur//60}min")
        elif stype == "cooldown":
            parts.append(f"cooldown {dur//60}min")
        elif stype == "interval" and reps:
            rest_dur = s.get("rest", {}).get("duration", 0)
            parts.append(f"{reps}x{dur//60}min{intensity}/{rest_dur//60}min rest")
        elif stype == "interval":
            parts.append(f"{dur}s{intensity}")
        elif stype == "steady":
            parts.append(f"steady {dur//60}min{intensity}")

        if not intensity and s.get("notes"):
            parts[-1] = f"{parts[-1]} ({s['notes']})" if parts else s["notes"]
    return " → ".join(parts)


def _fallback_description(profile: dict) -> str:
    exp = profile.get("experience_level", "intermediate")
    goal = profile.get("goal", "general_fitness")
    hours = profile.get("weekly_hours", 8)
    sports = profile.get("sports", ["cycling"])
    sport_str = ", ".join(s for s in sports if s != "strength")
    return (
        f"A constraint-based training plan for {exp}-level athletes focused on "
        f"{goal} with {hours}h/week across {sport_str}. Training density adapts "
        f"to available volume — quality sessions stay focused while easy volume "
        f"provides the aerobic foundation."
    )


def _fallback_progression(plan: dict) -> str:
    weeks = plan.get("weeks", [])
    build_count = sum(1 for w in weeks if w["week_type"] == "build")
    recovery_count = sum(1 for w in weeks if w["week_type"] == "recovery")
    return (
        f"{build_count} build weeks with {recovery_count} recovery weeks. "
        f"Volume progresses gradually with recovery periods for adaptation."
    )


async def adjust_plan(current_plan: dict, action: str, details: str) -> dict | None:
    """Ask the AI to adjust a plan after a skip/move."""
    prompt = f"""The athlete's current weekly plan is:
{json.dumps(current_plan, indent=2)}

Action taken: {action}
Details: {details}

Adjust the remaining days of the plan to compensate. Keep the same JSON structure.
Only modify days that haven't passed yet. Return the full updated plan JSON."""
    return await _generate(PLAN_PROMPT, prompt, tier="light")


def _get_model(tier: str) -> str:
    provider = settings.ai_provider
    if provider == "ollama":
        return settings.ollama_model_heavy if tier == "heavy" else settings.ollama_model_light
    elif provider == "claude":
        return settings.claude_model_heavy if tier == "heavy" else settings.claude_model_light
    elif provider == "openai":
        return settings.openai_model_heavy if tier == "heavy" else settings.openai_model_light
    return ""


_last_error: str = ""


def get_last_error() -> str:
    return _last_error


def _parse_json_response(text: str, stop_reason: str | None = None) -> dict | None:
    """Parse a model response, salvaging what we can from a truncated one.

    A response cut off at max_tokens still contains most of its objects. Rather
    than throwing the whole thing away, close the open brackets and keep the
    entries that did come through.
    """
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        pass

    # Trim back to the last complete top-level entry, then close the structure.
    salvage = text.rstrip().rstrip(",")
    for cut in range(len(salvage), 0, -1):
        if salvage[cut - 1] not in "}]":
            continue
        candidate = salvage[:cut]
        depth_curly = candidate.count("{") - candidate.count("}")
        depth_square = candidate.count("[") - candidate.count("]")
        if depth_curly < 0 or depth_square < 0:
            continue
        repaired = candidate + "]" * depth_square + "}" * depth_curly
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            continue
        log.warning(
            f"Recovered truncated JSON response (stop_reason={stop_reason}); "
            f"kept {cut} of {len(text)} chars"
        )
        return parsed

    log.error(f"JSON parse failed. First 200 chars: {text[:200]}")
    return None


async def _generate(system_prompt: str, user_prompt: str,
                    tier: str = "light") -> dict | None:
    global _last_error
    _last_error = ""
    model = _get_model(tier)
    log.info(f"AI generate: provider={settings.ai_provider} model={model} tier={tier}")
    try:
        if settings.ai_provider == "ollama":
            return await _ollama_generate(system_prompt, user_prompt, model, tier)
        elif settings.ai_provider == "claude":
            return await _claude_generate(system_prompt, user_prompt, model, tier)
        elif settings.ai_provider == "openai":
            return await _openai_generate(system_prompt, user_prompt, model, tier)
    except Exception as e:
        _last_error = str(e)
        log.error(f"AI generation failed: {e}")
        return None


async def _ollama_generate(system_prompt: str, user_prompt: str,
                           model: str, tier: str) -> dict | None:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{settings.ollama_url}/api/generate", json={
            "model": model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "format": "json",
        })
        if resp.status_code != 200:
            log.error(f"Ollama error: {resp.text}")
            return None
        data = resp.json()
        text = data.get("response", "")
        prompt_tokens = data.get("prompt_eval_count", len(user_prompt) // 4)
        completion_tokens = data.get("eval_count", len(text) // 4)
        _track_usage("ollama", model, tier, prompt_tokens, completion_tokens)
        return json.loads(text)


async def _claude_generate(system_prompt: str, user_prompt: str,
                           model: str, tier: str) -> dict | None:
    global _last_error
    if not settings.anthropic_api_key:
        _last_error = "No Anthropic API key set"
        return None
    timeout = 300 if tier == "heavy" else 90
    max_tokens = 32000 if tier == "heavy" else 4000
    is_thinking_model = "fable" in model or "opus" in model
    async with httpx.AsyncClient(timeout=timeout) as client:
        body: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if is_thinking_model:
            body["temperature"] = 1
            body["thinking"] = {"type": "adaptive"}
            body["output_config"] = {"effort": "high" if tier == "heavy" else "low"}
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
        )
        if resp.status_code != 200:
            error_text = resp.text[:500]
            log.error(f"Claude error ({resp.status_code}): {error_text}")
            _last_error = f"Claude API {resp.status_code}: {error_text}"
            return None
        resp_data = resp.json()
        usage_data = resp_data.get("usage", {})
        _track_usage("claude", model, tier,
                     usage_data.get("input_tokens", 0),
                     usage_data.get("output_tokens", 0))
        stop_reason = resp_data.get("stop_reason")
        if stop_reason == "max_tokens":
            log.warning(f"Claude response truncated (hit max_tokens={max_tokens})")
        text = ""
        for block in resp_data.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
                break
        if not text:
            _last_error = "No text block in Claude response"
            log.error(f"No text block found. Content types: {[b.get('type') for b in resp_data.get('content', [])]}")
            return None
        parsed = _parse_json_response(text, stop_reason)
        if parsed is None:
            _last_error = (
                f"Could not parse JSON. Response was {len(text)} chars, "
                f"stop_reason={stop_reason}"
            )
        return parsed


async def _openai_generate(system_prompt: str, user_prompt: str,
                           model: str, tier: str) -> dict | None:
    if not settings.openai_api_key:
        return None
    timeout = 120 if tier == "heavy" else 60
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        if resp.status_code != 200:
            log.error(f"OpenAI error: {resp.text}")
            return None
        resp_data = resp.json()
        usage_data = resp_data.get("usage", {})
        _track_usage("openai", model, tier,
                     usage_data.get("prompt_tokens", 0),
                     usage_data.get("completion_tokens", 0))
        text = resp_data["choices"][0]["message"]["content"]
        return json.loads(text)
