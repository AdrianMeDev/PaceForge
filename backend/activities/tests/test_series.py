import os
from pathlib import Path

import pytest

from activities.efforts import Sample, best_efforts
from activities.parsing.fit import MAX_MESSAGES
from activities.parsing.series import fit_series
from activities.parsing.types import InvalidFileError, UnsupportedFileError

from . import fit_builder
from .fit_builder import RECORD, UINT8, UINT16, UINT32, FitBuilder, activity_file, fit_time


class TestFitSeries:
    def test_the_samples_written_into_a_file_come_back_in_order(self) -> None:
        data = activity_file(samples=[(0, 200, 0, 150), (1, 210, 350, 151), (2, 220, 700, 152)])

        assert fit_series(data) == [
            Sample(0.0, 200.0, 0.0, 150.0),
            Sample(1.0, 210.0, 3.5, 151.0),
            Sample(2.0, 220.0, 7.0, 152.0),
        ]

    def test_invalid_markers_become_none(self) -> None:
        data = activity_file(samples=[(0, None, None, None), (1, 200, None, 150)])

        assert fit_series(data) == [Sample(0.0), Sample(1.0, 200.0, None, 150.0)]

    def test_seconds_are_counted_from_the_first_record(self) -> None:
        data = activity_file(samples=[(30, 200, 0, 150), (35, 200, 100, 150)])

        assert [sample.seconds for sample in fit_series(data)] == [0.0, 5.0]

    def test_records_without_a_time_are_left_out(self) -> None:
        data = activity_file(records=3, with_record_times=False)

        assert fit_series(data) == []

    def test_developer_fields_are_ignored(self) -> None:
        data = activity_file(records=3, developer_field=True)

        assert len(fit_series(data)) == 3

    def test_a_ride_gives_its_best_efforts(self) -> None:
        samples: list[tuple[int, int | None, int | None, int | None]] = [
            (s, 250, s * 900, 155) for s in range(1300)
        ]  # 9 m/s for over 20 minutes

        found = best_efforts(fit_series(activity_file(samples=samples)))

        assert found.power[1200].value == pytest.approx(250)
        assert found.power[1200].heart_rate == pytest.approx(155)
        assert found.speed[1200].value == pytest.approx(9)

    def test_a_cut_off_file_is_refused(self) -> None:
        with pytest.raises(InvalidFileError):
            fit_series(activity_file()[:-30])

    def test_a_flipped_byte_is_refused(self) -> None:
        data = bytearray(activity_file())
        data[40] ^= 0xFF

        with pytest.raises(InvalidFileError):
            fit_series(bytes(data))

    def test_a_wrong_checksum_at_the_end_is_refused(self) -> None:
        data = bytearray(activity_file())
        data[-1] ^= 0x01

        with pytest.raises(InvalidFileError):
            fit_series(bytes(data))

    @pytest.mark.parametrize("data", [b"", b"hello", b"<?xml version='1.0'?><x/>"])
    def test_something_else_is_not_a_fit_file(self, data: bytes) -> None:
        with pytest.raises(UnsupportedFileError):
            fit_series(data)

    def test_chained_files_are_refused(self) -> None:
        with pytest.raises(UnsupportedFileError):
            fit_series(activity_file() + activity_file())

    def test_too_many_messages_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import activities.parsing.series as series

        monkeypatch.setattr(series, "MAX_MESSAGES", 4)

        with pytest.raises(InvalidFileError, match="too much"):
            fit_series(activity_file(records=10))

    def test_the_cap_is_the_one_of_the_summary_parser(self) -> None:
        import activities.parsing.series as series

        assert series.MAX_MESSAGES == MAX_MESSAGES

    def test_no_error_text_contains_file_content(self) -> None:
        data = activity_file()[:-30] + b"SECRET-TRACK"

        with pytest.raises(InvalidFileError) as raised:
            fit_series(data)

        assert "SECRET" not in str(raised.value)

    def test_records_written_by_hand_are_read(self) -> None:
        start = fit_time(fit_builder.datetime(2026, 11, 1, tzinfo=fit_builder.UTC))
        builder = FitBuilder().message(0, [(0, fit_builder.ENUM, fit_builder.TYPE_ACTIVITY)])
        for s in range(3):
            builder.message(RECORD, [(253, UINT32, start + s), (7, UINT16, 100), (3, UINT8, 140)])

        assert len(fit_series(builder.build())) == 3


@pytest.mark.skipif(
    not os.environ.get("PACEFORGE_SAMPLE_FIT"),
    reason="set PACEFORGE_SAMPLE_FIT to the path of a real FIT file to run this check",
)
def test_a_real_file_gives_a_plausible_series() -> None:
    samples = fit_series(Path(os.environ["PACEFORGE_SAMPLE_FIT"]).read_bytes())

    assert len(samples) > 100
    assert samples == sorted(samples, key=lambda sample: sample.seconds)
    found = best_efforts(samples)
    assert found.power or found.speed
