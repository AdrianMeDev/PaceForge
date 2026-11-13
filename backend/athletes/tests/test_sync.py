import base64
import json
import logging
from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.utils import timezone

from accounts.models import User
from athletes.models import AthleteProfile, ThresholdValue
from athletes.sync import BASIS, sync_from_intervals
from athletes.thresholds import candidates, effective
from integrations.intervals import (
    IntervalsUnavailableError,
    InvalidKeyError,
    UnexpectedResponseError,
)
from integrations.models import ProviderConnection
from integrations.services import NotConnectedError
from integrations.tests.fake_intervals import FakeIntervals, running

from .conftest import make_user

pytestmark = pytest.mark.django_db

KEY = "k3y-0123456789-abcdefghij"
PATH = "/api/v1/athlete/0/sport-settings"
Source = ThresholdValue.Source


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def connect(owner: User, key: str = KEY) -> ProviderConnection:
    return ProviderConnection.objects.create(
        owner=owner, provider="intervals_icu", api_key=key, athlete_id="i1"
    )


def entry(types: list[str], **fields: object) -> dict[str, object]:
    return {
        "types": types,
        "ftp": None,
        "lthr": None,
        "max_hr": None,
        "threshold_pace": None,
    } | fields


def answer(fake: FakeIntervals, *entries: object) -> None:
    fake.bodies[PATH] = json.dumps(list(entries)).encode()


TYPICAL = (
    entry(["Ride", "VirtualRide"], ftp=250, lthr=165, max_hr=190),
    entry(["Run", "VirtualRun"], lthr=170, max_hr=188, threshold_pace=10 / 3),
    entry(["Swim"], lthr=150, max_hr=180, threshold_pace=0.9),
)


def rows(owner: User, source: str = Source.INTERVALS) -> dict[tuple[str, str], float]:
    return {
        (row.sport, row.metric): row.value
        for row in ThresholdValue.objects.filter(owner=owner, source=source)
    }


class TestWhatIsStored:
    def test_the_values_are_stored_with_the_source_and_a_fixed_basis(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, *TYPICAL)

        sync_from_intervals(alice)

        assert rows(alice) == {
            ("ride", "ftp"): 250,
            ("ride", "lthr"): 165,
            ("ride", "max_hr"): 190,
            ("run", "threshold_pace"): 300,
            ("run", "lthr"): 170,
            ("run", "max_hr"): 188,
        }
        assert set(ThresholdValue.objects.values_list("basis", flat=True)) == {BASIS}
        assert set(ThresholdValue.objects.values_list("source", flat=True)) == {"intervals"}

    def test_they_become_effective_when_nothing_was_typed_in(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, *TYPICAL)

        sync_from_intervals(alice)

        found = effective(alice, "ride", "ftp")
        assert found is not None
        assert (found.value, found.source, found.basis) == (250, "intervals", BASIS)

    def test_the_time_of_the_sync_is_kept_and_a_profile_is_made(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, *TYPICAL)
        before = timezone.now()

        sync_from_intervals(alice)

        profile = AthleteProfile.objects.get(owner=alice)
        assert profile.intervals_synced_at is not None
        assert before <= profile.intervals_synced_at <= timezone.now()

    def test_an_existing_profile_keeps_its_time_zone(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")
        connect(alice)
        answer(fake, *TYPICAL)

        sync_from_intervals(alice)

        assert AthleteProfile.objects.get(owner=alice).timezone == "Europe/Berlin"
        assert AthleteProfile.objects.count() == 1

    @pytest.mark.parametrize(
        ("given", "stored"), [(262.4, 262), (262.5, 263), (262.6, 263), (250, 250)]
    )
    def test_values_are_rounded_to_whole_numbers_half_up(
        self, fake: FakeIntervals, alice: User, given: float, stored: float
    ) -> None:
        connect(alice)
        answer(fake, entry(["Ride"], ftp=given))

        sync_from_intervals(alice)

        assert rows(alice) == {("ride", "ftp"): stored}

    def test_the_pace_arrives_in_seconds_per_kilometre(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry(["Run"], threshold_pace=3.3))  # 303.03 s/km

        sync_from_intervals(alice)

        assert rows(alice) == {("run", "threshold_pace"): 303}

    def test_a_threshold_that_does_not_exist_for_the_sport_is_not_stored(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(
            fake,
            entry(["Ride"], ftp=250, threshold_pace=3.3),  # cycling has no pace
            entry(["Run"], ftp=250, lthr=170),  # running has no power
        )

        sync_from_intervals(alice)

        assert rows(alice) == {("ride", "ftp"): 250, ("run", "lthr"): 170}

    def test_swimming_and_other_sports_are_not_stored(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry(["Swim"], lthr=150, max_hr=180), entry(["Other"], lthr=140))

        sync_from_intervals(alice)

        assert not ThresholdValue.objects.exists()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("ftp", 2001),  # the client lets it through, the profile does not
            ("ftp", 29),
            ("lthr", 251),
            ("lthr", 29),
            ("max_hr", 260),
            ("threshold_pace", 0.5),  # 2000 s/km
            ("threshold_pace", 12),  # 83 s/km
        ],
    )
    def test_a_value_outside_what_a_person_can_do_is_not_stored(
        self, fake: FakeIntervals, alice: User, field: str, value: float
    ) -> None:
        connect(alice)
        sport = ["Run"] if field == "threshold_pace" else ["Ride"]
        answer(
            fake,
            entry(sport, **{field: value}),
            entry(["Run"] if sport == ["Ride"] else ["Ride"], lthr=160),
        )

        sync_from_intervals(alice)

        assert (("run" if field == "threshold_pace" else "ride"), field) not in rows(alice)
        assert len(rows(alice)) == 1  # the other, valid value is there


class TestUpdatingAndRemoving:
    def test_a_second_sync_updates_changed_values(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        answer(fake, *TYPICAL)
        sync_from_intervals(alice)

        answer(fake, entry(["Ride"], ftp=260, lthr=165, max_hr=190), TYPICAL[1])
        sync_from_intervals(alice)

        assert rows(alice)[("ride", "ftp")] == 260
        assert ThresholdValue.objects.filter(source="intervals").count() == 6

    def test_unchanged_values_keep_the_time_they_were_changed(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, *TYPICAL)
        sync_from_intervals(alice)
        before = {row.pk: row.updated_at for row in ThresholdValue.objects.all()}

        sync_from_intervals(alice)

        after = {row.pk: row.updated_at for row in ThresholdValue.objects.all()}
        assert after == before

    def test_the_time_of_the_sync_moves_every_time(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        answer(fake, *TYPICAL)
        sync_from_intervals(alice)
        first = AthleteProfile.objects.get(owner=alice).intervals_synced_at

        sync_from_intervals(alice)

        second = AthleteProfile.objects.get(owner=alice).intervals_synced_at
        assert first is not None and second is not None and second > first

    def test_values_that_disappeared_are_removed(self, fake: FakeIntervals, alice: User) -> None:
        connect(alice)
        answer(fake, *TYPICAL)
        sync_from_intervals(alice)

        answer(fake, entry(["Ride"], ftp=250), TYPICAL[1])  # no LTHR and max HR for cycling
        sync_from_intervals(alice)

        assert ("ride", "lthr") not in rows(alice)
        assert ("ride", "max_hr") not in rows(alice)
        assert rows(alice)[("ride", "ftp")] == 250
        assert len(rows(alice)) == 4

    def test_a_group_that_is_gone_loses_all_its_values(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, *TYPICAL)
        sync_from_intervals(alice)

        answer(fake, TYPICAL[1])

        sync_from_intervals(alice)

        assert {sport for sport, _ in rows(alice)} == {"run"}

    def test_an_empty_answer_removes_everything_from_intervals(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, *TYPICAL)
        sync_from_intervals(alice)

        answer(fake)
        sync_from_intervals(alice)

        assert not ThresholdValue.objects.exists()
        assert AthleteProfile.objects.get(owner=alice).intervals_synced_at is not None

    def test_a_value_that_became_unusable_is_removed(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connect(alice)
        answer(fake, entry(["Ride"], ftp=250))
        sync_from_intervals(alice)

        answer(fake, entry(["Ride"], ftp=9999))
        sync_from_intervals(alice)

        assert not ThresholdValue.objects.exists()


class TestOtherSourcesAreLeftAlone:
    def test_a_typed_value_stays_effective_and_intervals_is_a_candidate(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        ThresholdValue.objects.create(
            owner=alice, sport="ride", metric="ftp", source="manual", value=255
        )
        connect(alice)
        answer(fake, *TYPICAL)

        sync_from_intervals(alice)

        assert effective(alice, "ride", "ftp").value == 255  # type: ignore[union-attr]
        assert [(c.source, c.value) for c in candidates(alice, "ride", "ftp")] == [
            ("manual", 255),
            ("intervals", 250),
        ]

    def test_typed_and_estimated_values_survive_even_when_intervals_has_nothing(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        manual = ThresholdValue.objects.create(
            owner=alice, sport="ride", metric="ftp", source="manual", value=255
        )
        estimated = ThresholdValue.objects.create(
            owner=alice, sport="ride", metric="max_hr", source="estimated", value=185, basis="x"
        )
        before = [(row.pk, row.value, row.basis, row.updated_at) for row in (manual, estimated)]
        connect(alice)
        answer(fake)

        sync_from_intervals(alice)

        after = [
            (row.pk, row.value, row.basis, row.updated_at)
            for row in ThresholdValue.objects.filter(pk__in=[manual.pk, estimated.pk]).order_by(
                "pk"
            )
        ]
        assert after == before

    def test_the_connection_is_not_changed_by_a_successful_sync(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        connection = connect(alice)
        answer(fake, *TYPICAL)
        before = (connection.status, connection.last_checked_at)

        sync_from_intervals(alice)

        connection.refresh_from_db()
        assert (connection.status, connection.last_checked_at) == before


class TestWhenItGoesWrong:
    def setup_values(self, fake: FakeIntervals, alice: User) -> tuple[Any, Any]:
        connection = connect(alice)
        answer(fake, *TYPICAL)
        sync_from_intervals(alice)
        fake.requests.clear()
        profile = AthleteProfile.objects.get(owner=alice)
        return connection, profile.intervals_synced_at

    def untouched(self, alice: User, connection: ProviderConnection, synced: Any) -> None:
        assert rows(alice)[("ride", "ftp")] == 250
        assert len(rows(alice)) == 6
        assert AthleteProfile.objects.get(owner=alice).intervals_synced_at == synced

    @pytest.mark.parametrize("status", [401, 403])
    def test_a_refused_key_marks_the_connection_invalid_and_changes_nothing(
        self, fake: FakeIntervals, alice: User, status: int
    ) -> None:
        connection, synced = self.setup_values(fake, alice)
        fake.status = status
        answer(fake, entry(["Ride"], ftp=300))

        with pytest.raises(InvalidKeyError):
            sync_from_intervals(alice)

        connection.refresh_from_db()
        assert connection.status == "invalid"
        self.untouched(alice, connection, synced)

    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    def test_an_unreachable_service_changes_nothing_not_even_the_connection(
        self, fake: FakeIntervals, alice: User, status: int
    ) -> None:
        connection, synced = self.setup_values(fake, alice)
        fake.status = status

        with pytest.raises(IntervalsUnavailableError):
            sync_from_intervals(alice)

        connection.refresh_from_db()
        assert connection.status == "connected"
        self.untouched(alice, connection, synced)

    def test_a_closed_port_changes_nothing(
        self, fake: FakeIntervals, alice: User, settings: Any
    ) -> None:
        connection, synced = self.setup_values(fake, alice)
        with running() as gone:
            settings.INTERVALS_API_BASE_URL = gone.url

        with pytest.raises(IntervalsUnavailableError):
            sync_from_intervals(alice)

        self.untouched(alice, connection, synced)

    @pytest.mark.parametrize("body", [b"{}", b"null", b"not json", b'"text"'])
    def test_an_odd_answer_changes_nothing(
        self, fake: FakeIntervals, alice: User, body: bytes
    ) -> None:
        connection, synced = self.setup_values(fake, alice)
        fake.bodies[PATH] = body

        with pytest.raises(UnexpectedResponseError):
            sync_from_intervals(alice)

        connection.refresh_from_db()
        assert connection.status == "connected"
        self.untouched(alice, connection, synced)

    def test_a_failure_while_saving_leaves_the_earlier_values(
        self, fake: FakeIntervals, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connection, synced = self.setup_values(fake, alice)
        answer(fake, entry(["Ride"], ftp=300, lthr=166, max_hr=191), TYPICAL[1])
        original = ThresholdValue.objects.update_or_create
        calls = {"n": 0}

        def failing(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return original(*args, **kwargs)

        monkeypatch.setattr(ThresholdValue.objects, "update_or_create", failing)

        with pytest.raises(RuntimeError):
            sync_from_intervals(alice)

        self.untouched(alice, connection, synced)
        assert rows(alice)[("ride", "lthr")] == 165

    def test_a_lost_instance_key_is_answered_like_a_refused_key_without_a_request(
        self, fake: FakeIntervals, alice: User, settings: Any
    ) -> None:
        connection = connect(alice)
        answer(fake, *TYPICAL)
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]  # the old key is gone

        with pytest.raises(InvalidKeyError):
            sync_from_intervals(alice)

        status = ProviderConnection.objects.defer("api_key").get(pk=connection.pk).status
        assert status == "invalid"
        assert fake.requests == []
        assert not ThresholdValue.objects.exists()

    def test_without_a_connection_nothing_is_asked_or_written(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        with pytest.raises(NotConnectedError):
            sync_from_intervals(alice)

        assert fake.requests == []
        assert not AthleteProfile.objects.exists()
        assert not ThresholdValue.objects.exists()


class TestWhoseKeyAndWhoseValues:
    @pytest.mark.parametrize("who", ["alice", "bob"])
    def test_each_user_is_synced_with_their_own_key_and_into_their_own_rows(
        self, fake: FakeIntervals, alice: User, bob: User, who: str
    ) -> None:
        users = {"alice": alice, "bob": bob}
        connect(alice, "alice-key-0123456789")
        connect(bob, "bob-key-0123456789")
        answer(fake, *TYPICAL)

        sync_from_intervals(users[who])

        [request] = fake.requests
        expected = base64.b64encode(f"API_KEY:{who}-key-0123456789".encode()).decode()
        assert request["headers"]["Authorization"] == f"Basic {expected}"
        other = bob if who == "alice" else alice
        assert rows(users[who]) and not rows(other)
        assert not AthleteProfile.objects.filter(owner=other).exists()

    def test_a_user_without_a_connection_never_uses_anothers(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(bob)
        answer(fake, *TYPICAL)

        with pytest.raises(NotConnectedError):
            sync_from_intervals(alice)

        assert fake.requests == []
        assert not ThresholdValue.objects.exists()

    def test_syncing_one_user_does_not_remove_the_values_of_another(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        connect(alice)
        connect(bob)
        answer(fake, *TYPICAL)
        sync_from_intervals(bob)

        answer(fake)  # alice's account is empty
        sync_from_intervals(alice)

        assert len(rows(bob)) == 6
        assert not rows(alice)


class TestSecrets:
    def test_neither_the_key_nor_a_value_is_logged_or_shown(
        self, fake: FakeIntervals, alice: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        connect(alice)
        answer(fake, entry(["Ride"], ftp=777, lthr=166))

        sync_from_intervals(alice)

        assert KEY not in caplog.text
        assert "777" not in caplog.text
        assert "166" not in caplog.text

    @pytest.mark.parametrize("status", [401, 429, 500])
    def test_failures_do_not_show_them_either(
        self,
        fake: FakeIntervals,
        alice: User,
        caplog: pytest.LogCaptureFixture,
        status: int,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        connect(alice)
        fake.status = status
        answer(fake, entry(["Ride"], ftp=777))

        with pytest.raises(Exception) as raised:  # noqa: PT011
            sync_from_intervals(alice)

        assert KEY not in repr(raised.value) + str(raised.value) + caplog.text
        assert "777" not in repr(raised.value) + caplog.text
