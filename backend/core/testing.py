"""Helpers for the isolation tests that every owned resource should have.

Usage in a test: authenticate an ``APIClient`` as user B, then assert that user A's object is
invisible to B::

    assert_cannot_access(client_of_b, f"/api/notes/{note_of_a.pk}/", payload={"title": "x"})
    assert_not_listed(client_of_b, "/api/notes/", note_of_a.pk)
"""

from typing import Any

from rest_framework import status
from rest_framework.test import APIClient

UNSAFE_AND_SAFE_METHODS = ("get", "put", "patch", "delete")


def assert_cannot_access(
    client: APIClient, detail_url: str, *, payload: dict[str, Any] | None = None
) -> None:
    """Every method on another user's object must answer 404 (not 403, which would leak it)."""
    for method in UNSAFE_AND_SAFE_METHODS:
        response = getattr(client, method)(detail_url, payload or {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND, (
            f"{method.upper()} {detail_url} returned {response.status_code}, expected 404"
        )


def assert_not_listed(client: APIClient, list_url: str, object_id: Any) -> None:
    response = client.get(list_url)
    assert response.status_code == status.HTTP_200_OK
    assert str(object_id) not in {str(item["id"]) for item in response.json()}
