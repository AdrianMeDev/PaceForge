from datetime import date, timedelta
from typing import Any

import pytest

from planning.rules import Finding, Severity
from planning.schema import Sport
from season import rules
from season.rules import (
    ALL_CHECKS,
    WINDOW_PERCENT,
    SeasonContext,
    check_capacity,
    check_key_sessions,
    check_minutes,
    check_races,
    check_sports,
    check_weeks,
    validate_season,
    window,
)
from season.schema import (
    Focus,
    KeySession,
    PlanWeek,
    SeasonPlan,
    SessionKind,
)
from season.skeleton import Race, Skeleton, SkeletonInputs, SkeletonWeek, build_skeleton

MONDAY = date(2026, 11, 16)
assert MONDAY.weekday() == 0


def skeleton(weeks: int = 6, *, capacity: int = 600, reference: int = 300) -> Skeleton:
    race = Race(MONDAY + timedelta(weeks=weeks - 1, days=6), "main", "running", 21_000, "Race")
    return build_skeleton(SkeletonInputs(MONDAY, (capacity,) * 52, (race,), reference, "normal"))


def follow(skel: Skeleton, *, races: bool = True) -> SeasonPlan:
    """A plan that does what the skeleton asks: all minutes in running, a race session in every
    week with a race (unless ``races`` is false)."""
    return SeasonPlan(
        tuple(
            PlanWeek(
                week.week_start,
                ((Sport.RUNNING, week.target_minutes),),
                Focus.ENDURANCE,
                "Because.",
                (KeySession(Sport.RUNNING, SessionKind.RACE, 1),) if races and week.races else (),
            )
            for week in skel.weeks
        )
    )


def change(plan: SeasonPlan, index: int, **fields: Any) -> SeasonPlan:
    weeks = list(plan.weeks)
    values = {**weeks[index].__dict__, **fields}
    weeks[index] = PlanWeek(**values)
    return SeasonPlan(tuple(weeks), plan.rationale)


def context(skel: Skeleton, sports: frozenset[Sport] | None = None) -> SeasonContext:
    return SeasonContext(skel, sports if sports is not None else frozenset(Sport))


def codes(findings: list[Finding]) -> list[str]:
    return [finding.code for finding in findings]


class TestAPlanThatFollowsTheSkeleton:
    @pytest.mark.parametrize("weeks", [1, 2, 6, 20, 52])
    def test_has_no_findings(self, weeks: int) -> None:
        skel = skeleton(weeks)

        report = validate_season(follow(skel), context(skel))

        assert report.findings == ()
        assert report.valid is True

    def test_the_rolling_skeleton_is_followed_too(self) -> None:
        skel = build_skeleton(SkeletonInputs(MONDAY, (400,) * 52, (), 300, "normal"))

        assert validate_season(follow(skel), context(skel)).findings == ()


class TestTheWindow:
    @pytest.mark.parametrize(
        ("target", "low", "high"),
        [(0, 0, 0), (1, 1, 1), (10, 9, 11), (100, 90, 110), (240, 216, 264), (255, 230, 280)],
    )
    def test_ten_percent_either_way_rounded_towards_the_target(
        self, target: int, low: int, high: int
    ) -> None:
        assert window(target) == (low, high)

    def test_the_percent_is_written_out_on_purpose(self) -> None:
        assert WINDOW_PERCENT == 10

    def test_the_low_end_is_never_above_the_target_nor_the_high_end_below(self) -> None:
        for target in range(0, 2000):
            low, high = window(target)

            assert low <= target <= high


class TestTheWeeks:
    def test_a_missing_week_is_named_once_for_the_number_and_once_for_the_place(self) -> None:
        skel = skeleton(6)
        plan = follow(skel)
        short = SeasonPlan(plan.weeks[:2] + plan.weeks[3:])

        found = check_weeks(short, context(skel))

        assert found == [
            Finding(
                Severity.ERROR,
                "weeks_mismatch",
                "The plan has 5 weeks; the season has 6, from 2026-11-16 to 2026-12-21.",
                "weeks",
            ),
            Finding(
                Severity.ERROR,
                "weeks_mismatch",
                "Week 3 must be the week of 2026-11-30.",
                "weeks[2].week_start",
            ),
        ]

    def test_an_extra_week_is_named_once(self) -> None:
        skel = skeleton(3)
        plan = follow(skel)
        extra = PlanWeek(MONDAY + timedelta(weeks=3), (), Focus.RECOVERY, "More.")

        found = check_weeks(SeasonPlan(plan.weeks + (extra,)), context(skel))

        assert codes(found) == ["weeks_mismatch"]
        assert found[0].path == "weeks"

    def test_the_right_number_of_wrong_weeks_is_named_at_the_first_wrong_one(self) -> None:
        skel = skeleton(4)
        plan = follow(skel)
        swapped = SeasonPlan((plan.weeks[0], plan.weeks[2], plan.weeks[1], plan.weeks[3]))

        found = check_weeks(swapped, context(skel))

        assert [f.path for f in found] == ["weeks[1].week_start"]

    def test_an_empty_plan_has_the_wrong_number_of_weeks(self) -> None:
        skel = skeleton(3)

        found = check_weeks(SeasonPlan(), context(skel))

        assert codes(found) == ["weeks_mismatch"]
        assert "has 0 weeks; the season has 3" in found[0].message

    def test_the_week_of_another_year_is_no_week_of_the_season(self) -> None:
        skel = skeleton(3)
        plan = change(follow(skel), 1, week_start=date(2025, 11, 17))

        assert codes(check_weeks(plan, context(skel))) == ["weeks_mismatch"]

    def test_the_other_checks_leave_a_week_that_is_not_in_the_season_alone(self) -> None:
        skel = skeleton(3)
        plan = change(
            follow(skel), 1, week_start=date(2025, 11, 17), minutes=((Sport.RUNNING, 99999),)
        )

        assert check_minutes(plan, context(skel)) == []
        assert check_capacity(plan, context(skel)) == []


class TestTheMinutes:
    def test_a_week_inside_the_window_is_fine_at_both_ends(self) -> None:
        skel = skeleton(6)
        target = skel.weeks[1].target_minutes
        low, high = window(target)

        for amount in (low, target, high):
            plan = change(follow(skel), 1, minutes=((Sport.RUNNING, amount),))

            assert check_minutes(plan, context(skel)) == []

    def test_a_week_just_outside_is_an_error_at_the_minutes(self) -> None:
        skel = skeleton(6)
        target = skel.weeks[1].target_minutes
        low, high = window(target)

        for amount in (low - 1, high + 1):
            plan = change(follow(skel), 1, minutes=((Sport.RUNNING, amount),))

            (found,) = check_minutes(plan, context(skel))

            assert (found.severity, found.code, found.path) == (
                Severity.ERROR,
                "minutes_outside_target",
                "weeks[1].minutes",
            )
            assert found.message == (
                f"The week of {skel.weeks[1].week_start} has {amount} minutes; the skeleton aims "
                f"for {target} (between {low} and {high})."
            )

    def test_the_minutes_of_all_sports_add_up(self) -> None:
        skel = skeleton(6)
        target = skel.weeks[1].target_minutes
        half = target // 2
        plan = change(
            follow(skel),
            1,
            minutes=((Sport.RUNNING, half), (Sport.CYCLING, target - half)),
        )

        assert check_minutes(plan, context(skel)) == []

    def test_a_week_without_a_target_must_have_no_minutes(self) -> None:
        skel = skeleton(6, capacity=0)
        plan = change(follow(skel), 2, minutes=((Sport.RUNNING, 1),))

        assert codes(check_minutes(plan, context(skel))) == ["minutes_outside_target"]
        assert check_minutes(follow(skel), context(skel)) == []

    def test_every_week_is_named_on_its_own(self) -> None:
        skel = skeleton(6)
        plan = change(change(follow(skel), 0, minutes=()), 3, minutes=())

        found = check_minutes(plan, context(skel))

        assert [f.path for f in found] == ["weeks[0].minutes", "weeks[3].minutes"]


class TestTheCapacity:
    def test_more_than_the_week_offers_is_an_error(self) -> None:
        skel = skeleton(6, capacity=300, reference=200)
        plan = change(follow(skel), 1, minutes=((Sport.RUNNING, 301),))

        (found,) = check_capacity(plan, context(skel))

        assert (found.severity, found.code, found.path) == (
            Severity.ERROR,
            "minutes_above_capacity",
            "weeks[1].minutes",
        )
        assert found.message.endswith("but you can train 300 in it.")

    def test_exactly_what_the_week_offers_is_fine(self) -> None:
        skel = skeleton(6, capacity=300, reference=200)
        plan = change(follow(skel), 1, minutes=((Sport.RUNNING, 300),))

        assert check_capacity(plan, context(skel)) == []

    def test_a_week_of_absence_offers_nothing(self) -> None:
        weeks = skeleton(6).weeks
        away = SkeletonWeek(weeks[2].week_start, weeks[2].phase, False, 0, 0)
        skel = Skeleton(weeks[:2] + (away,) + weeks[3:], None, 0, True, False)
        plan = change(follow(skel), 2, minutes=((Sport.RUNNING, 30),))

        assert codes(check_capacity(plan, context(skel))) == ["minutes_above_capacity"]


class TestTheSports:
    def test_minutes_in_a_sport_that_was_not_chosen_are_an_error_at_that_sport(self) -> None:
        skel = skeleton(6)
        plan = change(follow(skel), 1, minutes=((Sport.RUNNING, 100), (Sport.SWIMMING, 60)))

        found = check_sports(plan, context(skel, frozenset({Sport.RUNNING, Sport.CYCLING})))

        assert found == [
            Finding(
                Severity.ERROR,
                "sport_not_selected",
                f"The week of {skel.weeks[1].week_start} has swimming minutes, but you did not "
                "choose that sport.",
                "weeks[1].minutes.swimming",
            )
        ]

    def test_zero_minutes_in_a_sport_that_was_not_chosen_are_fine(self) -> None:
        skel = skeleton(6)
        plan = change(follow(skel), 1, minutes=((Sport.RUNNING, 100), (Sport.SWIMMING, 0)))

        assert check_sports(plan, context(skel, frozenset({Sport.RUNNING}))) == []

    def test_every_sport_is_fine_when_all_are_chosen(self) -> None:
        skel = skeleton(6)
        plan = change(follow(skel), 1, minutes=tuple((sport, 10) for sport in Sport))

        assert check_sports(plan, context(skel)) == []


class TestTheKeySessions:
    def session(self, sport: Sport = Sport.RUNNING, minutes: int = 90, **fields: Any) -> KeySession:
        return KeySession(sport, fields.pop("kind", SessionKind.LONG), minutes)

    def week_with(self, *sessions: KeySession, minutes: int = 200) -> tuple[Skeleton, SeasonPlan]:
        skel = skeleton(6)
        plan = change(
            follow(skel),
            1,
            minutes=((Sport.RUNNING, minutes),),
            key_sessions=sessions,
        )
        return skel, plan

    def test_sessions_that_fit_are_fine(self) -> None:
        skel, plan = self.week_with(self.session(minutes=90), self.session(minutes=110))

        assert check_key_sessions(plan, context(skel)) == []

    def test_a_session_in_a_sport_without_minutes_is_an_error_at_the_session(self) -> None:
        skel, plan = self.week_with(self.session(Sport.CYCLING, 60))

        assert check_key_sessions(plan, context(skel)) == [
            Finding(
                Severity.ERROR,
                "key_session_sport_missing",
                f"The week of {skel.weeks[1].week_start} has a cycling key session, but no "
                "cycling minutes.",
                "weeks[1].key_sessions[0].sport",
            )
        ]

    def test_a_sport_with_zero_minutes_has_none_either(self) -> None:
        skel = skeleton(6)
        plan = change(
            follow(skel),
            1,
            minutes=((Sport.RUNNING, 100), (Sport.CYCLING, 0)),
            key_sessions=(self.session(Sport.CYCLING, 30),),
        )

        assert codes(check_key_sessions(plan, context(skel))) == ["key_session_sport_missing"]

    def test_sessions_that_add_up_to_more_than_the_sport_are_an_error_once(self) -> None:
        skel, plan = self.week_with(
            self.session(minutes=90),
            self.session(minutes=90),
            self.session(minutes=90),
            minutes=200,
        )

        (found,) = check_key_sessions(plan, context(skel))

        assert (found.code, found.path) == ("key_sessions_too_long", "weeks[1].key_sessions")
        assert "add up to 270 minutes, more than its 200 running minutes" in found.message

    def test_sessions_of_the_other_sports_do_not_count_against_each_other(self) -> None:
        skel = skeleton(6)
        plan = change(
            follow(skel),
            1,
            minutes=((Sport.RUNNING, 100), (Sport.CYCLING, 100)),
            key_sessions=(self.session(Sport.RUNNING, 90), self.session(Sport.CYCLING, 90)),
        )

        assert check_key_sessions(plan, context(skel)) == []

    def test_a_week_without_sessions_is_fine(self) -> None:
        skel = skeleton(6)

        assert check_key_sessions(follow(skel), context(skel)) == []


class TestTheRaces:
    def test_a_week_with_a_race_wants_a_key_session_for_it(self) -> None:
        skel = skeleton(6)
        plan = follow(skel, races=False)

        (found,) = check_races(plan, context(skel))

        assert (found.severity, found.code, found.path) == (
            Severity.WARNING,
            "race_week_without_race",
            "weeks[5].key_sessions",
        )
        assert found.message.endswith("but no key session of the kind race.")

    def test_a_key_session_of_that_kind_makes_it_fine(self) -> None:
        skel = skeleton(6)
        plan = follow(skel, races=False)
        plan = change(plan, 5, key_sessions=(KeySession(Sport.RUNNING, SessionKind.RACE, 120),))

        assert check_races(plan, context(skel)) == []

    def test_a_week_without_a_race_needs_none(self) -> None:
        skel = skeleton(6)

        assert all(
            f.path == "weeks[5].key_sessions" for f in check_races(follow(skel), context(skel))
        )

    def test_a_c_race_counts_too(self) -> None:
        main = Race(MONDAY + timedelta(weeks=5, days=6), "main")
        c = Race(MONDAY + timedelta(weeks=2, days=5), "preparation")
        skel = build_skeleton(SkeletonInputs(MONDAY, (600,) * 52, (main, c), 300, "normal"))

        found = check_races(follow(skel, races=False), context(skel))

        assert [f.path for f in found] == ["weeks[2].key_sessions", "weeks[5].key_sessions"]


class TestTheReport:
    def test_all_checks_run_in_a_fixed_order(self) -> None:
        assert [check.__name__ for check in ALL_CHECKS] == [
            "check_weeks",
            "check_sports",
            "check_minutes",
            "check_capacity",
            "check_key_sessions",
            "check_races",
        ]

    def test_errors_make_the_plan_invalid_and_warnings_do_not(self) -> None:
        skel = skeleton(6)
        warned = validate_season(follow(skel, races=False), context(skel))
        broken = validate_season(change(follow(skel), 1, minutes=()), context(skel))

        assert [f.code for f in warned.warnings] == ["race_week_without_race"]
        assert warned.valid is True
        assert broken.valid is False
        assert "minutes_outside_target" in [f.code for f in broken.errors]

    def test_the_same_plan_gives_the_same_report(self) -> None:
        skel = skeleton(6)
        plan = change(follow(skel), 2, minutes=((Sport.SWIMMING, 5000),))

        assert validate_season(plan, context(skel)) == validate_season(plan, context(skel))

    def test_no_check_raises_on_any_plan(self) -> None:
        skel = skeleton(6)
        odd = SeasonPlan(
            (
                PlanWeek(MONDAY, (), Focus.RECOVERY, "x"),
                PlanWeek(MONDAY, (), Focus.RECOVERY, "x"),
                PlanWeek(date(1999, 1, 4), ((Sport.RUNNING, 1),), Focus.TEMPO, "y"),
            )
        )

        report = validate_season(odd, context(skel))

        assert report.errors
        assert all(isinstance(f, Finding) for f in report.findings)

    def test_a_season_of_no_weeks_has_nothing_to_check(self) -> None:
        empty = Skeleton((), None, 0, True, False)

        assert validate_season(SeasonPlan(), SeasonContext(empty)).findings == ()


class TestNothingTheCoachWroteIsRepeated:
    MARKER = "SECRET-MARKER-9f3"

    def test_no_message_holds_a_reason_a_detail_or_a_rationale(self) -> None:
        skel = skeleton(6)
        plan = SeasonPlan(
            tuple(
                PlanWeek(
                    week.week_start,
                    ((Sport.SWIMMING, 99_999),),
                    Focus.TEMPO,
                    self.MARKER,
                    (KeySession(Sport.CYCLING, SessionKind.LONG, 999, self.MARKER),),
                )
                for week in skel.weeks
            ),
            self.MARKER,
        )

        report = validate_season(plan, context(skel, frozenset({Sport.RUNNING})))

        assert len(report.findings) > 10
        assert all(
            self.MARKER not in f.message and self.MARKER not in f.path for f in report.findings
        )


def test_the_module_defines_one_window() -> None:
    assert rules.WINDOW_PERCENT == 10
