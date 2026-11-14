import json
import logging
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from accounts.tests.conftest import AuthApi
from activities import services
from activities.models import Activity, ActivityFile
from athletes.models import ThresholdValue

from .conftest import make_user, signed_in
from .fit_builder import activity_file
from .tcx_builder import tcx_document

pytestmark = pytest.mark.django_db

IMPORT = "/api/activities/import/"
LIST = "/api/activities/"
START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
SUMMARY_FIELDS = {
    "id",
    "source",
    "sport",
    "source_sport",
    "start_time",
    "elapsed_seconds",
    "timer_seconds",
    "distance_m",
    "avg_heart_rate",
    "max_heart_rate",
    "avg_power_w",
    "total_ascent_m",
    "calories",
    "manufacturer",
    "rpe",
    "notes",
    "load",
    "created_at",
}


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def upload(
    api: AuthApi,
    content: bytes,
    *,
    name: str = "run.fit",
    field: str = "file",
    csrf: bool = True,
) -> Any:
    headers = {"X-CSRFToken": api._csrf_token()} if csrf else {}
    return api.client.post(IMPORT, {field: SimpleUploadedFile(name, content)}, headers=headers)


def body(response: Any) -> Any:
    return json.loads(response.content)


def detail_url(activity_id: Any) -> str:
    return f"{LIST}{activity_id}/"


def counts() -> tuple[int, int]:
    return Activity.objects.count(), ActivityFile.objects.count()


def make_activities(owner: User, count: int) -> list[Activity]:
    return Activity.objects.bulk_create(
        Activity(
            owner=owner,
            source=Activity.Source.FIT_FILE,
            source_hash=f"{n:064x}",
            sport=Activity.Sport.RUNNING,
            start_time=START + timedelta(minutes=n),
        )
        for n in range(count)
    )


class TestWhoMayCome:
    @pytest.mark.parametrize(
        ("method", "url"),
        [
            ("GET", LIST),
            ("GET", detail_url(uuid4())),
            ("DELETE", detail_url(uuid4())),
            ("POST", IMPORT),
        ],
    )
    def test_anonymous_visitors_are_refused(self, method: str, url: str) -> None:
        response = AuthApi().call(method, url)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert counts() == (0, 0)

    def test_an_import_without_the_csrf_token_is_refused(self, alice: User) -> None:
        response = upload(signed_in(alice), activity_file(), csrf=False)

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert counts() == (0, 0)

    def test_a_delete_without_the_csrf_token_is_refused(self, alice: User) -> None:
        activity = make_activities(alice, 1)[0]
        api = signed_in(alice)

        response = api.client.delete(detail_url(activity.pk))

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert Activity.objects.count() == 1


class TestImport:
    def test_a_fit_file_is_imported_and_shown(self, alice: User) -> None:
        api = signed_in(alice)

        response = upload(api, activity_file())

        assert response.status_code == HTTPStatus.CREATED
        created = body(response)
        assert set(created) == SUMMARY_FIELDS
        assert created["source"] == "fit_file"
        assert created["sport"] == "running"
        assert created["start_time"] == "2026-11-12T06:30:00Z"
        assert created["distance_m"] == pytest.approx(12766.23)
        assert (created["avg_heart_rate"], created["max_heart_rate"]) == (155, 169)
        assert created["manufacturer"] == "garmin"
        listed = body(api.call("GET", LIST))
        assert [item["id"] for item in listed["results"]] == [created["id"]]
        assert listed["results"][0] == created
        shown = body(api.call("GET", detail_url(created["id"])))
        assert shown == {**created, "laps": shown["laps"]}
        assert len(shown["laps"]) == 1
        assert shown["laps"][0]["distance_m"] == pytest.approx(6383.0)
        assert counts() == (1, 1)

    def test_a_tcx_file_is_imported_and_shown(self, alice: User) -> None:
        api = signed_in(alice)

        response = upload(api, tcx_document(sport="Biking"), name="ride.tcx")

        assert response.status_code == HTTPStatus.CREATED
        created = body(response)
        assert created["source"] == "tcx_file"
        assert created["sport"] == "cycling"
        assert created["distance_m"] == pytest.approx(7000.0)
        shown = body(api.call("GET", detail_url(created["id"])))
        assert [lap["distance_m"] for lap in shown["laps"]] == [2000, 4000, 1000]

    def test_the_name_of_the_file_decides_nothing(self, alice: User) -> None:
        api = signed_in(alice)

        fit = upload(api, activity_file(), name="notes.txt")
        tcx = upload(api, tcx_document(sport="Biking"), name="ride.fit")

        assert fit.status_code == tcx.status_code == HTTPStatus.CREATED
        assert (body(fit)["source"], body(tcx)["source"]) == ("fit_file", "tcx_file")

    def test_the_list_leaves_out_the_laps_and_the_file_is_never_returned(self, alice: User) -> None:
        api = signed_in(alice)
        created = body(upload(api, tcx_document()))

        texts = [
            api.call("GET", LIST).content.decode(),
            api.call("GET", detail_url(created["id"])).content.decode(),
        ]

        assert '"laps"' not in texts[0]
        for text in texts:
            for private in ("12.345678", "23.456789", "source_hash", "owner", "Trackpoint"):
                assert private not in text

    def test_the_stored_file_is_the_uploaded_one(self, alice: User) -> None:
        data = tcx_document()
        created = body(upload(signed_in(alice), data))

        assert ActivityFile.objects.get(pk=created["id"]).read() == data


class TestRefusals:
    @pytest.mark.parametrize(
        ("name", "content", "status", "message"),
        [
            ("empty.fit", b"", HTTPStatus.BAD_REQUEST, "The file is empty."),
            ("a.fit", b"hello, this is text", HTTPStatus.BAD_REQUEST, "neither a FIT nor a TCX"),
            ("a.fit", activity_file()[:-30], HTTPStatus.BAD_REQUEST, None),
            ("a.fit", activity_file(sessions=2), HTTPStatus.BAD_REQUEST, None),
            (
                "a.tcx",
                tcx_document(prolog='<?xml version="1.0"?><!DOCTYPE x>'),
                HTTPStatus.BAD_REQUEST,
                "document type",
            ),
            ("a.tcx", tcx_document()[:-40], HTTPStatus.BAD_REQUEST, None),
        ],
    )
    def test_a_file_that_cannot_be_imported_stores_nothing(
        self, alice: User, name: str, content: bytes, status: HTTPStatus, message: str | None
    ) -> None:
        response = upload(signed_in(alice), content, name=name)

        assert response.status_code == status
        assert set(body(response)) == {"detail"}
        if message:
            assert message in body(response)["detail"]
        assert counts() == (0, 0)

    def test_a_request_without_a_file_field_is_refused(self, alice: User) -> None:
        response = upload(signed_in(alice), activity_file(), field="document")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"detail": "No file was uploaded."}
        assert counts() == (0, 0)

    def test_a_json_request_is_refused(self, alice: User) -> None:
        response = signed_in(alice).call("POST", IMPORT, {"file": "abc"})

        assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert counts() == (0, 0)

    def test_a_file_over_the_size_limit_is_refused_unread(
        self, alice: User, settings: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        data = activity_file()
        settings.ACTIVITY_UPLOAD_MAX_BYTES = len(data) - 1
        monkeypatch.setattr(
            services, "import_activity", lambda *a: pytest.fail("must not be called")
        )

        response = upload(signed_in(alice), data)

        assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        assert body(response) == {"detail": "The file is too large."}
        assert counts() == (0, 0)

    def test_a_file_exactly_at_the_limit_is_accepted(self, alice: User, settings: Any) -> None:
        data = activity_file()
        settings.ACTIVITY_UPLOAD_MAX_BYTES = len(data)

        assert upload(signed_in(alice), data).status_code == HTTPStatus.CREATED

    def test_the_same_file_again_answers_conflict_with_the_existing_id(self, alice: User) -> None:
        api = signed_in(alice)
        first = body(upload(api, activity_file()))

        response = upload(api, activity_file())

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "This activity has already been imported.",
            "existing_id": first["id"],
        }
        assert counts() == (1, 1)

    def test_the_same_run_in_another_format_answers_conflict(self, alice: User) -> None:
        api = signed_in(alice)
        first = body(upload(api, activity_file()))

        response = upload(api, tcx_document(), name="run.tcx")

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response)["existing_id"] == first["id"]

    def test_nothing_from_a_file_reaches_the_answer_or_the_log(
        self, alice: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        canary = b"CANARY-0451-private-track"
        api = signed_in(alice)
        caplog.set_level(logging.DEBUG)

        responses = [
            upload(api, canary),
            upload(api, activity_file()[:-30] + canary),
            upload(api, b"<x>" + canary + b"</x>", name="a.tcx"),
            upload(api, tcx_document(prolog='<!DOCTYPE c [<!ENTITY a "CANARY-0451">]>')),
        ]

        for response in responses:
            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert b"CANARY" not in response.content
        assert "CANARY" not in caplog.text

    def test_the_name_of_the_file_is_not_repeated_in_an_answer(
        self, alice: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        api = signed_in(alice)
        caplog.set_level(logging.DEBUG)

        response = upload(api, b"not an activity", name="home-CANARY-0451.fit")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert b"CANARY" not in response.content
        assert "CANARY" not in caplog.text


class TestIsolation:
    def test_each_user_sees_only_their_own_activities(self, alice: User, bob: User) -> None:
        alices = signed_in(alice)
        bobs = signed_in(bob)
        mine = body(upload(alices, activity_file()))
        theirs = body(upload(bobs, tcx_document(sport="Biking")))

        assert [a["id"] for a in body(alices.call("GET", LIST))["results"]] == [mine["id"]]
        assert [a["id"] for a in body(bobs.call("GET", LIST))["results"]] == [theirs["id"]]

    def test_the_same_file_can_be_imported_by_two_users(self, alice: User, bob: User) -> None:
        first = upload(signed_in(alice), activity_file())
        second = upload(signed_in(bob), activity_file())

        assert first.status_code == second.status_code == HTTPStatus.CREATED
        assert body(first)["id"] != body(second)["id"]
        assert counts() == (2, 2)

    def test_a_foreign_activity_answers_404_for_detail_and_delete(
        self, alice: User, bob: User
    ) -> None:
        mine = body(upload(signed_in(alice), activity_file()))
        bobs = signed_in(bob)

        assert bobs.call("GET", detail_url(mine["id"])).status_code == HTTPStatus.NOT_FOUND
        assert bobs.call("DELETE", detail_url(mine["id"])).status_code == HTTPStatus.NOT_FOUND
        assert Activity.objects.filter(pk=mine["id"]).exists()

    def test_a_conflict_never_names_an_activity_of_someone_else(
        self, alice: User, bob: User
    ) -> None:
        mine = body(upload(signed_in(alice), activity_file()))

        response = upload(signed_in(bob), activity_file())

        assert response.status_code == HTTPStatus.CREATED
        assert body(response)["id"] != mine["id"]

    def test_deleting_removes_only_the_own_row_and_its_file(self, alice: User, bob: User) -> None:
        alices = signed_in(alice)
        mine = body(upload(alices, activity_file()))
        theirs = body(upload(signed_in(bob), activity_file()))

        response = alices.call("DELETE", detail_url(mine["id"]))

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert alices.call("GET", detail_url(mine["id"])).status_code == HTTPStatus.NOT_FOUND
        remaining = [str(pk) for pk in Activity.objects.values_list("pk", flat=True)]
        assert remaining == [theirs["id"]]
        assert counts() == (1, 1)

    def test_an_administrator_sees_only_their_own_activities(self, alice: User) -> None:
        boss = make_user("boss@example.com", staff=True)
        upload(signed_in(alice), activity_file())
        api = signed_in(boss)
        mine = body(upload(api, tcx_document(sport="Biking")))

        listed = body(api.call("GET", LIST))["results"]

        assert [a["id"] for a in listed] == [mine["id"]]

    def test_a_deleted_activity_can_be_imported_again(self, alice: User) -> None:
        api = signed_in(alice)
        first = body(upload(api, activity_file()))
        api.call("DELETE", detail_url(first["id"]))

        assert upload(api, activity_file()).status_code == HTTPStatus.CREATED


class TestOtherRequests:
    def test_activities_cannot_be_created_or_changed_through_the_list_and_detail(
        self, alice: User
    ) -> None:
        api = signed_in(alice)
        mine = body(upload(api, activity_file()))

        assert api.call("POST", LIST, {"sport": "running"}).status_code == 405
        assert api.call("PUT", detail_url(mine["id"]), {"sport": "cycling"}).status_code == 405
        assert api.call("PATCH", detail_url(mine["id"]), {"sport": "cycling"}).status_code == 405
        assert Activity.objects.get(pk=mine["id"]).sport == "running"

    @pytest.mark.parametrize("ident", ["not-a-uuid", "12345", str(uuid4())])
    def test_an_unknown_id_is_a_404(self, alice: User, ident: str) -> None:
        api = signed_in(alice)

        assert api.call("GET", detail_url(ident)).status_code == HTTPStatus.NOT_FOUND
        assert api.call("DELETE", detail_url(ident)).status_code == HTTPStatus.NOT_FOUND

    def test_the_import_address_is_not_taken_for_an_activity(self, alice: User) -> None:
        assert signed_in(alice).call("GET", IMPORT).status_code == HTTPStatus.METHOD_NOT_ALLOWED


class TestPagination:
    def test_the_default_is_50_newest_first(self, alice: User) -> None:
        make_activities(alice, 60)

        page = body(signed_in(alice).call("GET", LIST))

        assert page["count"] == 60
        assert len(page["results"]) == 50
        starts = [a["start_time"] for a in page["results"]]
        assert starts == sorted(starts, reverse=True)
        assert page["results"][0]["start_time"] == "2026-11-12T07:29:00Z"
        assert page["next"] is not None
        assert page["previous"] is None

    def test_limit_and_offset(self, alice: User) -> None:
        make_activities(alice, 25)
        api = signed_in(alice)

        page = body(api.call("GET", f"{LIST}?limit=10&offset=20"))

        assert page["count"] == 25
        assert len(page["results"]) == 5
        assert page["results"][-1]["start_time"] == "2026-11-12T06:30:00Z"
        assert page["next"] is None
        assert page["previous"] is not None

    def test_the_limit_is_capped_at_200(self, alice: User) -> None:
        make_activities(alice, 205)

        page = body(signed_in(alice).call("GET", f"{LIST}?limit=1000"))

        assert len(page["results"]) == 200
        assert page["count"] == 205

    def test_an_empty_list(self, alice: User) -> None:
        page = body(signed_in(alice).call("GET", LIST))

        assert page == {"count": 0, "next": None, "previous": None, "results": []}

    def test_the_list_does_not_run_one_query_per_activity(
        self, alice: User, django_assert_max_num_queries: Any
    ) -> None:
        make_activities(alice, 30)
        api = signed_in(alice)

        with django_assert_max_num_queries(8):
            api.call("GET", LIST)

    def test_the_list_does_not_even_load_the_laps(self, alice: User) -> None:
        make_activities(alice, 3)
        api = signed_in(alice)

        with CaptureQueriesContext(connection) as queries:
            api.call("GET", LIST)

        selects = [q["sql"] for q in queries if 'FROM "activities_activity"' in q["sql"]]
        assert selects
        assert all('"laps"' not in sql for sql in selects)


class TestThrottling:
    def test_the_31st_import_within_a_minute_is_throttled_and_never_parsed(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reached = []
        real = services.parse_activity_file

        def counting(data: bytes) -> Any:
            reached.append(1)
            return real(data)

        monkeypatch.setattr(services, "parse_activity_file", counting)
        api = signed_in(alice)
        for _ in range(30):
            assert upload(api, b"not an activity").status_code == HTTPStatus.BAD_REQUEST

        response = upload(api, activity_file())

        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert "Retry-After" in response.headers
        assert len(reached) == 30
        assert counts() == (0, 0)

    def test_another_user_is_not_affected(self, alice: User, bob: User) -> None:
        alices = signed_in(alice)
        for _ in range(31):
            upload(alices, b"x")

        assert upload(signed_in(bob), activity_file()).status_code == HTTPStatus.CREATED

    def test_reading_and_deleting_are_not_throttled(self, alice: User) -> None:
        api = signed_in(alice)
        mine = make_activities(alice, 1)[0]
        for _ in range(31):
            upload(api, b"x")

        assert api.call("GET", LIST).status_code == HTTPStatus.OK
        assert api.call("GET", detail_url(mine.pk)).status_code == HTTPStatus.OK
        assert api.call("DELETE", detail_url(mine.pk)).status_code == HTTPStatus.NO_CONTENT


class TestEstimatedThresholds:
    """Importing and deleting keep the estimated maximum heart rate up to date."""

    def run_with(self, heart_rate: int, day: int) -> bytes:
        return activity_file(start=START + timedelta(days=day), session={17: heart_rate})

    def estimated(self, owner: User) -> dict[str, float]:
        return {
            row.sport: row.value
            for row in ThresholdValue.objects.filter(
                owner=owner, metric="max_hr", source="estimated"
            )
        }

    def test_the_third_matching_run_creates_the_estimate(self, alice: User) -> None:
        api = signed_in(alice)

        for day, heart_rate in enumerate((182, 184)):
            assert upload(api, self.run_with(heart_rate, day)).status_code == HTTPStatus.CREATED
        assert self.estimated(alice) == {}
        upload(api, self.run_with(171, 2))

        assert self.estimated(alice) == {"run": 184}
        shown = body(api.call("GET", "/api/athlete/"))
        found = shown["sports"]["run"]["thresholds"]["max_hr"]["effective"]
        assert (found["value"], found["source"]) == (184, "estimated")

    def test_deleting_the_activity_that_held_it_removes_the_estimate(self, alice: User) -> None:
        api = signed_in(alice)
        ids = [
            body(upload(api, self.run_with(hr, day)))["id"]
            for day, hr in enumerate((184, 183, 150))
        ]
        assert self.estimated(alice) == {"run": 184}

        response = api.call("DELETE", detail_url(ids[0]))

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert self.estimated(alice) == {}

    def test_a_refused_import_does_not_touch_the_estimates(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[object] = []
        monkeypatch.setattr(
            "activities.views.refresh_estimates_safely", lambda user: calls.append(user)
        )
        api = signed_in(alice)
        upload(api, self.run_with(184, 0))
        calls.clear()

        again = upload(api, self.run_with(184, 0))  # the same file
        broken = upload(api, b"not an activity")

        assert (again.status_code, broken.status_code) == (
            HTTPStatus.CONFLICT,
            HTTPStatus.BAD_REQUEST,
        )
        assert calls == []

    def test_a_failure_while_estimating_does_not_fail_the_import(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(user: User) -> None:
            raise RuntimeError("database gone")

        monkeypatch.setattr("athletes.estimates.refresh_estimates", fail)

        response = upload(signed_in(alice), self.run_with(184, 0))

        assert response.status_code == HTTPStatus.CREATED
        assert counts() == (1, 1)

    def test_a_failure_while_estimating_does_not_fail_a_deletion(
        self, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = signed_in(alice)
        created = body(upload(api, self.run_with(184, 0)))

        def fail(user: User) -> None:
            raise RuntimeError("database gone")

        monkeypatch.setattr("athletes.estimates.refresh_estimates", fail)
        response = api.call("DELETE", detail_url(created["id"]))

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert counts() == (0, 0)

    def test_each_user_gets_their_own_estimate(self, alice: User, bob: User) -> None:
        alices, bobs = signed_in(alice), signed_in(bob)
        for day, heart_rate in enumerate((190, 189, 150)):
            upload(alices, self.run_with(heart_rate, day))
        for day, heart_rate in enumerate((170, 169, 150)):
            upload(bobs, self.run_with(heart_rate, day))

        assert self.estimated(alice) == {"run": 190}
        assert self.estimated(bob) == {"run": 170}

    def test_deleting_a_foreign_activity_changes_no_estimate(self, alice: User, bob: User) -> None:
        alices, bobs = signed_in(alice), signed_in(bob)
        ids = [
            body(upload(alices, self.run_with(hr, day)))["id"]
            for day, hr in enumerate((184, 183, 150))
        ]

        response = bobs.call("DELETE", detail_url(ids[0]))

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert self.estimated(alice) == {"run": 184}
