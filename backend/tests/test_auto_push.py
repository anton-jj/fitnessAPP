"""Picking the right day's sessions out of a multi-week plan."""
from app.services.auto_push import workouts_on


def day(date, *workouts):
    return {"day": "monday", "date": date, "workouts": list(workouts)}


def ride(name="Endurance Ride"):
    return {"name": name, "sport": "cycling", "workout_type": "endurance"}


def rest():
    return {"name": "Rest Day", "sport": "rest", "workout_type": "rest"}


PLAN = {
    "weeks": [
        {"week_number": 1, "days": [
            day("2026-08-17", ride("Week 1 Monday")),
            day("2026-08-18", rest()),
        ]},
        {"week_number": 2, "days": [
            day("2026-08-24", ride("Week 2 Monday")),
        ]},
    ]
}


def test_only_that_date_is_returned():
    """The trap: every week has a Monday, so matching the weekday would push
    week 1's session every Monday of the block."""
    found = workouts_on(PLAN, "2026-08-24")
    assert [w["name"] for w in found] == ["Week 2 Monday"]


def test_rest_days_are_not_pushed():
    assert workouts_on(PLAN, "2026-08-18") == []


def test_a_date_outside_the_plan_gives_nothing():
    assert workouts_on(PLAN, "2026-12-25") == []


def test_two_sessions_on_one_day_both_come_back():
    plan = {"weeks": [{"days": [day("2026-08-17", ride("AM"), ride("PM"))]}]}
    assert [w["name"] for w in workouts_on(plan, "2026-08-17")] == ["AM", "PM"]


def test_a_single_week_plan_without_the_weeks_wrapper_still_works():
    """Quick weekly plans are stored flat rather than as a list of weeks."""
    plan = {"days": [day("2026-08-17", ride("Flat plan ride"))]}
    assert [w["name"] for w in workouts_on(plan, "2026-08-17")] == ["Flat plan ride"]


def test_an_empty_plan_is_handled():
    assert workouts_on({}, "2026-08-17") == []
