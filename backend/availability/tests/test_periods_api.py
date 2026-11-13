import json
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from athletes.models import AthleteProfile
from availability.capacity import minutes_on
from availability.models import UnavailablePeriod, WeekdayMinutes
from availability.serializers import MAX_PERIODS, TOO_MANY_PERIODS
from goals import services

from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

URL = "/api/availability/periods/"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
TODAY = date(2026, 11, 13)
FIELDS = {"id", "kind", "start_date", "end_date", "days", "status", "note"}


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def body(response: Any) -> Any:
    return json.loads(response.content)


def detail(pk: Any) -> str:
    return f"{URL}{pk}/"


def period(**fields: Any) -> dict[str, Any]:
    return {"kind": "vacation", "start_date": day(10), "end_date": day(23), **fields}


def stored(owner: User, **fields: Any) -> UnavailablePeriod:
    data = {
        "kind": "vacation",
        "start_date": TODAY + timedelta(days=10),
        "end_date": TODAY + timedelta(days=23),
    }
    return UnavailablePeriod.objects.create(owner=owner, **(data | fields))


def create(api: AuthApi, data: Any) -> Any:
    return api.call("POST", URL, data)


def listing(api: AuthApi) -> list[dict[str, Any]]:
    response = api.call("GET", URL)
    assert response.status_code == HTTPStatus.OK
    return list(body(response))


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("GET", URL),
            ("POST", URL),
            ("GET", detail(uuid4())),
            ("PATCH", detail(uuid4())),
            ("DELETE", detail(uuid4())),
        ],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        assert AuthApi().call(method, url, period()).status_code == HTTPStatus.FORBIDDEN
        assert not UnavailablePeriod.objects.exists()

    @pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
    def test_a_request_without_the_csrf_token_is_refused(self, alice: User, method: str) -> None:
        mine = stored(alice)
        api = signed_in(alice)

        response = api.client.generic(
            method,
            URL if method == "POST" else detail(mine.pk),
            data=json.dumps(period(note="changed")),
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert UnavailablePeriod.objects.count() == 1
        assert UnavailablePeriod.objects.get().note == ""

    def test_put_is_not_allowed(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PUT", detail(mine.pk), period())

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestCreatingAndReading:
    def test_a_period_is_created_and_read_back(self, alice: User) -> None:
        api = signed_in(alice)

        response = create(api, period(note="Mallorca"))

        assert response.status_code == HTTPStatus.CREATED
        created = body(response)
        assert set(created) == FIELDS
        assert created | {"id": None} == {
            "id": None,
            "kind": "vacation",
            "start_date": day(10),
            "end_date": day(23),
            "days": 14,
            "status": "upcoming",
            "note": "Mallorca",
        }
        assert UnavailablePeriod.objects.get().owner == alice
        assert api.call("GET", detail(created["id"])).status_code == HTTPStatus.OK
        assert listing(api) == [created]

    @pytest.mark.parametrize("kind", ["vacation", "illness", "other"])
    def test_every_kind_is_accepted(self, alice: User, kind: str) -> None:
        response = create(signed_in(alice), period(kind=kind))

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)["kind"] == kind

    def test_the_note_is_optional(self, alice: User) -> None:
        response = create(signed_in(alice), period())

        assert body(response)["note"] == ""

    def test_the_note_is_trimmed_and_kept_as_text(self, alice: User) -> None:
        response = create(signed_in(alice), period(note="  <script>1</script> & more  "))

        assert body(response)["note"] == "<script>1</script> & more"

    def test_a_single_day_has_one_day(self, alice: User) -> None:
        response = create(signed_in(alice), period(start_date=day(3), end_date=day(3)))

        assert body(response)["days"] == 1

    def test_the_longest_period_has_366_days(self, alice: User) -> None:
        response = create(signed_in(alice), period(start_date=day(0), end_date=day(365)))

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)["days"] == 366

    def test_a_period_in_the_past_may_be_recorded(self, alice: User) -> None:
        response = create(
            signed_in(alice), period(kind="illness", start_date=day(-9), end_date=day(-5))
        )

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)["status"] == "past"

    def test_the_client_cannot_set_what_the_server_decides(self, alice: User, bob: User) -> None:
        wanted = uuid4()

        response = create(
            signed_in(alice),
            period(id=str(wanted), owner=str(bob.pk), status="past", days=99),
        )

        created = body(response)
        assert created["id"] != str(wanted)
        assert created["status"] == "upcoming"
        assert created["days"] == 14
        assert UnavailablePeriod.objects.get().owner == alice

    def test_the_list_is_a_plain_array_without_paging(self, alice: User) -> None:
        for offset in range(3):
            stored(
                alice,
                start_date=TODAY + timedelta(days=offset),
                end_date=TODAY + timedelta(days=offset),
            )

        response = signed_in(alice).call("GET", URL)

        assert isinstance(body(response), list)
        assert len(body(response)) == 3


class TestStatusAndOrder:
    @pytest.mark.parametrize(
        ("start", "end", "status"),
        [
            (-10, -1, "past"),
            (-10, 0, "current"),
            (0, 0, "current"),
            (0, 5, "current"),
            (-3, 3, "current"),
            (1, 5, "upcoming"),
            (-10, -1, "past"),
        ],
    )
    def test_the_status_follows_today(self, alice: User, start: int, end: int, status: str) -> None:
        mine = stored(
            alice, start_date=TODAY + timedelta(days=start), end_date=TODAY + timedelta(days=end)
        )

        response = signed_in(alice).call("GET", detail(mine.pk))

        assert body(response)["status"] == status

    def test_going_on_and_coming_periods_come_first_nearest_first_then_the_past_latest_first(
        self, alice: User
    ) -> None:
        def make(start: int, end: int) -> str:
            return str(
                stored(
                    alice,
                    start_date=TODAY + timedelta(days=start),
                    end_date=TODAY + timedelta(days=end),
                ).pk
            )

        far = make(60, 70)
        old = make(-100, -90)
        soon = make(5, 6)
        recent = make(-20, -10)
        going_on = make(-2, 4)
        today_only = make(0, 0)
        yesterday = make(-3, -1)

        order = [entry["id"] for entry in listing(signed_in(alice))]

        # going on (started earlier first), coming by start, then past by end, latest first
        assert order == [going_on, today_only, soon, far, yesterday, recent, old]

    def test_the_day_is_the_users_own_day(self, alice: User) -> None:
        # 12:00 UTC on 13 November is already the 14th in Auckland
        AthleteProfile.objects.create(owner=alice, timezone="Pacific/Auckland")
        mine = stored(alice, start_date=TODAY, end_date=TODAY)

        response = signed_in(alice).call("GET", detail(mine.pk))

        assert body(response)["status"] == "past"

    def test_the_list_does_not_ask_the_database_once_per_period(self, alice: User) -> None:
        api = signed_in(alice)
        stored(alice)
        with CaptureQueriesContext(connection) as one:
            listing(api)
        for offset in range(15):
            stored(
                alice,
                start_date=TODAY + timedelta(days=offset),
                end_date=TODAY + timedelta(days=offset),
            )
        with CaptureQueriesContext(connection) as many:
            listing(api)

        assert len(many) == len(one)


class TestRefusals:
    @pytest.mark.parametrize("kind", ["", "holiday", "VACATION", 5, None, True, ["vacation"]])
    def test_an_unknown_kind_is_refused(self, alice: User, kind: Any) -> None:
        response = create(signed_in(alice), period(kind=kind))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["kind"]
        assert not UnavailablePeriod.objects.exists()

    @pytest.mark.parametrize("field", ["kind", "start_date", "end_date"])
    def test_a_missing_field_is_refused(self, alice: User, field: str) -> None:
        data = period()
        del data[field]

        response = create(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == [field]

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "tomorrow",
            "2027-13-01",
            "2027-02-30",
            "12.07.2027",
            20270712,
            1.5,
            True,
            None,
            [],
            "2027-07-12T10:00:00",
        ],
    )
    @pytest.mark.parametrize("field", ["start_date", "end_date"])
    def test_an_unusable_date_is_refused(self, alice: User, field: str, value: Any) -> None:
        response = create(signed_in(alice), period(**{field: value}))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == [field]
        assert not UnavailablePeriod.objects.exists()

    def test_the_end_cannot_be_before_the_start(self, alice: User) -> None:
        response = create(signed_in(alice), period(start_date=day(5), end_date=day(4)))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"end_date": ["The end cannot be before the start."]}

    def test_a_period_longer_than_366_days_is_refused(self, alice: User) -> None:
        response = create(signed_in(alice), period(start_date=day(0), end_date=day(366)))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"end_date": ["A period can last at most 366 days."]}

    @pytest.mark.parametrize("note", [5, ["x"], None, True, {"a": 1}, "x" * 201])
    def test_an_unusable_note_is_refused(self, alice: User, note: Any) -> None:
        response = create(signed_in(alice), period(note=note))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(body(response)) == ["note"]

    def test_a_note_of_200_characters_is_accepted(self, alice: User) -> None:
        response = create(signed_in(alice), period(note="x" * 200))

        assert response.status_code == HTTPStatus.CREATED

    @pytest.mark.parametrize("data", [[], "text", 5])
    def test_a_body_that_is_no_object_is_refused(self, alice: User, data: Any) -> None:
        response = create(signed_in(alice), data)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert not UnavailablePeriod.objects.exists()

    def test_every_problem_is_named_at_once(self, alice: User) -> None:
        response = create(signed_in(alice), period(kind="x", start_date="no", note="x" * 201))

        assert set(body(response)) == {"kind", "start_date", "note"}


class TestTheLimit:
    def test_a_hundred_periods_are_allowed_and_the_next_is_not(self, alice: User) -> None:
        assert MAX_PERIODS == 100
        UnavailablePeriod.objects.bulk_create(
            [
                UnavailablePeriod(
                    owner=alice,
                    kind="other",
                    start_date=TODAY + timedelta(days=i),
                    end_date=TODAY + timedelta(days=i),
                )
                for i in range(99)
            ]
        )
        api = signed_in(alice)

        assert create(api, period()).status_code == HTTPStatus.CREATED
        refused = create(api, period())

        assert refused.status_code == HTTPStatus.BAD_REQUEST
        assert body(refused) == {"non_field_errors": [TOO_MANY_PERIODS]}
        assert UnavailablePeriod.objects.count() == 100

    def test_the_message_says_what_to_do(self) -> None:
        assert TOO_MANY_PERIODS == "You can have at most 100 periods. Delete one first."

    def test_other_users_periods_do_not_count(self, alice: User, bob: User) -> None:
        UnavailablePeriod.objects.bulk_create(
            [
                UnavailablePeriod(owner=bob, kind="other", start_date=TODAY, end_date=TODAY)
                for _ in range(100)
            ]
        )

        assert create(signed_in(alice), period()).status_code == HTTPStatus.CREATED

    def test_deleting_one_makes_room(self, alice: User) -> None:
        UnavailablePeriod.objects.bulk_create(
            [
                UnavailablePeriod(owner=alice, kind="other", start_date=TODAY, end_date=TODAY)
                for _ in range(100)
            ]
        )
        api = signed_in(alice)
        assert create(api, period()).status_code == HTTPStatus.BAD_REQUEST

        victim = UnavailablePeriod.objects.first()
        assert victim is not None
        api.call("DELETE", detail(victim.pk))

        assert create(api, period()).status_code == HTTPStatus.CREATED

    def test_changing_a_period_is_not_stopped_by_a_full_list(self, alice: User) -> None:
        UnavailablePeriod.objects.bulk_create(
            [
                UnavailablePeriod(owner=alice, kind="other", start_date=TODAY, end_date=TODAY)
                for _ in range(99)
            ]
        )
        mine = stored(alice)

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"note": "still fine"})

        assert response.status_code == HTTPStatus.OK


class TestChanging:
    def test_one_field_changes_and_the_rest_stays(self, alice: User) -> None:
        mine = stored(alice, note="Mallorca")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"kind": "other"})

        assert response.status_code == HTTPStatus.OK
        mine.refresh_from_db()
        assert (mine.kind, mine.note) == ("other", "Mallorca")
        assert mine.start_date == TODAY + timedelta(days=10)

    def test_the_dates_can_move(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call(
            "PATCH", detail(mine.pk), {"start_date": day(20), "end_date": day(25)}
        )

        assert body(response)["days"] == 6
        mine.refresh_from_db()
        assert mine.start_date == TODAY + timedelta(days=20)

    def test_the_note_can_be_removed(self, alice: User) -> None:
        mine = stored(alice, note="Mallorca")

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"note": ""})

        assert body(response)["note"] == ""

    def test_an_end_before_the_existing_start_is_refused(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"end_date": day(9)})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "end_date" in body(response)
        mine.refresh_from_db()
        assert mine.end_date == TODAY + timedelta(days=23)

    def test_a_start_after_the_existing_end_is_refused(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"start_date": day(24)})

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_stretching_beyond_366_days_is_refused(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"end_date": day(10 + 366)})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "end_date" in body(response)

    @pytest.mark.parametrize(
        "changes",
        [{"kind": "holiday"}, {"start_date": "soon"}, {"note": 5}, {"end_date": None}],
    )
    def test_a_refused_change_leaves_the_period_as_it_was(
        self, alice: User, changes: dict[str, Any]
    ) -> None:
        mine = stored(alice, note="Mallorca")

        response = signed_in(alice).call("PATCH", detail(mine.pk), changes)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        mine.refresh_from_db()
        assert (mine.kind, mine.note) == ("vacation", "Mallorca")
        assert mine.end_date == TODAY + timedelta(days=23)

    def test_the_owner_and_the_id_cannot_be_changed(self, alice: User, bob: User) -> None:
        mine = stored(alice)

        signed_in(alice).call(
            "PATCH", detail(mine.pk), {"owner": str(bob.pk), "id": str(uuid4()), "note": "x"}
        )

        mine.refresh_from_db()
        assert mine.owner == alice
        assert UnavailablePeriod.objects.filter(pk=mine.pk).exists()

    def test_the_computed_fields_cannot_be_changed(self, alice: User) -> None:
        mine = stored(alice)

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"status": "past", "days": 1})

        assert body(response)["status"] == "upcoming"
        assert body(response)["days"] == 14

    def test_a_past_period_can_still_be_edited(self, alice: User) -> None:
        mine = stored(
            alice, start_date=TODAY - timedelta(days=9), end_date=TODAY - timedelta(days=5)
        )

        response = signed_in(alice).call("PATCH", detail(mine.pk), {"note": "flu"})

        assert response.status_code == HTTPStatus.OK
        assert body(response)["status"] == "past"


class TestDeleting:
    def test_a_period_is_deleted(self, alice: User) -> None:
        mine = stored(alice)
        api = signed_in(alice)

        response = api.call("DELETE", detail(mine.pk))

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert not UnavailablePeriod.objects.exists()
        assert api.call("GET", detail(mine.pk)).status_code == HTTPStatus.NOT_FOUND
        assert api.call("DELETE", detail(mine.pk)).status_code == HTTPStatus.NOT_FOUND


class TestOwnership:
    def test_the_list_shows_only_the_own_periods(self, alice: User, bob: User) -> None:
        mine = stored(alice)
        stored(bob)

        assert [entry["id"] for entry in listing(signed_in(alice))] == [str(mine.pk)]

    @pytest.mark.parametrize("method", ["GET", "PATCH", "DELETE"])
    def test_another_users_period_does_not_exist(self, alice: User, bob: User, method: str) -> None:
        theirs = stored(bob, note="private")

        response = signed_in(alice).call(method, detail(theirs.pk), {"note": "hacked"})

        assert response.status_code == HTTPStatus.NOT_FOUND
        theirs.refresh_from_db()
        assert theirs.note == "private"

    @pytest.mark.parametrize("pk", ["1", "abc", "x" * 36, "12345678-1234-1234-1234-12345678901g"])
    def test_an_id_that_is_no_uuid_is_not_found(self, alice: User, pk: str) -> None:
        assert signed_in(alice).call("GET", detail(pk)).status_code == HTTPStatus.NOT_FOUND

    def test_an_unknown_uuid_is_not_found(self, alice: User) -> None:
        assert signed_in(alice).call("GET", detail(uuid4())).status_code == HTTPStatus.NOT_FOUND


class TestCapacity:
    def test_a_recorded_period_takes_its_days_out_of_the_capacity(self, alice: User) -> None:
        for weekday in range(7):
            WeekdayMinutes.objects.create(owner=alice, weekday=weekday, minutes=60)
        target = TODAY + timedelta(days=10)
        assert minutes_on(alice, target) == 60

        created = create(signed_in(alice), period())

        assert minutes_on(alice, target) == 0
        assert minutes_on(alice, TODAY + timedelta(days=24)) == 60

        signed_in(alice).call("DELETE", detail(body(created)["id"]))
        assert minutes_on(alice, target) == 60
