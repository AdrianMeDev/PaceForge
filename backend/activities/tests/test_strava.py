import csv
import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from activities.management.commands import import_strava
from activities.strava import (
    _MAX_FIELD,
    MAX_ROWS,
    SPORTS,
    StravaListError,
    StravaRow,
    _number,
    read_activity_list,
    sport_of,
)

HEADER = [
    "Activity ID",
    "Activity Date",
    "Activity Name",
    "Activity Type",
    "Activity Description",
    "Elapsed Time",
    "Distance",
    "Max Heart Rate",
    "Relative Effort",
    "Commute",
    "Activity Private Note",
    "Activity Gear",
    "Filename",
    "Athlete Weight",
    "Elapsed Time",
    "Moving Time",
    "Distance",
    "Max Speed",
]


def line(
    activity_id: str = "1001",
    date: str = "Nov 14, 2026, 7:30:12 AM",
    kind: str = "Run",
    elapsed: str = "3600",
    km: str = "10.5",
    filename: str = "activities/1001.fit.gz",
    metres: str = "10500.2",
    name: str = "Morning Run",
) -> list[str]:
    return [
        activity_id,
        date,
        name,
        kind,
        "",
        elapsed,
        km,
        "170.0",
        "55",
        "false",
        "",
        "",
        filename,
        "70.0",
        elapsed,
        "3500",
        metres,
        "3.2",
    ]


def export(*lines: list[str], header: list[str] = HEADER, bom: bool = False) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(lines)
    return (("﻿" if bom else "") + out.getvalue()).encode()


class TestReadingALine:
    def test_a_typical_line(self) -> None:
        result = read_activity_list(export(line()))

        assert result.unreadable == 0
        (row,) = result.rows
        assert row.activity_id == "1001"
        assert row.start == datetime(2026, 11, 14, 7, 30, 12, tzinfo=UTC)
        assert (row.strava_type, row.sport) == ("Run", "running")
        assert row.elapsed_seconds == 3600
        assert row.filename == "activities/1001.fit.gz"

    def test_the_distance_is_the_one_in_metres_where_there_are_two(self) -> None:
        (row,) = read_activity_list(export(line(km="10.5", metres="10500.2"))).rows

        assert row.distance_m == pytest.approx(10500.2)

    def test_the_only_distance_is_kilometres(self) -> None:
        header = [name for i, name in enumerate(HEADER) if i != 16]
        fields = line(km="10.5")
        del fields[16]

        (row,) = read_activity_list(export(fields, header=header)).rows

        assert row.distance_m == pytest.approx(10500)

    def test_a_line_without_a_file(self) -> None:
        (row,) = read_activity_list(export(line(filename=""))).rows

        assert row.filename is None

    def test_a_missing_number_is_not_a_reason_to_leave_the_line_out(self) -> None:
        (row,) = read_activity_list(export(line(elapsed="", metres="", km=""))).rows

        assert (row.elapsed_seconds, row.distance_m) == (None, None)

    @pytest.mark.parametrize("value", ["nan", "inf", "-5", "x", "99999999999"])
    def test_an_impossible_number_is_dropped(self, value: str) -> None:
        (row,) = read_activity_list(export(line(elapsed=value, metres=value))).rows

        assert (row.elapsed_seconds, row.distance_m) == (None, None)

    def test_a_byte_order_mark_is_ignored(self) -> None:
        assert len(read_activity_list(export(line(), bom=True)).rows) == 1

    def test_several_lines_in_the_order_of_the_file(self) -> None:
        result = read_activity_list(export(line("1"), line("2"), line("3")))

        assert [row.activity_id for row in result.rows] == ["1", "2", "3"]

    def test_the_name_and_the_description_are_not_read(self) -> None:
        result = read_activity_list(export(line(name="SECRET NAME")))

        assert "SECRET" not in repr(result)

    def test_a_name_with_commas_and_line_breaks_does_not_shift_the_columns(self) -> None:
        (row,) = read_activity_list(export(line(name='Run, "fast"\nsecond line'))).rows

        assert row.activity_id == "1001"
        assert row.filename == "activities/1001.fit.gz"

    def test_empty_lines_are_not_activities(self) -> None:
        data = export(line("1")) + b"\n\n" + b",,,\n"

        result = read_activity_list(data)

        assert (len(result.rows), result.unreadable) == (1, 0)


GERMAN_HEADER = [
    "Aktivitäts-ID",
    "Aktivitätsdatum",
    "Name der Aktivität",
    "Aktivitätsart",
    "Aktivitätsbeschreibung",
    "Verstrichene Zeit",
    "Distanz",
    "Max. Herzfrequenz",
    "Relative Leistung",
    "Pendeln",
    "Hinweis zur Privatsphäre für Aktivitäten",
    "Aktivitätsausrüstung",
    "Dateiname",
    "Sportlergewicht",
    "Verstrichene Zeit",
    "Bewegungszeit",
    "Distanz",
    "Höchstgeschw.",
]


class TestAGermanExport:
    """An archive requested in German: the names, the dates and the decimal comma."""

    def read(self, **fields: str) -> list[StravaRow]:
        return list(read_activity_list(export(line(**fields), header=GERMAN_HEADER)).rows)

    def test_a_typical_line(self) -> None:
        (row,) = self.read(
            activity_id="1001",
            date="12.11.2026, 17:14:38",
            kind="Lauf",
            elapsed="2940",
            km="25,95",
            metres="25951.7",
            filename="activities/1001.fit.gz",
        )

        assert row.start == datetime(2026, 11, 12, 17, 14, 38, tzinfo=UTC)
        assert (row.strava_type, row.sport) == ("Lauf", "running")
        assert row.elapsed_seconds == 2940
        assert row.distance_m == pytest.approx(25951.7)
        assert row.filename == "activities/1001.fit.gz"

    def test_the_distance_with_a_decimal_comma_is_kilometres_where_it_is_the_only_one(self) -> None:
        header = [
            "Aktivitäts-ID",
            "Aktivitätsdatum",
            "Name",
            "Aktivitätsart",
            "x",
            "Zeit",
            "Distanz",
        ]
        header[5] = "Verstrichene Zeit"

        (row,) = read_activity_list(export(line(km="25,95")[:7], header=header)).rows

        assert row.distance_m == pytest.approx(25950)

    @pytest.mark.parametrize(
        ("kind", "sport"),
        [
            ("Lauf", "running"),
            ("Radfahrt", "cycling"),
            ("Virtuelle Radfahrt", "cycling"),
            ("Wandern", "other"),
            ("Spaziergang", "other"),
            ("Training", "other"),
        ],
    )
    def test_the_types_of_the_real_export(self, kind: str, sport: str) -> None:
        assert sport_of(kind) == sport

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("01.01.2026, 00:00:00", datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)),
            ("31.12.2025, 23:59:59", datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)),
            ("5.3.2026, 9:05:01", datetime(2026, 3, 5, 9, 5, 1, tzinfo=UTC)),
        ],
    )
    def test_the_dates(self, text: str, expected: datetime) -> None:
        (row,) = self.read(date=text)

        assert row.start == expected

    @pytest.mark.parametrize(
        "text", ["32.01.2026, 00:00:00", "30.02.2026, 00:00:00", "1.1.2026", "01.01.2026, 25:00:00"]
    )
    def test_a_date_that_does_not_exist_makes_the_line_unreadable(self, text: str) -> None:
        result = read_activity_list(export(line(date=text), header=GERMAN_HEADER))

        assert (len(result.rows), result.unreadable) == (0, 1)

    @pytest.mark.parametrize(
        ("text", "number"),
        [("25,95", 25.95), ("25951.7", 25951.7), ("1.234,5", 1234.5), ("0", 0.0), ("1,5", 1.5)],
    )
    def test_the_numbers(self, text: str, number: float) -> None:
        assert _number(text) == pytest.approx(number)

    @pytest.mark.parametrize("text", ["", "x", "1,2,3", ","])
    def test_what_is_no_number(self, text: str) -> None:
        assert _number(text) is None


class TestTheStart:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Jan 1, 2026, 12:00:00 AM", datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)),
            ("Jan 1, 2026, 12:30:00 PM", datetime(2026, 1, 1, 12, 30, 0, tzinfo=UTC)),
            ("Dec 31, 2025, 11:59:59 PM", datetime(2025, 12, 31, 23, 59, 59, tzinfo=UTC)),
            ("Mar 5, 2026, 9:05:01 AM", datetime(2026, 3, 5, 9, 5, 1, tzinfo=UTC)),
        ],
    )
    def test_the_way_strava_writes_it(self, text: str, expected: datetime) -> None:
        (row,) = read_activity_list(export(line(date=text))).rows

        assert row.start == expected

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "14/11/2026 07:30",
            "14 Nov 2026 at 07:30:12",
            "Nov 14, 2026, 7:30:12",
            "Nov 14, 2026, 13:30:12 PM",
            "Nov 14, 2026, 0:30:12 AM",
            "Nov 32, 2026, 7:30:12 AM",
            "Feb 30, 2026, 7:30:12 AM",
            "Foo 14, 2026, 7:30:12 AM",
            "Nov 14, 2026, 7:30 AM",
            "2026-11-14T07:30:12Z",
        ],
    )
    def test_another_way_makes_the_line_unreadable(self, text: str) -> None:
        result = read_activity_list(export(line("1"), line("2", date=text)))

        assert [row.activity_id for row in result.rows] == ["1"]
        assert result.unreadable == 1


class TestWhatMakesALineUnreadable:
    @pytest.mark.parametrize("activity_id", ["", "abc", "12 3", "-5"])
    def test_an_id_that_is_no_number(self, activity_id: str) -> None:
        result = read_activity_list(export(line(activity_id=activity_id)))

        assert (len(result.rows), result.unreadable) == (0, 1)

    def test_no_type(self) -> None:
        assert read_activity_list(export(line(kind=""))).unreadable == 1

    def test_a_line_that_is_too_short(self) -> None:
        data = export(line("1")) + b"2,Nov 14, 2026\n"

        result = read_activity_list(data)

        assert (len(result.rows), result.unreadable) == (1, 1)

    def test_a_field_that_is_much_too_large(self) -> None:
        data = export(line("1")) + b"2,Nov 14, 2026, 7:30:12 AM," + b"x" * 200_000 + b",Run\n"

        result = read_activity_list(data)

        assert [row.activity_id for row in result.rows] == ["1"]
        assert result.unreadable == 1

    def test_a_filename_at_the_limit_is_accepted(self) -> None:
        name = "a" * _MAX_FIELD

        result = read_activity_list(export(line(filename=name)))

        assert result.unreadable == 0
        (row,) = result.rows
        assert row.filename == name

    def test_an_overlong_filename_is_unreadable(self) -> None:
        name = "a" * (_MAX_FIELD + 1)

        result = read_activity_list(export(line(filename=name)))

        assert (len(result.rows), result.unreadable) == (0, 1)

    def test_the_count_is_exact(self) -> None:
        result = read_activity_list(
            export(line("1"), line("x"), line("2", kind=""), line("3", date="?"), line("4"))
        )

        assert (len(result.rows), result.unreadable) == (2, 3)


class TestWhatMakesTheListUnreadable:
    def test_no_text(self) -> None:
        with pytest.raises(StravaListError, match="not UTF-8"):
            read_activity_list(b"\xff\xfeA\x00")

    def test_empty(self) -> None:
        with pytest.raises(StravaListError, match="empty"):
            read_activity_list(b"")

    def test_a_list_in_a_language_that_is_not_read(self) -> None:
        french = ["ID de l'activité", "Date de l'activité", "Nom", "Type d'activité"]

        with pytest.raises(StravaListError, match="in English or German"):
            read_activity_list(export(header=french))

    @pytest.mark.parametrize("missing", ["Activity ID", "Activity Date", "Activity Type"])
    def test_a_column_that_is_needed_is_missing(self, missing: str) -> None:
        header = [name for name in HEADER if name != missing]

        with pytest.raises(StravaListError, match="columns of a Strava export"):
            read_activity_list(export(header=header))

    def test_a_message_holds_nothing_of_the_file(self) -> None:
        with pytest.raises(StravaListError) as raised:
            read_activity_list(export(header=["SECRET-COLUMN"]))

        assert "SECRET" not in str(raised.value)

    def test_too_many_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("activities.strava.MAX_ROWS", 3)

        with pytest.raises(StravaListError, match="too many lines"):
            read_activity_list(export(*[line(str(i)) for i in range(1, 6)]))

    def test_the_limit_is_a_sensible_one(self) -> None:
        assert 10_000 <= MAX_ROWS <= 1_000_000


class TestTheSports:
    @pytest.mark.parametrize(
        ("kind", "sport"),
        [
            ("Run", "running"),
            ("Trail Run", "running"),
            ("Virtual Run", "running"),
            ("Ride", "cycling"),
            ("Virtual Ride", "cycling"),
            ("E-Bike Ride", "cycling"),
            ("Mountain Bike Ride", "cycling"),
            ("Gravel Ride", "cycling"),
            ("Swim", "swimming"),
            ("Weight Training", "strength"),
            ("Walk", "other"),
            ("Hike", "other"),
            ("Yoga", "other"),
            ("Workout", "other"),
            ("Something New", "other"),
            ("run", "other"),
        ],
    )
    def test_the_sport_of_a_type(self, kind: str, sport: str) -> None:
        assert sport_of(kind) == sport

    def test_every_sport_of_the_table_is_one_of_the_activity(self) -> None:
        from activities.models import Activity

        assert set(SPORTS.values()) <= set(Activity.Sport.values)


class TestTheReadme:
    """The README says what the import takes and how: it must say what the code does."""

    ROOT = Path(__file__).resolve().parents[3]
    TEXT = " ".join((ROOT / "README.md").read_text().split())

    def test_it_names_the_command_and_its_options(self) -> None:
        assert "manage.py import_strava" in self.TEXT
        assert "--user you@example.com" in self.TEXT
        assert Path(import_strava.__file__).name == "import_strava.py"

    def test_it_names_the_columns_the_code_reads(self) -> None:
        for column in ("Activity ID", "Activity Date", "Activity Type", "Elapsed Time", "Distance"):
            assert f"*{column}*" in self.TEXT, column
        assert "Filename" in self.TEXT

    def test_the_types_it_lists_are_mapped_as_it_says(self) -> None:
        claimed = {
            "running": ["Run", "Trail Run", "Virtual Run"],
            "cycling": ["Ride", "Virtual Ride", "E-Bike Ride", "Mountain Bike Ride", "Gravel Ride"],
            "swimming": ["Swim"],
            "strength": ["Weight Training"],
        }
        for sport, types in claimed.items():
            for strava_type in types:
                assert sport_of(strava_type) == sport, strava_type
                assert strava_type in self.TEXT, strava_type
        for strava_type in ("Walk", "Hike", "Yoga"):
            assert sport_of(strava_type) == "other"

    def test_it_gives_the_date_as_strava_writes_it(self) -> None:
        assert "`Nov 14, 2026, 7:30:12 AM`" in self.TEXT
        (row,) = read_activity_list(export(line(date="Nov 14, 2026, 7:30:12 AM"))).rows
        assert row.start == datetime(2026, 11, 14, 7, 30, 12, tzinfo=UTC)

    def test_the_limit_of_the_page_is_the_one_in_the_settings(self) -> None:
        from rest_framework.settings import api_settings

        assert api_settings.DEFAULT_THROTTLE_RATES["activity_import"] == "30/min"
        assert "(30 a minute)" in self.TEXT
