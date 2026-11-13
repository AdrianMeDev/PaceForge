import os
from pathlib import Path

import pytest

from activities.efforts import Sample, best_efforts
from activities.parsing import parse_series
from activities.parsing.fit import MAX_MESSAGES
from activities.parsing.series import fit_series, tcx_series
from activities.parsing.types import InvalidFileError, UnsupportedFileError

from . import fit_builder
from .fit_builder import RECORD, UINT8, UINT16, UINT32, FitBuilder, activity_file, fit_time
from .tcx_builder import tcx_document, trackpoint_document


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


class TestTcxSeries:
    def test_the_trackpoints_come_back_in_order(self) -> None:
        data = trackpoint_document([(0, 0.0, 150, 200), (1, 3.5, 151, 210), (2, 7.0, 152, None)])

        assert tcx_series(data) == [
            Sample(0.0, 200.0, 0.0, 150.0),
            Sample(1.0, 210.0, 3.5, 151.0),
            Sample(2.0, None, 7.0, 152.0),
        ]

    def test_missing_elements_stay_none(self) -> None:
        data = trackpoint_document([(0, None, None, None), (5, 10.0, None, None)])

        assert tcx_series(data) == [Sample(0.0), Sample(5.0, None, 10.0, None)]

    def test_trackpoints_without_a_usable_time_are_left_out(self) -> None:
        data = trackpoint_document([(0, 0.0, 150, None), (1, 3.0, 150, None)]).replace(
            b"<Time>2026-11-12T06:30:01.000Z</Time>", b"<Time>soon</Time>"
        )

        assert [sample.seconds for sample in tcx_series(data)] == [0.0]

    def test_numbers_that_are_no_numbers_stay_none(self) -> None:
        data = trackpoint_document([(0, 0.0, 150, 200)]).replace(b">150<", b">fast<")

        assert tcx_series(data) == [Sample(0.0, 200.0, 0.0, None)]

    def test_lap_values_are_not_mistaken_for_trackpoint_values(self) -> None:
        samples = tcx_series(tcx_document())

        assert {sample.heart_rate for sample in samples} == {111.0}  # the lap averages differ

    def test_a_run_gives_its_best_pace(self) -> None:
        points: list[tuple[float, float | None, int | None, int | None]] = [
            (s, s * 10 / 3, 160, None) for s in range(1801)
        ]

        found = best_efforts(tcx_series(trackpoint_document(points)))

        assert 1000 / found.speed[1800].value == pytest.approx(300)
        assert found.speed[1800].heart_rate == pytest.approx(160)

    @pytest.mark.parametrize(
        "prolog",
        [
            '<?xml version="1.0"?><!DOCTYPE x>',
            '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]>',
            '<?xml version="1.0"?><!DOCTYPE x SYSTEM "file:///etc/passwd">',
        ],
    )
    def test_a_document_type_is_refused_as_in_the_summary(self, prolog: str) -> None:
        with pytest.raises(InvalidFileError, match="document type"):
            tcx_series(tcx_document(prolog=prolog))

    def test_a_document_type_is_refused_in_utf_16_too(self) -> None:
        text = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x><TrainingCenterDatabase/>'

        with pytest.raises(InvalidFileError, match="document type"):
            tcx_series(text.encode("utf-16"))

    def test_another_xml_document_is_not_a_tcx_file(self) -> None:
        with pytest.raises(UnsupportedFileError):
            tcx_series(b"<?xml version='1.0'?><html><body/></html>")

    def test_broken_xml_is_refused(self) -> None:
        with pytest.raises(InvalidFileError, match="well-formed"):
            tcx_series(tcx_document()[:-40])

    def test_too_many_trackpoints_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import activities.parsing.series as series

        monkeypatch.setattr(series, "MAX_TRACKPOINTS", 5)

        with pytest.raises(InvalidFileError, match="too much"):
            tcx_series(trackpoint_document([(s, None, None, None) for s in range(6)]))

    def test_too_deep_nesting_is_refused(self) -> None:
        deep = "<a>" * 70 + "</a>" * 70
        data = tcx_document(inside=deep)

        with pytest.raises(InvalidFileError, match="nested"):
            tcx_series(data)

    def test_a_long_text_is_cut_and_its_nonsense_never_counts(self) -> None:
        points: list[tuple[float, float | None, int | None, int | None]] = [
            (s, s * 3.0, 150, None) for s in range(400)
        ]
        data = trackpoint_document(points).replace(b">150<", b">" + b"1" * 10_000 + b"<", 1)

        samples = tcx_series(data)

        assert samples[0].heart_rate == float("1" * 64)  # only 64 characters are read
        assert best_efforts(samples).speed[300].heart_rate == pytest.approx(150)

    def test_the_first_value_of_a_trackpoint_counts(self) -> None:
        data = trackpoint_document([(0, 0.0, 150, None)]).replace(
            b"<HeartRateBpm><Value>150</Value></HeartRateBpm>",
            b"<HeartRateBpm><Value>150</Value></HeartRateBpm>"
            b"<HeartRateBpm><Value>99</Value></HeartRateBpm>",
        )

        assert tcx_series(data)[0].heart_rate == 150

    def test_a_time_without_a_time_zone_is_left_out(self) -> None:
        data = trackpoint_document([(0, 0.0, 150, None), (1, 3.0, 150, None)]).replace(
            b"2026-11-12T06:30:01.000Z", b"2026-11-12T06:30:01"
        )

        assert len(tcx_series(data)) == 1

    def test_values_in_the_wrong_place_do_not_count(self) -> None:
        foreign = (
            b"<Extensions><ns3:TPX><ns3:Speed>3</ns3:Speed></ns3:TPX></Extensions>"
            b"<Other><Value>77</Value><Watts>9</Watts></Other>"
        )
        data = trackpoint_document([(0, 0.0, None, None)]).replace(
            b"<DistanceMeters>0.0</DistanceMeters>",
            b"<DistanceMeters>0.0</DistanceMeters>" + foreign,
        )

        assert tcx_series(data) == [Sample(0.0, None, 0.0, None)]

    def test_too_many_elements_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import activities.parsing.series as series

        monkeypatch.setattr(series, "MAX_ELEMENTS", 20)

        with pytest.raises(InvalidFileError, match="too much"):
            tcx_series(trackpoint_document([(s, 1.0, 150, 200) for s in range(10)]))

    def test_no_error_text_contains_file_content(self) -> None:
        with pytest.raises(InvalidFileError) as raised:
            tcx_series(tcx_document(prolog='<!DOCTYPE c [<!ENTITY a "SECRET">]>'))

        assert "SECRET" not in str(raised.value)


class TestDetection:
    def test_a_fit_file_is_read_as_fit(self) -> None:
        assert parse_series(activity_file(samples=[(0, 200, 0, 150)])) == [
            Sample(0.0, 200.0, 0.0, 150.0)
        ]

    def test_a_tcx_file_is_read_as_tcx(self) -> None:
        assert parse_series(trackpoint_document([(0, 1.0, None, None)])) == [
            Sample(0.0, None, 1.0, None)
        ]

    @pytest.mark.parametrize("data", [b"", b"hello", b"\x00" * 20, b"PK\x03\x04zip"])
    def test_anything_else_is_unsupported(self, data: bytes) -> None:
        with pytest.raises(UnsupportedFileError):
            parse_series(data)


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


@pytest.mark.skipif(
    not os.environ.get("PACEFORGE_SAMPLE_TCX"),
    reason="set PACEFORGE_SAMPLE_TCX to the path of a real TCX file to run this check",
)
def test_a_real_tcx_file_gives_a_plausible_series() -> None:
    samples = tcx_series(Path(os.environ["PACEFORGE_SAMPLE_TCX"]).read_bytes())

    assert len(samples) > 100
    assert best_efforts(samples).speed
