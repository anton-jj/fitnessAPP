"""Minimal FIT file generator for indoor cycling activities.
Produces valid .fit files that Strava, Coros, and Garmin Connect can import."""

import struct
from datetime import datetime, timezone
from io import BytesIO

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

# FIT message types
FILE_ID = 0
SESSION = 18
LAP = 19
RECORD = 20
EVENT = 21
ACTIVITY = 34

# Field types
ENUM = 0
UINT8 = 2
UINT16 = 132
UINT32 = 134
SINT16 = 131


def _fit_timestamp(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - FIT_EPOCH).total_seconds())


def _crc16(data: bytes) -> int:
    crc_table = [
        0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
    ]
    crc = 0
    for byte in data:
        tmp = crc_table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ crc_table[byte & 0xF]
        tmp = crc_table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ crc_table[(byte >> 4) & 0xF]
    return crc


class FitWriter:
    def __init__(self):
        self._buf = BytesIO()
        self._definitions: dict[int, list] = {}
        self._data_start = 0

    def _write_header(self):
        header = struct.pack("<BBHI4s", 14, 0x20, 0x08D0, 0, b".FIT")
        crc = _crc16(header)
        header += struct.pack("<H", crc)
        self._buf.write(header)
        self._data_start = self._buf.tell()

    def _write_definition(self, local_id: int, global_msg: int, fields: list[tuple[int, int, int]]):
        self._definitions[local_id] = fields
        record_header = 0x40 | (local_id & 0x0F)
        self._buf.write(struct.pack("<B", record_header))
        self._buf.write(struct.pack("<BBHB", 0, 0, global_msg, len(fields)))
        for field_def_num, size, base_type in fields:
            self._buf.write(struct.pack("<BBB", field_def_num, size, base_type))

    def _write_data(self, local_id: int, values: list):
        record_header = local_id & 0x0F
        self._buf.write(struct.pack("<B", record_header))
        fields = self._definitions[local_id]
        for (_, size, base_type), val in zip(fields, values):
            if base_type == UINT32 or base_type == 134:
                self._buf.write(struct.pack("<I", val & 0xFFFFFFFF))
            elif base_type == UINT16 or base_type == 132:
                self._buf.write(struct.pack("<H", val & 0xFFFF))
            elif base_type == SINT16 or base_type == 131:
                self._buf.write(struct.pack("<h", val))
            elif base_type == UINT8 or base_type == ENUM or base_type == 2:
                self._buf.write(struct.pack("<B", val & 0xFF))
            else:
                self._buf.write(struct.pack("<B", val & 0xFF))

    def finalize(self) -> bytes:
        data = self._buf.getvalue()
        data_size = len(data) - self._data_start
        data = data[:4] + struct.pack("<I", data_size) + data[8:]
        file_crc = _crc16(data)
        return data + struct.pack("<H", file_crc)


def generate_fit(
    start_time: datetime,
    duration_seconds: int,
    power_data: list[int],
    hr_data: list[int] | None = None,
    cadence_data: list[int] | None = None,
    avg_power: int | None = None,
    normalized_power: int | None = None,
    ftp: int = 200,
) -> bytes:
    writer = FitWriter()
    writer._write_header()

    ts = _fit_timestamp(start_time)

    # File ID
    writer._write_definition(0, FILE_ID, [
        (0, 1, ENUM),    # type (activity = 4)
        (1, 2, UINT16),  # manufacturer
        (2, 2, UINT16),  # product
        (3, 4, UINT32),  # serial_number
        (4, 4, UINT32),  # time_created
    ])
    writer._write_data(0, [4, 1, 1, 12345, ts])

    # Event (start)
    writer._write_definition(1, EVENT, [
        (253, 4, UINT32),  # timestamp
        (0, 1, ENUM),      # event (timer = 0)
        (1, 1, ENUM),      # event_type (start = 0)
    ])
    writer._write_data(1, [ts, 0, 0])

    # Records (1 per second)
    writer._write_definition(2, RECORD, [
        (253, 4, UINT32),  # timestamp
        (7, 2, UINT16),    # power
        (3, 1, UINT8),     # heart_rate
        (4, 1, UINT8),     # cadence
    ])

    sample_interval = max(1, duration_seconds // len(power_data)) if power_data else 1

    for i in range(len(power_data)):
        t = ts + i * sample_interval
        p = max(0, power_data[i]) if i < len(power_data) else 0
        hr = (hr_data[i] if hr_data and i < len(hr_data) else 0) & 0xFF
        cad = (cadence_data[i] if cadence_data and i < len(cadence_data) else 0) & 0xFF
        writer._write_data(2, [t, p, hr, cad])

    end_ts = ts + duration_seconds

    # Event (stop)
    writer._write_definition(3, EVENT, [
        (253, 4, UINT32),
        (0, 1, ENUM),
        (1, 1, ENUM),
    ])
    writer._write_data(3, [end_ts, 0, 4])  # event_type stop_all = 4

    # Lap
    total_power = sum(power_data) if power_data else 0
    calc_avg = total_power // len(power_data) if power_data else 0

    writer._write_definition(4, LAP, [
        (253, 4, UINT32),  # timestamp
        (2, 4, UINT32),    # start_time
        (7, 4, UINT32),    # total_elapsed_time (ms)
        (8, 4, UINT32),    # total_timer_time (ms)
        (0, 1, ENUM),      # event
        (1, 1, ENUM),      # event_type
        (24, 1, ENUM),     # lap_trigger (session_end = 7)
        (25, 1, ENUM),     # sport (cycling = 2)
        (19, 2, UINT16),   # avg_power
        (20, 2, UINT16),   # max_power
    ])
    max_p = max(power_data) if power_data else 0
    writer._write_data(4, [
        end_ts, ts,
        duration_seconds * 1000, duration_seconds * 1000,
        9, 1, 7, 2,
        avg_power or calc_avg, max_p,
    ])

    # Session
    writer._write_definition(5, SESSION, [
        (253, 4, UINT32),  # timestamp
        (2, 4, UINT32),    # start_time
        (7, 4, UINT32),    # total_elapsed_time (ms)
        (8, 4, UINT32),    # total_timer_time (ms)
        (0, 1, ENUM),      # event
        (1, 1, ENUM),      # event_type
        (5, 1, ENUM),      # sport (cycling = 2)
        (6, 1, ENUM),      # sub_sport (indoor_cycling = 6)
        (25, 1, ENUM),     # first_lap_index
        (26, 2, UINT16),   # num_laps
        (20, 2, UINT16),   # avg_power
        (21, 2, UINT16),   # max_power
        (34, 2, UINT16),   # normalized_power
        (29, 2, UINT16),   # threshold_power
    ])
    writer._write_data(5, [
        end_ts, ts,
        duration_seconds * 1000, duration_seconds * 1000,
        8, 1, 2, 6,
        0, 1,
        avg_power or calc_avg, max_p,
        normalized_power or avg_power or calc_avg,
        ftp,
    ])

    # Activity
    writer._write_definition(6, ACTIVITY, [
        (253, 4, UINT32),  # timestamp
        (0, 4, UINT32),    # total_timer_time (100ths of sec)
        (1, 2, UINT16),    # num_sessions
        (2, 1, ENUM),      # type (manual = 0)
        (3, 1, ENUM),      # event (activity = 26)
        (4, 1, ENUM),      # event_type (stop = 1)
    ])
    writer._write_data(6, [end_ts, duration_seconds * 100, 1, 0, 26, 1])

    return writer.finalize()
