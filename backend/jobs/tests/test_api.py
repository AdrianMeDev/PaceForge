"""Tests for the jobs API: settings toggles and the job run log."""

from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.testing import assert_not_listed
from jobs.models import Code, Job, JobRun, JobSettings, Outcome
from jobs.tests.conftest import make_user

pytestmark = pytest.mark.django_db

SETTINGS_URL = "/api/jobs/settings/"
RUNS_URL = "/api/jobs/runs/"


def _client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestAuthentication:
    def test_unauthenticated_requests_are_refused(self) -> None:
        anonymous = APIClient()

        assert anonymous.get(SETTINGS_URL).status_code == HTTPStatus.FORBIDDEN
        assert anonymous.patch(SETTINGS_URL, {"sync": False}, format="json").status_code == (
            HTTPStatus.FORBIDDEN
        )
        assert anonymous.get(RUNS_URL).status_code == HTTPStatus.FORBIDDEN


class TestJobSettingsApi:
    def test_get_defaults_without_creating_row(self) -> None:
        alice = make_user("alice@example.com")
        client = _client_for(alice)

        response = client.get(SETTINGS_URL)

        assert response.status_code == HTTPStatus.OK
        assert response.json() == {
            "sync": True,
            "week_review": True,
            "week_draft": True,
        }
        assert JobSettings.objects.filter(owner=alice).count() == 0

    def test_patch_creates_row_on_first_call_and_updates_existing(self) -> None:
        alice = make_user("alice@example.com")
        client = _client_for(alice)

        first = client.patch(SETTINGS_URL, {"sync": False}, format="json")
        assert first.status_code == HTTPStatus.OK
        assert first.json() == {
            "sync": False,
            "week_review": True,
            "week_draft": True,
        }
        assert JobSettings.objects.filter(owner=alice).count() == 1

        second = client.patch(
            SETTINGS_URL,
            {"week_review": False, "week_draft": False},
            format="json",
        )
        assert second.status_code == HTTPStatus.OK
        assert second.json() == {
            "sync": False,
            "week_review": False,
            "week_draft": False,
        }
        assert JobSettings.objects.filter(owner=alice).count() == 1

        stored = JobSettings.objects.get(owner=alice)
        assert (stored.sync, stored.week_review, stored.week_draft) == (False, False, False)

    @pytest.mark.parametrize(
        "payload",
        [
            {"sync": "false"},
            {"sync": "true"},
            {"sync": 1},
            {"week_review": 0},
            {"week_draft": None},
            {"sync": []},
            {"unknown": False},
            {"sync": True, "extra": 1},
            {},
            [],
        ],
    )
    def test_bad_values_return_400(self, payload: Any) -> None:
        alice = make_user("alice@example.com")
        client = _client_for(alice)

        response = client.patch(SETTINGS_URL, payload, format="json")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert JobSettings.objects.filter(owner=alice).count() == 0

    def test_settings_isolation(self) -> None:
        alice = make_user("alice@example.com")
        bob = make_user("bob@example.com")
        client_a = _client_for(alice)
        client_b = _client_for(bob)

        assert (
            client_a.patch(SETTINGS_URL, {"sync": False}, format="json").status_code
            == HTTPStatus.OK
        )

        # Bob still sees his own defaults.
        b_get = client_b.get(SETTINGS_URL)
        assert b_get.status_code == HTTPStatus.OK
        assert b_get.json() == {"sync": True, "week_review": True, "week_draft": True}

        # Bob's PATCH affects only Bob's row, never Alice's.
        b_patch = client_b.patch(SETTINGS_URL, {"week_draft": False}, format="json")
        assert b_patch.status_code == HTTPStatus.OK
        assert JobSettings.objects.get(owner=alice).sync is False
        assert JobSettings.objects.get(owner=alice).week_draft is True
        assert JobSettings.objects.get(owner=bob).sync is True
        assert JobSettings.objects.get(owner=bob).week_draft is False


class TestJobRunsApi:
    def test_lists_runs_with_expected_fields(self) -> None:
        alice = make_user("alice@example.com")
        client = _client_for(alice)
        t0 = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
        t1 = datetime(2026, 11, 19, 10, 1, tzinfo=UTC)
        older = JobRun.objects.create(
            owner=alice,
            job=Job.SYNC,
            week_start=None,
            started_at=t0,
            finished_at=t1,
            outcome=Outcome.DONE,
            code="",
            counts={"created": 3},
        )
        newer = JobRun.objects.create(
            owner=alice,
            job=Job.WEEK_DRAFT,
            week_start=date(2026, 11, 23),
            started_at=t0 + timedelta(hours=1),
            finished_at=t1 + timedelta(hours=1),
            outcome=Outcome.SKIPPED,
            code=Code.ALREADY_PLANNED,
            counts={},
        )

        response = client.get(RUNS_URL)

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert len(data) == 2
        assert [item["id"] for item in data] == [str(newer.pk), str(older.pk)]
        assert data[0] == {
            "id": str(newer.pk),
            "job": Job.WEEK_DRAFT,
            "week_start": "2026-11-23",
            "started_at": "2026-11-19T11:00:00Z",
            "finished_at": "2026-11-19T11:01:00Z",
            "outcome": Outcome.SKIPPED,
            "code": Code.ALREADY_PLANNED,
            "counts": {},
        }
        assert data[1]["week_start"] is None
        assert data[1]["code"] == ""
        assert data[1]["counts"] == {"created": 3}

    def test_limits_to_newest_50(self) -> None:
        alice = make_user("alice@example.com")
        client = _client_for(alice)
        base = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        created = [
            JobRun.objects.create(
                owner=alice,
                job=Job.SYNC,
                started_at=base + timedelta(minutes=index),
                finished_at=base + timedelta(minutes=index, seconds=5),
                outcome=Outcome.DONE,
                code="",
                counts={"created": index},
            )
            for index in range(55)
        ]

        response = client.get(RUNS_URL)

        assert response.status_code == HTTPStatus.OK
        data = response.json()
        assert len(data) == 50
        expected_ids = [str(run.pk) for run in reversed(created[5:])]
        assert [item["id"] for item in data] == expected_ids

    def test_runs_isolation(self) -> None:
        alice = make_user("alice@example.com")
        bob = make_user("bob@example.com")
        alices_run = JobRun.objects.create(
            owner=alice,
            job=Job.SYNC,
            outcome=Outcome.DONE,
            code="",
            counts={"created": 1},
        )
        bobs_run = JobRun.objects.create(
            owner=bob,
            job=Job.SYNC,
            outcome=Outcome.DONE,
            code="",
            counts={"created": 2},
        )

        client_b = _client_for(bob)
        assert_not_listed(client_b, RUNS_URL, alices_run.pk)
        assert [item["id"] for item in client_b.get(RUNS_URL).json()] == [str(bobs_run.pk)]
