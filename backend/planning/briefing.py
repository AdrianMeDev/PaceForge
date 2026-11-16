"""What the coach is told about an athlete when it drafts a week: a fixed, bounded set of facts.

``build_briefing`` turns the planning context and a few more rows into plain JSON data; the prompt
(``planning.prompt``) wraps it, nothing else is ever sent. What is in it: the week and today,
what each day offers, the zone tables of the zone systems the athlete can use, the active goals,
the minutes done in recent weeks, the athlete's injuries (a body part and sports from a fixed
list), the limits of the rules that follow from the athlete's intensity level (``limits``), a
summary of last week's confirmed plan and how that week went (``previous_week_review``: numbers
and one fixed word, no free text; see ``reviews.briefing``).

What is not in it: names, e-mail addresses, activity names or descriptions, ids of any kind, the
thresholds of sports without zones, the provider settings. The only free text is the title and
notes of a goal, cut to ``GOAL_NOTES_MAX`` characters, and the athlete's text about their
limitations, cut to ``LIMITATIONS_TEXT_MAX_TOLD`` characters and only if the athlete switched
that on, and the reason and the details of the week in the confirmed season plan (the coach's
own words from that plan, cut to their limits); the prompt says that they are data and not
instructions. Size is bounded by construction
(``MAX_GOALS``, ``MAX_LIMITATIONS_TOLD``, the fixed zone tables) and checked in the tests against
``MAX_BYTES``.
"""

import json
from datetime import date, timedelta
from typing import Any

from django.db.models import Case, F, IntegerField, Value, When

from accounts.models import User
from athletes import best_times
from athletes.thresholds import all_candidates
from athletes.zones import ZoneSet, heart_rate_zones, pace_zones, power_zones
from goals.assessing import assessment_data, facts_of, form_from
from goals.models import Goal
from goals.realism import Form, assess
from goals.services import today_of
from reviews.services import WeekReview, week_summary
from season.schema import DETAIL_MAX, REASON_MAX
from season.weeks import SeasonWeekFacts

from .context import PlanContext, build_context
from .models import PlannedWorkout, WeeklyPlan
from .schema import Slot, Sport, ZoneSystem

# At most this many active goals are told, the main goal first; the rest is only counted.
MAX_GOALS = 5
# Goal notes are cut here (the model allows more); titles are short enough already.
GOAL_NOTES_MAX = 300
# At most this many current limitations are told, the newest first; the rest is only counted.
MAX_LIMITATIONS_TOLD = 10
# The free text about limitations is cut here, and only told if the athlete allowed it.
LIMITATIONS_TEXT_MAX_TOLD = 150
# The most the JSON of a briefing may take, measured in UTF-8 bytes with every free-text
# character as a six-byte escape (a control character), the worst a character can cost. It was
# 20 000 until the wishes for a week left 54 bytes of room, and 24 000 until the assessment of
# every goal came with it; 28 000 is still a few thousand tokens.
MAX_BYTES = 28_000

# The sport groups of the athlete's thresholds.
_THRESHOLD_SPORT = {Sport.CYCLING: "ride", Sport.RUNNING: "run"}


def build_briefing(user: User, monday: date) -> dict[str, Any]:
    """The briefing for the week that starts on ``monday``, as JSON-compatible data.

    The same data gives the same briefing. The number of queries does not depend on how much
    data there is.
    """
    context = build_context(user, monday)  # raises ValueError unless it is a Monday
    today = today_of(user)
    held = all_candidates(user, list(context.best_times))
    goals, goals_not_shown = _goals(user, today, form_from(list(context.best_times), held))
    return {
        "week_start": monday.isoformat(),
        "today": today.isoformat(),
        "days": _days(context),
        "weekly_budget_minutes": context.weekly_budget,
        "weekly_minutes_available": context.weekly_minutes,
        "zone_systems": _zone_systems(context, held),
        "goals": goals,
        "goals_not_shown": goals_not_shown,
        "recent_weeks_minutes": list(context.recent_weeks),
        # The athlete's own idea of a normal week; zero says nothing, so it is not told.
        "typical_weekly_minutes": context.typical_weekly_minutes or None,
        # The sports the athlete wants (all four if none was chosen), in the order of the format,
        # and whether stretching may be added to sessions.
        "sports": [sport.value for sport in Sport if sport in context.sports],
        "stretching": context.stretching,
        # The wishes for a week (``null``: none) and the dates of the long sessions of the week.
        "training_days": context.training_days,
        "min_weekly_minutes": context.min_weekly_minutes,
        "long_days": _long_days(context),
        "sport_preferences": _sport_preferences(context),
        "strength_focus": context.strength_focus,
        "athlete": _athlete(context),
        "best_times": _best_times(context),
        "vdot": _vdot(context),
        "fixed_sessions": _fixed_sessions(context),
        "limits": _limits(context),
        "limitations": _limitations(context),
        "limitations_not_shown": max(0, len(context.limitations) - MAX_LIMITATIONS_TOLD),
        "limitations_text": (
            context.limitations_text[:LIMITATIONS_TEXT_MAX_TOLD]
            if context.limitations_text
            else None
        ),
        "season_week": season_week_data(context.season_week),
        "previous_week_plan": _previous_week(user, monday),
        "previous_week_review": _previous_week_review(user, monday),
    }


def season_week_data(facts: SeasonWeekFacts | None) -> dict[str, Any] | None:
    """What the confirmed season plan says about the week: the phase and the minutes of the
    skeleton, and what the coach filled in then. ``null`` if there is no confirmed plan or the
    week is not in it. The reason and the detail of a key session are the coach's own words from
    that plan, cut to their limits: data, never instructions. Races are told by day and priority
    (the titles are in ``goals``)."""
    if facts is None:
        return None
    return {
        "phase": facts.phase.value,
        "recovery": facts.recovery,
        "target_minutes": facts.target_minutes,
        "minutes": [{"sport": sport.value, "minutes": amount} for sport, amount in facts.minutes],
        "total_minutes": facts.total_minutes,
        "focus": facts.focus.value,
        "key_sessions": [
            {
                "sport": session.sport.value,
                "kind": session.kind.value,
                "minutes": session.minutes,
                "detail": session.detail[:DETAIL_MAX],
            }
            for session in facts.key_sessions
        ],
        "reason": facts.reason[:REASON_MAX],
        "races": [
            {"date": race.day.isoformat(), "priority": race.priority} for race in facts.races
        ],
    }


def _long_days(context: PlanContext) -> list[dict[str, str]]:
    """The day of this week on which the athlete wants the long session of a sport, as a date."""
    return [
        {"sport": sport.value, "date": (context.week_start + timedelta(days=offset)).isoformat()}
        for sport, offset in context.long_days
    ]


def _sport_preferences(context: PlanContext) -> list[dict[str, Any]]:
    """What the athlete said about each sport they said something about: its role and the least
    and the most sessions a week they want of it (``null`` for what they did not say)."""
    return [
        {
            "sport": facts.sport.value,
            "role": facts.role,
            "sessions_min": facts.sessions_min,
            "sessions_max": facts.sessions_max,
        }
        for facts in context.sport_preferences
    ]


def _athlete(context: PlanContext) -> dict[str, Any]:
    """What the athlete said about their body and training: the age (not the birth year), the sex,
    the weight, the resting heart rate, the years of training of the sports they named, the
    experience with strength training and the equipment for it. Numbers and fixed words; ``null``
    for what was not said."""
    facts = context.athlete
    return {
        "age": facts.age,
        "sex": facts.sex,
        "weight_kg": facts.weight_kg,
        "resting_hr": facts.resting_hr,
        "training_years": [
            {"sport": sport.value, "years": years} for sport, years in facts.training_years
        ],
        "strength_experience": facts.strength_experience,
        "strength_equipment": list(facts.strength_equipment),
    }


def _best_times(context: PlanContext) -> list[dict[str, Any]]:
    """The athlete's running best times in the order of the distances: the distance (a fixed
    word), the time in seconds, the day of the race, the VDOT, whether the race is recent enough to
    count and whether this is the one that the threshold pace comes from."""
    counted = best_times.counting(list(context.best_times))
    return [
        {
            "distance": entry.distance,
            "seconds": entry.seconds,
            "date": entry.date.isoformat(),
            "vdot": round(entry.vdot, 1),
            "recent": entry.recent,
            "counts": entry == counted,
        }
        for entry in context.best_times
    ]


def _vdot(context: PlanContext) -> float | None:
    """The VDOT of the best time that counts; ``null`` if none does."""
    counted = best_times.counting(list(context.best_times))
    return None if counted is None else round(counted.vdot, 1)


def _fixed_sessions(context: PlanContext) -> list[dict[str, Any]]:
    """The sessions that happen every week, as the date of this week on which each one lies, the
    sport, the minutes and the part of the day (``null``: none named). Fixed words and numbers."""
    return [
        {
            "date": (context.week_start + timedelta(days=fixed.weekday)).isoformat(),
            "sport": fixed.sport.value,
            "minutes": fixed.minutes,
            "slot": fixed.slot.value if fixed.slot else None,
        }
        for fixed in context.fixed_sessions
    ]


def _limits(context: PlanContext) -> dict[str, int]:
    """The limits of the rules that depend on the athlete: they are in the briefing and not in the
    system prompt, so that the prompt is the same for every athlete."""
    limits = context.limits
    return {
        "max_hard_days": limits.max_hard_days,
        "progression_warning_percent": limits.progression_warning_percent,
        "progression_error_percent": limits.progression_error_percent,
        "easy_share_percent": limits.easy_share_percent,
    }


def _limitations(context: PlanContext) -> list[dict[str, Any]]:
    """The current injuries and limitations, the newest first, as the body part (a fixed word)
    and the sports it affects in the order of the format. No text of the athlete."""
    return [
        {
            "body_part": entry.body_part,
            "sports": [sport.value for sport in Sport if sport in entry.sports],
        }
        for entry in context.limitations[:MAX_LIMITATIONS_TOLD]
    ]


def to_json(briefing: dict[str, Any]) -> str:
    """The briefing as text: sorted keys and no spaces, so the same briefing is the same text."""
    return json.dumps(briefing, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _days(context: PlanContext) -> list[dict[str, Any]]:
    return [
        {
            "date": (context.week_start + timedelta(days=offset)).isoformat(),
            "minutes": context.minutes[offset],
            "absence": context.absences[offset],
            # Whether two workouts are allowed, and the parts of the day that are open, in the
            # order of the day.
            "double_allowed": context.double_days[offset],
            "slots": [slot.value for slot in Slot if slot in context.time_windows[offset]],
        }
        for offset in range(7)
    ]


def _zone_systems(context: PlanContext, held: dict[tuple[str, str], list[Any]]) -> list[Any]:
    result = []
    for sport, system in sorted(context.zone_systems):
        group = _THRESHOLD_SPORT[sport]
        zone_set = _zone_set(system, group, held)
        if zone_set is None:  # cannot happen for a usable system; never send half a table
            continue
        result.append(
            {
                "sport": sport.value,
                "system": system.value,
                "threshold": {
                    "metric": zone_set.basis,
                    "value": held[(group, zone_set.basis)][0].value,
                },
                "zones": [
                    {
                        "zone": zone.number,
                        "name": zone.name,
                        "lower": zone.lower,
                        "upper": zone.upper,
                        "unit": zone.unit,
                    }
                    for zone in zone_set.zones
                ],
            }
        )
    return result


def _zone_set(
    system: ZoneSystem, group: str, held: dict[tuple[str, str], list[Any]]
) -> ZoneSet | None:
    def value(metric: str) -> float | None:
        found = held.get((group, metric))
        return found[0].value if found else None

    if system is ZoneSystem.POWER:
        return power_zones(value("ftp"))
    if system is ZoneSystem.PACE:
        return pace_zones(value("threshold_pace"))
    return heart_rate_zones(value("lthr"), value("max_hr"))


def _goals(user: User, today: date, form: Form) -> tuple[list[dict[str, Any]], int]:
    active = Goal.objects.for_user(user).filter(status=Goal.Status.ACTIVE)
    # A (main), then B (secondary), then C (preparation race); a goal without a date comes last.
    rank = Case(
        When(priority=Goal.Priority.MAIN, then=Value(0)),
        When(priority=Goal.Priority.SECONDARY, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    ordered = active.annotate(rank=rank).order_by(
        "rank", F("target_date").asc(nulls_last=True), "created_at", "id"
    )
    shown = [_goal(goal, today, form) for goal in ordered[:MAX_GOALS]]
    return shown, max(active.count() - MAX_GOALS, 0)


def _goal(goal: Goal, today: date, form: Form) -> dict[str, Any]:
    return {
        "priority": goal.priority,
        "kind": goal.kind,
        "title": goal.title,
        "notes": goal.notes[:GOAL_NOTES_MAX],
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "days_until": (goal.target_date - today).days if goal.target_date else None,
        "discipline": goal.discipline or None,
        "distance_m": goal.distance_m,
        "target_time_seconds": goal.target_time_seconds,
        "metric": goal.metric or None,
        "target_value": goal.target_value,
        # Whether the target is realistic, judged by code from the athlete's form and the time left
        # (``goals.realism``); ``null`` for a goal that has no target to judge.
        "assessment": None
        if goal.kind == Goal.Kind.GENERAL
        else assessment_data(assess(facts_of(goal), form, today)),
    }


def _previous_week(user: User, monday: date) -> list[dict[str, Any]]:
    """The confirmed plan of the week before, one entry per workout: no titles, no notes."""
    previous = monday - timedelta(days=7)
    rows = (
        PlannedWorkout.objects.for_user(user)
        .filter(plan__week_start=previous, plan__status=WeeklyPlan.Status.CONFIRMED)
        .order_by("day", "position", "id")
        .values_list("day", "sport", "goal", "duration_minutes")
    )
    return [
        {"day": (day - previous).days, "sport": sport, "goal": goal, "minutes": minutes}
        for day, sport, goal, minutes in rows
    ]


def _previous_week_review(user: User, monday: date) -> dict[str, Any] | None:
    """How the week before went, from the review of the user: numbers and one fixed word (what a
    review of that week recommended for the next one), never a title, a note or the comment of the
    coach itself. ``None`` when that week has not begun or has nothing in it."""
    review = week_summary(user, monday - timedelta(days=7))
    if review is None:
        return None
    total = review.comparison.total
    feedback = review.feedback
    return {
        "statuses": {status.value: count for status, count in review.comparison.statuses.items()},
        "planned_minutes": total.planned_minutes,
        "done_minutes": total.actual_minutes,
        "unplanned_sessions": len(review.match.unplanned),
        "rated_sessions": total.rated_count,
        "mean_rpe": _mean_rpe(review),
        "feedback": (
            None
            if feedback is None
            else {
                "fatigue": feedback.fatigue,
                "motivation": feedback.motivation,
                "pain": feedback.pain,
            }
        ),
        "next_week": review.comment.next_week if review.comment is not None else None,
    }


def _mean_rpe(review: WeekReview) -> float | None:
    """The mean of the ratings of the sessions of the week, one decimal; ``None`` without any."""
    ratings = [activity.rpe for activity in review.activities if activity.rpe is not None]
    return round(sum(ratings) / len(ratings), 1) if ratings else None
