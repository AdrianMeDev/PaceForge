import gzip
import io
import zipfile
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User
from activities.models import Activity, ActivityFile
from activities.parsing import is_compressed, parse_activity_file, unpack
from activities.services import import_activity
from activities.strava import _MAX_FIELD, ExportError, ImportCounts, import_export

from .fit_builder import activity_file
from .gpx_builder import gpx_document
from .tcx_builder import tcx_document
from .test_strava import export as csv_export
from .test_strava import line

pytestmark = pytest.mark.django_db

DAY = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


def day(n: int) -> datetime:
    return DAY + timedelta(days=n)


def when(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    marker = "AM" if moment.hour < 12 else "PM"
    return f"{moment:%b} {moment.day}, {moment.year}, {hour}:{moment:%M:%S} {marker}"


def archive(
    members: dict[str, bytes], rows: list[list[str]] | None = None, *, listing: bytes | None = None
) -> io.BytesIO:
    """A Strava export: ``members`` by their names and ``activities.csv`` from ``rows``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
        if listing is not None:
            zf.writestr("activities.csv", listing)
        elif rows is not None:
            zf.writestr("activities.csv", csv_export(*rows))
    buffer.seek(0)
    return buffer


def row(
    n: int, filename: str, *, kind: str = "Run", elapsed: str = "600", metres: str = "1800"
) -> list[str]:
    kilometres = str(float(metres) / 1000) if metres else ""
    return line(str(1000 + n), when(day(n)), kind, elapsed, kilometres, filename, metres)


class TestRecordings:
    def test_the_recordings_of_every_kind_are_imported(self, alice: User) -> None:
        source = archive(
            {
                "activities/1.fit": activity_file(start=day(0)),
                "activities/2.fit.gz": gzip.compress(activity_file(start=day(1))),
                "activities/3.tcx.gz": gzip.compress(
                    tcx_document(laps=[{"start": day(2), "seconds": 1800, "distance": 5000}])
                ),
                "activities/4.gpx": gpx_document(start=day(3)),
                "activities/5.gpx.gz": gzip.compress(gpx_document(start=day(4))),
            },
            [
                row(n, f"activities/{n + 1}.{ext}")
                for n, ext in enumerate(["fit", "fit.gz", "tcx.gz", "gpx", "gpx.gz"])
            ],
        )

        counts = import_export(alice, source)

        assert (counts.imported, counts.total) == (5, 5)
        assert sorted(Activity.objects.values_list("source", flat=True)) == [
            "fit_file",
            "fit_file",
            "gpx_file",
            "gpx_file",
            "tcx_file",
        ]
        assert ActivityFile.objects.count() == 5

    def test_the_sport_of_the_list_is_used_where_the_file_does_not_know_it(
        self, alice: User
    ) -> None:
        source = archive(
            {
                "activities/1.gpx": gpx_document(start=day(0), track_type=None),
                "activities/2.gpx": gpx_document(start=day(1), track_type=None),
            },
            [
                row(0, "activities/1.gpx", kind="Run"),
                row(1, "activities/2.gpx", kind="Walk"),
            ],
        )

        import_export(alice, source)

        sports = dict(Activity.objects.values_list("start_time", "sport"))
        assert sports == {day(0): "running", day(1): "other"}

    def test_the_sport_of_the_file_is_not_overruled_by_the_list(self, alice: User) -> None:
        source = archive(
            {"activities/1.fit": activity_file(start=day(0))},  # a run
            [row(0, "activities/1.fit", kind="Ride")],
        )

        import_export(alice, source)

        assert Activity.objects.get().sport == "running"

    def test_a_second_run_adds_nothing(self, alice: User) -> None:
        members = {
            "activities/1.fit": activity_file(start=day(0)),
            "activities/2.gpx": gpx_document(start=day(1)),
        }
        rows = [row(0, "activities/1.fit"), row(1, "activities/2.gpx", elapsed="600")]
        rows.append(row(2, "", kind="Weight Training", elapsed="2700", metres=""))
        import_export(alice, archive(members, rows))
        before = Activity.objects.count()

        counts = import_export(alice, archive(members, rows))

        assert Activity.objects.count() == before == 3
        assert (counts.imported, counts.entered, counts.duplicates) == (0, 0, 3)

    def test_a_session_the_account_has_from_somewhere_else_is_skipped(self, alice: User) -> None:
        import_activity(alice, activity_file(start=day(0)))  # an upload of the same run
        source = archive(
            {"activities/1.fit.gz": gzip.compress(activity_file(start=day(0)))},
            [row(0, "activities/1.fit.gz")],
        )

        counts = import_export(alice, source)

        assert (counts.imported, counts.duplicates) == (0, 1)
        assert Activity.objects.count() == 1

    def test_the_activities_of_another_account_do_not_count(self, alice: User) -> None:
        bob = User.objects.create_user("bob@example.com")
        members = {"activities/1.fit": activity_file(start=day(0))}
        rows = [row(0, "activities/1.fit")]
        import_export(alice, archive(members, rows))

        counts = import_export(bob, archive(members, rows))

        assert counts.imported == 1
        assert Activity.objects.filter(owner=bob).count() == 1


class TestRepeatedMembers:
    @pytest.mark.parametrize(
        ("case", "expected", "opens", "unpacks", "parses"),
        [
            ("new", ImportCounts(imported=1, duplicates=39), 1, 1, 1),
            ("existing", ImportCounts(duplicates=40), 1, 1, 1),
            ("corrupt_recording", ImportCounts(unreadable=40), 1, 1, 1),
            ("corrupt_gzip", ImportCounts(unreadable=40), 1, 1, 0),
            ("oversized_gzip", ImportCounts(unreadable=40), 1, 1, 0),
            ("oversized_member", ImportCounts(unreadable=40), 0, 0, 0),
            ("missing", ImportCounts(missing=40), 0, 0, 0),
        ],
    )
    def test_each_member_is_attempted_once(
        self,
        alice: User,
        settings: object,
        case: str,
        expected: ImportCounts,
        opens: int,
        unpacks: int,
        parses: int,
    ) -> None:
        settings.ACTIVITY_UPLOAD_MAX_BYTES = 5_000  # type: ignore[attr-defined]
        recording = activity_file(start=day(0))
        if case == "existing":
            import_activity(alice, recording)
        data = {
            "corrupt_recording": gzip.compress(b"not a recording"),
            "corrupt_gzip": b"\x1f\x8bbroken",
            "oversized_gzip": gzip.compress(b"x" * 20_000),
            "oversized_member": b"x" * 20_000,
        }.get(case, gzip.compress(recording))
        filename = "activities/repeated.fit.gz"
        source = archive(
            {} if case == "missing" else {filename: data},
            [row(n, filename) for n in range(40)],
        )
        progress: list[tuple[int, int]] = []

        with (
            patch("activities.strava.MAX_PARSED_RECORDINGS", 1),
            patch("activities.strava.MAX_TOTAL_UNPACKED_BYTES", 20_000),
            patch.object(
                zipfile.ZipFile, "getinfo", autospec=True, side_effect=zipfile.ZipFile.getinfo
            ) as lookup,
            patch.object(
                zipfile.ZipFile, "open", autospec=True, side_effect=zipfile.ZipFile.open
            ) as opened,
            patch.object(
                zipfile.ZipExtFile, "read", autospec=True, side_effect=zipfile.ZipExtFile.read
            ) as read,
            patch("activities.strava.unpack", wraps=unpack) as unpacked,
            patch("activities.services.parse_activity_file", wraps=parse_activity_file) as parsed,
        ):
            counts = import_export(
                alice, source, progress=lambda done, total: progress.append((done, total))
            )

        assert counts == expected
        assert counts.total == 40
        assert sum(call.args[1] == filename for call in lookup.call_args_list) == 1
        assert sum(call.args[1].filename == filename for call in opened.call_args_list) == opens
        assert sum(call.args[0].name == filename for call in read.call_args_list) == opens
        assert unpacked.call_count == unpacks
        assert parsed.call_count == parses
        assert progress == [(n, 40) for n in range(1, 41)]
        assert Activity.objects.count() == (1 if case in ("new", "existing") else 0)
        assert ActivityFile.objects.count() == Activity.objects.count()

    def test_cached_outcomes_do_not_survive_an_import(self, alice: User) -> None:
        filename = "activities/repeated.fit.gz"
        rows = [row(n, filename) for n in range(40)]

        assert import_export(alice, archive({}, rows)) == ImportCounts(missing=40)
        members = {filename: gzip.compress(activity_file(start=day(0)))}
        assert import_export(alice, archive(members, rows)) == ImportCounts(
            imported=1, duplicates=39
        )
        assert import_export(alice, archive(members, rows)) == ImportCounts(duplicates=40)


class TestWorkBudgets:
    @pytest.mark.parametrize("compressed", [False, True])
    def test_total_output_across_distinct_members_is_bounded(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, compressed: bool
    ) -> None:
        data = b"not a recording" * 100
        packed = gzip.compress(data) if compressed else data
        names = [f"activities/{n}.fit" + (".gz" if compressed else "") for n in range(100)]
        rows = [row(n, name) for n, name in enumerate(names)]
        listing = csv_export(*rows)
        per_file = len(packed) + (len(data) if compressed else 0)
        cap = len(listing) + 3 * per_file + per_file // 2
        monkeypatch.setattr("activities.strava.MAX_TOTAL_UNPACKED_BYTES", cap)
        source = archive(dict.fromkeys(names, packed), listing=listing)
        produced = 0
        original_read = zipfile.ZipExtFile.read
        original_decompressobj = zlib.decompressobj

        def read(member: zipfile.ZipExtFile, size: int = -1) -> bytes:
            nonlocal produced
            result = original_read(member, size)
            produced += len(result)
            return result

        def decompressobj(window: int) -> Mock:
            real = original_decompressobj(window)
            tracked = Mock(wraps=real)

            def decompress(data: bytes, max_length: int) -> bytes:
                nonlocal produced
                result = real.decompress(data, max_length)
                produced += len(result)
                tracked.eof = real.eof
                return result

            def flush() -> bytes:
                nonlocal produced
                result = real.flush()
                produced += len(result)
                return result

            tracked.decompress.side_effect = decompress
            tracked.flush.side_effect = flush
            return tracked

        def tracked_unpack(data: bytes, limit: int) -> bytes:
            with patch("activities.parsing.compressed.zlib.decompressobj", decompressobj):
                return unpack(data, limit)

        with (
            patch.object(zipfile.ZipExtFile, "read", read),
            patch("activities.strava.unpack", tracked_unpack),
            patch("activities.services.parse_activity_file", wraps=parse_activity_file) as parsed,
        ):
            with pytest.raises(
                ExportError, match=r"^The archive exceeds the bulk import work limit\.$"
            ):
                import_export(alice, source)

        assert produced == cap + 1  # Only the final exhaustion probe exceeds the budget.
        assert parsed.call_count == 3
        assert not Activity.objects.exists()

    @pytest.mark.parametrize("compressed", [False, True])
    @pytest.mark.parametrize("valid", [False, True])
    def test_distinct_parse_attempts_are_bounded_and_saved_activities_refresh(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, compressed: bool, valid: bool
    ) -> None:
        monkeypatch.setattr("activities.strava.MAX_PARSED_RECORDINGS", 3)
        names = [f"activities/{n}.fit" + (".gz" if compressed else "") for n in range(100)]
        members = {}
        for n, name in enumerate(names):
            data = activity_file(start=day(n)) if valid else b"not a recording"
            members[name] = gzip.compress(data) if compressed else data
        calls: list[User] = []
        monkeypatch.setattr("activities.strava.refresh_estimates_safely", calls.append)
        with patch("activities.services.parse_activity_file", wraps=parse_activity_file) as parsed:
            with pytest.raises(ExportError, match="work limit"):
                import_export(
                    alice, archive(members, [row(n, name) for n, name in enumerate(names)])
                )

        assert parsed.call_count == 3
        assert Activity.objects.count() == (3 if valid else 0)
        assert calls == ([alice] if valid else [])

    def test_the_list_uses_the_same_byte_budget(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        listing = csv_export(row(0, ""))
        monkeypatch.setattr("activities.strava.MAX_TOTAL_UNPACKED_BYTES", len(listing) - 1)
        with pytest.raises(ExportError, match="work limit"):
            import_export(alice, archive({}, listing=listing))
        assert not Activity.objects.exists()

    @pytest.mark.parametrize("compressed", [False, True])
    def test_exact_byte_and_parse_limits_are_allowed(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, compressed: bool
    ) -> None:
        data = activity_file(start=day(0))
        packed = gzip.compress(data) if compressed else data
        filename = "activities/1.fit.gz" if compressed else "activities/1.fit"
        rows = [row(n, filename) for n in range(40)]
        cap = len(csv_export(*rows)) + len(packed) + (len(data) if compressed else 0)
        monkeypatch.setattr("activities.strava.MAX_TOTAL_UNPACKED_BYTES", cap)
        monkeypatch.setattr("activities.strava.MAX_PARSED_RECORDINGS", 1)

        assert import_export(alice, archive({filename: packed}, rows)) == ImportCounts(
            imported=1, duplicates=39
        )

    @pytest.mark.parametrize("compressed", [False, True])
    def test_individual_oversized_files_remain_unreadable_within_budget(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, compressed: bool
    ) -> None:
        monkeypatch.setattr("django.conf.settings.ACTIVITY_UPLOAD_MAX_BYTES", 5_000)
        monkeypatch.setattr("activities.strava.MAX_TOTAL_UNPACKED_BYTES", 20_000)
        data = b"x" * 20_000
        filename = "activities/large.fit.gz" if compressed else "activities/large.fit"
        source = archive(
            {filename: gzip.compress(data) if compressed else data}, [row(0, filename)]
        )
        with patch("activities.services.parse_activity_file", wraps=parse_activity_file) as parsed:
            assert import_export(alice, source) == ImportCounts(unreadable=1)
        parsed.assert_not_called()

    @pytest.mark.parametrize("broken", [False, True])
    def test_failed_gzip_attempts_also_consume_the_shared_budget(
        self, alice: User, monkeypatch: pytest.MonkeyPatch, broken: bool
    ) -> None:
        monkeypatch.setattr("django.conf.settings.ACTIVITY_UPLOAD_MAX_BYTES", 5_000)
        packed = b"\x1f\x8bbroken" if broken else gzip.compress(b"x" * 20_000)
        names = [f"activities/{n}.fit.gz" for n in range(100)]
        rows = [row(n, name) for n, name in enumerate(names)]
        cap = len(csv_export(*rows)) + 2 * (len(packed) + 5_001) + len(packed) + 2_500
        monkeypatch.setattr("activities.strava.MAX_TOTAL_UNPACKED_BYTES", cap)
        with (
            patch("activities.strava.unpack", wraps=unpack) as unpacked,
            patch("activities.services.parse_activity_file", wraps=parse_activity_file) as parsed,
        ):
            with pytest.raises(ExportError, match="work limit"):
                import_export(alice, archive(dict.fromkeys(names, packed), rows))
        assert unpacked.call_count == 3
        assert unpacked.call_args.args[1] == 2_500
        parsed.assert_not_called()

    def test_manual_activities_refresh_when_a_later_recording_exhausts_the_budget(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("activities.strava.MAX_PARSED_RECORDINGS", 0)
        calls: list[User] = []
        monkeypatch.setattr("activities.strava.refresh_estimates_safely", calls.append)
        source = archive(
            {"activities/1.fit": activity_file(start=day(1))},
            [row(0, ""), row(1, "activities/1.fit")],
        )
        with pytest.raises(ExportError, match="work limit"):
            import_export(alice, source)
        assert Activity.objects.count() == 1
        assert Activity.objects.get().source == Activity.Source.MANUAL
        assert calls == [alice]

    def test_nested_gzip_is_refused_before_import_activity_can_unpack_it(self, alice: User) -> None:
        nested = gzip.compress(gzip.compress(activity_file(start=day(0))))
        source = archive({"activities/nested.fit.gz": nested}, [row(0, "activities/nested.fit.gz")])
        with (
            patch("activities.strava.unpack", wraps=unpack) as unpacked,
            patch("activities.services.unpack", wraps=unpack) as service_unpack,
            patch("activities.services.parse_activity_file", wraps=parse_activity_file) as parsed,
        ):
            assert import_export(alice, source) == ImportCounts(unreadable=1)
        assert unpacked.call_count == 1
        service_unpack.assert_not_called()
        parsed.assert_not_called()

    def test_import_activity_receives_only_plain_data(self, alice: User) -> None:
        data = gzip.compress(activity_file(start=day(0)))
        with patch("activities.services.unpack", wraps=unpack) as service_unpack:
            import_export(
                alice, archive({"activities/1.fit.gz": data}, [row(0, "activities/1.fit.gz")])
            )
        assert service_unpack.call_count == 1
        assert not is_compressed(service_unpack.call_args.args[0])


class TestLinesWithoutARecording:
    def test_a_line_alone_is_entered_like_a_session_by_hand(self, alice: User) -> None:
        source = archive({}, [row(0, "", kind="Weight Training", elapsed="2700", metres="")])

        counts = import_export(alice, source)

        assert (counts.entered, counts.imported) == (1, 0)
        activity = Activity.objects.get()
        assert (activity.source, activity.sport) == ("manual", "strength")
        assert activity.start_time == day(0)
        assert activity.timer_seconds == 45 * 60
        assert activity.distance_m is None
        assert not ActivityFile.objects.exists()

    def test_the_distance_is_taken_over(self, alice: User) -> None:
        source = archive({}, [row(0, "", kind="Ride", elapsed="3600", metres="25400")])

        import_export(alice, source)

        assert Activity.objects.get().distance_m == pytest.approx(25400)

    @pytest.mark.parametrize("elapsed", ["", "0", "20", "x", "100000"])
    def test_a_line_with_no_usable_duration_is_not_entered(self, alice: User, elapsed: str) -> None:
        counts = import_export(alice, archive({}, [row(0, "", elapsed=elapsed, metres="")]))

        assert (counts.entered, counts.unreadable) == (0, 1)
        assert Activity.objects.count() == 0

    def test_a_line_from_before_the_earliest_date_is_not_entered(self, alice: User) -> None:
        old = line("7", "Jan 1, 1999, 7:00:00 AM", "Run", "600", "1", "", "1000")

        counts = import_export(alice, archive({}, [old]))

        assert (counts.entered, counts.unreadable) == (0, 1)


class TestWhatCannotBeImported:
    def test_a_recording_that_is_not_in_the_export_is_counted(self, alice: User) -> None:
        counts = import_export(alice, archive({}, [row(0, "activities/gone.fit")]))

        assert (counts.missing, counts.imported) == (1, 0)

    def test_a_name_that_leads_out_of_the_export_is_just_missing(self, alice: User) -> None:
        source = archive({"x.fit": activity_file()}, [row(0, "../x.fit"), row(1, "/etc/passwd")])

        counts = import_export(alice, source)

        assert (counts.missing, counts.imported) == (2, 0)

    def test_a_recording_that_cannot_be_read_does_not_stop_the_others(self, alice: User) -> None:
        source = archive(
            {
                "activities/1.fit": b"this is no recording",
                "activities/2.fit": activity_file(start=day(1)),
                "activities/3.fit.gz": b"\x1f\x8bbroken",
            },
            [row(n, f"activities/{n + 1}.{e}") for n, e in enumerate(["fit", "fit", "fit.gz"])],
        )

        counts = import_export(alice, source)

        assert (counts.imported, counts.unreadable) == (1, 2)

    def test_a_recording_that_is_too_large_is_skipped_also_when_it_lies(
        self, alice: User, settings: object
    ) -> None:
        settings.ACTIVITY_UPLOAD_MAX_BYTES = 5_000  # type: ignore[attr-defined]
        bomb = gzip.compress(b"\x00" * 5_000_000)  # a few kilobytes that unpack to megabytes
        big = b"x" * 20_000
        source = archive(
            {"activities/1.fit.gz": bomb, "activities/2.fit": big},
            [row(0, "activities/1.fit.gz"), row(1, "activities/2.fit")],
        )

        counts = import_export(alice, source)

        assert (counts.imported, counts.unreadable) == (0, 2)
        assert Activity.objects.count() == 0

    def test_a_line_of_the_list_that_cannot_be_read_is_counted(self, alice: User) -> None:
        bad = line("x", "not a date", "Run", "600", "1", "", "1000")
        source = archive(
            {"activities/1.fit": activity_file(start=day(0))}, [bad, row(0, "activities/1.fit")]
        )

        counts = import_export(alice, source)

        assert (counts.imported, counts.lines_unreadable) == (1, 1)

    def test_an_overlong_filename_is_unreadable_and_not_entered(self, alice: User) -> None:
        overlong = "a" * (_MAX_FIELD + 1)
        source = archive({}, [row(0, overlong, kind="Run", elapsed="600", metres="1800")])

        counts = import_export(alice, source)

        assert (counts.lines_unreadable, counts.entered) == (1, 0)
        assert Activity.objects.count() == 0

    def test_a_member_of_the_archive_that_the_list_does_not_name_is_ignored(
        self, alice: User
    ) -> None:
        source = archive({"activities/1.fit": activity_file(start=day(0))}, [])

        counts = import_export(alice, source)

        assert counts.total == 0
        assert Activity.objects.count() == 0

    def test_the_counts_add_up(self, alice: User) -> None:
        source = archive(
            {"activities/1.fit": activity_file(start=day(0)), "activities/2.fit": b"no"},
            [
                row(0, "activities/1.fit"),
                row(1, "activities/2.fit"),
                row(2, "activities/3.fit"),
                row(3, "", elapsed="600", metres=""),
                line("x", "?", "Run"),
            ],
        )

        counts = import_export(alice, source)

        assert counts == ImportCounts(
            imported=1, entered=1, duplicates=0, unreadable=1, missing=1, lines_unreadable=1
        )


class TestTheArchive:
    def test_a_file_that_is_no_zip(self, alice: User) -> None:
        with pytest.raises(ExportError, match="not a ZIP"):
            import_export(alice, io.BytesIO(b"this is not a zip archive"))

    def test_a_path_that_does_not_exist(self, alice: User, tmp_path: Path) -> None:
        missing = tmp_path / "nothing.zip"
        with pytest.raises(ExportError) as raised:
            import_export(alice, missing)

        message = str(raised.value)
        assert "not found" in message
        assert "not a ZIP" not in message
        assert str(missing) not in message
        assert "nothing.zip" not in message

    def test_a_directory_cannot_be_opened(self, alice: User, tmp_path: Path) -> None:
        with pytest.raises(ExportError) as raised:
            import_export(alice, tmp_path)

        message = str(raised.value)
        assert "cannot be opened" in message
        assert "not found" not in message
        assert "not a ZIP" not in message
        assert str(tmp_path) not in message

    def test_an_archive_without_the_list(self, alice: User) -> None:
        with pytest.raises(ExportError, match="no activities.csv"):
            import_export(alice, archive({"activities/1.fit": activity_file()}))

    def test_a_list_that_is_no_list(self, alice: User) -> None:
        with pytest.raises(ExportError, match="columns of a Strava export"):
            import_export(alice, archive({}, listing=b"a,b,c\n1,2,3\n"))

    def test_a_list_that_is_too_large(self, alice: User, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("activities.strava.MAX_LIST_BYTES", 100)

        with pytest.raises(ExportError, match="cannot be read"):
            import_export(alice, archive({}, [row(0, "")]))

    def test_an_archive_with_too_many_members(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("activities.strava.MAX_MEMBERS", 2)

        with pytest.raises(ExportError, match="too many files"):
            import_export(alice, archive({"a": b"1", "b": b"2"}, []))

    def test_an_archive_that_is_read_from_a_path(self, alice: User, tmp_path: Path) -> None:
        path = tmp_path / "export.zip"
        path.write_bytes(
            archive(
                {"activities/1.fit": activity_file(start=day(0))}, [row(0, "activities/1.fit")]
            ).getvalue()
        )

        assert import_export(alice, path).imported == 1

    def test_a_message_holds_nothing_of_the_file(self, alice: User) -> None:
        with pytest.raises(ExportError) as raised:
            import_export(alice, archive({}, listing=b"SECRET-COLUMN\nSECRET-VALUE\n"))

        assert "SECRET" not in str(raised.value)

    def test_the_progress_is_reported_after_each_line(self, alice: User) -> None:
        seen: list[tuple[int, int]] = []
        source = archive({}, [row(n, "activities/gone.fit") for n in range(3)])

        import_export(alice, source, progress=lambda done, total: seen.append((done, total)))

        assert seen == [(1, 3), (2, 3), (3, 3)]


class TestTheEstimates:
    def test_they_are_refreshed_once_after_an_import(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[User] = []
        monkeypatch.setattr("activities.strava.refresh_estimates_safely", calls.append)
        source = archive(
            {
                "activities/1.fit": activity_file(start=day(0)),
                "activities/2.fit": activity_file(start=day(1)),
            },
            [row(0, "activities/1.fit"), row(1, "activities/2.fit")],
        )

        import_export(alice, source)

        assert calls == [alice]

    def test_not_when_nothing_was_added(self, alice: User, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[User] = []
        monkeypatch.setattr("activities.strava.refresh_estimates_safely", calls.append)

        import_export(alice, archive({}, [row(0, "activities/gone.fit")]))

        assert calls == []


class TestTheCommand:
    def run(self, *args: str) -> str:
        out = io.StringIO()
        call_command("import_strava", *args, stdout=out)
        return out.getvalue()

    def zip_at(self, tmp_path: Path) -> Path:
        path = tmp_path / "export.zip"
        path.write_bytes(
            archive(
                {"activities/1.fit.gz": gzip.compress(activity_file(start=day(0)))},
                [row(0, "activities/1.fit.gz"), row(1, "", elapsed="1800", metres="")],
            ).getvalue()
        )
        return path

    def test_it_imports_for_the_account_and_prints_counts(
        self, alice: User, tmp_path: Path
    ) -> None:
        output = self.run(str(self.zip_at(tmp_path)), "--user", "alice@example.com")

        assert "Imported 1 with a recording and 1 without one." in output
        assert Activity.objects.filter(owner=alice).count() == 2

    def test_the_email_is_matched_like_at_the_login(self, alice: User, tmp_path: Path) -> None:
        self.run(str(self.zip_at(tmp_path)), "--user", "  Alice@Example.com ")

        assert Activity.objects.filter(owner=alice).count() == 2

    def test_a_second_run_reports_what_it_skipped(self, alice: User, tmp_path: Path) -> None:
        path = self.zip_at(tmp_path)
        self.run(str(path), "--user", "alice@example.com")

        output = self.run(str(path), "--user", "alice@example.com")

        assert "Imported 0 with a recording and 0 without one." in output
        assert "Skipped 2 that you have already." in output

    def test_an_unknown_account(self, tmp_path: Path) -> None:
        with pytest.raises(CommandError, match="no account"):
            self.run(str(self.zip_at(tmp_path)), "--user", "nobody@example.com")

    def test_an_archive_that_cannot_be_used(self, alice: User, tmp_path: Path) -> None:
        path = tmp_path / "bad.zip"
        path.write_bytes(b"no zip")

        with pytest.raises(CommandError) as raised:
            self.run(str(path), "--user", "alice@example.com")

        message = str(raised.value)
        assert "not a ZIP" in message
        assert str(path) not in message
        assert "bad.zip" not in message

    def test_a_missing_archive(self, alice: User, tmp_path: Path) -> None:
        missing = tmp_path / "missing.zip"

        with pytest.raises(CommandError) as raised:
            self.run(str(missing), "--user", "alice@example.com")

        message = str(raised.value)
        assert "not found" in message
        assert "not a ZIP" not in message
        assert str(missing) not in message
        assert "missing.zip" not in message

    @pytest.mark.parametrize("budget", ["MAX_TOTAL_UNPACKED_BYTES", "MAX_PARSED_RECORDINGS"])
    def test_budget_exhaustion_is_a_fixed_command_error(
        self, alice: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, budget: str
    ) -> None:
        monkeypatch.setattr(f"activities.strava.{budget}", 0)
        path = self.zip_at(tmp_path)
        with pytest.raises(CommandError) as raised:
            self.run(str(path), "--user", "alice@example.com")
        assert str(raised.value) == "The archive exceeds the bulk import work limit."

    def test_the_user_is_needed(self, tmp_path: Path) -> None:
        with pytest.raises(CommandError, match="--user"):
            self.run(str(self.zip_at(tmp_path)))

    def test_nothing_of_a_file_is_printed(self, alice: User, tmp_path: Path) -> None:
        output = self.run(str(self.zip_at(tmp_path)), "--user", "alice@example.com")

        assert "Morning Run" not in output
        assert "activities/" not in output
