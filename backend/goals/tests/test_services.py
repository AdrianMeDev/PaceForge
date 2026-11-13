from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from athletes.models import AthleteProfile
from goals import services

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 11, 13, 23, 30, tzinfo=UTC)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


class TestTheTimeZoneOfAUser:
    def test_without_a_profile_it_is_utc(self, alice: User) -> None:
        assert services.time_zone_of(alice) is UTC

    def test_a_profile_without_a_time_zone_gives_utc(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="")

        assert services.time_zone_of(alice) is UTC

    def test_the_time_zone_of_the_profile_is_used(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")

        assert services.time_zone_of(alice) == ZoneInfo("Europe/Berlin")

    @pytest.mark.parametrize("name", ["Mars/Olympus", "../etc/passwd", "localtime", "nowhere"])
    def test_a_name_the_server_cannot_find_gives_utc(self, alice: User, name: str) -> None:
        # The profile checks the name when it is saved; this is the second line of defence.
        AthleteProfile.objects.filter(owner=alice).delete()
        profile = AthleteProfile(owner=alice, timezone=name)
        profile.save()

        assert services.time_zone_of(alice) is UTC

    def test_only_the_own_profile_counts(self, alice: User, bob: User) -> None:
        AthleteProfile.objects.create(owner=bob, timezone="Asia/Tokyo")

        assert services.time_zone_of(alice) is UTC
        assert services.time_zone_of(bob) == ZoneInfo("Asia/Tokyo")

    def test_it_takes_one_query(self, alice: User) -> None:
        AthleteProfile.objects.create(owner=alice, timezone="Europe/Berlin")

        with CaptureQueriesContext(connection) as queries:
            services.time_zone_of(alice)

        assert len(queries) == 1


class TestToday:
    def test_it_is_the_day_in_the_time_zone_of_the_user(
        self, alice: User, bob: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(services, "_utc_now", lambda: NOW)
        AthleteProfile.objects.create(owner=bob, timezone="Pacific/Auckland")

        # 23:30 UTC on the 13th is already the 14th in Auckland
        assert services.today_of(alice).isoformat() == "2026-11-13"
        assert services.today_of(bob).isoformat() == "2026-11-14"
