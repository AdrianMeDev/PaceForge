import pytest
from django.db import connection


@pytest.mark.django_db
def test_tests_run_against_postgresql() -> None:
    assert connection.vendor == "postgresql"

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
