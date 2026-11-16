"""The page ``docs/season.md`` is compared with the code, so that it cannot drift."""

import re
from datetime import date
from pathlib import Path

import pytest

from accounts.models import User
from season import briefing, generation, prompt, rules, schema, skeleton
from season.briefing import build_briefing
from season.inputs import skeleton_for
from season.skeleton import Phase

ROOT = Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs" / "season.md").read_text()
ORDINAL_ENDINGS = {1: "st", 2: "nd", 3: "rd"}


def section(heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", DOC, re.S | re.M)
    assert match, f"no section {heading!r}"
    return match.group(1)


def table_after(text: str, first_cell: str) -> list[list[str]]:
    """The body rows of the table whose header row starts with ``first_cell``."""
    start = text.index(f"| {first_cell} |")
    rows = []
    for line in text[start:].splitlines():
        if not line.startswith("|"):
            break
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        if cells[0] == first_cell or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        rows.append(cells)
    return rows


def constants() -> dict[str, int | float]:
    return {
        name: value
        for name, value in vars(skeleton).items()
        if name.isupper() and isinstance(value, int | float) and not isinstance(value, bool)
    }


class TestTheLimits:
    def test_every_documented_limit_has_the_value_in_the_code(self) -> None:
        documented = {
            row[0]: float(row[1]) for row in table_after(section("The limits"), "Constant")
        }

        for name, value in documented.items():
            assert constants()[name] == value, name

    def test_every_number_of_the_code_is_documented(self) -> None:
        documented = {row[0] for row in table_after(section("The limits"), "Constant")}

        assert documented == set(constants())


class TestTheTables:
    def test_the_ramp_and_the_rhythm_of_each_level(self) -> None:
        rows = {row[0]: row for row in table_after(section("The minutes"), "Level")}

        assert set(rows) == set(skeleton.RAMP_PERCENT) == set(skeleton.RECOVERY_EVERY)
        for level, row in rows.items():
            assert int(row[1]) == skeleton.RAMP_PERCENT[level], level
            every = skeleton.RECOVERY_EVERY[level]
            assert row[2] == f"{every}{ORDINAL_ENDINGS.get(every, 'th')} week", level

    def test_the_taper_by_the_race(self) -> None:
        rows = {row[0]: row for row in table_after(section("The weeks"), "Discipline")}

        assert set(rows) == set(skeleton._TAPER_LIMITS_M)
        for discipline, (short, middle) in skeleton._TAPER_LIMITS_M.items():
            row = rows[discipline]
            first, second, third = skeleton.TAPER_WEEKS
            assert [row[1], row[2], row[3], row[4], row[5]] == [
                f"{short:,.0f} m".replace(",", " "),
                str(first),
                f"{middle:,.0f} m".replace(",", " "),
                str(second),
                str(third),
            ]

    def test_the_share_of_every_taper_week(self) -> None:
        rows = table_after(section("The minutes"), "Taper weeks")

        for row in rows:
            length = int(row[0])
            shown = [int(cell.rstrip(" %")) for cell in row[1:] if cell]
            assert tuple(shown) == skeleton.TAPER_PERCENT[length]
        assert {int(row[0]) for row in rows} == set(skeleton.TAPER_PERCENT)


class TestTheWords:
    def test_every_phase_is_named_on_the_page(self) -> None:
        for phase in Phase:
            assert f"`{phase.value}`" in DOC or f"**{phase.value}**" in DOC, phase

    def test_the_weeks_of_the_page_are_those_of_the_code(self) -> None:
        text = section("The weeks")

        assert "`MAX_WEEKS`" in text
        assert "`ROLLING_WEEKS`" in text

    def test_the_api_names_every_field_of_a_week_and_of_a_race(self) -> None:
        from datetime import date

        from season.serializers import skeleton_data
        from season.skeleton import Race, Skeleton, SkeletonWeek

        race = Race(date(2027, 1, 3), "main", "running", 5000, "x")
        week = SkeletonWeek(date(2026, 12, 28), Phase.BASE, False, 1, 2, (race,))
        data = skeleton_data(Skeleton((week,), race, 1, False, False))
        text = section("The API")

        for name in (*data, *data["weeks"][0], *data["main_race"]):
            assert f"`{name}`" in text, name


class TestTheFormat:
    def test_the_limits_of_the_format_are_those_of_the_code(self) -> None:
        text = section("The format of a filled season")
        documented = {row[0]: int(row[1]) for row in table_after(text, "Constant")}
        defined = {
            name: value
            for name, value in vars(schema).items()
            if name.isupper()
            and isinstance(value, int)
            and not isinstance(value, bool)
            # the most weeks is the one of the skeleton and listed with its limits
            and name != "MAX_WEEKS"
        }

        assert documented == defined

    def test_every_field_of_a_week_a_session_and_the_plan_is_named(self) -> None:
        import dataclasses

        text = section("The format of a filled season")

        for dataclass in (schema.SeasonPlan, schema.PlanWeek, schema.KeySession):
            for field in dataclasses.fields(dataclass):
                assert f"`{field.name}`" in text, field.name

    def test_every_word_of_the_choices_is_named(self) -> None:
        text = section("The format of a filled season")

        for enum in (schema.Focus, schema.SessionKind):
            for member in enum:
                assert f"`{member.value}`" in text, member

    def test_the_most_weeks_is_that_of_the_skeleton(self) -> None:
        assert "`MAX_WEEKS`" in section("The format of a filled season")


class TestTheChecks:
    def in_the_code(self) -> set[tuple[str, str]]:
        source = Path(rules.__file__).read_text()
        return {
            (code, severity.lower())
            for severity, code in re.findall(r'Severity\.(ERROR|WARNING),\s*"([a-z_]+)"', source)
        }

    def test_the_table_lists_every_finding_with_its_severity(self) -> None:
        documented = {(row[0], row[1]) for row in table_after(section("The checks"), "Code")}

        assert documented == self.in_the_code()

    def test_every_check_is_covered_by_the_table(self) -> None:
        # the number of checks and of codes can only move together with the page
        assert len(rules.ALL_CHECKS) == 6
        assert len(self.in_the_code()) == 7

    def test_the_window_is_the_one_of_the_code(self) -> None:
        documented = {row[0]: int(row[1]) for row in table_after(section("The checks"), "Constant")}

        assert documented == {"WINDOW_PERCENT": rules.WINDOW_PERCENT}


class TestWhatTheCoachIsTold:
    @pytest.mark.django_db
    def test_every_key_of_the_briefing_is_documented_and_every_documented_key_is_there(
        self,
    ) -> None:
        user = User.objects.create_user("docs@example.com")
        told = set(build_briefing(user, date(2026, 11, 19), skeleton_for(user)))
        text = section("What the coach is told")

        documented = {
            cell for row in table_after(text, "Key") for cell in re.split(r",\s*", row[0])
        }

        assert documented == told

    def test_the_limits_are_those_of_the_code(self) -> None:
        text = section("What the coach is told")
        documented = {row[0]: int(row[1]) for row in table_after(text, "Constant")}

        assert documented == {
            "MAX_RACES_TOLD": briefing.MAX_RACES_TOLD,
            "RACE_TITLE_TOLD_MAX": briefing.RACE_TITLE_TOLD_MAX,
            "MAX_BYTES": briefing.MAX_BYTES,
            "SEASON_MAX_TOKENS": prompt.SEASON_MAX_TOKENS,
        }


class TestTheFilledPlans:
    def test_the_attempts_are_the_ones_of_the_code(self) -> None:
        documented = {
            row[0]: int(row[1]) for row in table_after(section("The filled plans"), "Constant")
        }

        assert documented == {"ATTEMPTS": generation.ATTEMPTS}

    def test_the_statuses_are_named(self) -> None:
        from season.models import SeasonPlanVersion

        text = section("The filled plans")

        for status in SeasonPlanVersion.Status:
            assert f"`{status.value}`" in text, status

    def test_the_api_names_the_endpoints_and_the_fields_of_a_summary(self) -> None:
        text = section("The API")

        for name in ("/api/season/plans/", "generate/", "confirm/", "discard/"):
            assert name in text, name
        for field in (
            "id",
            "version",
            "status",
            "reason",
            "week_count",
            "created_at",
            "confirmed_at",
        ):
            assert f"`{field}`" in text, field
