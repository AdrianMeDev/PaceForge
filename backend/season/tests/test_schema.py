import ast
import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from planning.schema import Sport
from season import schema
from season.schema import (
    Focus,
    KeySession,
    PlanFormatError,
    PlanWeek,
    Problem,
    SeasonPlan,
    SessionKind,
    parse_season_plan,
    to_json,
)

MONDAY = date(2026, 11, 16)
MARKER = "SECRET-MARKER-9f3"


def session(**fields: Any) -> dict[str, Any]:
    return {"sport": "running", "kind": "long", "minutes": 90, **fields}


def week(**fields: Any) -> dict[str, Any]:
    return {
        "week_start": "2026-11-16",
        "minutes": {"running": 180, "strength": 45},
        "focus": "endurance",
        "reason": "Build the base.",
        **fields,
    }


def plan(**fields: Any) -> dict[str, Any]:
    return {"weeks": [week()], **fields}


def with_week(**fields: Any) -> dict[str, Any]:
    return plan(weeks=[week(**fields)])


def with_session(**fields: Any) -> dict[str, Any]:
    return with_week(key_sessions=[session(**fields)])


def problems_of(data: object) -> list[Problem]:
    with pytest.raises(PlanFormatError) as raised:
        parse_season_plan(data)
    return list(raised.value.problems)


def paths_of(data: object) -> list[str]:
    return [problem.path for problem in problems_of(data)]


class TestAValidPlan:
    def test_the_smallest_plan_is_a_season_of_no_weeks(self) -> None:
        assert parse_season_plan({"weeks": []}) == SeasonPlan((), "")

    def test_a_week_has_its_fields(self) -> None:
        (found,) = parse_season_plan(plan()).weeks

        assert found == PlanWeek(
            MONDAY,
            ((Sport.RUNNING, 180), (Sport.STRENGTH, 45)),
            Focus.ENDURANCE,
            "Build the base.",
            (),
        )
        assert found.total == 225

    def test_the_rationale_is_trimmed_and_optional(self) -> None:
        assert parse_season_plan(plan(rationale="  Why  ")).rationale == "Why"
        assert parse_season_plan(plan()).rationale == ""

    def test_the_minutes_come_in_the_order_of_the_sports_whatever_the_order_sent(self) -> None:
        data = with_week(minutes={"strength": 45, "cycling": 60, "running": 90})

        (found,) = parse_season_plan(data).weeks

        assert [sport.value for sport, _ in found.minutes] == ["running", "cycling", "strength"]

    def test_a_week_may_have_no_minutes_at_all(self) -> None:
        (found,) = parse_season_plan(with_week(minutes={})).weeks

        assert found.minutes == ()
        assert found.total == 0

    def test_zero_minutes_of_a_sport_are_kept(self) -> None:
        (found,) = parse_season_plan(with_week(minutes={"running": 0})).weeks

        assert found.minutes == ((Sport.RUNNING, 0),)

    def test_a_key_session_has_its_defaults(self) -> None:
        (found,) = parse_season_plan(with_session()).weeks[0].key_sessions

        assert found == KeySession(Sport.RUNNING, SessionKind.LONG, 90, "")

    def test_a_key_session_with_a_detail(self) -> None:
        (found,) = parse_season_plan(with_session(detail="  3 x 10 min  ")).weeks[0].key_sessions

        assert found.detail == "3 x 10 min"

    def test_it_is_written_back_unchanged(self) -> None:
        data = plan(
            rationale="Why",
            weeks=[
                week(key_sessions=[session(detail="steady")]),
                week(week_start="2026-11-23", focus="recovery", minutes={"running": 90}),
            ],
        )
        original = parse_season_plan(data)

        again = parse_season_plan(json.loads(json.dumps(to_json(original))))

        assert again == original

    def test_every_field_is_written_out(self) -> None:
        original = parse_season_plan(with_week(key_sessions=[session()]))

        assert to_json(original) == {
            "rationale": "",
            "weeks": [
                {
                    "week_start": "2026-11-16",
                    "minutes": {"running": 180, "strength": 45},
                    "focus": "endurance",
                    "key_sessions": [
                        {"sport": "running", "kind": "long", "minutes": 90, "detail": ""}
                    ],
                    "reason": "Build the base.",
                }
            ],
        }

    def test_it_does_not_change_what_it_was_given(self) -> None:
        data = with_session(detail=" x ")
        before = copy.deepcopy(data)

        parse_season_plan(data)

        assert data == before

    @pytest.mark.parametrize("focus", [f.value for f in Focus])
    def test_every_focus_is_known(self, focus: str) -> None:
        assert parse_season_plan(with_week(focus=focus)).weeks[0].focus == focus

    @pytest.mark.parametrize("kind", [k.value for k in SessionKind])
    def test_every_kind_of_session_is_known(self, kind: str) -> None:
        (found,) = parse_season_plan(with_session(kind=kind)).weeks[0].key_sessions

        assert found.kind == kind


class TestWhatIsRefused:
    @pytest.mark.parametrize("data", [None, [], "plan", 5, True])
    def test_a_plan_that_is_no_object(self, data: object) -> None:
        assert problems_of(data) == [Problem("", "Must be an object.")]

    def test_the_weeks_are_required_and_a_list(self) -> None:
        assert problems_of({}) == [Problem("weeks", "Is required.")]
        assert problems_of({"weeks": {}}) == [Problem("weeks", "Must be a list.")]

    def test_at_most_a_year_of_weeks(self) -> None:
        many = plan(weeks=[week()] * 53)

        assert problems_of(many) == [Problem("weeks", "Must have at most 52 entries.")]
        assert len(parse_season_plan(plan(weeks=[week()] * 52)).weeks) == 52

    def test_an_unknown_field_is_reported_at_its_parent(self) -> None:
        assert paths_of(plan(colour="red", SECRETMARKER=1)) == [""]
        assert paths_of(with_week(colour="red", SECRETMARKER=1)) == ["weeks[0]"]
        assert paths_of(with_session(colour="red", SECRETMARKER=1)) == ["weeks[0].key_sessions[0]"]

    @pytest.mark.parametrize("missing", ["week_start", "minutes", "focus", "reason"])
    def test_a_required_field_of_a_week(self, missing: str) -> None:
        data = plan()
        del data["weeks"][0][missing]

        assert problems_of(data) == [Problem(f"weeks[0].{missing}", "Is required.")]

    @pytest.mark.parametrize("missing", ["sport", "kind", "minutes"])
    def test_a_required_field_of_a_session(self, missing: str) -> None:
        data = with_session()
        del data["weeks"][0]["key_sessions"][0][missing]

        assert problems_of(data) == [Problem(f"weeks[0].key_sessions[0].{missing}", "Is required.")]

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("week_start", "2026-11-17", "A week starts on a Monday."),
            ("week_start", "16.11.2026", "Must be a date like 2027-07-12."),
            ("week_start", 20261116, "Must be a date like 2027-07-12."),
            (
                "focus",
                "rest",
                "Must be one of: recovery, endurance, tempo, threshold, vo2max, race_specific.",
            ),
            (
                "focus",
                None,
                "Must be one of: recovery, endurance, tempo, threshold, vo2max, race_specific.",
            ),
            ("reason", "", "Must not be empty."),
            ("reason", "   ", "Must not be empty."),
            ("reason", "x" * 301, "Must have at most 300 characters."),
            ("reason", "a\nb", "Must not contain control characters."),
            ("reason", 5, "Must be text."),
            ("minutes", [], "Must be an object."),
            ("minutes", "180", "Must be an object."),
            ("key_sessions", {}, "Must be a list."),
            ("key_sessions", "long run", "Must be a list."),
        ],
    )
    def test_a_field_of_a_week_that_is_not_usable_is_named(
        self, field: str, value: object, message: str
    ) -> None:
        assert problems_of(with_week(**{field: value})) == [Problem(f"weeks[0].{field}", message)]

    @pytest.mark.parametrize(
        ("minutes", "message"),
        [
            (-1, "Must be between 0 and 10080."),
            (10081, "Must be between 0 and 10080."),
            (60.5, "Must be a whole number."),
            ("60", "Must be a whole number."),
            (True, "Must be a whole number."),
            (None, "Must be a whole number."),
        ],
    )
    def test_the_minutes_of_a_sport_must_be_whole_and_in_range(
        self, minutes: object, message: str
    ) -> None:
        assert problems_of(with_week(minutes={"running": minutes})) == [
            Problem("weeks[0].minutes.running", message)
        ]

    def test_an_unknown_sport_is_named_if_it_looks_like_a_name(self) -> None:
        assert problems_of(with_week(minutes={"golf": 60})) == [
            Problem("weeks[0].minutes.golf", "Unknown sport.")
        ]
        assert paths_of(with_week(minutes={"a b": 60})) == ["weeks[0].minutes.?"]
        assert paths_of(with_week(minutes={"Running": 60})) == ["weeks[0].minutes.Running"]

    def test_a_sport_that_is_no_text_is_not_shown_either(self) -> None:
        data = with_week()
        data["weeks"][0]["minutes"] = {5: 60}

        assert paths_of(data) == ["weeks[0].minutes.?"]

    def test_at_most_three_key_sessions(self) -> None:
        data = with_week(key_sessions=[session()] * 4)

        assert problems_of(data) == [
            Problem("weeks[0].key_sessions", "Must have at most 3 entries.")
        ]
        assert (
            len(parse_season_plan(with_week(key_sessions=[session()] * 3)).weeks[0].key_sessions)
            == 3
        )

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("sport", "golf", "Must be one of: running, cycling, swimming, strength."),
            ("sport", None, "Must be one of: running, cycling, swimming, strength."),
            (
                "kind",
                "rest",
                "Must be one of: long, tempo, threshold, vo2max, race_pace, strength, race.",
            ),
            ("minutes", 0, "Must be between 1 and 1440."),
            ("minutes", 1441, "Must be between 1 and 1440."),
            ("minutes", 90.5, "Must be a whole number."),
            ("detail", "x" * 61, "Must have at most 60 characters."),
            ("detail", "a\nb", "Must not contain control characters."),
            ("detail", 5, "Must be text."),
        ],
    )
    def test_a_field_of_a_session_that_is_not_usable_is_named(
        self, field: str, value: object, message: str
    ) -> None:
        assert problems_of(with_session(**{field: value})) == [
            Problem(f"weeks[0].key_sessions[0].{field}", message)
        ]

    def test_every_problem_of_every_week_is_named_at_once(self) -> None:
        data = plan(
            weeks=[
                week(focus="x"),
                week(),
                week(reason="", key_sessions=[session(minutes=0), session(kind="x")]),
            ],
            rationale=5,
        )

        assert paths_of(data) == [
            "rationale",
            "weeks[0].focus",
            "weeks[2].reason",
            "weeks[2].key_sessions[0].minutes",
            "weeks[2].key_sessions[1].kind",
        ]

    def test_a_week_of_the_wrong_type_is_named(self) -> None:
        assert problems_of(plan(weeks=["week"])) == [Problem("weeks[0]", "Must be an object.")]


class TestNothingOfTheInputIsRepeated:
    def everything(self, data: object) -> str:
        with pytest.raises(PlanFormatError) as raised:
            parse_season_plan(data)
        parts = [str(raised.value), repr(raised.value)]
        for problem in raised.value.problems:
            parts += [problem.path, problem.message]
        return " ".join(parts)

    @pytest.mark.parametrize(
        "data",
        [
            plan(rationale=[MARKER]),
            with_week(week_start=MARKER),
            with_week(focus=MARKER),
            with_week(reason=MARKER[:6] + "\n" + MARKER[6:]),
            with_week(minutes={"running": MARKER}),
            with_week(minutes={MARKER: 5}),
            with_week(**{MARKER: 1}),
            with_session(kind=MARKER),
            with_session(sport=MARKER),
            with_session(detail=[MARKER]),
            with_session(**{MARKER: 1}),
            plan(**{MARKER: 1}),
        ],
    )
    def test_no_message_path_or_text_holds_a_value_of_the_input(self, data: object) -> None:
        assert MARKER not in self.everything(data)


class TestTheLimits:
    def test_the_limits_are_written_out_on_purpose(self) -> None:
        # The other tests read the constants and would follow a change.
        assert (schema.RATIONALE_MAX, schema.REASON_MAX, schema.DETAIL_MAX) == (1000, 300, 60)
        assert (schema.MAX_KEY_SESSIONS, schema.WEEK_MINUTES_MAX) == (3, 10080)
        assert schema.KEY_SESSION_MINUTES_MAX == 1440

    def test_the_module_needs_no_django(self) -> None:
        source = Path(schema.__file__).read_text()
        imported = {
            node.module.split(".")[0]
            if isinstance(node, ast.ImportFrom) and node.module
            else alias.name.split(".")[0]
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(name="")])
        }

        assert "django" not in imported


class TestWhateverIsSent:
    JUNK: list[Any] = [
        None,
        True,
        0,
        -1,
        3.5,
        "",
        "x",
        [],
        {},
        [None],
        {"weeks": None},
        {"weeks": [None]},
        {"weeks": [{}]},
        {"weeks": [{"week_start": 5, "minutes": 5, "focus": 5, "reason": 5}]},
        {"weeks": [week(key_sessions=[None, 5, "x", []])]},
        {"weeks": [week(minutes={"running": {"a": 1}})]},
    ]

    @pytest.mark.parametrize("data", JUNK)
    def test_garbage_gives_a_plan_or_a_format_error_and_nothing_else(self, data: object) -> None:
        try:
            parse_season_plan(data)
        except PlanFormatError as error:
            assert error.problems
            assert all(isinstance(problem, Problem) for problem in error.problems)
