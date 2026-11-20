import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import generate_totp_secret
from django.db import connection, models

from accounts.models import User
from accounts.services.export import (
    EXPORT_VERSION,
    INTEGRATION_EXPORT_FIELDS,
    _integration_row,
    build_user_export,
)
from activities.models import Activity, ActivityFile
from athletes.models import AthleteProfile, BestTime, ThresholdValue
from availability.models import (
    AvailabilitySettings,
    FixedSession,
    Limitation,
    SportPreference,
    UnavailablePeriod,
    WeekdayMinutes,
)
from chat.models import ChatMessage
from coach.models import AIModelPrice, AIProviderConfiguration, AIUsageRecord
from core.fields import EncryptedTextField
from goals.models import Goal
from integrations.models import ProviderConnection
from jobs.models import JobRun, JobSettings
from planning.models import PlannedWorkout, WeeklyPlan
from reviews.models import WeekComment, WeekFeedback, WorkoutReview
from season.models import SeasonPlanVersion
from wellness.models import DailyWellness

pytestmark = pytest.mark.django_db

PASSWORD = "export-test-password"
AI_KEY = "sk-export-ai-key"
INTERVALS_KEY = "export-intervals-key"
TOTP_SECRET = generate_totp_secret()
BINARY_MARKER = b"TRACKPOINT-MARKER"


def make_user(email: str) -> User:
    return User.objects.create_user(email, PASSWORD, display_name=f"Name of {email}")


def populate(user: User, tag: str) -> None:
    """One record of every personal model, with ``tag`` in the text so that a leak is visible."""
    AthleteProfile.objects.create(owner=user, timezone="Europe/Berlin", weight_kg=70)
    ThresholdValue.objects.create(
        owner=user, sport="run", metric="lthr", value=170, source="manual", basis=tag
    )
    BestTime.objects.create(owner=user, distance="5k", seconds=1500, date=date(2025, 5, 1))

    AvailabilitySettings.objects.create(owner=user, weekly_budget_minutes=300)
    WeekdayMinutes.objects.create(owner=user, weekday=1, minutes=60)
    SportPreference.objects.create(owner=user, sport="running", role="goal")
    FixedSession.objects.create(owner=user, weekday=2, sport="running", minutes=45)
    UnavailablePeriod.objects.create(
        owner=user,
        kind="vacation",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 8),
        note=tag,
    )
    Limitation.objects.create(owner=user, body_part="knee")

    Goal.objects.create(owner=user, kind="general", title=f"Goal {tag}")

    activity = Activity.objects.create(
        owner=user,
        source="fit_file",
        source_hash=f"hash-{tag}".ljust(64, "0"),
        sport="running",
        start_time=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
        distance_m=10000,
        notes=f"Note {tag}",
        laps=[{"seconds": 300}],
        best_efforts={"power": {"5": 300}},
    )
    ActivityFile.for_activity(activity, BINARY_MARKER + tag.encode()).save()
    Activity.objects.create(
        owner=user,
        source="intervals_icu",
        external_id=f"external-{tag}",
        sport="cycling",
        start_time=datetime(2026, 3, 2, 8, 0, tzinfo=UTC),
    )

    DailyWellness.objects.create(owner=user, day=date(2026, 3, 1), hrv=55.5)

    SeasonPlanVersion.objects.create(owner=user, request=f"Season {tag}")
    plan = WeeklyPlan.objects.create(owner=user, week_start=date(2026, 3, 2), note=f"Week {tag}")
    workout = PlannedWorkout.objects.create(
        owner=user,
        plan=plan,
        day=date(2026, 3, 3),
        sport="running",
        title=f"Workout {tag}",
        goal="endurance",
        duration_minutes=45,
    )
    WorkoutReview.objects.create(owner=user, workout=workout, activity=activity, status="done")
    WeekFeedback.objects.create(owner=user, week_start=date(2026, 3, 2), notes=f"Feedback {tag}")
    WeekComment.objects.create(
        owner=user, week_start=date(2026, 3, 2), comment=f"Comment {tag}", next_week="hold"
    )
    ChatMessage.objects.create(owner=user, role="coach", text=f"Message {tag}", plan=plan)

    AIProviderConfiguration.objects.create(
        owner=user, provider="anthropic", model=f"model-{tag}", api_key=AI_KEY
    )
    AIUsageRecord.objects.create(
        owner=user, provider="anthropic", model=f"model-{tag}", purpose="chat", outcome="success"
    )
    AIModelPrice.objects.create(
        owner=user,
        model=f"model-{tag}",
        input_per_million=Decimal("3.5"),
        output_per_million=Decimal("15"),
    )
    ProviderConnection.objects.create(
        owner=user, provider="intervals_icu", api_key=INTERVALS_KEY, athlete_id=f"i-{tag}"
    )
    JobSettings.objects.create(owner=user)
    JobRun.objects.create(owner=user, job="sync", outcome="done")


def add_secrets(user: User) -> None:
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": TOTP_SECRET},
    )
    RecoveryCodes.activate(user)


def test_an_empty_account_exports_its_own_data_only() -> None:
    user = make_user("empty@example.com")

    data = build_user_export(user)

    assert data["version"] == EXPORT_VERSION
    assert data["account"] == {
        "email": "empty@example.com",
        "display_name": "Name of empty@example.com",
        "date_joined": data["account"]["date_joined"],
    }
    assert data["profile"] == {"athlete": None, "thresholds": [], "best_times": []}
    assert data["availability"]["settings"] is None
    assert data["plans"] == {"season": [], "weeks": []}
    assert data["coach"] == {"provider": None, "usage": [], "prices": []}
    assert data["automation"]["settings"] is None
    for section in ("goals", "activities", "wellness", "chat", "integrations"):
        assert data[section] == []
    json.dumps(data)


def test_a_populated_account_exports_every_domain() -> None:
    user = make_user("full@example.com")
    populate(user, "alpha")

    data = build_user_export(user)

    assert json.loads(json.dumps(data)) == data
    assert data["account"]["email"] == "full@example.com"
    assert data["profile"]["athlete"]["timezone"] == "Europe/Berlin"
    assert data["profile"]["thresholds"][0]["value"] == 170
    assert data["profile"]["best_times"][0]["seconds"] == 1500
    availability = data["availability"]
    assert availability["settings"]["weekly_budget_minutes"] == 300
    assert availability["weekdays"][0]["minutes"] == 60
    assert availability["sport_preferences"][0]["sport"] == "running"
    assert availability["fixed_sessions"][0]["minutes"] == 45
    assert availability["unavailable_periods"][0]["start_date"] == "2026-07-01"
    assert availability["limitations"][0]["body_part"] == "knee"
    assert data["goals"][0]["title"] == "Goal alpha"
    assert {a["sport"] for a in data["activities"]} == {"running", "cycling"}
    running = next(a for a in data["activities"] if a["sport"] == "running")
    assert running["laps"] == [{"seconds": 300}]
    assert running["start_time"].startswith("2026-03-01T08:00:00")
    assert data["wellness"][0]["hrv"] == 55.5
    assert data["plans"]["season"][0]["request"] == "Season alpha"
    (week,) = data["plans"]["weeks"]
    assert [w["title"] for w in week["workouts"]] == ["Workout alpha"]
    assert "plan_id" not in week["workouts"][0]
    assert data["reviews"]["workouts"][0]["workout_id"] == week["workouts"][0]["id"]
    assert data["reviews"]["week_feedback"][0]["notes"] == "Feedback alpha"
    assert data["reviews"]["week_comments"][0]["comment"] == "Comment alpha"
    assert data["chat"][0]["text"] == "Message alpha"
    assert data["chat"][0]["plan_id"] == week["id"]
    coach = data["coach"]
    assert coach["provider"]["model"] == "model-alpha"
    assert coach["provider"]["has_api_key"] is True
    assert coach["usage"][0]["purpose"] == "chat"
    assert coach["prices"][0]["input_per_million"] == "3.5000"
    assert data["integrations"][0]["athlete_id"] == "i-alpha"
    assert data["automation"]["settings"]["sync"] is True
    assert data["automation"]["runs"][0]["job"] == "sync"


def test_secrets_and_binary_files_are_not_exported() -> None:
    user = make_user("secret@example.com")
    populate(user, "alpha")
    add_secrets(user)
    codes = RecoveryCodes.activate(user).get_unused_codes()

    data = build_user_export(user)
    text = json.dumps(data)

    for secret in (user.password, AI_KEY, INTERVALS_KEY, TOTP_SECRET, *codes):
        assert secret and secret not in text
    assert BINARY_MARKER.decode() not in text
    assert "password" not in data["account"]
    for key in ("api_key", "source_hash", "external_id", "best_efforts", "file", "data"):
        assert not any(key in activity for activity in data["activities"])
    assert "api_key" not in data["coach"]["provider"]
    assert "api_key" not in data["integrations"][0]
    assert "hash-alpha" not in text
    assert "external-alpha" not in text


@pytest.mark.parametrize("synced", [False, True])
def test_integration_export_contains_exact_metadata(synced: bool) -> None:
    user = make_user("integration@example.com")
    ProviderConnection.objects.create(
        owner=user,
        provider="intervals_icu",
        api_key=INTERVALS_KEY,
        athlete_id="i-export",
        status="invalid",
        connected_at=datetime(2026, 3, 1, 8, tzinfo=UTC),
        last_checked_at=datetime(2026, 3, 2, 9, tzinfo=UTC),
        last_sync_at=datetime(2026, 3, 2, 8, tzinfo=UTC) if synced else None,
        last_sync_error="invalid_key" if synced else "",
    )

    data = build_user_export(user)

    assert data["integrations"] == [
        {
            "provider": "intervals_icu",
            "athlete_id": "i-export",
            "status": "invalid",
            "connected_at": "2026-03-01T08:00:00Z",
            "last_checked_at": "2026-03-02T09:00:00Z",
            "last_sync_at": "2026-03-02T08:00:00Z" if synced else None,
            "last_sync_error": "invalid_key" if synced else "",
        }
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT api_key FROM integrations_providerconnection WHERE owner_id = %s", [user.pk]
        )
        (ciphertext,) = cursor.fetchone()
    assert ciphertext.startswith("enc:v1:")
    text = json.dumps(data)
    assert INTERVALS_KEY not in text
    assert ciphertext not in text


def test_integration_allowlist_excludes_credentials_and_internal_fields() -> None:
    assert set(INTEGRATION_EXPORT_FIELDS) == {
        "provider",
        "athlete_id",
        "status",
        "connected_at",
        "last_checked_at",
        "last_sync_at",
        "last_sync_error",
    }
    assert not {"owner", "id"}.intersection(INTEGRATION_EXPORT_FIELDS)
    for name in INTEGRATION_EXPORT_FIELDS:
        assert not isinstance(ProviderConnection._meta.get_field(name), EncryptedTextField)


def test_integration_export_omits_future_plain_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = ProviderConnection(provider="intervals_icu", athlete_id="i-export")
    plain_field = models.TextField()
    plain_field.set_attributes_from_name("future_token")
    monkeypatch.setattr(
        ProviderConnection._meta,
        "concrete_fields",
        (*ProviderConnection._meta.concrete_fields, plain_field),
    )
    monkeypatch.setattr(instance, "future_token", "future-credential-marker", raising=False)

    row = _integration_row(instance)

    assert set(row) == set(INTEGRATION_EXPORT_FIELDS)
    assert "future_token" not in row
    assert "future-credential-marker" not in row.values()


def test_the_export_of_one_user_has_nothing_of_another() -> None:
    first = make_user("first@example.com")
    second = make_user("second@example.com")
    populate(first, "alpha")
    populate(second, "bravo")
    add_secrets(second)

    first_text = json.dumps(build_user_export(first))
    second_text = json.dumps(build_user_export(second))

    assert "alpha" in first_text
    assert "bravo" not in first_text
    assert "second@example.com" not in first_text
    assert str(second.pk) not in first_text
    assert "alpha" not in second_text
    assert "first@example.com" not in second_text
    for ids in (
        Activity.objects.for_user(second).values_list("id", flat=True),
        PlannedWorkout.objects.for_user(second).values_list("id", flat=True),
        ChatMessage.objects.for_user(second).values_list("id", flat=True),
    ):
        assert all(str(pk) not in first_text for pk in ids)
