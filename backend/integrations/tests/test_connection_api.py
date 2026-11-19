import base64
import json
import logging
from datetime import timedelta
from http import HTTPStatus
from typing import Any

import pytest
from cryptography.fernet import Fernet
from django.db import IntegrityError, connection
from django.utils import timezone

from accounts.models import User
from accounts.tests.conftest import AuthApi
from core.encryption import PREFIX
from integrations.models import ProviderConnection

from .conftest import make_user, signed_in
from .fake_intervals import FakeIntervals, running

pytestmark = pytest.mark.django_db

URL = "/api/integrations/intervals/"
CHECK = "/api/integrations/intervals/check/"
KEY = "k3y-0123456789-abcdefghij"
OTHER_KEY = "other-9876543210-zyxwvutsrq"
STATE_FIELDS = {
    "connected",
    "status",
    "athlete_id",
    "connected_at",
    "last_checked_at",
    "last_sync_at",
    "last_sync_error",
}


def athlete(fake: FakeIntervals, athlete_id: str = "i100") -> None:
    fake.status = 200
    fake.body = json.dumps({"id": athlete_id, "email": "private@example.com"}).encode()


def stored_key(owner: User) -> str:
    table = ProviderConnection._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT api_key FROM {table} WHERE owner_id = %s", [owner.pk])
        return cursor.fetchone()[0]


def rows() -> int:
    return ProviderConnection.objects.count()


class TestWhoMayCome:
    @pytest.mark.parametrize(
        ("method", "url"),
        [("GET", URL), ("PUT", URL), ("DELETE", URL), ("POST", CHECK)],
    )
    def test_anonymous_visitors_are_refused(
        self, fake: FakeIntervals, method: str, url: str
    ) -> None:
        response = AuthApi().call(method, url, {"api_key": KEY})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert rows() == 0
        assert fake.requests == []

    def test_a_request_without_the_csrf_token_is_refused(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT", URL, data=json.dumps({"api_key": KEY}), content_type="application/json"
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert rows() == 0
        assert fake.requests == []

    def test_every_signed_in_user_may_use_it_not_only_administrators(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        assert not alice.is_staff

        assert signed_in(alice).call("PUT", URL, {"api_key": KEY}).status_code == HTTPStatus.OK


class TestTheStatus:
    def test_without_a_connection_it_says_so(self, fake: FakeIntervals, alice: User) -> None:
        response = signed_in(alice).call("GET", URL)

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {"connected": False}

    def test_with_a_connection_it_shows_the_state_and_no_key(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        athlete(fake, "i797177")
        api.call("PUT", URL, {"api_key": KEY})

        body = api.call("GET", URL).json()

        assert set(body) == STATE_FIELDS
        assert body["connected"] is True
        assert body["status"] == "connected"
        assert body["athlete_id"] == "i797177"
        assert body["last_sync_at"] is None
        assert body["last_sync_error"] == ""

    def test_sync_state_is_exposed(self, fake: FakeIntervals, alice: User) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        synced_at = timezone.now().replace(microsecond=0)
        ProviderConnection.objects.update(last_sync_at=synced_at, last_sync_error="unavailable")

        body = api.call("GET", URL).json()

        assert body["last_sync_at"] == synced_at.isoformat().replace("+00:00", "Z")
        assert body["last_sync_error"] == "unavailable"

    def test_reading_it_does_not_call_intervals_or_need_the_key(
        self, fake: FakeIntervals, alice: User, settings: Any
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        fake.requests.clear()
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]  # the old key is gone

        response = api.call("GET", URL)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["connected"] is True
        assert fake.requests == []


class TestConnecting:
    def test_a_valid_key_is_checked_stored_encrypted_and_not_returned(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        athlete(fake, "i42")

        response = signed_in(alice).call("PUT", URL, {"api_key": KEY})

        assert response.status_code == HTTPStatus.OK
        body = response.json()
        assert set(body) == STATE_FIELDS
        assert (body["status"], body["athlete_id"]) == ("connected", "i42")
        assert KEY not in response.content.decode()
        raw = stored_key(alice)
        assert raw.startswith(PREFIX) and KEY not in raw
        assert ProviderConnection.objects.get(owner=alice).api_key == KEY
        [request] = fake.requests
        assert request["path"].endswith("/athlete/0")
        assert KEY in base64.b64decode(request["headers"]["Authorization"][6:]).decode()

    def test_the_key_is_trimmed(self, fake: FakeIntervals, alice: User) -> None:
        signed_in(alice).call("PUT", URL, {"api_key": f"  {KEY}\n"})

        assert ProviderConnection.objects.get(owner=alice).api_key == KEY

    def test_only_the_athlete_id_is_kept_from_the_answer(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        athlete(fake)

        response = signed_in(alice).call("PUT", URL, {"api_key": KEY})

        assert "private@example.com" not in response.content.decode()
        assert "private@example.com" not in repr(ProviderConnection.objects.values().get())

    def test_a_second_key_replaces_the_first_and_keeps_one_row(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        first = stored_key(alice)
        past = timezone.now() - timedelta(days=3)
        ProviderConnection.objects.update(
            connected_at=past, last_sync_at=past, last_sync_error="invalid_key"
        )

        response = api.call("PUT", URL, {"api_key": OTHER_KEY})

        assert response.status_code == HTTPStatus.OK
        assert rows() == 1
        assert stored_key(alice) != first
        replaced = ProviderConnection.objects.get(owner=alice)
        assert replaced.api_key == OTHER_KEY
        assert replaced.connected_at > timezone.now() - timedelta(minutes=1)
        assert replaced.last_sync_error == ""
        assert replaced.last_sync_at == past
        assert response.json()["last_sync_error"] == ""

    def test_a_refused_key_gives_a_400_and_stores_nothing(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        fake.status = 401

        response = signed_in(alice).call("PUT", URL, {"api_key": KEY})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert list(response.json()) == ["api_key"]
        assert "did not accept" in response.json()["api_key"][0]
        assert rows() == 0

    def test_a_refused_new_key_leaves_the_existing_connection_untouched(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        athlete(fake, "i1")
        api.call("PUT", URL, {"api_key": KEY})
        before = stored_key(alice)
        fake.status = 403

        response = api.call("PUT", URL, {"api_key": OTHER_KEY})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert stored_key(alice) == before
        assert ProviderConnection.objects.get(owner=alice).api_key == KEY
        assert ProviderConnection.objects.get(owner=alice).athlete_id == "i1"

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_an_unavailable_intervals_gives_a_503_and_changes_nothing(
        self, fake: FakeIntervals, alice: User, status: int
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        before = stored_key(alice)
        fake.status = status

        response = api.call("PUT", URL, {"api_key": OTHER_KEY})

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert "try again later" in response.json()["detail"]
        assert stored_key(alice) == before

    def test_an_unreachable_intervals_gives_a_503(self, alice: User, settings: Any) -> None:
        with running() as gone:
            settings.INTERVALS_API_BASE_URL = gone.url

        response = signed_in(alice).call("PUT", URL, {"api_key": KEY})

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert rows() == 0

    def test_an_answer_that_makes_no_sense_gives_a_502(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        fake.body = b"<html>maintenance</html>"

        response = signed_in(alice).call("PUT", URL, {"api_key": KEY})

        assert response.status_code == HTTPStatus.BAD_GATEWAY
        assert rows() == 0

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"api_key": ""},
            {"api_key": "   "},
            {"api_key": None},
            {"api_key": 12345},
            {"api_key": ["a"]},
            {"api_key": {"a": 1}},
            {"api_key": "x" * 201},
            {"other": KEY},
        ],
    )
    def test_a_missing_blank_or_odd_key_is_refused_before_intervals_is_called(
        self, fake: FakeIntervals, alice: User, payload: dict[str, Any]
    ) -> None:
        response = signed_in(alice).call("PUT", URL, payload)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "api_key" in response.json()
        assert fake.requests == []
        assert rows() == 0

    def test_a_malformed_body_is_refused_without_echoing_the_key(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        token = api.client.cookies["csrftoken"].value

        response = api.client.generic(
            "PUT",
            URL,
            data=f'{{"api_key": "{KEY}"',
            content_type="application/json",
            headers={"X-CSRFToken": token},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert KEY not in response.content.decode()
        assert fake.requests == []

    def test_a_body_that_is_not_json_is_refused_without_echoing_the_key(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        token = api.client.cookies["csrftoken"].value

        response = api.client.generic(
            "PUT",
            URL,
            data=f"api_key={KEY}",
            content_type="application/x-www-form-urlencoded",
            headers={"X-CSRFToken": token},
        )

        assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert KEY not in response.content.decode()
        assert fake.requests == []

    def test_a_connection_whose_key_cannot_be_decrypted_can_be_replaced(
        self, fake: FakeIntervals, alice: User, settings: Any
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]  # the old key is gone

        response = api.call("PUT", URL, {"api_key": OTHER_KEY})

        assert response.status_code == HTTPStatus.OK
        assert rows() == 1
        assert ProviderConnection.objects.get(owner=alice).api_key == OTHER_KEY

    def test_a_request_that_creates_the_row_at_the_same_moment_is_handled(
        self, fake: FakeIntervals, alice: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_save = ProviderConnection.save
        raced: list[bool] = []

        def racing_save(self: ProviderConnection, *args: Any, **kwargs: Any) -> None:
            if not raced:
                raced.append(True)
                raise IntegrityError("another request created the row first")
            real_save(self, *args, **kwargs)

        monkeypatch.setattr(ProviderConnection, "save", racing_save)

        response = signed_in(alice).call("PUT", URL, {"api_key": KEY})

        assert response.status_code == HTTPStatus.OK
        assert rows() == 1
        assert ProviderConnection.objects.get(owner=alice).api_key == KEY


class TestChecking:
    def test_without_a_connection_it_is_a_404(self, fake: FakeIntervals, alice: User) -> None:
        response = signed_in(alice).call("POST", CHECK)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert fake.requests == []

    def test_a_working_key_stays_connected_and_the_time_moves_on(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        past = timezone.now() - timedelta(days=2)
        ProviderConnection.objects.update(
            last_checked_at=past, last_sync_at=past, last_sync_error="unavailable"
        )
        fake.requests.clear()

        response = api.call("POST", CHECK)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["status"] == "connected"
        assert set(response.json()) == STATE_FIELDS
        assert ProviderConnection.objects.get(owner=alice).last_checked_at > past
        assert response.json()["last_sync_error"] == ""
        assert ProviderConnection.objects.get(owner=alice).last_sync_error == ""
        assert ProviderConnection.objects.get(owner=alice).last_sync_at == past
        [request] = fake.requests  # the stored key is what is sent
        assert KEY in base64.b64decode(request["headers"]["Authorization"][6:]).decode()

    def test_a_key_that_is_refused_now_is_marked_invalid_and_kept(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        fake.status = 401

        response = api.call("POST", CHECK)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["status"] == "invalid"
        assert response.json()["connected"] is True
        assert ProviderConnection.objects.get(owner=alice).status == "invalid"
        assert rows() == 1

    def test_an_invalid_connection_is_connected_again_when_the_key_works(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        fake.status = 401
        api.call("POST", CHECK)
        athlete(fake)

        response = api.call("POST", CHECK)

        assert response.json()["status"] == "connected"

    @pytest.mark.parametrize("status", [429, 502])
    def test_an_unavailable_intervals_leaves_the_state_as_it_was(
        self, fake: FakeIntervals, alice: User, status: int
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        ProviderConnection.objects.update(last_sync_error="unavailable")
        fields = ("status", "last_checked_at", "last_sync_at", "last_sync_error")
        before = ProviderConnection.objects.values(*fields).get()
        fake.status = status

        response = api.call("POST", CHECK)

        assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert ProviderConnection.objects.values(*fields).get() == before

    def test_a_key_that_cannot_be_decrypted_is_invalid_without_calling_intervals(
        self, fake: FakeIntervals, alice: User, settings: Any
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        fake.requests.clear()
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

        response = api.call("POST", CHECK)

        assert response.status_code == HTTPStatus.OK
        assert response.json()["status"] == "invalid"
        assert fake.requests == []


class TestDisconnecting:
    def test_it_removes_the_connection_and_the_key(self, fake: FakeIntervals, alice: User) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})

        response = api.call("DELETE", URL)

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert rows() == 0
        assert api.call("GET", URL).json() == {"connected": False}

    def test_removing_nothing_is_fine(self, fake: FakeIntervals, alice: User) -> None:
        assert signed_in(alice).call("DELETE", URL).status_code == HTTPStatus.NO_CONTENT

    def test_it_does_not_call_intervals_or_need_the_key(
        self, fake: FakeIntervals, alice: User, settings: Any
    ) -> None:
        api = signed_in(alice)
        api.call("PUT", URL, {"api_key": KEY})
        fake.requests.clear()
        settings.ENCRYPTION_KEYS = [Fernet.generate_key().decode()]

        response = api.call("DELETE", URL)

        assert response.status_code == HTTPStatus.NO_CONTENT
        assert rows() == 0
        assert fake.requests == []


class TestEveryUserHasOnlyTheirOwn:
    def two_connected(self, fake: FakeIntervals, alice: User, bob: User) -> tuple[Any, Any]:
        alices, bobs = signed_in(alice), signed_in(bob)
        athlete(fake, "i-alice")
        alices.call("PUT", URL, {"api_key": KEY})
        athlete(fake, "i-bob")
        bobs.call("PUT", URL, {"api_key": OTHER_KEY})
        return alices, bobs

    def test_each_sees_only_their_own_connection(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        alices, bobs = self.two_connected(fake, alice, bob)

        assert alices.call("GET", URL).json()["athlete_id"] == "i-alice"
        assert bobs.call("GET", URL).json()["athlete_id"] == "i-bob"

    def test_replacing_a_key_changes_only_the_own_one(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        alices, bobs = self.two_connected(fake, alice, bob)
        alices_before = stored_key(alice)

        athlete(fake, "i-bob-2")
        bobs.call("PUT", URL, {"api_key": "bobs-new-key"})

        assert stored_key(alice) == alices_before
        assert ProviderConnection.objects.get(owner=alice).api_key == KEY
        assert ProviderConnection.objects.get(owner=bob).api_key == "bobs-new-key"

    def test_removing_removes_only_the_own_one(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        alices, bobs = self.two_connected(fake, alice, bob)

        bobs.call("DELETE", URL)

        assert ProviderConnection.objects.get().owner == alice
        assert alices.call("GET", URL).json()["connected"] is True

    def test_checking_uses_only_the_own_key_and_cannot_reach_another_users(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        alices, bobs = self.two_connected(fake, alice, bob)
        fake.requests.clear()

        bobs.call("POST", CHECK)

        [request] = fake.requests
        sent = base64.b64decode(request["headers"]["Authorization"][6:]).decode()
        assert sent == f"API_KEY:{OTHER_KEY}"

    def test_a_user_without_a_connection_gets_nothing_of_anothers(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        signed_in(alice).call("PUT", URL, {"api_key": KEY})
        bobs = signed_in(bob)

        assert bobs.call("GET", URL).json() == {"connected": False}
        assert bobs.call("POST", CHECK).status_code == HTTPStatus.NOT_FOUND
        assert bobs.call("DELETE", URL).status_code == HTTPStatus.NO_CONTENT
        assert ProviderConnection.objects.get(owner=alice).api_key == KEY

    def test_an_administrator_sees_only_their_own_connection_too(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        admin = make_user("boss@example.com", staff=True)
        signed_in(alice).call("PUT", URL, {"api_key": KEY})
        admins = signed_in(admin)

        assert admins.call("GET", URL).json() == {"connected": False}
        assert admins.call("POST", CHECK).status_code == HTTPStatus.NOT_FOUND

    def test_no_user_id_in_the_request_changes_whose_connection_is_used(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        alices, bobs = self.two_connected(fake, alice, bob)

        response = bobs.call(
            "PUT", URL, {"api_key": "bobs-new-key", "owner": str(alice.pk), "id": 1}
        )

        assert response.status_code == HTTPStatus.OK
        assert ProviderConnection.objects.get(owner=alice).api_key == KEY


class TestTheKeyStaysSecret:
    def test_it_is_in_no_response_header_body_or_log_line(
        self, fake: FakeIntervals, alice: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        api = signed_in(alice)
        token = api.client.cookies["csrftoken"].value
        seen: list[str] = []

        def note(response: Any) -> None:
            seen.append(response.content.decode() + str(dict(response.headers)))

        note(api.call("PUT", URL, {"api_key": KEY}))
        note(api.call("GET", URL))
        note(api.call("POST", CHECK))
        for status, body in [(401, b"{}"), (503, b"{}"), (200, b"garbage"), (200, b'{"id": 5}')]:
            fake.status, fake.body = status, body
            note(api.call("PUT", URL, {"api_key": KEY}))
            note(api.call("POST", CHECK))
        for payload in ({"api_key": [KEY]}, {"api_key": KEY * 20}, {"api_key": {"k": KEY}}):
            note(api.call("PUT", URL, payload))
        note(
            api.client.generic(
                "PUT",
                URL,
                data=f'{{"api_key": "{KEY}",',
                content_type="application/json",
                headers={"X-CSRFToken": token},
            )
        )
        note(api.call("DELETE", URL))

        assert seen
        assert all(KEY not in text for text in seen)
        assert KEY not in caplog.text


class TestThrottling:
    def test_the_eleventh_save_within_a_minute_is_throttled(
        self, fake: FakeIntervals, alice: User
    ) -> None:
        api = signed_in(alice)
        for _ in range(10):
            assert api.call("PUT", URL, {"api_key": KEY}).status_code == HTTPStatus.OK

        response = api.call("PUT", URL, {"api_key": KEY})

        assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert "Retry-After" in response.headers
        assert len(fake.requests) == 10  # the throttled request never reached Intervals.icu

    def test_saving_and_checking_share_one_counter(self, fake: FakeIntervals, alice: User) -> None:
        api = signed_in(alice)
        for _ in range(5):
            api.call("PUT", URL, {"api_key": KEY})
            api.call("POST", CHECK)

        assert api.call("PUT", URL, {"api_key": KEY}).status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert api.call("POST", CHECK).status_code == HTTPStatus.TOO_MANY_REQUESTS

    def test_reading_and_removing_are_not_throttled(self, fake: FakeIntervals, alice: User) -> None:
        api = signed_in(alice)
        for _ in range(10):
            api.call("PUT", URL, {"api_key": KEY})

        assert api.call("GET", URL).status_code == HTTPStatus.OK
        assert api.call("DELETE", URL).status_code == HTTPStatus.NO_CONTENT

    def test_another_user_is_not_affected(
        self, fake: FakeIntervals, alice: User, bob: User
    ) -> None:
        alices = signed_in(alice)
        for _ in range(11):
            alices.call("PUT", URL, {"api_key": KEY})

        assert signed_in(bob).call("PUT", URL, {"api_key": KEY}).status_code == HTTPStatus.OK
