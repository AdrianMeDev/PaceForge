"""The page ``docs/season.md`` is compared with the code, so that it cannot drift."""

import re
from pathlib import Path

from season import schema, skeleton
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
