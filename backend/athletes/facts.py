"""The body and training data of a user as plain values, for what is told to the coach.

One query. Only what the user said is given; ``None``, an empty tuple or an empty list says
nothing. The birth year is turned into an age by the caller, who knows which day it is.
"""

from dataclasses import dataclass

from accounts.models import User

from .models import YEARS_SPORTS, AthleteProfile


@dataclass(frozen=True)
class BodyAndTraining:
    birth_year: int | None = None
    sex: str | None = None
    weight_kg: float | None = None
    resting_hr: int | None = None
    # (sport, whole years) for the sports the user said something about, in the order of
    # ``YEARS_SPORTS``.
    training_years: tuple[tuple[str, int], ...] = ()
    strength_experience: str | None = None
    # In the order of ``Equipment``.
    strength_equipment: tuple[str, ...] = ()


def body_and_training(user: User) -> BodyAndTraining:
    profile = AthleteProfile.objects.for_user(user).first()
    if profile is None:
        return BodyAndTraining()
    years = (
        (sport, value)
        for sport in YEARS_SPORTS
        if (value := getattr(profile, f"years_{sport}")) is not None
    )
    return BodyAndTraining(
        birth_year=profile.birth_year,
        sex=profile.sex or None,
        weight_kg=profile.weight_kg,
        resting_hr=profile.resting_hr,
        training_years=tuple(years),
        strength_experience=profile.strength_experience or None,
        strength_equipment=tuple(profile.equipment),
    )
