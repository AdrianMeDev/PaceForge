"""A small FIT encoder for tests, so no real (and personal) file has to be committed.

Only what the tests need: definition and data messages, developer fields and the two CRCs.
Values are given as the raw numbers a device writes (the FIT profile scales them: seconds are
milliseconds, distances are centimetres); ``None`` writes the "invalid" marker of the type.
"""

import struct
from datetime import UTC, datetime
from typing import Any

FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)

ENUM, UINT8, UINT16, UINT32, STRING = 0x00, 0x02, 0x84, 0x86, 0x07
_SIZE = {ENUM: 1, UINT8: 1, UINT16: 2, UINT32: 4}
_FORMAT = {ENUM: "B", UINT8: "B", UINT16: "H", UINT32: "I"}
_INVALID = {ENUM: 0xFF, UINT8: 0xFF, UINT16: 0xFFFF, UINT32: 0xFFFFFFFF}

# Global message numbers
FILE_ID, SESSION, LAP, RECORD, ACTIVITY = 0, 18, 19, 20, 34
FIELD_DESCRIPTION, DEVELOPER_DATA_ID = 206, 207

# Enum values
TYPE_ACTIVITY, TYPE_WORKOUT = 4, 5
SPORT_RUNNING, SPORT_CYCLING, SPORT_SWIMMING, SPORT_TRAINING, SPORT_WALKING = 1, 2, 5, 10, 11
SPORT_E_BIKING = 21
SUB_GENERIC, SUB_TREADMILL, SUB_INDOOR_CYCLING, SUB_STRENGTH = 0, 1, 6, 20
MANUFACTURER_GARMIN, MANUFACTURER_COROS = 1, 294

_CRC_TABLE = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)  # fmt: skip


def crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        for nibble in (byte & 0xF, (byte >> 4) & 0xF):
            crc = ((crc >> 4) & 0x0FFF) ^ _CRC_TABLE[crc & 0xF] ^ _CRC_TABLE[nibble]
    return crc


def fit_time(moment: datetime) -> int:
    return int((moment - FIT_EPOCH).total_seconds())


class FitBuilder:
    def __init__(self) -> None:
        self._body = bytearray()
        self._definitions: dict[int, tuple[int, bytes]] = {}

    def message(
        self,
        global_number: int,
        fields: list[tuple[int, int, Any]],
        *,
        developer: list[tuple[int, int, bytes]] | None = None,
    ) -> FitBuilder:
        """Add one message. ``fields``: (field number, base type, value); ``developer``: (field
        number, developer data index, raw bytes)."""
        developer = developer or []
        layout = b"".join(
            struct.pack("BBB", number, _width(base, value), base) for number, base, value in fields
        )
        dev_layout = b"".join(struct.pack("BBB", n, len(raw), i) for n, i, raw in developer)
        definition = struct.pack(
            "<BBBHB", 0x40 | (0x20 if developer else 0), 0, 0, global_number, len(fields)
        )
        definition += layout
        if developer:
            definition += struct.pack("B", len(developer)) + dev_layout
        if self._definitions.get(0) != (global_number, definition):
            self._body += definition
            self._definitions[0] = (global_number, definition)
        self._body += b"\x00" + b"".join(_encode(base, value) for _, base, value in fields)
        self._body += b"".join(raw for _, _, raw in developer)
        return self

    def raw(self, content: bytes) -> FitBuilder:
        """Append bytes as they are, to write malformed content that still has a valid checksum."""
        self._body += content
        return self

    def build(self) -> bytes:
        header = struct.pack("<BBHI4s", 14, 0x20, 21158, len(self._body), b".FIT")
        header += struct.pack("<H", crc16(header))
        content = header + bytes(self._body)
        return content + struct.pack("<H", crc16(content))


def _width(base: int, value: Any) -> int:
    return 16 if base == STRING else _SIZE[base]


def _encode(base: int, value: Any) -> bytes:
    if base == STRING:
        return str(value).encode()[:15].ljust(16, b"\x00")
    return struct.pack("<" + _FORMAT[base], _INVALID[base] if value is None else value)


def activity_file(
    *,
    start: datetime = datetime(2026, 11, 12, 6, 30, tzinfo=UTC),
    file_type: int = TYPE_ACTIVITY,
    manufacturer: int | None = MANUFACTURER_GARMIN,
    product_name: str | None = None,
    sport: int | None = SPORT_RUNNING,
    sub_sport: int | None = None,
    session: dict[int, int | None] | None = None,
    laps: list[dict[int, int | None]] | None = None,
    records: int = 5,
    developer_field: bool = False,
    sessions: int = 1,
    with_session_start: bool = True,
    with_record_times: bool = True,
    samples: list[tuple[int, int | None, int | None, int | None]] | None = None,
) -> bytes:
    """A typical activity file. ``session`` overrides or adds raw session fields by number
    (``None`` writes the invalid marker); the defaults describe a 65 minute, 12.77 km run.
    ``samples`` replaces the generated records: (seconds after the start, power in W, distance in
    centimetres, heart rate), ``None`` writing the invalid marker."""
    builder = FitBuilder()
    start_fit = fit_time(start)
    id_fields: list[tuple[int, int, Any]] = [(0, ENUM, file_type), (1, UINT16, manufacturer)]
    if product_name is not None:
        id_fields.append((8, STRING, product_name))
    builder.message(FILE_ID, id_fields)
    if developer_field:
        builder.message(DEVELOPER_DATA_ID, [(3, UINT8, 0)])
        builder.message(
            FIELD_DESCRIPTION,
            [(0, UINT8, 0), (1, UINT8, 0), (2, UINT8, 0x84), (3, STRING, "stride_x")],
        )
    for offset, power, distance, heart_rate in samples or []:
        builder.message(
            RECORD,
            [
                (253, UINT32, start_fit + offset),
                (7, UINT16, power),
                (5, UINT32, distance),
                (3, UINT8, heart_rate),
            ],
        )
    for n in range(0 if samples is not None else records):
        fields: list[tuple[int, int, Any]] = [(3, UINT8, 140 + n % 60), (7, UINT16, 300 + n % 100)]
        if with_record_times:
            fields.insert(0, (253, UINT32, start_fit + n))
        builder.message(
            RECORD, fields, developer=[(0, 0, struct.pack("<H", 7))] if developer_field else None
        )
    for lap in laps if laps is not None else [{}]:
        defaults: dict[int, int | None] = {
            2: start_fit,
            7: 1_950_000,
            9: 638_300,
            15: 150,
            16: 165,
            253: start_fit + 1950,
        }
        lap_fields = {**defaults, **lap}
        builder.message(
            LAP, [(n, UINT32 if n in (2, 7, 9, 253) else UINT8, v) for n, v in lap_fields.items()]
        )
    for _ in range(sessions):
        values: dict[int, int | None] = {
            253: start_fit + 3905,
            7: 3_904_590,
            8: 3_900_000,
            9: 1_276_623,
            11: 1133,
            16: 155,
            17: 169,
            20: 325,
            22: 11,
        }
        if with_session_start:
            values[2] = start_fit
        if sport is not None:
            values[5] = sport
        if sub_sport is not None:
            values[6] = sub_sport
        values.update(session or {})
        builder.message(SESSION, [(n, _SESSION_TYPES[n], v) for n, v in values.items()])
    builder.message(ACTIVITY, [(253, UINT32, start_fit + 3905), (1, UINT16, sessions)])
    return builder.build()


_SESSION_TYPES = {2: UINT32, 253: UINT32, 5: ENUM, 6: ENUM, 7: UINT32, 8: UINT32, 9: UINT32,
                  11: UINT16, 16: UINT8, 17: UINT8, 20: UINT16, 22: UINT16}  # fmt: skip
