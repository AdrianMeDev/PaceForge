import os
import random
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pytest

from activities.models import Activity
from activities.parsing import fit
from activities.parsing.fit import parse_fit
from activities.parsing.types import (
    FIT_FILE,
    InvalidFileError,
    ParsedActivity,
    ParsedLap,
    UnsupportedFileError,
)

from .fit_builder import (
    MANUFACTURER_COROS,
    SPORT_CYCLING,
    SPORT_E_BIKING,
    SPORT_RUNNING,
    SPORT_SWIMMING,
    SPORT_TRAINING,
    SPORT_WALKING,
    SUB_GENERIC,
    SUB_INDOOR_CYCLING,
    SUB_STRENGTH,
    TYPE_WORKOUT,
    FitBuilder,
    activity_file,
    fit_time,
)

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)


class TestWhatIsRead:
    def test_a_file_gives_exactly_the_values_written_into_it(self) -> None:
        parsed = parse_fit(activity_file())

        assert parsed == ParsedActivity(
            source=FIT_FILE,
            sport="running",
            source_sport="running",
            start_time=START,
            elapsed_seconds=3904.59,
            timer_seconds=3900.0,
            distance_m=12766.23,
            avg_heart_rate=155,
            max_heart_rate=169,
            avg_power_w=325,
            total_ascent_m=11,
            calories=1133,
            manufacturer="garmin",
            laps=(ParsedLap(START, 1950.0, 6383.0, 150, 165),),
        )

    def test_the_start_is_an_aware_utc_time(self) -> None:
        parsed = parse_fit(activity_file())

        assert parsed.start_time.tzinfo is not None
        assert parsed.start_time.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_the_manufacturer_is_taken_from_the_file_id(self) -> None:
        assert parse_fit(activity_file(manufacturer=MANUFACTURER_COROS)).manufacturer == "coros"

    def test_an_unknown_manufacturer_is_not_made_up(self) -> None:
        assert parse_fit(activity_file(manufacturer=None)).manufacturer == ""

    def test_laps_are_read_in_order(self) -> None:
        laps: list[dict[int, int | None]] = [
            {2: fit_time(START) + 0, 7: 1_000_000, 9: 100_000},
            {2: fit_time(START) + 1000, 7: 2_000_000, 9: 250_000},
            {2: fit_time(START) + 3000, 7: 900_000, 9: 80_000},
        ]

        parsed = parse_fit(activity_file(laps=laps))

        assert [lap.elapsed_seconds for lap in parsed.laps] == [1000.0, 2000.0, 900.0]
        assert [lap.distance_m for lap in parsed.laps] == [1000.0, 2500.0, 800.0]
        assert [lap.start_time for lap in parsed.laps] == sorted(
            lap.start_time for lap in parsed.laps
        )  # type: ignore[type-var]

    def test_a_file_without_laps_has_none(self) -> None:
        assert parse_fit(activity_file(laps=[])).laps == ()

    def test_a_lap_without_heart_rate_has_none(self) -> None:
        parsed = parse_fit(activity_file(laps=[{15: None, 16: None}]))

        assert parsed.laps[0].avg_heart_rate is None
        assert parsed.laps[0].max_heart_rate is None
        assert parsed.laps[0].elapsed_seconds == 1950.0

    def test_developer_fields_do_not_get_in_the_way(self) -> None:
        with_developer = parse_fit(activity_file(developer_field=True))

        assert with_developer == parse_fit(activity_file())

    def test_unknown_messages_are_skipped(self) -> None:
        builder = FitBuilder()
        builder.message(0, [(0, 0x00, 4), (1, 0x84, 1)])
        builder.message(9999, [(0, 0x02, 7)])
        builder.message(18, [(2, 0x86, fit_time(START)), (5, 0x00, 1)])

        assert parse_fit(builder.build()).sport == "running"

    def test_a_valid_file_produces_no_warnings(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")

            parse_fit(activity_file(developer_field=True))


class TestMissingAndImplausibleValues:
    @pytest.mark.parametrize(
        ("field", "attribute"),
        [
            (7, "elapsed_seconds"),
            (8, "timer_seconds"),
            (9, "distance_m"),
            (11, "calories"),
            (16, "avg_heart_rate"),
            (17, "max_heart_rate"),
            (20, "avg_power_w"),
            (22, "total_ascent_m"),
        ],
    )
    def test_a_value_the_file_marks_invalid_stays_empty(self, field: int, attribute: str) -> None:
        parsed = parse_fit(activity_file(session={field: None}))

        assert getattr(parsed, attribute) is None
        assert parsed.sport == "running"  # the rest is untouched

    def test_zero_heart_rate_is_no_measurement(self) -> None:
        parsed = parse_fit(activity_file(session={16: 0, 17: 0}))

        assert parsed.avg_heart_rate is None and parsed.max_heart_rate is None

    def test_zero_power_is_reported_as_it_is(self) -> None:
        assert parse_fit(activity_file(session={20: 0})).avg_power_w == 0

    def test_absurd_values_are_dropped_not_clamped(self) -> None:
        parsed = parse_fit(activity_file(session={7: 4_000_000_000, 9: 4_000_000_000, 17: 250}))

        assert parsed.elapsed_seconds is None  # more than 30 days
        assert parsed.distance_m is None  # more than 10 000 km
        assert parsed.max_heart_rate == 250  # unusual, but possible: kept

    def test_the_start_falls_back_to_the_first_record(self) -> None:
        later_lap: list[dict[int, int | None]] = [{2: fit_time(START) + 60}]

        parsed = parse_fit(activity_file(with_session_start=False, laps=later_lap))

        assert parsed.start_time == START  # the record, not the lap that starts a minute later

    def test_the_start_falls_back_to_the_first_lap_when_there_are_no_record_times(self) -> None:
        later_lap: list[dict[int, int | None]] = [{2: fit_time(START) + 60}]

        parsed = parse_fit(
            activity_file(with_session_start=False, with_record_times=False, laps=later_lap)
        )

        assert parsed.start_time == datetime(2026, 11, 12, 6, 31, tzinfo=UTC)

    def test_without_any_start_time_the_file_is_refused(self) -> None:
        with pytest.raises(InvalidFileError, match="no start time"):
            parse_fit(
                activity_file(with_session_start=False, with_record_times=False, laps=[{2: None}])
            )


class TestSports:
    @pytest.mark.parametrize(
        ("sport", "sub_sport", "expected", "raw"),
        [
            (SPORT_RUNNING, None, "running", "running"),
            (SPORT_CYCLING, None, "cycling", "cycling"),
            (SPORT_CYCLING, SUB_INDOOR_CYCLING, "cycling", "cycling/indoor_cycling"),
            (SPORT_E_BIKING, None, "cycling", "e_biking"),
            (SPORT_SWIMMING, None, "swimming", "swimming"),
            (SPORT_TRAINING, SUB_STRENGTH, "strength", "training/strength_training"),
            (SPORT_TRAINING, None, "other", "training"),
            (SPORT_TRAINING, SUB_GENERIC, "other", "training"),
            (SPORT_WALKING, None, "other", "walking"),
        ],
    )
    def test_the_sport_is_normalised_and_the_original_wording_kept(
        self, sport: int, sub_sport: int | None, expected: str, raw: str
    ) -> None:
        parsed = parse_fit(activity_file(sport=sport, sub_sport=sub_sport))

        assert (parsed.sport, parsed.source_sport) == (expected, raw)

    def test_a_sport_the_profile_does_not_know_becomes_other_with_its_number(self) -> None:
        parsed = parse_fit(activity_file(sport=250))

        assert parsed.sport == "other"
        assert parsed.source_sport == "250"

    def test_a_file_without_a_sport_is_other_with_nothing_to_show(self) -> None:
        parsed = parse_fit(activity_file(sport=None))

        assert (parsed.sport, parsed.source_sport) == ("other", "")

    def test_every_sport_that_can_come_out_is_a_choice_of_the_model(self) -> None:
        produced = {
            parse_fit(activity_file(sport=s, sub_sport=sub)).sport
            for s, sub in [
                (SPORT_RUNNING, None),
                (SPORT_CYCLING, None),
                (SPORT_SWIMMING, None),
                (SPORT_TRAINING, SUB_STRENGTH),
                (SPORT_WALKING, None),
                (None, None),
            ]
        }

        assert produced <= set(Activity.Sport.values)
        assert FIT_FILE in Activity.Source.values


class TestWhatIsRefused:
    def test_a_file_that_is_cut_off_is_refused(self) -> None:
        data = activity_file(records=50)

        for cut in (len(data) // 2, len(data) - 1, len(data) - 5, 14):
            with pytest.raises(InvalidFileError, match="damaged or incomplete"):
                parse_fit(data[:cut])

    def test_a_flipped_byte_is_caught_by_the_checksum(self) -> None:
        data = bytearray(activity_file(records=50))
        data[len(data) // 2] ^= 0xFF

        with pytest.raises(InvalidFileError, match="damaged or incomplete"):
            parse_fit(bytes(data))

    def test_a_wrong_checksum_at_the_end_is_caught(self) -> None:
        data = bytearray(activity_file())
        data[-1] ^= 0x01

        with pytest.raises(InvalidFileError):
            parse_fit(bytes(data))

    @pytest.mark.parametrize(
        "data", [b"", b"\x00", b"hello, this is not a FIT file at all", b"x" * 5000, b"\x0e\x20"]
    )
    def test_something_that_is_not_a_fit_file_is_unsupported(self, data: bytes) -> None:
        with pytest.raises(UnsupportedFileError, match="not a FIT file"):
            parse_fit(data)

    def test_garbage_after_a_valid_header_is_refused(self) -> None:
        data = activity_file()

        with pytest.raises(InvalidFileError):
            parse_fit(data[:14] + b"\x00" * 300)

    def test_a_file_that_is_not_an_activity_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedFileError, match="not an activity"):
            parse_fit(activity_file(file_type=TYPE_WORKOUT))

    def test_a_file_without_a_session_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedFileError, match="no activity summary"):
            parse_fit(activity_file(sessions=0))

    def test_a_file_with_several_sessions_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedFileError, match="several sessions"):
            parse_fit(activity_file(sessions=3))

    def test_two_files_stuck_together_are_unsupported(self) -> None:
        one = activity_file()

        with pytest.raises(UnsupportedFileError, match="several FIT files"):
            parse_fit(one + one)

    @pytest.mark.parametrize(
        ("label", "definition"),
        [
            ("a data message without a definition", b"\x05\x01\x02\x03"),
            (
                "a field of an unknown type",
                bytes([0x41, 0, 0, 0x10, 0x27, 1, 0, 2, 0x55]) + b"\x01\x02",
            ),
            (
                "a field wider than its type",
                bytes([0x41, 0, 0, 0x10, 0x27, 1, 0, 3, 0x84]) + b"\x00\x01\x02\x00",
            ),
        ],
    )
    def test_malformed_content_with_a_valid_checksum_is_refused(
        self, label: str, definition: bytes
    ) -> None:
        builder = FitBuilder().message(0, [(0, 0x00, 4), (1, 0x84, 1)]).raw(definition)
        builder.message(18, [(2, 0x86, fit_time(START)), (5, 0x00, 1)])

        with pytest.raises(InvalidFileError, match="damaged or incomplete"):
            parse_fit(builder.build())

    def test_a_file_with_too_much_data_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fit, "MAX_MESSAGES", 10)

        with pytest.raises(InvalidFileError, match="too much data"):
            parse_fit(activity_file(records=50))

    def test_a_file_with_too_many_laps_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fit, "MAX_LAPS", 3)

        with pytest.raises(InvalidFileError, match="too many laps"):
            parse_fit(activity_file(laps=[{}] * 5))

    def test_a_file_just_inside_the_limits_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fit, "MAX_LAPS", 5)

        assert len(parse_fit(activity_file(laps=[{}] * 5)).laps) == 5

    @pytest.mark.parametrize("seed", range(40))
    def test_random_damage_never_ends_in_an_unexpected_exception(self, seed: int) -> None:
        rng = random.Random(seed)
        data = bytearray(activity_file(records=30, developer_field=bool(seed % 2)))
        for _ in range(rng.randint(1, 6)):
            data[rng.randrange(len(data))] = rng.randrange(256)

        try:
            parse_fit(bytes(data))
        except InvalidFileError, UnsupportedFileError:
            pass

    def test_no_error_text_contains_anything_from_the_file(self) -> None:
        secret = "SECRET-DEVICE-NAME"
        data = bytearray(activity_file(product_name=secret, records=30))
        shown: list[str] = []

        variants = [bytes(data[:60]), bytes(data[:-3]), bytes(data)[:14] + bytes(data)[20:]]
        flipped = bytearray(data)
        flipped[40] ^= 0xFF
        variants.append(bytes(flipped))
        variants.append(activity_file(product_name=secret, file_type=TYPE_WORKOUT))
        variants.append(activity_file(product_name=secret, sessions=2))
        for variant in variants:
            try:
                parse_fit(variant)
            except (InvalidFileError, UnsupportedFileError) as error:
                shown.append(f"{error} {error!r} {error.__cause__!r} {error.__context__!r}")

        assert shown
        assert not any(secret in text for text in shown)


@pytest.mark.skipif(
    not os.environ.get("PACEFORGE_SAMPLE_FIT"),
    reason="set PACEFORGE_SAMPLE_FIT to the path of a real FIT file to run this check",
)
def test_a_real_file_from_a_device_gives_plausible_values() -> None:
    parsed = parse_fit(Path(os.environ["PACEFORGE_SAMPLE_FIT"]).read_bytes())

    assert parsed.start_time.tzinfo is not None
    assert parsed.distance_m is None or parsed.distance_m > 0
    assert parsed.elapsed_seconds is None or parsed.elapsed_seconds > 0
    assert parsed.laps
