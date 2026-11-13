"""The page ``docs/weekly-plan.md`` is compared with the code, so that it cannot drift."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from planning import models, rules, schema
from planning.context import PlanContext
from planning.rules import SPORT_ZONE_SYSTEMS
from planning.schema import Sport, ZoneSystem, parse_week_plan
from planning.validation import validate_week

ROOT = Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs" / "weekly-plan.md").read_text()
README = (ROOT / "README.md").read_text()


def section(heading: str) -> str:
    """The text of a ``##`` section of the page, up to the next one."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", DOC, re.S | re.M)
    assert match, f"no section {heading!r}"
    return match.group(1)


def rows(text: str) -> list[list[str]]:
    """The body rows of the tables in ``text``, cells without backticks."""
    found = []
    for line in text.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        found.append([cell.strip().replace("`", "") for cell in line.strip("|").split("|")])
    return [row for row in found if row[0] not in {"Field", "Code", "Constant", "System", "Status"}]


def example() -> object:
    match = re.search(r"```json\n(.*?)\n```", section("Example"), re.S)
    assert match, "no example"
    return json.loads(match.group(1))


class TestTheExample:
    def test_it_is_a_plan_the_parser_accepts(self) -> None:
        plan = parse_week_plan(example())

        assert plan.week_start == date(2027, 7, 12)
        assert [w.sport for w in plan.workouts] == [Sport.CYCLING, Sport.RUNNING, Sport.CYCLING]
        assert plan.workouts[1].segments[1].repeat == 4

    def test_it_passes_every_check_for_an_athlete_who_can_do_it(self) -> None:
        plan = parse_week_plan(example())
        context = PlanContext(
            week_start=date(2027, 7, 12),
            minutes=(0, 120, 0, 90, 0, 180, 0),
            absences=(None,) * 7,
            weekly_budget=None,
            weekly_minutes=390,
            zone_systems=frozenset(
                {(Sport.CYCLING, ZoneSystem.POWER), (Sport.RUNNING, ZoneSystem.PACE)}
            ),
            recent_weeks=(270, 300, 280),
        )

        report = validate_week(plan, context)

        assert report.findings == ()

    def test_the_segments_of_the_example_add_up(self) -> None:
        # 900 + 4 x 480 + 4 x 180 + 600 = 4140 seconds = 69 minutes
        plan = parse_week_plan(example())

        intervals = plan.workouts[1]
        total = sum(s.seconds * s.repeat for s in intervals.segments)

        assert abs(total - intervals.duration_minutes * 60) <= rules.DURATION_TOLERANCE_SECONDS


class TestTheLimits:
    def constants(self) -> dict[str, int]:
        return {
            name: value
            for module in (rules, schema, models)
            for name, value in vars(module).items()
            if name.isupper() and isinstance(value, int) and not isinstance(value, bool)
        }

    def test_every_documented_limit_has_the_value_in_the_code(self) -> None:
        constants = self.constants()
        documented = {name: int(value) for name, value, *_ in rows(section("The limits"))}

        for name, value in documented.items():
            assert constants[name] == value, name

    def test_every_limit_of_the_rules_and_the_format_is_documented(self) -> None:
        documented = {row[0] for row in rows(section("The limits"))}
        defined = {
            name
            for module in (rules, schema)
            for name, value in vars(module).items()
            if name.isupper() and isinstance(value, int) and not isinstance(value, bool)
        }

        assert defined == documented


class TestTheRules:
    def in_the_code(self) -> set[tuple[str, str]]:
        source = Path(rules.__file__).read_text()
        return {
            (code, severity.lower())
            for severity, code in re.findall(r'Severity\.(ERROR|WARNING),\s*"([a-z_]+)"', source)
        }

    def test_the_table_lists_every_finding_with_its_severity(self) -> None:
        documented = {(row[0], row[1]) for row in rows(section("The rules"))}

        assert documented == self.in_the_code()

    def test_every_check_of_the_rules_is_covered_by_the_table(self) -> None:
        # the number of checks and of codes can only move together with the page
        assert len(rules.ALL_CHECKS) == 11
        assert len(self.in_the_code()) == 14


class TestTheZoneSystems:
    def test_the_table_has_the_zone_counts_and_the_sports_of_the_code(self) -> None:
        table = {row[0]: row for row in rows(section("Zone systems"))}

        for system in ZoneSystem:
            zones, sports = int(table[system.value][1]), table[system.value][2]
            assert zones == schema.ZONE_COUNT[system.value]
            fitting = {
                sport.value for sport, allowed in SPORT_ZONE_SYSTEMS.items() if system in allowed
            }
            assert set(sports.split(", ")) == fitting


class TestTheStatuses:
    def test_the_table_lists_the_statuses_of_the_model(self) -> None:
        documented = {row[0] for row in rows(section("Saving, versions and confirming"))}

        assert {s.value for s in models.WeeklyPlan.Status} <= documented


class TestTheFormatTables:
    def fields(self, heading_row: str) -> set[str]:
        text = section("The format")
        start = text.index(heading_row)
        table = text[start:].split("\n\n")[0]
        return {cell for row in rows(table) for cell in re.split(r",\s*", row[0])}

    def test_the_plan_fields(self) -> None:
        assert {"week_start", "rationale", "workouts"} <= self.fields(
            "| Field | Required | Meaning |"
        )

    def test_the_enums_named_on_the_page_are_those_of_the_code(self) -> None:
        text = section("The format")

        for enum in (schema.Sport, schema.Goal, schema.SegmentKind):
            for member in enum:
                assert f"`{member.value}`" in text, member

    def test_an_example_written_from_the_documented_fields_only_is_accepted(self) -> None:
        # every key of the example is a documented field
        documented = set(re.findall(r"`([a-z_]+)`", section("The format")))

        def keys(node: object) -> set[str]:
            if isinstance(node, dict):
                return set(node) | {k for v in node.values() for k in keys(v)}
            if isinstance(node, list):
                return {k for v in node for k in keys(v)}
            return set()

        assert keys(example()) <= documented


class TestTheReadme:
    def test_it_points_to_the_page(self) -> None:
        assert "docs/weekly-plan.md" in README

    def test_the_page_exists_and_is_not_empty(self) -> None:
        assert len(DOC) > 3000


def test_the_page_names_every_public_service_function() -> None:
    from planning import services

    for name in ("save_draft", "canonical", "validate", "confirm"):
        assert f"services.{name}" in DOC, name
        assert callable(getattr(services, name))


@pytest.mark.parametrize("word", ["Monday", "superseded", "tolerance"])
def test_a_few_words_that_the_page_must_keep(word: str) -> None:
    assert word in DOC
