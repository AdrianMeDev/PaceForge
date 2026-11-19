from typing import Any

import pytest
from django.test import Client

HEALTH_URL = "/api/health/"


@pytest.fixture
def strict_hosts(settings: Any) -> None:
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["paceforge.example.com"]


@pytest.mark.usefixtures("strict_hosts")
def test_health_is_ok_anonymously_for_an_allowed_host() -> None:
    response = Client().get(HEALTH_URL, headers={"host": "paceforge.example.com"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.usefixtures("strict_hosts")
def test_health_rejects_a_disallowed_host() -> None:
    response = Client().get(HEALTH_URL, headers={"host": "evil.example.org"})

    assert response.status_code == 400
