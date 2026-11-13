import os
import random
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from activities.models import Activity
from activities.parsing import (
    InvalidFileError,
    UnsupportedFileError,
    parse_activity_file,
    parse_tcx,
    tcx,
)
from activities.parsing.types import TCX_FILE, ParsedActivity, ParsedLap

from .fit_builder import activity_file
from .tcx_builder import DEFAULT_LAPS, START, big_document, stamp, tcx_document

SECRET = "TOP-SECRET-FILE-CONTENT"


class TestWhatIsRead:
    def test_a_document_gives_what_its_laps_report(self) -> None:
        parsed = parse_tcx(tcx_document())

        assert parsed == ParsedActivity(
            source=TCX_FILE,
            sport="running",
            source_sport="Running",
            start_time=START,
            elapsed_seconds=2130.0,  # to the last trackpoint, the 30 s pause included
            timer_seconds=2100.0,
            distance_m=7000.0,
            avg_heart_rate=144,  # (140*600 + 150*1200 + 130*300) / 2100
            max_heart_rate=170,
            avg_power_w=226,  # (200*600 + 250*1200 + 180*300) / 2100
            total_ascent_m=None,
            calories=350,
            manufacturer="Test Watch",
            laps=(
                ParsedLap(START, 600.0, 2000.0, 140, 150),
                ParsedLap(START + timedelta(seconds=600), 1200.0, 4000.0, 150, 170),
                ParsedLap(START + timedelta(seconds=1830), 300.0, 1000.0, 130, 140),
            ),
        )

    def test_values_of_trackpoints_are_not_mistaken_for_values_of_laps(self) -> None:
        parsed = parse_tcx(tcx_document())

        assert parsed.distance_m == 7000.0  # not the 999999 of every trackpoint
        assert parsed.avg_heart_rate != 111  # not the heart rate of the trackpoints
        assert parsed.avg_power_w != 9999  # not the watts of the trackpoints

    def test_the_total_ascent_is_never_computed(self) -> None:
        assert parse_tcx(tcx_document()).total_ascent_m is None

    def test_pretty_printed_documents_and_other_namespace_prefixes_work(self) -> None:
        document = tcx_document().decode().replace("><", ">\n  <").replace("ns3:", "x:")
        document = document.replace("xmlns:ns3=", "xmlns:x=")

        assert parse_tcx(document.encode()) == parse_tcx(tcx_document())

    def test_unknown_elements_are_ignored(self) -> None:
        extra = "<Author><Name>Somebody</Name></Author><Whatever><Lap/><Trackpoint/></Whatever>"

        assert parse_tcx(tcx_document(inside=extra)) == parse_tcx(tcx_document())

    def test_a_byte_order_mark_and_other_encodings_work(self) -> None:
        document = tcx_document()
        expected = parse_tcx(document)

        assert parse_tcx(b"\xef\xbb\xbf" + document) == expected
        text = document.decode().replace('encoding="UTF-8"', 'encoding="UTF-16"')
        assert parse_tcx(text.encode("utf-16")) == expected
        latin = tcx_document(creator="Uhr é").decode().replace("UTF-8", "ISO-8859-1")
        assert parse_tcx(latin.encode("latin-1")).manufacturer == "Uhr é"


class TestSports:
    @pytest.mark.parametrize(
        ("sport", "expected", "raw"),
        [
            ("Running", "running", "Running"),
            ("Biking", "cycling", "Biking"),
            ("Other", "other", "Other"),
            ("Swimming", "other", "Swimming"),
            (None, "other", ""),
        ],
    )
    def test_the_sport_is_normalised_and_the_original_wording_kept(
        self, sport: str | None, expected: str, raw: str
    ) -> None:
        parsed = parse_tcx(tcx_document(sport=sport))

        assert (parsed.sport, parsed.source_sport) == (expected, raw)

    def test_every_sport_that_can_come_out_is_a_choice_of_the_model(self) -> None:
        produced = {parse_tcx(tcx_document(sport=s)).sport for s in ("Running", "Biking", "x")}

        assert produced <= set(Activity.Sport.values)
        assert TCX_FILE in Activity.Source.values


class TestMissingValues:
    def lap(self, **changes: Any) -> dict[str, Any]:
        return {**DEFAULT_LAPS[0], **changes}

    @pytest.mark.parametrize(
        ("missing", "attributes"),
        [
            ("seconds", ["timer_seconds", "avg_heart_rate", "avg_power_w"]),
            ("distance", ["distance_m"]),
            ("calories", ["calories"]),
            ("avg_hr", ["avg_heart_rate"]),
            ("max_hr", ["max_heart_rate"]),
            ("avg_watts", ["avg_power_w"]),
        ],
    )
    def test_a_value_one_lap_does_not_report_stays_empty_for_the_whole_activity(
        self, missing: str, attributes: list[str]
    ) -> None:
        laps = [self.lap(**{missing: None}), DEFAULT_LAPS[1], DEFAULT_LAPS[2]]

        parsed = parse_tcx(tcx_document(laps=laps))

        for attribute in attributes:
            assert getattr(parsed, attribute) is None, attribute
        assert parsed.sport == "running"  # the rest is untouched

    def test_a_document_without_optional_elements_still_gives_the_rest(self) -> None:
        bare = [{"start": START, "seconds": 600}]

        parsed = parse_tcx(tcx_document(laps=bare, creator=None, sport=None))

        assert parsed.timer_seconds == 600.0
        assert parsed.distance_m is None
        assert parsed.calories is None
        assert parsed.avg_heart_rate is None and parsed.max_heart_rate is None
        assert parsed.avg_power_w is None
        assert parsed.manufacturer == ""

    @pytest.mark.parametrize("value", ["abc", "nan", "inf", "-5", "1e999", ""])
    def test_a_value_that_is_not_a_plausible_number_is_dropped(self, value: str) -> None:
        document = (
            tcx_document()
            .decode()
            .replace(
                "<DistanceMeters>2000</DistanceMeters>", f"<DistanceMeters>{value}</DistanceMeters>"
            )
        )

        parsed = parse_tcx(document.encode())

        assert parsed.distance_m is None
        assert parsed.laps[0].distance_m is None
        assert parsed.timer_seconds == 2100.0

    def test_zero_heart_rate_is_no_measurement(self) -> None:
        laps = [self.lap(avg_hr=0, max_hr=0), DEFAULT_LAPS[1], DEFAULT_LAPS[2]]

        parsed = parse_tcx(tcx_document(laps=laps))

        assert parsed.avg_heart_rate is None and parsed.max_heart_rate is None

    def test_a_lap_of_zero_seconds_does_not_divide_by_zero(self) -> None:
        parsed = parse_tcx(tcx_document(laps=[self.lap(seconds=0)]))

        assert parsed.timer_seconds == 0.0
        assert parsed.avg_heart_rate is None


class TestTimes:
    def test_times_with_an_offset_are_converted_to_utc(self) -> None:
        document = tcx_document().decode().replace(stamp(START), "2026-11-12T08:30:00.000+02:00", 2)

        parsed = parse_tcx(document.encode())

        assert parsed.start_time == START

    def test_a_time_without_a_zone_is_taken_as_utc(self) -> None:
        document = tcx_document().decode().replace(stamp(START), "2026-11-12T06:30:00", 2)

        assert parse_tcx(document.encode()).start_time == START

    def test_the_start_of_the_first_lap_wins_over_the_activity_id(self) -> None:
        parsed = parse_tcx(tcx_document(activity_id=START + timedelta(hours=1)))

        assert parsed.start_time == START

    def test_the_start_falls_back_to_the_activity_id(self) -> None:
        document = (
            tcx_document()
            .decode()
            .replace(f'<Lap StartTime="{stamp(START)}">', '<Lap StartTime="garbage">')
        )

        assert parse_tcx(document.encode()).start_time == START

    def test_the_start_falls_back_to_the_first_trackpoint(self) -> None:
        document = tcx_document(activity_id="not a time").decode()
        document = document.replace(f'<Lap StartTime="{stamp(START)}">', '<Lap StartTime="">')

        assert parse_tcx(document.encode()).start_time == START

    def test_without_any_usable_time_the_file_is_refused(self) -> None:
        document = tcx_document(activity_id=None, points=0).decode()
        document = document.replace(f'<Lap StartTime="{stamp(START)}">', "<Lap>")

        with pytest.raises(InvalidFileError, match="no start time"):
            parse_tcx(document.encode())

    def test_the_elapsed_time_without_trackpoints_comes_from_the_last_lap(self) -> None:
        parsed = parse_tcx(tcx_document(points=0))

        assert parsed.elapsed_seconds == 2130.0  # last lap start + its duration

    def test_the_elapsed_time_is_empty_when_nothing_says_how_long_it_lasted(self) -> None:
        parsed = parse_tcx(tcx_document(laps=[{"start": START}], points=0))

        assert parsed.elapsed_seconds == 0.0 or parsed.elapsed_seconds is None


class TestDocumentTypeDeclarations:
    BOMB = (
        '<!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">'
        + "".join(
            f'<!ENTITY {name} "{"&" + previous + ";"}{"&" + previous + ";"}{"&" + previous + ";"}'
            f'{"&" + previous + ";"}">'
            for previous, name in zip("abcdefghi", "bcdefghij", strict=True)
        )
        + "]>"
    )

    @pytest.mark.parametrize(
        "declaration",
        [
            "<!DOCTYPE TrainingCenterDatabase>",
            '<!DOCTYPE TrainingCenterDatabase [<!ENTITY x "y">]>',
            '<!DOCTYPE TrainingCenterDatabase [<!ENTITY x SYSTEM "file:///etc/passwd">]>',
            '<!DOCTYPE TrainingCenterDatabase SYSTEM "http://127.0.0.1:9/evil.dtd">',
            '<!DOCTYPE TrainingCenterDatabase [<!ENTITY % p SYSTEM "file:///etc/hostname"> %p;]>',
            BOMB,
            "<!-- a comment first --><!DOCTYPE TrainingCenterDatabase>",
            "<?pi first?><!DOCTYPE TrainingCenterDatabase [<!ELEMENT x ANY>]>",
        ],
    )
    def test_a_document_type_declaration_is_refused(self, declaration: str) -> None:
        document = tcx_document(before_root=declaration)

        with pytest.raises(InvalidFileError, match="document type declaration"):
            parse_tcx(document)

    def test_it_is_refused_in_other_encodings_too(self) -> None:
        document = tcx_document(
            before_root='<!DOCTYPE TrainingCenterDatabase [<!ENTITY x "y">]>',
            prolog='<?xml version="1.0" encoding="UTF-16"?>',
        ).decode()

        with pytest.raises(InvalidFileError, match="document type declaration"):
            parse_tcx(document.encode("utf-16"))

    def test_an_entity_bomb_is_refused_at_once_and_never_expanded(self) -> None:
        document = tcx_document(before_root=self.BOMB, inside="<Notes>&j;</Notes>")
        started = time.perf_counter()

        with pytest.raises(InvalidFileError):
            parse_tcx(document)

        assert (
            time.perf_counter() - started < 1.0
        )  # expanded it would be four to the ninth times 10 bytes

    def test_the_file_an_entity_points_to_is_never_read_or_shown(self, tmp_path: Path) -> None:
        secret_file = tmp_path / "secret.txt"
        secret_file.write_text(SECRET)
        document = tcx_document(
            before_root=f'<!DOCTYPE t [<!ENTITY x SYSTEM "{secret_file.as_uri()}">]>',
            creator="&x;",
        )

        with pytest.raises(InvalidFileError) as raised:
            parse_tcx(document)

        assert SECRET not in f"{raised.value} {raised.value!r}"

    def test_a_comment_or_processing_instruction_alone_is_fine(self) -> None:
        document = tcx_document(before_root="<!-- hello --><?note something?>")

        assert parse_tcx(document).sport == "running"


class TestWhatIsRefused:
    @pytest.mark.parametrize(
        "document",
        [
            b"",
            b"   \n",
            b"<TrainingCenterDatabase>",
            b"<TrainingCenterDatabase><b></TrainingCenterDatabase></b>",
            b"<TrainingCenterDatabase/><TrainingCenterDatabase/>",
            b"<TrainingCenterDatabase>\x00</TrainingCenterDatabase>",
            b"<TrainingCenterDatabase a='1' a='2'/>",
            b"<?xml version='1.0'?><!--",
            b"<TrainingCenterDatabase>&undefined;</TrainingCenterDatabase>",
        ],
    )
    def test_xml_that_is_not_well_formed_is_refused(self, document: bytes) -> None:
        with pytest.raises(InvalidFileError, match="not well-formed"):
            parse_tcx(document)

    def test_an_encoding_that_is_not_known_is_refused_with_its_own_message(self) -> None:
        document = b'<?xml version="1.0" encoding="x-nonsense"?><TrainingCenterDatabase/>'

        with pytest.raises(InvalidFileError, match="encoding that is not supported"):
            parse_tcx(document)

    def test_a_document_cut_off_anywhere_is_refused(self) -> None:
        document = tcx_document()

        for cut in range(0, len(document) - 1, 97):
            with pytest.raises((InvalidFileError, UnsupportedFileError)):
                parse_tcx(document[:cut])

    @pytest.mark.parametrize(
        "document",
        [
            b"<gpx><trk/></gpx>",
            b"<html><body>hello</body></html>",
            b'<?xml version="1.0"?><kml/>',
        ],
    )
    def test_xml_of_another_kind_is_unsupported(self, document: bytes) -> None:
        with pytest.raises(UnsupportedFileError, match="not a TCX"):
            parse_tcx(document)

    def test_a_tcx_without_an_activity_is_unsupported(self) -> None:
        courses = tcx_document(activities=0).replace(b"<Activities></Activities>", b"<Courses/>")

        with pytest.raises(UnsupportedFileError, match="no activity"):
            parse_tcx(courses)

    def test_several_activities_are_unsupported(self) -> None:
        with pytest.raises(UnsupportedFileError, match="several activities"):
            parse_tcx(tcx_document(activities=2))

    def test_a_multisport_session_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedFileError, match="several sports"):
            parse_tcx(tcx_document(inside="<MultiSportSession/>"))

    def test_an_activity_without_laps_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedFileError, match="no laps"):
            parse_tcx(tcx_document(laps=[]))

    def test_an_activity_in_the_wrong_place_is_not_found(self) -> None:
        misplaced = (
            b"<TrainingCenterDatabase><Other><Activity Sport='Running'/></Other>"
            b"</TrainingCenterDatabase>"
        )

        with pytest.raises(UnsupportedFileError, match="no activity"):
            parse_tcx(misplaced)


class TestLapsAreOnlyReadWhereTheyBelong:
    ALIEN = "<Courses><Lap><TotalTimeSeconds>999</TotalTimeSeconds><DistanceMeters>1</DistanceMeters></Lap></Courses>"  # noqa: E501

    def test_a_lap_outside_the_activity_is_ignored(self) -> None:
        assert parse_tcx(tcx_document(inside=self.ALIEN)) == parse_tcx(tcx_document())

    def test_a_document_with_only_foreign_laps_has_no_activity_and_no_crash(self) -> None:
        document = tcx_document(activities=0).replace(
            b"<Activities></Activities>", self.ALIEN.encode()
        )

        with pytest.raises(UnsupportedFileError, match="no activity"):
            parse_tcx(document)

    def test_a_lap_inside_a_lap_does_not_change_the_values(self) -> None:
        nested = b"<Lap><TotalTimeSeconds>5</TotalTimeSeconds><Calories>7</Calories></Lap>"
        document = tcx_document().replace(b"<Intensity>", nested + b"<Intensity>", 1)

        assert parse_tcx(document) == parse_tcx(tcx_document())

    def test_values_in_the_wrong_place_of_a_lap_are_ignored(self) -> None:
        wrapped = b"<Wrapper><TotalTimeSeconds>5</TotalTimeSeconds></Wrapper>"
        document = tcx_document().replace(b"<Intensity>", wrapped + b"<Intensity>", 1)

        assert parse_tcx(document) == parse_tcx(tcx_document())

    def test_a_bug_in_the_reader_would_not_pass_for_a_bad_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(self: Any, *args: Any) -> None:
            raise IndexError("a bug")

        monkeypatch.setattr(tcx._Reader, "start", broken)

        with pytest.raises(IndexError):
            parse_tcx(tcx_document())

    @pytest.mark.parametrize("seed", range(300))
    def test_random_element_structures_never_end_in_an_unexpected_exception(
        self, seed: int
    ) -> None:
        names = ["TrainingCenterDatabase", "Activities", "Activity", "Lap", "Track", "Trackpoint",
                 "Value", "Time", "AverageHeartRateBpm", "MaximumHeartRateBpm", "TotalTimeSeconds",
                 "DistanceMeters", "Calories", "Extensions", "LX", "TPX", "AvgWatts", "Creator",
                 "Name", "Id", "Courses", "MultiSportSession", "Other"]  # fmt: skip
        texts = ["", "5", "abc", "1e9", "-3", "2026-11-12T06:30:00Z", "nan", "140"]
        rng = random.Random(seed)

        def node(depth: int) -> str:
            name = rng.choice(names)
            attributes = rng.choice(["", ' Sport="Running"', f' StartTime="{rng.choice(texts)}"'])
            children = (
                "".join(node(depth + 1) for _ in range(rng.randint(0, 3))) if depth < 7 else ""
            )
            return f"<{name}{attributes}>{rng.choice(texts)}{children}</{name}>"

        body = "".join(node(1) for _ in range(rng.randint(1, 4)))
        document = f"<TrainingCenterDatabase>{body}</TrainingCenterDatabase>"

        try:
            parse_tcx(document.encode())
        except InvalidFileError, UnsupportedFileError:
            pass


class TestLimits:
    def test_too_many_trackpoints_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tcx, "MAX_TRACKPOINTS", 5)

        with pytest.raises(InvalidFileError, match="too much data"):
            parse_tcx(tcx_document(points=3))  # 9 trackpoints in three laps

    def test_a_document_just_inside_the_limit_is_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tcx, "MAX_TRACKPOINTS", 9)

        assert parse_tcx(tcx_document(points=3)).timer_seconds == 2100.0

    def test_too_many_elements_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tcx, "MAX_ELEMENTS", 30)

        with pytest.raises(InvalidFileError, match="too much data"):
            parse_tcx(tcx_document())

    def test_too_many_laps_are_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tcx, "MAX_LAPS", 2)

        with pytest.raises(InvalidFileError, match="too many laps"):
            parse_tcx(tcx_document())

    def test_deep_nesting_is_refused_without_a_stack_overflow(self) -> None:
        document = b"<TrainingCenterDatabase>" + b"<a>" * 100_000

        with pytest.raises(InvalidFileError, match="nested too deeply"):
            parse_tcx(document)

    def test_a_large_document_is_read_with_little_memory(self) -> None:
        document = big_document(60_000)  # about 40 MB of XML is too large; this is a few MB
        assert len(document) > 5_000_000
        tracemalloc.start()
        try:
            parsed = parse_tcx(document)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert parsed.distance_m == 180_000.0
        assert peak < 20_000_000

    def test_a_huge_text_in_an_unwanted_element_is_not_kept(self) -> None:
        notes = "<Notes>" + "x" * 8_000_000 + "</Notes>"
        document = tcx_document().replace(
            b"<Activities>", b"<Wrapper>" + notes.encode() + b"</Wrapper><Activities>"
        )
        tracemalloc.start()
        try:
            parsed = parse_tcx(document)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert parsed.timer_seconds == 2100.0
        assert peak < 5_000_000

    def test_a_huge_text_in_a_wanted_element_is_cut_not_kept(self) -> None:
        document = tcx_document(creator="N" * 8_000_000)
        tracemalloc.start()
        try:
            parsed = parse_tcx(document)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert len(parsed.manufacturer) <= 50
        assert peak < 5_000_000


class TestNoFileContentInErrors:
    def test_no_error_text_contains_anything_from_the_file(self) -> None:
        shown: list[str] = []
        variants = [
            tcx_document(creator=SECRET, before_root="<!DOCTYPE x>"),
            tcx_document(creator=SECRET, activities=2),
            tcx_document(creator=SECRET, laps=[]),
            tcx_document(creator=SECRET)[:-30],
            tcx_document(creator=SECRET).replace(b"</Activities>", b"</Wrong>"),
            f"<gpx><name>{SECRET}</name></gpx>".encode(),
            tcx_document(creator=SECRET, inside="<MultiSportSession/>"),
        ]
        for variant in variants:
            try:
                parse_tcx(variant)
            except (InvalidFileError, UnsupportedFileError) as error:
                shown.append(f"{error} {error!r} {error.__cause__!r} {error.__context__!r}")

        assert len(shown) == len(variants)
        assert not any(SECRET in text for text in shown)


class TestFormatDetection:
    def test_a_fit_file_is_read_as_fit(self) -> None:
        assert parse_activity_file(activity_file()).source == "fit_file"

    def test_a_tcx_file_is_read_as_tcx(self) -> None:
        assert parse_activity_file(tcx_document()).source == "tcx_file"

    @pytest.mark.parametrize(
        "prefix",
        [b"", b"\xef\xbb\xbf", b"  \n\t", b"\r\n"],
    )
    def test_whitespace_and_a_byte_order_mark_before_the_xml_are_fine(self, prefix: bytes) -> None:
        assert parse_activity_file(prefix + tcx_document()).source == "tcx_file"

    def test_a_utf16_document_is_recognised(self) -> None:
        text = tcx_document().decode().replace("UTF-8", "UTF-16")

        assert parse_activity_file(text.encode("utf-16")).source == "tcx_file"

    @pytest.mark.parametrize(
        "data",
        [
            b"",
            b"hello",
            b"{}",
            b"PK\x03\x04" + b"\x00" * 50,
            b"\x00" * 100,
            os.urandom(300),
            b"\x89PNG\r\n\x1a\n" + b"x" * 20,
        ],
    )
    def test_everything_else_is_unsupported(self, data: bytes) -> None:
        with pytest.raises(UnsupportedFileError, match="neither a FIT nor a TCX"):
            parse_activity_file(data)

    def test_the_name_of_a_file_decides_nothing_because_only_the_content_is_given(self) -> None:
        # The importer never passes a file name: a TCX saved as ".fit" is still a TCX.
        assert parse_activity_file(tcx_document()).sport == "running"

    def test_a_fit_file_cut_to_the_xml_detection_does_not_confuse_the_formats(self) -> None:
        with pytest.raises(UnsupportedFileError):
            parse_activity_file(activity_file()[:11])

    def test_the_result_of_both_formats_has_the_same_shape(self) -> None:
        fit_result = parse_activity_file(activity_file())
        tcx_result = parse_activity_file(tcx_document())

        assert type(fit_result) is type(tcx_result) is ParsedActivity
        assert fit_result.start_time.tzinfo is not None and tcx_result.start_time.tzinfo is not None
        assert fit_result.start_time == datetime(2026, 11, 12, 6, 30, tzinfo=UTC)


@pytest.mark.skipif(
    not os.environ.get("PACEFORGE_SAMPLE_TCX"),
    reason="set PACEFORGE_SAMPLE_TCX to the path of a real TCX file to run this check",
)
def test_a_real_file_from_a_device_gives_plausible_values() -> None:
    parsed = parse_activity_file(Path(os.environ["PACEFORGE_SAMPLE_TCX"]).read_bytes())

    assert parsed.source == "tcx_file"
    assert parsed.start_time.tzinfo is not None
    assert parsed.distance_m is None or parsed.distance_m > 0
    assert parsed.timer_seconds is None or parsed.timer_seconds > 0
    assert parsed.laps
