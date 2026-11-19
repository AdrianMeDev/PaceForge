import random
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction

from accounts.models import User
from activities.models import Activity, ActivityFile

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def hash_of(n: int) -> str:
    return f"{n:064x}"


def activity(
    owner: User,
    *,
    n: int = 1,
    start: datetime = START,
    sport: str = Activity.Sport.RUNNING,
    **fields: Any,
) -> Activity:
    return Activity.objects.create(
        owner=owner,
        source=Activity.Source.FIT_FILE,
        source_hash=hash_of(n),
        sport=sport,
        start_time=start,
        **fields,
    )


def stored_bytes(activity_id: Any) -> bytes:
    table = connection.ops.quote_name(ActivityFile._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT data FROM {table} WHERE activity_id = %s", [activity_id])
        return bytes(cursor.fetchone()[0])


class TestOwnership:
    def test_a_user_cannot_import_the_same_file_twice(self, alice: User) -> None:
        activity(alice, n=1)

        with pytest.raises(IntegrityError), transaction.atomic():
            activity(alice, n=1, start=START + timedelta(days=1))

        assert Activity.objects.count() == 1

    def test_a_user_cannot_hold_two_activities_with_the_same_start_and_sport(
        self, alice: User
    ) -> None:
        activity(alice, n=1)

        with pytest.raises(IntegrityError), transaction.atomic():
            activity(alice, n=2)

        assert Activity.objects.count() == 1

    def test_the_same_start_in_another_sport_is_another_activity(self, alice: User) -> None:
        activity(alice, n=1, sport=Activity.Sport.RUNNING)
        activity(alice, n=2, sport=Activity.Sport.CYCLING)

        assert Activity.objects.count() == 2

    def test_another_user_may_hold_the_same_file_and_the_same_start(
        self, alice: User, bob: User
    ) -> None:
        activity(alice, n=1)
        activity(bob, n=1)

        assert Activity.objects.count() == 2

    def test_for_user_shows_only_the_own_activities(self, alice: User, bob: User) -> None:
        alices = activity(alice, n=1)
        bobs = activity(bob, n=2)

        assert list(Activity.objects.for_user(alice)) == [alices]
        assert list(Activity.objects.for_user(bob)) == [bobs]

    def test_anonymous_users_see_nothing(self, alice: User) -> None:
        activity(alice)

        assert not Activity.objects.for_user(AnonymousUser()).exists()

    def test_deleting_the_user_deletes_the_activities_and_their_files(self, alice: User) -> None:
        mine = activity(alice)
        ActivityFile.for_activity(mine, b"content").save()

        alice.delete()

        assert not Activity.objects.exists()
        assert not ActivityFile.objects.exists()

    def test_deleting_an_activity_deletes_its_file_and_nothing_else(
        self, alice: User, bob: User
    ) -> None:
        mine, theirs = activity(alice, n=1), activity(bob, n=2)
        ActivityFile.for_activity(mine, b"mine").save()
        ActivityFile.for_activity(theirs, b"theirs").save()

        mine.delete()

        assert [f.activity_id for f in ActivityFile.objects.all()] == [theirs.pk]


class TestTheValues:
    def test_only_what_identifies_an_activity_is_required(self, alice: User) -> None:
        created = activity(alice)

        created.refresh_from_db()
        assert created.elapsed_seconds is None
        assert created.timer_seconds is None
        assert created.distance_m is None
        assert created.avg_heart_rate is None
        assert created.max_heart_rate is None
        assert created.avg_power_w is None
        assert created.avg_pace_s_per_km is None
        assert created.training_load is None
        assert created.external_id == ""
        assert created.total_ascent_m is None
        assert created.calories is None
        assert created.manufacturer == ""
        assert created.source_sport == ""
        assert created.laps == []

    def test_a_minimal_activity_is_valid(self, alice: User) -> None:
        minimal = Activity(
            owner=alice,
            source="tcx_file",
            source_hash=hash_of(1),
            sport="other",
            start_time=START,
        )

        minimal.full_clean()  # no laps, no measurements, no manufacturer: nothing is required

    def test_values_and_laps_are_kept_as_given(self, alice: User) -> None:
        laps = [{"start": "2026-11-12T06:30:00Z", "seconds": 360.5, "distance_m": 1000.0}]

        created = activity(
            alice,
            elapsed_seconds=3904.59,
            timer_seconds=3800.0,
            distance_m=12766.23,
            avg_heart_rate=155,
            max_heart_rate=169,
            avg_power_w=230,
            avg_pace_s_per_km=305.5,
            training_load=65.25,
            total_ascent_m=120,
            calories=850,
            manufacturer="coros",
            source_sport="trail_running",
            laps=laps,
        )

        created.refresh_from_db()
        assert (created.elapsed_seconds, created.distance_m) == (3904.59, 12766.23)
        assert (created.avg_heart_rate, created.max_heart_rate, created.avg_power_w) == (
            155,
            169,
            230,
        )
        assert created.laps == laps
        assert (created.avg_pace_s_per_km, created.training_load) == (305.5, 65.25)
        assert created.start_time == START

    @pytest.mark.parametrize(
        "field",
        ["elapsed_seconds", "timer_seconds", "distance_m", "avg_pace_s_per_km", "training_load"],
    )
    def test_a_negative_measurement_is_refused_by_the_database(
        self, alice: User, field: str
    ) -> None:
        values: dict[str, Any] = {field: -1.0}

        with pytest.raises(IntegrityError), transaction.atomic():
            activity(alice, **values)

    def test_zero_is_a_valid_measurement(self, alice: User) -> None:
        created = activity(
            alice,
            elapsed_seconds=0.0,
            timer_seconds=0.0,
            distance_m=0.0,
            avg_pace_s_per_km=0.0,
            training_load=0.0,
        )

        created.refresh_from_db()
        assert created.distance_m == 0.0
        assert created.avg_pace_s_per_km == created.training_load == 0.0

    @pytest.mark.parametrize(
        ("field", "value"), [("sport", "golf"), ("source", "kml_file"), ("source_hash", "x" * 65)]
    )
    def test_unknown_choices_and_too_long_hashes_are_not_valid(
        self, alice: User, field: str, value: str
    ) -> None:
        created = Activity(
            owner=alice,
            source="fit_file",
            source_hash=hash_of(1),
            sport="running",
            start_time=START,
        )
        setattr(created, field, value)

        with pytest.raises(ValidationError) as raised:
            created.full_clean()

        assert field in raised.value.message_dict

    def test_the_list_is_ordered_newest_first(self, alice: User) -> None:
        old = activity(alice, n=1, start=START - timedelta(days=2))
        new = activity(alice, n=2, start=START)
        middle = activity(alice, n=3, start=START - timedelta(days=1))

        assert list(Activity.objects.for_user(alice)) == [new, middle, old]

    def test_the_text_names_sport_start_and_owner_but_not_the_file(self, alice: User) -> None:
        created = activity(alice, n=255)

        text = str(created)

        assert "Running" in text and "2026-11-12 06:30" in text and str(alice.pk) in text
        assert hash_of(255) not in text

    def test_ids_are_uuids_that_do_not_reveal_the_count(self, alice: User) -> None:
        first, second = activity(alice, n=1), activity(alice, n=2, start=START + timedelta(hours=1))

        assert first.pk != second.pk
        assert len(str(first.pk)) == 36


class TestTheFile:
    def test_the_content_comes_back_byte_for_byte(self, alice: User) -> None:
        # Incompressible bytes, but the same every run, so that a failure can be repeated.
        content = random.Random(1).randbytes(5000) + b"\x00\x00" + b".FIT" * 100
        mine = activity(alice)

        ActivityFile.for_activity(mine, content).save()

        loaded = ActivityFile.objects.get(activity=mine)
        assert loaded.read() == content
        assert loaded.original_size == len(content)

    def test_it_is_stored_compressed_and_does_not_show_its_content(self, alice: User) -> None:
        content = b"<TrainingCenterDatabase>" + b"<Trackpoint/>" * 5000
        mine = activity(alice)

        ActivityFile.for_activity(mine, content).save()

        raw = stored_bytes(mine.pk)
        assert raw[:2] == b"\x1f\x8b"
        assert len(raw) < len(content) // 10
        assert b"Trackpoint" not in raw

    def test_the_compressed_bytes_depend_only_on_the_content(self, alice: User) -> None:
        mine = activity(alice)

        first = ActivityFile.for_activity(mine, b"same content")
        second = ActivityFile.for_activity(mine, b"same content")

        assert bytes(first.data) == bytes(second.data)

    def test_the_compressed_bytes_do_not_depend_on_the_time_of_saving(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mine = activity(alice)
        monkeypatch.setattr(time, "time", lambda: 1_000_000_000.0)
        first = bytes(ActivityFile.for_activity(mine, b"same content").data)
        monkeypatch.setattr(time, "time", lambda: 2_000_000_000.0)

        second = bytes(ActivityFile.for_activity(mine, b"same content").data)

        assert first == second

    def test_an_empty_file_round_trips(self, alice: User) -> None:
        mine = activity(alice)

        ActivityFile.for_activity(mine, b"").save()

        assert ActivityFile.objects.get(activity=mine).read() == b""

    def test_an_activity_has_one_file_and_saving_again_replaces_it(self, alice: User) -> None:
        mine = activity(alice)
        ActivityFile.for_activity(mine, b"one").save()

        ActivityFile.for_activity(mine, b"two").save()

        assert ActivityFile.objects.count() == 1
        assert ActivityFile.objects.get(activity=mine).read() == b"two"

    def test_a_second_insert_for_the_same_activity_is_refused(self, alice: User) -> None:
        mine = activity(alice)
        ActivityFile.for_activity(mine, b"one").save()

        with pytest.raises(IntegrityError), transaction.atomic():
            ActivityFile.for_activity(mine, b"two").save(force_insert=True)

        assert ActivityFile.objects.get(activity=mine).read() == b"one"

    def test_the_text_does_not_show_the_content(self, alice: User) -> None:
        mine = activity(alice)

        shown = str(ActivityFile.for_activity(mine, b"secret-track-data"))

        assert "secret-track-data" not in shown
        assert "17 bytes" in shown


def by_hand(owner: User, **fields: Any) -> Activity:
    values: dict[str, Any] = {
        "owner": owner,
        "source": Activity.Source.MANUAL,
        "sport": Activity.Sport.STRENGTH,
        "start_time": START,
        **fields,
    }
    return Activity.objects.create(**values)


class TestEnteredByHand:
    def test_it_needs_no_file_and_may_have_an_rpe_and_a_note(self, alice: User) -> None:
        found = by_hand(alice, timer_seconds=2700, rpe=7, notes="Legs were heavy")

        found.refresh_from_db()
        assert (found.source_hash, found.rpe, found.notes) == ("", 7, "Legs were heavy")

    def test_rpe_and_note_are_empty_by_default(self, alice: User) -> None:
        found = by_hand(alice)

        assert (found.rpe, found.notes) == (None, "")

    def test_activities_without_a_hash_do_not_clash_on_the_empty_hash(self, alice: User) -> None:
        # Two sessions at the same time but in other sports: only the hash could tell them apart.
        by_hand(alice, sport=Activity.Sport.STRENGTH)
        by_hand(alice, sport=Activity.Sport.OTHER)

        assert Activity.objects.filter(source_hash="").count() == 2

    def test_two_by_hand_with_different_starts_are_fine(self, alice: User) -> None:
        by_hand(alice)
        by_hand(alice, start_time=START + timedelta(days=1))

        assert Activity.objects.count() == 2

    def test_the_same_start_and_sport_is_still_one_activity(self, alice: User) -> None:
        by_hand(alice)

        with pytest.raises(IntegrityError), transaction.atomic():
            by_hand(alice)

    @pytest.mark.parametrize("rpe", [1, 5, 10])
    def test_an_rpe_from_1_to_10_is_stored(self, alice: User, rpe: int) -> None:
        assert by_hand(alice, rpe=rpe).rpe == rpe

    @pytest.mark.parametrize("rpe", [0, 11, 100])
    def test_an_rpe_outside_1_to_10_is_refused_by_the_database(self, alice: User, rpe: int) -> None:
        with pytest.raises(IntegrityError, match="activities_rpe_in_range"), transaction.atomic():
            by_hand(alice, rpe=rpe)

    def test_a_manual_activity_must_not_have_a_hash(self, alice: User) -> None:
        with (
            pytest.raises(IntegrityError, match="activities_hash_goes_with_a_file"),
            transaction.atomic(),
        ):
            by_hand(alice, source_hash=hash_of(1))

    @pytest.mark.parametrize(
        "source", [Activity.Source.FIT_FILE, Activity.Source.TCX_FILE, Activity.Source.GPX_FILE]
    )
    def test_a_file_activity_must_have_a_hash(self, alice: User, source: str) -> None:
        with (
            pytest.raises(IntegrityError, match="activities_hash_goes_with_a_file"),
            transaction.atomic(),
        ):
            by_hand(alice, source=source, source_hash="")

    def test_a_hash_is_still_used_once_per_user(self, alice: User, bob: User) -> None:
        activity(alice, n=1)
        activity(bob, n=1)

        with pytest.raises(IntegrityError), transaction.atomic():
            activity(alice, n=1, start=START + timedelta(days=1))

    def test_a_note_longer_than_the_limit_is_refused_by_validation(self, alice: User) -> None:
        found = Activity(
            owner=alice,
            source=Activity.Source.MANUAL,
            sport=Activity.Sport.STRENGTH,
            start_time=START,
            notes="x" * 501,
        )

        with pytest.raises(ValidationError) as raised:
            found.full_clean(exclude=["owner", "id"])

        assert "notes" in raised.value.message_dict


def from_intervals(owner: User, **fields: Any) -> Activity:
    return Activity.objects.create(
        **{
            "owner": owner,
            "source": Activity.Source.INTERVALS_ICU,
            "external_id": "i123",
            "sport": Activity.Sport.RUNNING,
            "start_time": START,
            **fields,
        }
    )


class TestFromIntervals:
    def test_it_has_an_external_id_and_no_file_hash(self, alice: User) -> None:
        created = from_intervals(alice, avg_pace_s_per_km=305.5, training_load=65.25)

        created.refresh_from_db()
        created.full_clean()
        assert created.get_source_display() == "Intervals.icu"
        assert (created.external_id, created.source_hash) == ("i123", "")
        assert (created.avg_pace_s_per_km, created.training_load) == (305.5, 65.25)
        assert not ActivityFile.objects.filter(activity=created).exists()

    def test_an_external_id_is_used_once_per_owner_and_source(self, alice: User) -> None:
        from_intervals(alice)

        with (
            pytest.raises(IntegrityError, match="activities_one_per_external_id_and_owner"),
            transaction.atomic(),
        ):
            from_intervals(alice, start_time=START + timedelta(days=1))

    def test_another_owner_can_have_the_same_external_id(self, alice: User, bob: User) -> None:
        from_intervals(alice)
        from_intervals(bob)

        assert Activity.objects.count() == 2

    def test_other_external_ids_do_not_clash_on_the_empty_hash(self, alice: User) -> None:
        from_intervals(alice)
        from_intervals(alice, external_id="i124", start_time=START + timedelta(days=1))

        assert Activity.objects.filter(source_hash="").count() == 2

    def test_an_external_id_is_required(self, alice: User) -> None:
        with (
            pytest.raises(IntegrityError, match="activities_external_id_goes_with_provider"),
            transaction.atomic(),
        ):
            from_intervals(alice, external_id="")

    def test_a_file_hash_is_refused(self, alice: User) -> None:
        with (
            pytest.raises(IntegrityError, match="activities_hash_goes_with_a_file"),
            transaction.atomic(),
        ):
            from_intervals(alice, source_hash=hash_of(1))

    @pytest.mark.parametrize(
        "source",
        [
            Activity.Source.MANUAL,
            Activity.Source.FIT_FILE,
            Activity.Source.TCX_FILE,
            Activity.Source.GPX_FILE,
        ],
    )
    def test_other_sources_cannot_have_an_external_id(self, alice: User, source: str) -> None:
        with (
            pytest.raises(IntegrityError, match="activities_external_id_goes_with_provider"),
            transaction.atomic(),
        ):
            from_intervals(
                alice,
                source=source,
                source_hash="" if source == Activity.Source.MANUAL else hash_of(1),
            )

    def test_it_still_cannot_duplicate_a_file_activitys_start_and_sport(self, alice: User) -> None:
        activity(alice)

        with (
            pytest.raises(IntegrityError, match="activities_one_per_start_and_owner"),
            transaction.atomic(),
        ):
            from_intervals(alice)
