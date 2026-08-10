"""Tests for the outbound sync formats: FIT workout files and the ICS feed.

Both are consumed by software we do not control (Garmin Connect, the COROS
app, calendar clients), so the encoding has to be right without a round trip
through a real device.
"""
import io

import fitdecode
import pytest

from app.services.fit_workout import (
    POWER_OFFSET,
    generate_workout_fit,
    workout_filename,
)
from app.services.ics_feed import _fold, plan_to_ics
from app.services.intervals import _event_payload, _describe_steps


def decode(data: bytes) -> list[dict]:
    frames = []
    with fitdecode.FitReader(io.BytesIO(data)) as reader:
        for frame in reader:
            if frame.frame_type == fitdecode.FIT_FRAME_DATA:
                frames.append({
                    "name": frame.name,
                    **{f.name: f.value for f in frame.fields},
                })
    return frames


BIKE = {
    "name": "3x12 Threshold", "sport": "cycling", "duration_minutes": 75,
    "steps": [
        {"type": "warmup", "duration": 720, "power": 0.55, "notes": "warmup"},
        {"type": "interval", "duration": 720, "power": 1.00, "repeat": 3,
         "rest": {"type": "rest", "duration": 300, "power": 0.55},
         "notes": "threshold"},
        {"type": "cooldown", "duration": 540, "power": 0.50, "notes": "spin down"},
    ],
}

RUN = {
    "name": "4x10 Tempo", "sport": "running", "duration_minutes": 60,
    "steps": [
        {"type": "warmup", "duration": 600, "pace": 386, "notes": "easy jog"},
        {"type": "interval", "duration": 600, "pace": 300, "repeat": 4,
         "rest": {"type": "rest", "duration": 180, "pace": 386}, "notes": "tempo"},
    ],
}

SWIM = {
    "name": "8x100 CSS", "sport": "swimming", "duration_minutes": 45,
    "steps": [
        {"type": "warmup", "duration": 420, "notes": "300m easy"},
        {"type": "interval", "duration": 120, "pace": 100, "repeat": 8,
         "rest": {"type": "rest", "duration": 15}, "notes": "8x100m"},
    ],
}

STRENGTH = {
    "name": "Single-Leg A", "sport": "strength", "duration_minutes": 30,
    "steps": [
        {"type": "warmup", "duration": 300, "notes": "dynamic stretch"},
        {"type": "steady", "duration": 300, "notes": "Split Squat 3x8"},
    ],
}


# --- FIT workout files ---

@pytest.mark.parametrize("workout", [BIKE, RUN, SWIM, STRENGTH])
def test_fit_workout_is_parseable(workout):
    """A real FIT parser must accept the file, header CRC included."""
    frames = decode(generate_workout_fit(workout, ftp=250))
    file_id = next(f for f in frames if f["name"] == "file_id")
    assert file_id["type"] == "workout"

    header = next(f for f in frames if f["name"] == "workout")
    assert header["wkt_name"] == workout["name"]
    steps = [f for f in frames if f["name"] == "workout_step"]
    assert header["num_valid_steps"] == len(steps)
    assert steps


def test_cycling_targets_are_watts_from_ftp():
    steps = [f for f in decode(generate_workout_fit(BIKE, ftp=250))
             if f["name"] == "workout_step"]
    threshold = steps[1]
    assert threshold["target_type"] == "power"
    # 100% of a 250W FTP, stored with the FIT +1000 offset and a tolerance band
    assert threshold["custom_target_power_low"] == 240 + POWER_OFFSET
    assert threshold["custom_target_power_high"] == 260 + POWER_OFFSET


def test_running_targets_are_speed_not_power():
    steps = [f for f in decode(generate_workout_fit(RUN, ftp=250))
             if f["name"] == "workout_step"]
    work = steps[1]
    assert work["target_type"] == "speed"
    # 300s/km is 3.33 m/s; the band brackets it
    assert work["custom_target_speed_low"] < 3.34 < work["custom_target_speed_high"]
    assert all(s.get("custom_target_power_low") is None for s in steps)


def test_swim_pace_is_per_hundred_metres():
    steps = [f for f in decode(generate_workout_fit(SWIM, ftp=250))
             if f["name"] == "workout_step"]
    work = next(s for s in steps if s["target_type"] == "speed")
    # 100s per 100m is exactly 1 m/s
    assert work["custom_target_speed_low"] < 1.0 < work["custom_target_speed_high"]


def test_strength_steps_have_no_machine_target():
    steps = [f for f in decode(generate_workout_fit(STRENGTH))
             if f["name"] == "workout_step"]
    assert all(s["target_type"] == "open" for s in steps)
    assert any("Split Squat" in (s["wkt_step_name"] or "") for s in steps)


def test_repeat_blocks_point_back_at_the_right_step():
    steps = [f for f in decode(generate_workout_fit(BIKE, ftp=250))
             if f["name"] == "workout_step"]
    repeat = next(s for s in steps
                  if s["duration_type"] == "repeat_until_steps_cmplt")
    assert repeat["repeat_steps"] == 3
    # The loop starts at the work step, which follows the warmup
    assert repeat["duration_step"] == 1


def test_workout_with_no_steps_still_produces_a_valid_file():
    frames = decode(generate_workout_fit(
        {"name": "Open Ride", "sport": "cycling", "duration_minutes": 90}
    ))
    assert [f for f in frames if f["name"] == "workout_step"]


def test_long_names_do_not_overflow_the_field():
    workout = {**BIKE, "name": "x" * 200}
    frames = decode(generate_workout_fit(workout, ftp=250))
    header = next(f for f in frames if f["name"] == "workout")
    assert len(header["wkt_name"]) <= 31


def test_filename_is_filesystem_safe():
    name = workout_filename({"name": "4x8 @ 90% / hard!"}, "2026-08-10")
    assert name.endswith(".fit")
    assert all(c.isalnum() or c in "._-" for c in name)


# --- intervals.icu payload ---

def test_planned_workouts_go_to_the_calendar_not_the_library():
    payload = _event_payload(BIKE, "2026-08-10", ftp=250)
    assert payload["category"] == "WORKOUT"
    assert payload["start_date_local"] == "2026-08-10T00:00:00"
    assert payload["type"] == "Ride"
    assert payload["moving_time"] == 75 * 60
    assert payload["external_id"].startswith("pulse-2026-08-10-cycling")
    assert payload["filename"].endswith(".fit")
    assert payload["file_contents_base64"]


def test_event_payload_maps_each_sport():
    assert _event_payload(RUN, "2026-08-10", 250)["type"] == "Run"
    assert _event_payload(SWIM, "2026-08-10", 250)["type"] == "Swim"
    assert _event_payload(STRENGTH, "2026-08-10", 250)["type"] == "WeightTraining"


def test_repushing_the_same_session_keeps_a_stable_id():
    first = _event_payload(BIKE, "2026-08-10", 250)["external_id"]
    second = _event_payload(BIKE, "2026-08-10", 250)["external_id"]
    assert first == second


def test_description_includes_the_interval_structure():
    text = _describe_steps(BIKE)
    assert "3x" in text
    assert "threshold" in text


# --- ICS feed ---

def test_ics_folding_is_reversible_and_within_the_octet_limit():
    for probe in ["DESCRIPTION:" + "é" * 200, "SUMMARY:" + "—" * 100,
                  "X:" + "a" * 300, "SHORT:ok"]:
        folded = _fold(probe)
        assert folded.replace("\r\n ", "") == probe
        assert max(len(line.encode()) for line in folded.split("\r\n")) <= 75


def test_ics_feed_structure():
    plan = {"weeks": [{"week_number": 1, "days": [
        {"day": "monday", "date": "2026-08-10", "workouts": [
            BIKE,
            {"name": "Rest Day", "workout_type": "rest", "sport": "rest"},
        ]},
    ]}]}
    ics = plan_to_ics(plan, "Test Plan")

    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.rstrip().endswith("END:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") == 1  # rest excluded
    assert "SUMMARY:3x12 Threshold" in ics
    assert ics.endswith("\r\n")


def test_ics_escapes_reserved_characters():
    plan = {"weeks": [{"days": [{"date": "2026-08-10", "workouts": [
        {"name": "Hard; fast, now", "sport": "cycling", "duration_minutes": 60,
         "workout_type": "threshold", "description": "line one\nline two"},
    ]}]}]}
    ics = plan_to_ics(plan)
    assert "Hard\\; fast\\, now" in ics
    assert "line one\\nline two" in ics


def test_ics_skips_days_without_a_date():
    plan = {"weeks": [{"days": [{"day": "monday", "workouts": [BIKE]}]}]}
    assert plan_to_ics(plan).count("BEGIN:VEVENT") == 0


# --- Regressions found by pushing real workouts to intervals.icu ---

def test_every_step_carries_a_message_index():
    """Without it a repeat cannot reference the step it loops from.

    intervals.icu reported "No step found for duration_value 1" on every
    interval session because the steps had no index to point at.
    """
    for workout in (BIKE, RUN, SWIM, STRENGTH):
        steps = [f for f in decode(generate_workout_fit(workout, ftp=250))
                 if f["name"] == "workout_step"]
        indexes = [s["message_index"] for s in steps]
        assert indexes == list(range(len(steps))), f"{workout['name']}: {indexes}"


def test_repeat_points_at_an_index_that_exists():
    for workout in (BIKE, RUN, SWIM, STRENGTH):
        steps = [f for f in decode(generate_workout_fit(workout, ftp=250))
                 if f["name"] == "workout_step"]
        valid = {s["message_index"] for s in steps}
        for step in steps:
            if step["duration_type"] == "repeat_until_steps_cmplt":
                assert step["duration_step"] in valid, (
                    f"{workout['name']}: repeat points at {step['duration_step']}"
                )


def test_swim_steps_are_measured_in_metres():
    """A swim prescribed as time plus a pace target made intervals.icu derive
    a 16km, six-hour recovery swim. Distance is the native unit."""
    from app.services.plan_builder import _build_swim_steps
    workout = {"name": "Swim", "sport": "swimming", "duration_minutes": 35,
               "steps": _build_swim_steps("threshold", 35, 0, 100)}
    steps = [f for f in decode(generate_workout_fit(workout, ftp=250))
             if f["name"] == "workout_step"]

    swum = [s for s in steps if s["duration_type"] == "distance"]
    assert len(swum) >= 3, "swim steps should be distance-based"
    for step in swum:
        assert 25 <= step["duration_distance"] <= 4000, step


def test_push_copy_avoids_rep_steps():
    """intervals.icu reports "Unhandled duration_type: REPS" and drops them."""
    from app.services.plan_builder import _build_strength_steps
    workout = {"name": "Circuit", "sport": "strength", "duration_minutes": 31,
               "steps": _build_strength_steps(0, 3)}

    pushed = [f for f in decode(generate_workout_fit(workout, rep_steps=False))
              if f["name"] == "workout_step"]
    assert all(s["duration_type"] != "reps" for s in pushed)
    assert any(s["duration_type"] == "time" for s in pushed)

    # The downloadable copy keeps reps, which watches do understand.
    download = [f for f in decode(generate_workout_fit(workout, rep_steps=True))
                if f["name"] == "workout_step"]
    assert any(s["duration_type"] == "reps" for s in download)


def test_run_step_names_are_cues_not_repeated_paces():
    """The pace is a structured target; the name should add something."""
    from app.services.plan_builder import _build_run_steps
    workout = {"name": "Threshold", "sport": "running", "duration_minutes": 55,
               "steps": _build_run_steps("threshold", 55, 0, 300)}
    steps = [f for f in decode(generate_workout_fit(workout, ftp=250))
             if f["name"] == "workout_step" and s_name(f)]
    for step in steps:
        assert "/km" not in s_name(step), f"pace duplicated in name: {s_name(step)}"
    assert any(s["target_type"] == "speed" for s in steps)


def s_name(step: dict) -> str:
    return step.get("wkt_step_name") or ""
