import gzip
from datetime import timedelta

import pytest

from accounts.models import User
from activities.models import Activity, ActivityFile
from activities.parsing import (
    InvalidFileError,
    UnsupportedFileError,
    parse_activity_file,
    parse_gpx,
    parse_series,
)
from activities.parsing.gpx import distance_between, gpx_series
from activities.services import DuplicateActivityError, import_activity

from .gpx_builder import START, gpx_document
from .tcx_builder import tcx_document

pytestmark = pytest.mark.django_db


class TestTheSummary:
    def test_a_typical_run(self) -> None:
        parsed = parse_gpx(gpx_document())

        assert parsed.source == "gpx_file"
        assert parsed.sport == "running"
        assert parsed.source_sport == "running"
        assert parsed.start_time == START
        assert parsed.elapsed_seconds == 600
        assert parsed.manufacturer == "Test App"

    def test_the_distance_is_added_up_from_the_points(self) -> None:
        parsed = parse_gpx(gpx_document())  # 60 steps of 10 s at 3 m/s

        assert parsed.distance_m == pytest.approx(1800, rel=0.01)

    def test_the_heart_rate_is_the_mean_and_the_highest_of_the_points(self) -> None:
        parsed = parse_gpx(gpx_document(heart_rate=150))

        assert (parsed.avg_heart_rate, parsed.max_heart_rate) == (150, 150)

    def test_a_file_without_heart_rate_has_none(self) -> None:
        parsed = parse_gpx(gpx_document(heart_rate=None))

        assert (parsed.avg_heart_rate, parsed.max_heart_rate) == (None, None)

    def test_the_moving_time_is_not_known_and_not_guessed(self) -> None:
        parsed = parse_gpx(gpx_document())

        assert parsed.timer_seconds is None
        assert parsed.laps == ()
        assert parsed.avg_power_w is None
        assert parsed.total_ascent_m is None
        assert parsed.calories is None

    @pytest.mark.parametrize(
        ("kind", "sport"),
        [
            ("running", "running"),
            ("Run", "running"),
            ("VirtualRun", "running"),
            ("cycling", "cycling"),
            ("Ride", "cycling"),
            ("VirtualRide", "cycling"),
            ("swimming", "swimming"),
            ("hiking", "other"),
            ("", "other"),
            (None, "other"),
        ],
    )
    def test_the_sport_comes_from_the_type_of_the_track_if_it_has_one(
        self, kind: str | None, sport: str
    ) -> None:
        assert parse_gpx(gpx_document(track_type=kind)).sport == sport

    def test_several_segments_are_one_activity(self) -> None:
        parsed = parse_gpx(gpx_document(segments=3))

        assert parsed.elapsed_seconds == 600
        assert parsed.distance_m == pytest.approx(1800, rel=0.01)

    def test_a_pause_between_points_counts_for_the_duration(self) -> None:
        document = gpx_document(count=2, step=3600)

        assert parse_gpx(document).elapsed_seconds == 3600

    def test_a_missing_creator_is_an_empty_manufacturer(self) -> None:
        assert parse_gpx(gpx_document(creator=None)).manufacturer == ""

    def test_the_start_is_in_utc(self) -> None:
        document = gpx_document().replace(b"Z</time>", b"+02:00</time>")

        assert parse_gpx(document).start_time.utcoffset() == timedelta(0)

    def test_the_text_of_the_file_is_not_taken_over(self) -> None:
        parsed = parse_gpx(gpx_document(creator="x" * 500, track_type="y" * 500))

        assert len(parsed.manufacturer) <= 50
        assert len(parsed.source_sport) <= 50


class TestWhatIsRefused:
    def test_a_file_without_time_stamps(self) -> None:
        with pytest.raises(InvalidFileError, match="no track with time stamps"):
            parse_gpx(gpx_document(with_time=False))

    def test_a_track_of_one_point(self) -> None:
        with pytest.raises(InvalidFileError, match="time stamps"):
            parse_gpx(gpx_document(count=1))

    def test_a_file_without_a_track(self) -> None:
        document = b'<?xml version="1.0"?><gpx version="1.1"><wpt lat="1" lon="1"/></gpx>'

        with pytest.raises(InvalidFileError):
            parse_gpx(document)

    def test_xml_that_is_no_gpx(self) -> None:
        with pytest.raises(UnsupportedFileError, match="not a GPX"):
            parse_gpx(b"<?xml version='1.0'?><kml></kml>")

    def test_a_document_type_declaration(self) -> None:
        document = b'<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY x "y">]><gpx></gpx>'

        with pytest.raises(InvalidFileError, match="GPX file must not contain a document type"):
            parse_gpx(document)

    def test_xml_that_is_not_well_formed(self) -> None:
        with pytest.raises(InvalidFileError, match="GPX file is not well-formed"):
            parse_gpx(b"<gpx><trk>")

    def test_a_file_nested_too_deeply(self) -> None:
        document = b"<gpx>" + b"<a>" * 100 + b"</a>" * 100 + b"</gpx>"

        with pytest.raises(InvalidFileError, match="nested too deeply"):
            parse_gpx(document)

    def test_too_many_points(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("activities.parsing.gpx.MAX_TRACKPOINTS", 5)

        with pytest.raises(InvalidFileError, match="too much data"):
            parse_gpx(gpx_document(count=10))

    def test_a_message_holds_nothing_of_the_file(self) -> None:
        with pytest.raises(InvalidFileError) as raised:
            parse_gpx(gpx_document(with_time=False, creator="SECRET-CREATOR"))

        assert "SECRET" not in str(raised.value)

    def test_points_with_places_that_cannot_be_are_left_out_of_the_distance(self) -> None:
        document = gpx_document().replace(b'lon="13.4"', b'lon="999"', 3)

        parsed = parse_gpx(document)

        assert parsed.distance_m is not None
        assert parsed.distance_m < 1800


class TestTellingTheFormatsApart:
    def test_xml_with_a_gpx_root_is_read_as_gpx(self) -> None:
        assert parse_activity_file(gpx_document()).source == "gpx_file"

    def test_xml_with_a_tcx_root_is_still_read_as_tcx(self) -> None:
        assert parse_activity_file(tcx_document()).source == "tcx_file"

    def test_a_gpx_file_without_a_prolog_is_read(self) -> None:
        assert parse_activity_file(gpx_document(prolog="")).source == "gpx_file"

    def test_a_gpx_file_after_a_byte_order_mark_is_read(self) -> None:
        assert parse_activity_file(b"\xef\xbb\xbf" + gpx_document()).source == "gpx_file"

    def test_a_gpx_file_with_a_prefix_on_its_root_is_read(self) -> None:
        document = (
            gpx_document()
            .replace(b"<gpx ", b'<g:gpx xmlns:g="urn:test" ')
            .replace(b"</gpx>", b"</g:gpx>")
        )

        assert parse_activity_file(document).source == "gpx_file"

    def test_a_file_that_is_neither_is_refused_with_a_fixed_text(self) -> None:
        with pytest.raises(UnsupportedFileError, match="neither a FIT, a TCX nor a GPX"):
            parse_activity_file(b"hello")


class TestTheSeries:
    def test_the_points_with_their_time_distance_and_heart_rate(self) -> None:
        series = gpx_series(gpx_document())

        assert len(series) == 61
        assert series[0].seconds == 0
        assert series[-1].seconds == 600
        assert series[-1].distance == pytest.approx(1800, rel=0.01)
        assert {sample.heart_rate for sample in series} == {150}
        assert {sample.power for sample in series} == {None}

    def test_the_distance_only_grows(self) -> None:
        distances = [s.distance for s in gpx_series(gpx_document()) if s.distance is not None]

        assert distances == sorted(distances)

    def test_parse_series_reads_gpx_too(self) -> None:
        assert len(parse_series(gpx_document())) == 61

    def test_a_file_without_time_stamps_has_no_series(self) -> None:
        with pytest.raises(InvalidFileError):
            gpx_series(gpx_document(with_time=False))


class TestTheDistance:
    def test_a_degree_of_latitude_is_about_111_kilometres(self) -> None:
        assert distance_between((52.0, 13.0), (53.0, 13.0)) == pytest.approx(111_195, rel=0.001)

    def test_the_same_place_is_no_distance(self) -> None:
        assert distance_between((52.5, 13.4), (52.5, 13.4)) == 0

    def test_it_is_the_same_both_ways(self) -> None:
        a, b = (52.5, 13.4), (48.1, 11.6)

        assert distance_between(a, b) == pytest.approx(distance_between(b, a))


class TestImporting:
    @pytest.fixture
    def alice(self) -> User:
        return User.objects.create_user("alice@example.com")

    def test_a_gpx_file_is_imported_and_the_original_is_kept(self, alice: User) -> None:
        data = gpx_document()

        activity = import_activity(alice, data)

        assert (activity.source, activity.sport) == ("gpx_file", "running")
        assert activity.start_time == START
        assert ActivityFile.objects.get(activity=activity).read() == data

    def test_its_best_efforts_are_computed_from_the_series(self, alice: User) -> None:
        activity = import_activity(alice, gpx_document(count=361))  # an hour

        assert isinstance(activity.best_efforts, dict)
        assert activity.best_efforts.get("speed")

    def test_a_compressed_gpx_file_is_imported_too(self, alice: User) -> None:
        activity = import_activity(alice, gzip.compress(gpx_document()))

        assert activity.source == "gpx_file"

    def test_the_same_file_twice_is_a_duplicate(self, alice: User) -> None:
        import_activity(alice, gpx_document())

        with pytest.raises(DuplicateActivityError):
            import_activity(alice, gpx_document())

        assert Activity.objects.count() == 1

    def test_the_same_run_from_a_fit_file_is_a_duplicate(self, alice: User) -> None:
        from .fit_builder import activity_file

        fit = import_activity(alice, activity_file(start=START))
        duration = fit.timer_seconds or 0
        document = gpx_document(start=START, count=int(duration // 10) + 1)

        with pytest.raises(DuplicateActivityError):
            import_activity(alice, document)

    def test_another_user_is_not_a_duplicate(self, alice: User) -> None:
        bob = User.objects.create_user("bob@example.com")
        import_activity(alice, gpx_document())

        assert import_activity(bob, gpx_document()).owner == bob
