"""Constraint tests for the plan builder.

These assert the training rules the planner is supposed to guarantee, across a
wide sweep of athlete profiles. They are pure functions with no I/O, so they
run in CI in a couple of seconds.
"""
import itertools

import pytest

from app.services.plan_builder import (
    DAY_ORDER,
    _allocate_sport_sessions,
    compute_session_target,
    SPORT_PROPERTIES,
    build_plan,
    STRENGTH_BLOCKS,
    estimate_strength_minutes,
    compute_readiness,
    compute_recovery_schedule,
    compute_volume_progression,
    format_pace,
    run_pace_seconds,
)

EVENTS = ["5k", "10k", "marathon", "olympic_triathlon", "ironman_70.3",
          "ironman", "general_fitness"]
SPORT_SETS = [
    ["cycling"],
    ["running", "strength"],
    ["cycling", "running"],
    ["cycling", "running", "swimming", "strength"],
    ["swimming", "cycling"],
]
EXPERIENCES = ["beginner", "intermediate", "advanced"]


def make_profile(**overrides) -> dict:
    profile = dict(
        experience_level="intermediate",
        plan_duration_weeks=8,
        weekly_hours=10.0,
        sports=["cycling", "running", "swimming", "strength"],
        goal_event="olympic_triathlon",
        preferred_hard_days=["tuesday", "thursday"],
        preferred_rest_days=[],
        max_sessions_per_day=1,
    )
    profile.update(overrides)
    return profile


def all_workouts(plan: dict):
    for week in plan["weeks"]:
        for day in week["days"]:
            for workout in day["workouts"]:
                if workout["workout_type"] != "rest":
                    yield week, day, workout


# --- The sweep: every combination must produce a safe, valid plan ---

SWEEP = list(itertools.product(EVENTS, SPORT_SETS, [3, 6, 10, 16], EXPERIENCES))


@pytest.mark.parametrize("event,sports,hours,experience", SWEEP)
def test_plan_is_safe_and_within_budget(event, sports, hours, experience):
    profile = make_profile(goal_event=event, sports=sports,
                           weekly_hours=hours, experience_level=experience)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")

    assert plan["weeks"], "plan produced no weeks"
    assert not plan.get("safety_warnings"), plan.get("safety_warnings")

    peak = max(w["target_hours"] for w in plan["weeks"])
    assert peak <= hours + 0.25, (
        f"peak {peak}h exceeds the athlete's stated {hours}h"
    )

    for _, _, workout in all_workouts(plan):
        cap = SPORT_PROPERTIES.get(workout["sport"], {}).get("max_session_minutes", 300)
        assert 0 < workout["duration_minutes"] <= cap
        assert workout["tss_estimate"] >= 0


# --- Sport-specific prescription ---

def test_runs_are_prescribed_in_pace_never_power():
    plan = build_plan(make_profile(sports=["running", "cycling"], goal_event="marathon"),
                      ftp=250, start_date="2026-08-10", threshold_pace=270)
    runs = [w for _, _, w in all_workouts(plan) if w["sport"] == "running"]
    assert runs, "expected running sessions"
    for workout in runs:
        for step in workout["steps"]:
            assert "power" not in step, f"run step carries a power target: {step}"
            assert step.get("pace"), f"run step has no pace: {step}"


def test_rides_are_prescribed_in_power():
    plan = build_plan(make_profile(sports=["cycling"]), ftp=250, start_date="2026-08-10")
    rides = [w for _, _, w in all_workouts(plan) if w["sport"] == "cycling"]
    assert rides
    assert any("power" in step for w in rides for step in w["steps"])


def test_swims_carry_pace_and_never_reference_ftp():
    plan = build_plan(make_profile(), ftp=250, start_date="2026-08-10", css_pace=100)
    swims = [w for _, _, w in all_workouts(plan) if w["sport"] == "swimming"]
    assert swims, "expected swim sessions"
    for workout in swims:
        assert "FTP" not in workout["target_zone"]
        for step in workout["steps"]:
            assert "power" not in step


def test_faster_threshold_gives_faster_prescribed_pace():
    assert run_pace_seconds("endurance", 240) < run_pace_seconds("endurance", 300)
    assert run_pace_seconds("threshold", 300) < run_pace_seconds("endurance", 300)
    assert format_pace(300) == "5:00/km"


# --- Frequency and archetypes ---

@pytest.mark.parametrize("hours", [8, 12, 16])
@pytest.mark.parametrize("rest_days", [[], ["monday"]])
def test_swimming_gets_more_than_one_session(hours, rest_days):
    """Swimming's value is frequency; one session a week is a scheduling bug.

    Build weeks only — a taper week is deliberately tiny and one swim in it is
    the plan working, not failing.
    """
    profile = make_profile(weekly_hours=hours, preferred_rest_days=rest_days,
                           max_sessions_per_day=2)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        if week["week_type"] != "build":
            continue
        swims = sum(
            1 for day in week["days"] for w in day["workouts"] if w["sport"] == "swimming"
        )
        assert swims >= 2, f"week {week['week_number']} has only {swims} swim(s)"


# --- Frequency follows volume ---

def sessions_per_sport(week: dict) -> dict:
    counts: dict[str, int] = {}
    for day in week["days"]:
        for workout in day["workouts"]:
            if workout["workout_type"] not in ("rest", "strength"):
                counts[workout["sport"]] = counts.get(workout["sport"], 0) + 1
    return counts


@pytest.mark.parametrize("hours,minimum", [(6, 2), (10, 3), (13, 3), (16, 4)])
def test_triathlon_frequency_ladder(hours, minimum):
    """At 10-13h a triathlete should be at 3-3-3, not 2-2-2.

    Stated without strength: lifting competes for the same weekly budget, so
    this isolates the endurance frequency question.
    """
    profile = make_profile(weekly_hours=hours, plan_duration_weeks=8,
                           sports=["cycling", "running", "swimming"],
                           max_sessions_per_day=2)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    peak = max(plan["weeks"], key=lambda w: w["target_hours"])
    counts = sessions_per_sport(peak)
    for sport in ("swimming", "cycling", "running"):
        assert counts.get(sport, 0) >= minimum, (
            f"{hours}h peak week has {counts} — expected >= {minimum} of each"
        )


def test_extra_sessions_favour_the_bike():
    """The bike takes the largest share of added frequency."""
    counts = _allocate_sport_sessions(["cycling", "running", "swimming"], 11, "cycling")
    assert counts["cycling"] == max(counts.values()), counts
    assert min(counts.values()) >= 3, f"a discipline got starved: {counts}"


def test_the_primary_sport_leads_even_when_it_is_not_the_bike():
    """A marathoner runs more than they ride, cheap bike volume notwithstanding."""
    counts = _allocate_sport_sessions(["running", "cycling"], 11, "running")
    assert counts["running"] > counts["cycling"], counts


def test_session_target_never_falls_as_hours_rise():
    previous = 0
    for hours in range(2, 25):
        target = compute_session_target(hours, 3, 7, 2)
        assert target >= previous, f"{hours}h gives fewer sessions than {hours - 1}h"
        previous = target


def test_frequency_follows_the_weeks_own_volume():
    """An early ramp week is a smaller week and carries fewer sessions."""
    profile = make_profile(weekly_hours=14, plan_duration_weeks=8,
                           max_sessions_per_day=2)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    first = sum(sessions_per_sport(plan["weeks"][0]).values())
    peak_week = max(plan["weeks"], key=lambda w: w["target_hours"])
    peak = sum(sessions_per_sport(peak_week).values())
    assert first < peak, f"session count flat across the ramp ({first} vs {peak})"


def test_single_session_days_when_doubles_are_not_allowed():
    profile = make_profile(weekly_hours=14, max_sessions_per_day=1)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for _, day, _ in all_workouts(plan):
        endurance = [
            w for w in day["workouts"]
            if w["workout_type"] not in ("rest", "strength")
        ]
        assert len(endurance) <= 1, f"{day['day']} has {len(endurance)} sessions"


# --- Recovery cadence ---

@pytest.mark.parametrize("experience,build_run", [
    ("beginner", 3), ("intermediate", 4), ("advanced", 5),
])
def test_recovery_cadence_by_experience(experience, build_run):
    week_types = compute_recovery_schedule(12, experience)
    assert week_types[:build_run] == ["build"] * build_run
    assert week_types[build_run] == "recovery"


def test_each_discipline_gets_at_most_one_long_session_per_week():
    plan = build_plan(make_profile(weekly_hours=12), ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        longs: dict[str, int] = {}
        for day in week["days"]:
            for workout in day["workouts"]:
                if workout.get("archetype") == "long":
                    longs[workout["sport"]] = longs.get(workout["sport"], 0) + 1
        assert all(n <= 1 for n in longs.values()), longs


def test_quality_sessions_are_not_on_consecutive_days():
    plan = build_plan(make_profile(), ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        hard = [
            any(w.get("archetype") == "quality" for w in day["workouts"])
            for day in week["days"]
        ]
        assert not any(a and b for a, b in zip(hard, hard[1:]))


def test_multi_sport_doubles_use_different_sports():
    profile = make_profile(weekly_hours=16, max_sessions_per_day=2)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for _, day, _ in all_workouts(plan):
        endurance = [
            w for w in day["workouts"]
            if w["workout_type"] not in ("rest", "strength")
        ]
        if len(endurance) > 1:
            sports = {w["sport"] for w in endurance}
            assert len(sports) == len(endurance), f"{day['day']}: {sports}"


def test_rest_days_are_respected():
    profile = make_profile(preferred_rest_days=["monday", "friday"])
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        for day in week["days"]:
            if day["day"] in ("monday", "friday"):
                assert all(w["workout_type"] == "rest" for w in day["workouts"])


def test_no_forced_rest_day_when_none_requested():
    profile = make_profile(weekly_hours=14, preferred_rest_days=[])
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    week = plan["weeks"][2]
    training_days = sum(
        1 for day in week["days"]
        if any(w["workout_type"] != "rest" for w in day["workouts"])
    )
    assert training_days == len(DAY_ORDER)


# --- Progression ---

@pytest.mark.parametrize("total_weeks", [4, 8, 12, 20])
def test_ramp_reaches_the_target_at_the_last_build_week(total_weeks):
    week_types = compute_recovery_schedule(total_weeks, "intermediate")
    multipliers = compute_volume_progression(week_types, "intermediate")
    build = [m for m, t in zip(multipliers, week_types) if t == "build"]
    assert build
    assert max(build) == pytest.approx(1.0, abs=0.01), (
        f"{total_weeks}wk plan peaks at {max(build):.2f} of available hours"
    )
    assert build[0] < 1.0, "a plan should not open at full volume"
    assert build == sorted(build), "build weeks should increase monotonically"


def test_ramp_starts_from_current_volume_when_known():
    week_types = compute_recovery_schedule(12, "intermediate")
    multipliers = compute_volume_progression(week_types, "intermediate", 10 / 16)
    assert multipliers[0] == pytest.approx(0.625, abs=0.01)


def test_weekly_increase_never_exceeds_the_safe_step():
    for experience, limit in [("beginner", 0.06), ("intermediate", 0.08), ("advanced", 0.10)]:
        week_types = compute_recovery_schedule(12, experience)
        multipliers = compute_volume_progression(week_types, experience)
        build = [m for m, t in zip(multipliers, week_types) if t == "build"]
        for previous, current in zip(build, build[1:]):
            assert current / previous <= 1 + limit + 1e-6


def test_recovery_weeks_are_lighter_than_the_build_weeks_around_them():
    profile = make_profile(plan_duration_weeks=8, weekly_hours=12)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    weeks = plan["weeks"]
    for i, week in enumerate(weeks):
        if week["week_type"] != "recovery" or i == 0:
            continue
        assert week["target_hours"] < weeks[i - 1]["target_hours"]


# --- Synced training data feeds the plan ---

def test_readiness_maps_form_to_a_start_adjustment():
    assert compute_readiness({"tsb": -35, "ctl": 80})["state"] == "fatigued"
    assert compute_readiness({"tsb": -15, "ctl": 70})["state"] == "tired"
    assert compute_readiness({"tsb": 2, "ctl": 70})["state"] == "ready"
    assert compute_readiness({"tsb": 25, "ctl": 30})["state"] == "detrained"
    assert compute_readiness(None)["state"] == "unknown"


def test_readiness_never_makes_a_block_harder():
    for tsb in range(-40, 40, 5):
        assert compute_readiness({"tsb": tsb, "ctl": 60})["multiplier"] <= 1.0


def test_observed_volume_sets_the_starting_point():
    profile = make_profile(weekly_hours=14, observed_weekly_hours=9.0)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    assessment = plan["progression_assessment"]
    assert assessment["volume_source"] == "observed"
    assert assessment["start_hours"] == pytest.approx(9.0, abs=0.3)


def test_a_stated_volume_overrides_observed_history():
    """The athlete may know something the data does not."""
    profile = make_profile(weekly_hours=14, observed_weekly_hours=9.0,
                           current_weekly_hours=12.0)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    assessment = plan["progression_assessment"]
    assert assessment["volume_source"] == "stated"
    assert assessment["start_hours"] == pytest.approx(12.0, abs=0.3)


def test_no_history_falls_back_to_the_default_ramp():
    plan = build_plan(make_profile(weekly_hours=14), ftp=250, start_date="2026-08-10")
    assert plan["progression_assessment"]["volume_source"] == "default"


def test_fatigue_opens_the_block_easier():
    profile = make_profile(weekly_hours=14, observed_weekly_hours=10.0)
    fresh = build_plan(profile, ftp=250, fitness_context={"tsb": 5, "ctl": 70},
                       start_date="2026-08-10")
    buried = build_plan(profile, ftp=250, fitness_context={"tsb": -30, "ctl": 80},
                        start_date="2026-08-10")
    assert (buried["progression_assessment"]["start_hours"]
            < fresh["progression_assessment"]["start_hours"])
    assert buried["progression_assessment"]["readiness_note"]


def test_fatigue_does_not_lower_the_peak():
    """Opening easier is a start adjustment, not a smaller block."""
    profile = make_profile(weekly_hours=14, observed_weekly_hours=10.0,
                           plan_duration_weeks=12)
    buried = build_plan(profile, ftp=250, fitness_context={"tsb": -30, "ctl": 80},
                        start_date="2026-08-10")
    assert buried["progression_assessment"]["peak_hours"] == pytest.approx(14.0, abs=0.3)


# --- Cycling carries the volume ---

def endurance_minutes_by_sport(week: dict) -> dict:
    minutes: dict[str, int] = {}
    for day in week["days"]:
        for workout in day["workouts"]:
            if workout["workout_type"] in ("rest", "strength"):
                continue
            minutes[workout["sport"]] = (
                minutes.get(workout["sport"], 0) + workout["duration_minutes"]
            )
    return minutes


@pytest.mark.parametrize("hours", [8, 10, 13, 16, 20])
def test_cycling_carries_the_most_volume(hours):
    """The bike is the volume engine — lowest cost per hour of aerobic work."""
    profile = make_profile(weekly_hours=hours, plan_duration_weeks=8,
                           max_sessions_per_day=2)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    peak = max(plan["weeks"], key=lambda w: w["target_hours"])
    minutes = endurance_minutes_by_sport(peak)
    total = sum(minutes.values())

    assert minutes["cycling"] == max(minutes.values()), minutes
    assert minutes["cycling"] / total >= 0.40, (
        f"{hours}h: bike is only {minutes['cycling'] / total:.0%} of endurance volume"
    )


def test_bike_share_grows_with_volume():
    """Extra hours go to the bike before anywhere else."""
    shares = []
    for hours in (8, 20):
        profile = make_profile(weekly_hours=hours, plan_duration_weeks=8,
                               max_sessions_per_day=2)
        plan = build_plan(profile, ftp=250, start_date="2026-08-10")
        peak = max(plan["weeks"], key=lambda w: w["target_hours"])
        minutes = endurance_minutes_by_sport(peak)
        shares.append(minutes["cycling"] / sum(minutes.values()))
    assert shares[1] > shares[0], f"bike share flat across volume: {shares}"


# --- Strength is sets and reps ---

def test_strength_sessions_prescribe_sets_and_reps():
    """"Bulgarian Split Squat, 5:00 steady" is not how anyone lifts."""
    plan = build_plan(make_profile(weekly_hours=12, max_sessions_per_day=2),
                      ftp=250, start_date="2026-08-10")
    lifts = [w for _, _, w in all_workouts(plan) if w["sport"] == "strength"]
    assert lifts, "expected strength sessions"

    for session in lifts:
        work = [s for s in session["steps"] if s.get("reps")]
        assert work, f"no rep-based steps in {session['name']}"
        for step in work:
            assert step["sets"] >= 1
            assert step["reps"] >= 1
            assert step.get("exercise"), "step has no named exercise"
            assert step.get("exercise_category") is not None
            assert step["rest"]["duration"] > 0, "sets need rest between them"
            # A rep-based step must not also claim a wall-clock duration.
            assert "duration" not in step


def test_strength_duration_matches_the_prescribed_sets():
    for block in STRENGTH_BLOCKS:
        estimate = estimate_strength_minutes(block)
        assert 20 <= estimate <= 60, f"{block['name']} estimates {estimate}min"


def test_strength_never_dominates_the_week():
    profile = make_profile(weekly_hours=6, max_sessions_per_day=2)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        strength = sum(
            w["duration_minutes"] for d in week["days"] for w in d["workouts"]
            if w["sport"] == "strength"
        )
        total = sum(
            w["duration_minutes"] for d in week["days"] for w in d["workouts"]
            if w["workout_type"] != "rest"
        )
        assert strength / max(total, 1) <= 0.35, (
            f"week {week['week_number']}: strength is {strength}/{total} min"
        )


def sessions_and_minutes(week: dict) -> tuple[dict, dict]:
    counts: dict[str, int] = {}
    minutes: dict[str, int] = {}
    for day in week["days"]:
        for workout in day["workouts"]:
            if workout["workout_type"] in ("rest", "strength"):
                continue
            sport = workout["sport"]
            counts[sport] = counts.get(sport, 0) + 1
            minutes[sport] = minutes.get(sport, 0) + workout["duration_minutes"]
    return counts, minutes


def peak_week(hours: int, **overrides) -> dict:
    profile = make_profile(weekly_hours=hours, plan_duration_weeks=8,
                           max_sessions_per_day=2, **overrides)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    return max(plan["weeks"], key=lambda w: w["target_hours"])


def test_bike_volume_comes_from_frequency_not_marathon_rides():
    """Extra hours buy extra rides, not one enormous ride.

    A 20h athlete riding five times for well over two hours each is the
    failure mode this guards against.
    """
    counts, minutes = sessions_and_minutes(peak_week(20))
    assert counts["cycling"] >= 6, f"only {counts['cycling']} rides at 20h: {counts}"
    average = minutes["cycling"] / counts["cycling"]
    assert average <= 135, f"average ride is {average:.0f}min — too long, add frequency"


@pytest.mark.parametrize("hours,minimum_rides", [(10, 3), (13, 4), (16, 5), (20, 6)])
def test_ride_count_scales_with_volume(hours, minimum_rides):
    counts, _ = sessions_and_minutes(peak_week(hours))
    assert counts["cycling"] >= minimum_rides, (
        f"{hours}h gives {counts['cycling']} rides, expected >= {minimum_rides}"
    )


def test_bike_has_the_most_sessions_once_volume_is_real():
    """Below ~12h everything is even; above it the bike should lead."""
    for hours in (13, 16, 20):
        counts, _ = sessions_and_minutes(peak_week(hours))
        assert counts["cycling"] == max(counts.values()), f"{hours}h: {counts}"


def test_no_discipline_is_starved_as_the_bike_grows():
    for hours in (13, 16, 20):
        counts, _ = sessions_and_minutes(peak_week(hours))
        assert counts.get("running", 0) >= 3, f"{hours}h: {counts}"
        assert counts.get("swimming", 0) >= 3, f"{hours}h: {counts}"


# --- Starting a block mid-week ---

def training_days_in(week: dict) -> list[str]:
    return [d["day"] for d in week["days"]
            if any(w["workout_type"] != "rest" for w in d["workouts"])]


def test_a_block_can_start_on_the_coming_monday():
    plan = build_plan(make_profile(weekly_hours=12, max_sessions_per_day=2),
                      ftp=250, start_date="2026-08-10")
    assert plan["weeks"][0]["days"][0]["date"] == "2026-08-10"
    assert len(training_days_in(plan["weeks"][0])) == 7


@pytest.mark.parametrize("start_from,expected_days", [
    ("2026-08-10", 7),   # Monday — the whole week
    ("2026-08-13", 4),   # Thursday — Thu/Fri/Sat/Sun
    ("2026-08-16", 1),   # Sunday — one day
])
def test_mid_week_start_only_schedules_the_days_that_are_left(start_from, expected_days):
    plan = build_plan(make_profile(weekly_hours=12, max_sessions_per_day=2),
                      ftp=250, start_date="2026-08-10", first_week_from=start_from)
    first = plan["weeks"][0]
    assert len(training_days_in(first)) == expected_days

    # Days before the start carry nothing at all.
    for day in first["days"]:
        if day["date"] < start_from:
            assert all(w["workout_type"] == "rest" for w in day["workouts"])


def test_a_short_first_week_carries_a_smaller_load():
    """Four days should not carry seven days of training."""
    full = build_plan(make_profile(weekly_hours=12, max_sessions_per_day=2),
                      ftp=250, start_date="2026-08-10")
    partial = build_plan(make_profile(weekly_hours=12, max_sessions_per_day=2),
                         ftp=250, start_date="2026-08-10",
                         first_week_from="2026-08-13")
    assert partial["weeks"][0]["target_hours"] < full["weeks"][0]["target_hours"]


def test_only_the_first_week_is_shortened():
    plan = build_plan(make_profile(weekly_hours=12, plan_duration_weeks=4,
                                   max_sessions_per_day=2),
                      ftp=250, start_date="2026-08-10", first_week_from="2026-08-14")
    assert len(training_days_in(plan["weeks"][1])) == 7
    assert plan["weeks"][1]["target_hours"] > plan["weeks"][0]["target_hours"]


def test_mid_week_start_still_produces_a_safe_plan():
    for start_from in ("2026-08-11", "2026-08-13", "2026-08-15", "2026-08-16"):
        plan = build_plan(make_profile(weekly_hours=14, max_sessions_per_day=2),
                          ftp=250, start_date="2026-08-10",
                          first_week_from=start_from)
        assert not plan.get("safety_warnings"), plan.get("safety_warnings")
        assert all(w["target_hours"] >= 0 for w in plan["weeks"])


def test_mid_week_start_respects_rest_days():
    plan = build_plan(
        make_profile(weekly_hours=12, preferred_rest_days=["saturday", "sunday"],
                     max_sessions_per_day=2),
        ftp=250, start_date="2026-08-10", first_week_from="2026-08-15",
    )
    # Saturday and Sunday are rest days, so a Saturday start leaves nothing.
    assert training_days_in(plan["weeks"][0]) == []
    assert plan["weeks"][0]["target_hours"] == 0


# --- Hard per-sport constraints ---

def sessions_by_day(week: dict, sport: str) -> list[str]:
    return [d["day"] for d in week["days"]
            for w in d["workouts"] if w["sport"] == sport]


def test_a_sport_restricted_to_certain_days_never_lands_elsewhere():
    """Pool hours are a fact, not a preference."""
    profile = make_profile(weekly_hours=13, max_sessions_per_day=2,
                           sport_limits={"swimming": {"days": ["tuesday", "thursday"]}})
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        for day in sessions_by_day(week, "swimming"):
            assert day in ("tuesday", "thursday"), day


def test_a_session_cap_is_never_exceeded():
    profile = make_profile(weekly_hours=16, max_sessions_per_day=2,
                           sport_limits={"running": {"max_sessions": 2}})
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        assert len(sessions_by_day(week, "running")) <= 2, week["week_number"]


def test_constrained_volume_moves_to_the_other_disciplines():
    """Capping the run should not simply lose those hours."""
    free = build_plan(make_profile(weekly_hours=16, max_sessions_per_day=2),
                      ftp=250, start_date="2026-08-10")
    capped = build_plan(
        make_profile(weekly_hours=16, max_sessions_per_day=2,
                     sport_limits={"running": {"max_sessions": 2}}),
        ftp=250, start_date="2026-08-10")
    peak_free = max(free["weeks"], key=lambda w: w["target_hours"])["target_hours"]
    peak_capped = max(capped["weeks"], key=lambda w: w["target_hours"])["target_hours"]
    assert peak_capped >= peak_free * 0.9, f"{peak_capped}h vs {peak_free}h"


def test_constraints_still_produce_a_safe_plan():
    combos = [
        {"swimming": {"days": ["tuesday"], "max_sessions": 1}},
        {"running": {"max_sessions": 1}, "swimming": {"max_sessions": 1}},
        {"cycling": {"days": ["saturday", "sunday"]}},
    ]
    for limits in combos:
        plan = build_plan(
            make_profile(weekly_hours=14, max_sessions_per_day=2, sport_limits=limits),
            ftp=250, start_date="2026-08-10")
        assert not plan.get("safety_warnings"), (limits, plan["safety_warnings"])
        assert all(w["target_hours"] >= 0 for w in plan["weeks"])


def test_no_limits_behaves_as_before():
    without = build_plan(make_profile(weekly_hours=13, max_sessions_per_day=2),
                         ftp=250, start_date="2026-08-10")
    empty = build_plan(make_profile(weekly_hours=13, max_sessions_per_day=2,
                                    sport_limits={}),
                       ftp=250, start_date="2026-08-10")
    assert [w["target_hours"] for w in without["weeks"]] == \
           [w["target_hours"] for w in empty["weeks"]]
