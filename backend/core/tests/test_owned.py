from http import HTTPStatus
from types import SimpleNamespace
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView

from accounts.models import User
from core.permissions import IsOwner
from core.testing import assert_cannot_access, assert_not_listed
from core.tests.sample.models import Note
from core.views import authenticated_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _sample_urls(settings: Any) -> None:
    settings.ROOT_URLCONF = "core.tests.sample.urls"


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def alices_note(alice: User) -> Note:
    return Note.objects.create(owner=alice, title="alice's note")


def test_for_user_returns_only_own_objects(alice: User, bob: User, alices_note: Note) -> None:
    bobs_note = Note.objects.create(owner=bob, title="bob's note")

    assert list(Note.objects.for_user(alice)) == [alices_note]
    assert list(Note.objects.for_user(bob)) == [bobs_note]


def test_for_user_returns_nothing_for_anonymous_users(alices_note: Note) -> None:
    assert not Note.objects.for_user(AnonymousUser()).exists()


def test_list_contains_only_own_objects(alice: User, bob: User, alices_note: Note) -> None:
    Note.objects.create(owner=bob, title="bob's note")

    response = client_for(alice).get("/notes/")

    assert [item["id"] for item in response.json()] == [alices_note.pk]
    assert_not_listed(client_for(bob), "/notes/", alices_note.pk)


def test_foreign_objects_answer_404_for_every_method(bob: User, alices_note: Note) -> None:
    assert_cannot_access(
        client_for(bob), f"/notes/{alices_note.pk}/", payload={"title": "hijacked"}
    )

    alices_note.refresh_from_db()  # still exists, still unchanged
    assert alices_note.title == "alice's note"


def test_owner_can_read_update_and_delete(alice: User, alices_note: Note) -> None:
    client = client_for(alice)
    url = f"/notes/{alices_note.pk}/"

    assert client.get(url).status_code == HTTPStatus.OK
    assert client.patch(url, {"title": "renamed"}, format="json").status_code == HTTPStatus.OK
    alices_note.refresh_from_db()
    assert alices_note.title == "renamed"
    assert client.delete(url).status_code == HTTPStatus.NO_CONTENT
    assert not Note.objects.filter(pk=alices_note.pk).exists()


@pytest.mark.parametrize("base_url", ["/notes", "/writable-owner-notes"])
def test_owner_is_taken_from_the_session_on_create(base_url: str, alice: User, bob: User) -> None:
    response = client_for(bob).post(
        f"{base_url}/", {"title": "mine", "owner": alice.pk}, format="json"
    )

    assert response.status_code == HTTPStatus.CREATED
    assert Note.objects.get(pk=response.json()["id"]).owner == bob


@pytest.mark.parametrize("base_url", ["/notes", "/writable-owner-notes"])
def test_owner_cannot_be_changed_by_update(
    base_url: str, alice: User, bob: User, alices_note: Note
) -> None:
    client = client_for(alice)

    patch_response = client.patch(f"{base_url}/{alices_note.pk}/", {"owner": bob.pk}, format="json")
    assert patch_response.status_code == HTTPStatus.OK
    alices_note.refresh_from_db()
    assert alices_note.owner == alice

    put_response = client.put(
        f"{base_url}/{alices_note.pk}/", {"title": "updated", "owner": bob.pk}, format="json"
    )
    assert put_response.status_code == HTTPStatus.OK
    alices_note.refresh_from_db()
    assert alices_note.title == "updated"
    assert alices_note.owner == alice


def test_read_only_owner_ignores_nonexistent_user_ids(alice: User, alices_note: Note) -> None:
    client = client_for(alice)
    nonexistent_user_id = 999999

    create_response = client.post(
        "/notes/", {"title": "mine", "owner": nonexistent_user_id}, format="json"
    )
    assert create_response.status_code == HTTPStatus.CREATED
    assert Note.objects.get(pk=create_response.json()["id"]).owner == alice

    patch_response = client.patch(
        f"/notes/{alices_note.pk}/", {"owner": nonexistent_user_id}, format="json"
    )
    assert patch_response.status_code == HTTPStatus.OK
    alices_note.refresh_from_db()
    assert alices_note.owner == alice

    put_response = client.put(
        f"/notes/{alices_note.pk}/",
        {"title": "updated", "owner": nonexistent_user_id},
        format="json",
    )
    assert put_response.status_code == HTTPStatus.OK
    alices_note.refresh_from_db()
    assert alices_note.title == "updated"
    assert alices_note.owner == alice


def test_anonymous_requests_are_refused(alices_note: Note) -> None:
    client = APIClient()

    assert client.get("/notes/").status_code == HTTPStatus.FORBIDDEN
    assert client.get(f"/notes/{alices_note.pk}/").status_code == HTTPStatus.FORBIDDEN


def test_anonymous_requests_are_refused_when_apiview_defaults_allow_any(
    monkeypatch: pytest.MonkeyPatch, alices_note: Note
) -> None:
    monkeypatch.setattr(APIView, "permission_classes", [AllowAny])
    client = APIClient()

    assert client.get("/notes/").status_code == HTTPStatus.FORBIDDEN
    assert client.get(f"/notes/{alices_note.pk}/").status_code == HTTPStatus.FORBIDDEN


def test_unscoped_queryset_fails_loudly_instead_of_leaking(alice: User) -> None:
    with pytest.raises(ImproperlyConfigured, match="OwnedModel"):
        client_for(alice).get("/unscoped/")


def test_is_owner_permission_checks_object_ownership(
    alice: User, bob: User, alices_note: Note
) -> None:
    permission = IsOwner()
    view = APIView()
    factory = APIRequestFactory()

    def request_as(user: User | AnonymousUser) -> Request:
        request = Request(factory.get("/"))
        request.user = user
        return request

    assert permission.has_object_permission(request_as(alice), view, alices_note)
    assert not permission.has_object_permission(request_as(bob), view, alices_note)
    assert not permission.has_object_permission(request_as(AnonymousUser()), view, alices_note)


def test_deleting_a_user_deletes_their_objects(alice: User, bob: User, alices_note: Note) -> None:
    bobs_note = Note.objects.create(owner=bob, title="bob's note")

    alice.delete()

    assert list(Note.objects.all()) == [bobs_note]


def test_authenticated_user_returns_authenticated_user(alice: User) -> None:
    request = Request(APIRequestFactory().get("/"))
    request.user = alice

    assert authenticated_user(request) == alice


def test_authenticated_user_rejects_anonymous_user() -> None:
    request = Request(APIRequestFactory().get("/"))
    request.user = AnonymousUser()

    with pytest.raises(NotAuthenticated):
        authenticated_user(request)


def test_authenticated_user_rejects_non_user_principal() -> None:
    request = Request(APIRequestFactory().get("/"))
    non_user: Any = SimpleNamespace(is_authenticated=True)
    request.user = non_user

    with pytest.raises(NotAuthenticated):
        authenticated_user(request)
