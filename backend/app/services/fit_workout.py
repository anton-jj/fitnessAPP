"""FIT *workout* file generator (structured sessions, not recorded activities).

A FIT workout file is the one format every major watch ecosystem accepts:
Garmin Connect and the COROS app both import them, and intervals.icu will
take one as an attachment and forward it to whichever device is connected.
Writing one here means Pulse does not depend on any vendor's partner API —
Garmin's requires a legal entity and is currently closed to new applicants,
and COROS's is partner-only.

Encoding follows the FIT profile: file_id(0), workout(26), workout_step(27).
"""
import struct
from datetime import datetime, timezone
from io import BytesIO

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

# Global message numbers
FILE_ID = 0
WORKOUT = 26
WORKOUT_STEP = 27

# Base types
ENUM = 0x00
UINT8 = 0x02
UINT16 = 0x84
UINT32 = 0x86
STRING = 0x07

FILE_TYPE_WORKOUT = 5

SPORT_IDS = {
    "generic": 0,
    "running": 1,
    "cycling": 2,
    "swimming": 5,
    "strength": 10,   # "training"
}

# workout_step.duration_type
DURATION_TIME = 0
DURATION_DISTANCE = 1
DURATION_OPEN = 5
DURATION_REPEAT_UNTIL_STEPS_CMPLT = 6
# Strength steps are counted in repetitions, not seconds.
DURATION_REPS = 29

# workout_step.target_type
TARGET_SPEED = 0
TARGET_HEART_RATE = 1
TARGET_OPEN = 2
TARGET_CADENCE = 3
TARGET_POWER = 4

# workout_step.intensity
INTENSITY_ACTIVE = 0
INTENSITY_REST = 1
INTENSITY_WARMUP = 2
INTENSITY_COOLDOWN = 3

# FIT exercise taxonomy; 65534 is the profile's "unknown" sentinel but the
# field is a single byte here, so use 255 (invalid) when there is no category.
EXERCISE_CATEGORY_UNKNOWN = 255

# Power targets are stored with a +1000 offset so the field can also express
# "% of FTP" values below 1000.
POWER_OFFSET = 1000

_CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]


def _crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def _fit_timestamp(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - FIT_EPOCH).total_seconds())


class _Writer:
    """Minimal FIT encoder: definition + data records, little-endian."""

    def __init__(self):
        self.buf = BytesIO()
        self.buf.write(b"\x00" * 14)  # header rewritten in finalize()
        self.defs: dict[int, list] = {}

    def define(self, local_id: int, global_msg: int,
               fields: list[tuple[int, int, int]]) -> None:
        self.defs[local_id] = fields
        self.buf.write(struct.pack("<B", 0x40 | (local_id & 0x0F)))
        self.buf.write(struct.pack("<BBHB", 0, 0, global_msg, len(fields)))
        for num, size, base in fields:
            self.buf.write(struct.pack("<BBB", num, size, base))

    def write(self, local_id: int, values: list) -> None:
        self.buf.write(struct.pack("<B", local_id & 0x0F))
        for (_, size, base), value in zip(self.defs[local_id], values):
            if base == STRING:
                raw = (value or "").encode("utf-8")[: size - 1]
                self.buf.write(raw + b"\x00" * (size - len(raw)))
            elif base == UINT32:
                self.buf.write(struct.pack("<I", 0xFFFFFFFF if value is None else value & 0xFFFFFFFF))
            elif base == UINT16:
                self.buf.write(struct.pack("<H", 0xFFFF if value is None else value & 0xFFFF))
            else:
                self.buf.write(struct.pack("<B", 0xFF if value is None else value & 0xFF))

    def finalize(self) -> bytes:
        body = self.buf.getvalue()[14:]
        header = struct.pack("<BBHI4s", 14, 0x20, 0x08D0, len(body), b".FIT")
        header += struct.pack("<H", _crc16(header))
        data = header + body
        return data + struct.pack("<H", _crc16(data))


def _step_targets(step: dict, sport: str, ftp: int) -> tuple[int, int, int, int]:
    """Return (target_type, target_value, custom_low, custom_high).

    Cycling steps carry a power range in watts; running and swimming carry a
    speed range in mm/s derived from the prescribed pace. Anything without a
    machine target (strength) is left open so the watch just shows the text.
    """
    power = step.get("power")
    if sport == "cycling" and isinstance(power, (int, float)):
        watts = max(0, int(power * ftp))
        low = max(0, watts - 10)
        return TARGET_POWER, 0, low + POWER_OFFSET, watts + 10 + POWER_OFFSET

    pace = step.get("pace")  # seconds per km (run) or per 100m (swim)
    if pace:
        metres = 100 if sport == "swimming" else 1000
        speed_mm_s = int(metres * 1000 / pace)
        # A tolerance band, otherwise the watch alerts constantly.
        return TARGET_SPEED, 0, int(speed_mm_s * 0.95), int(speed_mm_s * 1.05)

    return TARGET_OPEN, 0, 0, 0


def _flatten(steps: list[dict]) -> list[dict]:
    """Expand repeat blocks into the FIT step list.

    FIT expresses repeats as a trailing step that points back at the index the
    loop starts from, so the work and rest steps are written once and then
    followed by a repeat marker.
    """
    out: list[dict] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        repeat = step.get("repeat") or step.get("sets") or 1
        rest = step.get("rest")
        if repeat > 1 and rest:
            start = len(out)
            out.append({**step, "_intensity": INTENSITY_ACTIVE})
            out.append({**rest, "_intensity": INTENSITY_REST})
            out.append({"_repeat_from": start, "_repeat_count": int(repeat)})
        else:
            out.append({**step, "_intensity": _intensity_for(step)})
    return out


def _intensity_for(step: dict) -> int:
    kind = (step.get("type") or "").lower()
    if kind == "warmup":
        return INTENSITY_WARMUP
    if kind == "cooldown":
        return INTENSITY_COOLDOWN
    if kind in ("rest", "recovery"):
        return INTENSITY_REST
    return INTENSITY_ACTIVE


# A strength set takes roughly this long, used when reps have to be expressed
# as time for a consumer that cannot read rep counts.
SECONDS_PER_REP = 4


def generate_workout_fit(workout: dict, ftp: int = 200,
                         created: datetime | None = None,
                         rep_steps: bool = True) -> bytes:
    """Encode one planned workout as a FIT workout file.

    `rep_steps` controls whether strength sets are written as repetitions.
    Watches handle them; intervals.icu reports "Unhandled duration_type: REPS"
    and drops the step, so the push path asks for timed equivalents instead.
    """
    sport = workout.get("sport", "cycling")
    sport_id = SPORT_IDS.get(sport, SPORT_IDS["generic"])
    name = (workout.get("name") or "Pulse Workout")[:31]
    steps = _flatten(workout.get("steps") or [])

    if not steps:
        steps = [{
            "duration": (workout.get("duration_minutes") or 60) * 60,
            "notes": workout.get("description", ""),
            "_intensity": INTENSITY_ACTIVE,
        }]

    writer = _Writer()

    writer.define(0, FILE_ID, [
        (0, 1, ENUM),      # type
        (1, 2, UINT16),    # manufacturer
        (2, 2, UINT16),    # product
        (3, 4, UINT32),    # serial_number
        (4, 4, UINT32),    # time_created
    ])
    writer.write(0, [
        FILE_TYPE_WORKOUT, 255, 0, 0,
        _fit_timestamp(created or datetime.now(timezone.utc)),
    ])

    writer.define(1, WORKOUT, [
        (8, 32, STRING),   # wkt_name
        (4, 1, ENUM),      # sport
        (6, 2, UINT16),    # num_valid_steps
    ])
    writer.write(1, [name, sport_id, len(steps)])

    writer.define(2, WORKOUT_STEP, [
        (254, 2, UINT16),  # message_index — repeats reference steps by this
        (0, 32, STRING),   # wkt_step_name
        (1, 1, ENUM),      # duration_type
        (2, 4, UINT32),    # duration_value
        (3, 1, ENUM),      # target_type
        (4, 4, UINT32),    # target_value
        (5, 4, UINT32),    # custom_target_value_low
        (6, 4, UINT32),    # custom_target_value_high
        (7, 1, ENUM),      # intensity
        (10, 1, ENUM),     # exercise_category
    ])

    for index, step in enumerate(steps):
        if "_repeat_from" in step:
            writer.write(2, [
                index, "", DURATION_REPEAT_UNTIL_STEPS_CMPLT, step["_repeat_from"],
                TARGET_OPEN, step["_repeat_count"], 0, 0, INTENSITY_ACTIVE,
                EXERCISE_CATEGORY_UNKNOWN,
            ])
            continue

        reps = step.get("reps")
        metres = step.get("distance_m")
        seconds = int(step.get("duration") or 0)
        target_type, target_value, low, high = _step_targets(step, sport, ftp)
        label = step.get("label") or step.get("exercise") or step.get("notes") or ""

        if reps and rep_steps:
            duration_type, duration_value = DURATION_REPS, int(reps)
        elif reps:
            # The consumer cannot read rep counts, so express the set as the
            # time it takes instead of dropping the step entirely.
            duration_type = DURATION_TIME
            duration_value = max(1, int(reps) * SECONDS_PER_REP) * 1000
        elif metres:
            # Swimming is prescribed in metres. Sending time plus a pace target
            # makes the consumer derive a distance, and it derives nonsense.
            duration_type, duration_value = DURATION_DISTANCE, int(metres * 100)
        elif seconds:
            duration_type, duration_value = DURATION_TIME, seconds * 1000
        else:
            duration_type, duration_value = DURATION_OPEN, 0

        writer.write(2, [
            index, label[:31],
            duration_type, duration_value,
            target_type, target_value, low, high,
            step.get("_intensity", INTENSITY_ACTIVE),
            step.get("exercise_category", EXERCISE_CATEGORY_UNKNOWN),
        ])

    return writer.finalize()


def workout_filename(workout: dict, date: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in (workout.get("name") or "workout"))
    return f"{date}_{safe[:40]}.fit"
