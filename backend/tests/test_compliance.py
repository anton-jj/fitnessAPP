"""Tests for the compliance loop: reading what was done, and adapting what is left."""
import copy
from datetime import datetime, timedelta

import pytest

from app.services.compliance import (
    MIN_VOLUME_FACTOR,
    _recommend,
    adapt_remaining_weeks,
)


def week(number, start, sessions, week_type="build"):
    """Build a plan week from (day_offset, sport, minutes, archetype) tuples."""
    begin = datetime.strptime(start, "%Y-%m-%d")
    days = []
    for offset in range(7):
        date = (begin + timedelta(days=offset)).strftime("%Y-%m-%d")
        workouts = [
            {
                "name": f"{sport} session", "sport": sport,
                "workout_type": "endurance", "archetype": archetype,
                "duration_minutes": minutes, "tss_estimate": minutes,
                "distance_km": 10, "steps": [
                    {"type": "warmup", "duration": 600},
                    {"type": "steady", "duration": (minutes - 15) * 60},
                    {"type": "cooldown", "duration": 300},
                ],
            }
            for day_offset, sport, minutes, archetype in sessions
            if day_offset == offset
        ]
        days.append({
            "day": ["monday", "tuesday", "wednesday", "thursday", "friday",
                    "saturday", "sunday"][offset],
            "date": date,
            "workouts": workouts or [{
                "name": "Rest Day", "sport": "rest", "workout_type": "rest",
                "duration_minutes": 0, "steps": [],
            }],
        })
    return {"week_number": number, "week_type": week_type,
            "target_hours": 0, "target_tss": 0, "days": days}


def summary(ratio, sports=None):
    """A finished-week compliance summary, as plan_compliance would produce."""
    return {
        "ratio": ratio,
        "by_sport": sports or {},
        "planned_hours": 10, "completed_hours": 10 * ratio,
    }


# --- Recommendations ---

def test_one_week_is_not_enough_evidence():
    result = _recommend([summary(0.4)])
    assert result["action"] == "none"
    assert "not enough" in result["reason"]


def test_consistent_under_completion_scales_the_plan_down():
    result = _recommend([summary(0.6), summary(0.65), summary(0.55)])
    assert result["action"] == "reduce"
    assert result["volume_factor"] < 1.0
    assert "60%" in result["reason"] or "completed" in result["reason"]


def test_a_single_bad_week_does_not_gut_the_block():
    """A holiday week alongside two good ones should not trigger a cut."""
    result = _recommend([summary(1.0), summary(0.15), summary(1.0)])
    assert result["action"] == "none", result


def test_reductions_are_bounded():
    result = _recommend([summary(0.1), summary(0.1), summary(0.1)])
    assert result["volume_factor"] >= MIN_VOLUME_FACTOR


def test_increases_are_bounded():
    result = _recommend([summary(2.0), summary(2.0), summary(2.0)])
    assert result["action"] == "increase"
    assert result["volume_factor"] <= 1.15


def test_on_track_changes_nothing():
    result = _recommend([summary(0.98), summary(1.02), summary(0.95)])
    assert result["action"] == "none"
    assert result["volume_factor"] == 1.0


def test_a_consistently_skipped_sport_is_dropped():
    swim_skipped = {
        "swimming": {"planned_sessions": 3, "completed_sessions": 0,
                     "planned_minutes": 120, "completed_minutes": 0},
        "cycling": {"planned_sessions": 3, "completed_sessions": 3,
                    "planned_minutes": 240, "completed_minutes": 240},
    }
    result = _recommend([summary(0.95, swim_skipped), summary(1.0, swim_skipped)])
    assert "swimming" in result["drop_sports"]
    assert result["action"] in ("rebalance", "reduce")


def test_a_sport_being_done_is_never_dropped():
    kept = {
        "swimming": {"planned_sessions": 3, "completed_sessions": 3,
                     "planned_minutes": 120, "completed_minutes": 120},
    }
    result = _recommend([summary(1.0, kept), summary(1.0, kept)])
    assert result["drop_sports"] == []


# --- Applying the adaptation ---

NOW = datetime(2026, 8, 20)

PLAN = {
    "weeks": [
        week(1, "2026-08-10", [(0, "cycling", 60, "easy"), (2, "running", 60, "easy")]),
        week(2, "2026-08-17", [(0, "cycling", 60, "easy"), (2, "running", 60, "easy")]),
        week(3, "2026-08-24", [(0, "cycling", 60, "easy"), (2, "running", 60, "easy"),
                               (4, "swimming", 40, "easy"), (5, "swimming", 40, "easy")]),
        week(4, "2026-08-31", [(0, "cycling", 60, "easy"), (2, "running", 60, "easy")]),
    ]
}


def durations(plan, week_index):
    return [w["duration_minutes"]
            for d in plan["weeks"][week_index]["days"]
            for w in d["workouts"] if w["workout_type"] != "rest"]


def test_weeks_already_underway_are_left_alone():
    """Rewriting a session the athlete may have done today is worse than
    leaving it slightly wrong."""
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 0.8, "drop_sports": []}, today=NOW)
    assert durations(plan, 0) == [60, 60]   # finished week
    assert durations(plan, 1) == [60, 60]   # week in progress
    assert plan["adaptation"]["weeks_changed"] == 2


def test_future_weeks_scale():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 0.8, "drop_sports": []}, today=NOW)
    assert all(d < 60 for d in durations(plan, 3))


def test_scaling_keeps_the_week_totals_honest():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 0.8, "drop_sports": []}, today=NOW)
    for index in (2, 3):
        target = plan["weeks"][index]
        minutes = sum(durations(plan, index))
        assert target["target_hours"] == pytest.approx(minutes / 60, abs=0.1)
        assert target["target_tss"] > 0


def test_scaling_respects_the_session_floor():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 0.3, "drop_sports": []}, today=NOW)
    assert all(d >= 30 for d in durations(plan, 3))


def test_scaling_respects_the_sport_ceiling():
    big = {"weeks": [week(1, "2026-09-07", [(0, "swimming", 60, "easy")])]}
    plan = adapt_remaining_weeks(big, {"volume_factor": 1.15, "drop_sports": []},
                                 today=NOW)
    # Swimming caps easy sessions at 60 minutes
    assert durations(plan, 0)[0] <= 60


def test_dropping_a_sport_removes_only_one_session():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 1.0, "drop_sports": ["swimming"]},
                                 today=NOW)
    swims = [w for d in plan["weeks"][2]["days"] for w in d["workouts"]
             if w["sport"] == "swimming"]
    assert len(swims) == 1, "should drop one swim, not the discipline"


def test_a_sports_last_session_is_never_dropped():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 1.0, "drop_sports": ["cycling"]},
                                 today=NOW)
    rides = [w for d in plan["weeks"][3]["days"] for w in d["workouts"]
             if w["sport"] == "cycling"]
    assert len(rides) == 1, "a single session must survive"


def test_steps_are_rescaled_with_the_session():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 0.7, "drop_sports": []}, today=NOW)
    workout = next(w for d in plan["weeks"][3]["days"] for w in d["workouts"]
                   if w["workout_type"] != "rest")
    steady = next(s for s in workout["steps"] if s["type"] == "steady")
    warmup = next(s for s in workout["steps"] if s["type"] == "warmup")
    assert steady["duration"] < (60 - 15) * 60, "work should shrink"
    assert warmup["duration"] == 600, "warmup should not"


def test_adaptation_records_what_it_did():
    plan = adapt_remaining_weeks(
        copy.deepcopy(PLAN),
        {"volume_factor": 0.8, "drop_sports": ["swimming"], "reason": "because"},
        today=NOW)
    record = plan["adaptation"]
    assert record["volume_factor"] == 0.8
    assert record["dropped_sports"] == ["swimming"]
    assert record["reason"] == "because"
    assert record["weeks_changed"] == 2


def test_adapting_a_finished_plan_changes_nothing():
    past = {"weeks": [week(1, "2026-08-03", [(0, "cycling", 60, "easy")])]}
    plan = adapt_remaining_weeks(past, {"volume_factor": 0.5, "drop_sports": []},
                                 today=NOW)
    assert plan["adaptation"]["changed_now"] == 0
    assert durations(plan, 0) == [60]


# --- Adapting twice must not compound ---

def test_adapting_twice_does_not_scale_twice():
    """Pressing adapt again should be a no-op, not a second 30% cut."""
    recommendation = {"volume_factor": 0.7, "drop_sports": []}
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN), recommendation, today=NOW)
    after_first = durations(plan, 3)

    plan = adapt_remaining_weeks(plan, recommendation, today=NOW)
    assert durations(plan, 3) == after_first
    assert plan["adaptation"]["changed_now"] == 0


def test_a_stronger_recommendation_applies_only_the_difference():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 0.9, "drop_sports": []}, today=NOW)
    plan = adapt_remaining_weeks(plan,
                                 {"volume_factor": 0.7, "drop_sports": []}, today=NOW)
    # 60min scaled once to 0.7 of the original, not 0.9 * 0.7
    assert durations(plan, 3) == [pytest.approx(40, abs=6)] * 2


def test_relaxing_a_recommendation_scales_back_up():
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN),
                                 {"volume_factor": 0.7, "drop_sports": []}, today=NOW)
    plan = adapt_remaining_weeks(plan,
                                 {"volume_factor": 1.0, "drop_sports": []}, today=NOW)
    assert durations(plan, 3) == [pytest.approx(60, abs=5)] * 2


def test_a_sport_is_not_dropped_twice():
    recommendation = {"volume_factor": 1.0, "drop_sports": ["swimming"]}
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN), recommendation, today=NOW)
    first = len([w for d in plan["weeks"][2]["days"] for w in d["workouts"]
                 if w["sport"] == "swimming"])
    plan = adapt_remaining_weeks(plan, recommendation, today=NOW)
    second = len([w for d in plan["weeks"][2]["days"] for w in d["workouts"]
                  if w["sport"] == "swimming"])
    assert first == second == 1


def test_a_no_op_adapt_does_not_erase_the_previous_one():
    recommendation = {"volume_factor": 0.7, "drop_sports": [], "reason": "real change"}
    plan = adapt_remaining_weeks(copy.deepcopy(PLAN), recommendation, today=NOW)
    assert plan["adaptation"]["weeks_changed"] == 2

    plan = adapt_remaining_weeks(plan, recommendation, today=NOW)
    assert plan["adaptation"]["weeks_changed"] == 2, "record was overwritten"
    assert plan["adaptation"]["reason"] == "real change"
    assert plan["adaptation"]["last_checked"]
