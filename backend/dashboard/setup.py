"""Which steps of the setup an athlete has done, worked out from the data they have entered.

The steps are in the order a new account should take them. Nothing is stored: a step is done
because its data exists, so a deleted goal opens its step again. Every step is one ``exists()``
query on the data of the user it is given, so the number of queries does not depend on the data.
"""

from dataclasses import dataclass

from django.db.models import Model

from accounts.models import User
from activities.models import Activity
from athletes.models import AthleteProfile
from availability.models import WeekdayMinutes
from coach.models import AIProviderConfiguration
from goals.models import Goal
from integrations.models import ProviderConnection
from planning.models import WeeklyPlan
from season.models import SeasonPlanVersion


@dataclass(frozen=True)
class SetupStep:
    """One step: ``key`` names it for the page, ``optional`` steps are not needed for "all done"."""

    key: str
    done: bool
    optional: bool = False


def _has(user: User, model: type[Model], **filters: object) -> bool:
    return model._default_manager.filter(owner=user, **filters).exists()


def setup_of(user: User) -> tuple[SetupStep, ...]:
    return (
        SetupStep("profile", _has(user, AthleteProfile, timezone__gt="")),
        SetupStep("training_time", _has(user, WeekdayMinutes, minutes__gt=0)),
        SetupStep("ai_coach", _has(user, AIProviderConfiguration)),
        SetupStep("intervals", _has(user, ProviderConnection), optional=True),
        SetupStep("goal", _has(user, Goal, status=Goal.Status.ACTIVE)),
        SetupStep("activities", _has(user, Activity)),
        SetupStep(
            "season", _has(user, SeasonPlanVersion, status=SeasonPlanVersion.Status.CONFIRMED)
        ),
        SetupStep("first_week", _has(user, WeeklyPlan, status=WeeklyPlan.Status.CONFIRMED)),
    )
