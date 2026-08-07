"""Constraint tests for the plan builder.

These assert the training rules the planner is supposed to guarantee, across a
wide sweep of athlete profiles. They are pure functions with no I/O, so they
run in CI in a couple of seconds.
"""
import itertools

import pytest

from app.services.plan_builder import (
    DAY_ORDER,
    SPORT_PROPERTIES,
    build_plan,
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
    """Swimming's value is frequency; one session a week is a scheduling bug."""
    profile = make_profile(weekly_hours=hours, preferred_rest_days=rest_days)
    plan = build_plan(profile, ftp=250, start_date="2026-08-10")
    for week in plan["weeks"]:
        swims = sum(
            1 for day in week["days"] for w in day["workouts"] if w["sport"] == "swimming"
        )
        assert swims >= 1, f"week {week['week_number']} has no swim at all"


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
