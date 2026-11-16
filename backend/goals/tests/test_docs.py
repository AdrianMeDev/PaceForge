"""The page ``docs/goals.md`` is compared with the code, so that it cannot drift."""

import re
from pathlib import Path

import pytest

from goals import realism
from goals.realism import PREP_WEEKS, Reason

ROOT = Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs" / "goals.md").read_text()
README = (ROOT / "README.md").read_text()
FLAT_README = " ".join(README.split())


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


def constants() -> dict[str, float]:
    return {
        name: float(value)
        for name, value in vars(realism).items()
        if name.isupper()
        and not name.startswith("_")
        and isinstance(value, int | float)
        and not isinstance(value, bool)
    }


class TestTheConstants:
    def test_every_documented_constant_has_the_value_in_the_code(self) -> None:
        documented = {
            row[0]: float(row[1]) for row in table_after(section("The judgement"), "Constant")
        }

        for name, value in documented.items():
            assert constants()[name] == value, name

    def test_every_constant_of_the_module_is_documented(self) -> None:
        documented = {row[0] for row in table_after(section("The judgement"), "Constant")}

        assert documented == set(constants())


class TestThePreparation:
    def test_the_weeks_by_distance_are_those_of_the_code(self) -> None:
        documented = [
            int(row[1]) for row in table_after(section("A short preparation"), "Distance up to")
        ]

        assert documented == [weeks for _, weeks in PREP_WEEKS]
        assert len(documented) == len(PREP_WEEKS)

    def test_the_readme_names_the_same_weeks(self) -> None:
        weeks = {limit: number for limit, number in PREP_WEEKS}

        assert f"{weeks[5000.0]} for 5 km" in FLAT_README
        assert f"{weeks[10000.0]} for 10 km" in FLAT_README
        assert f"{weeks[21097.5]} for a half marathon" in FLAT_README
        assert f"{weeks[42195.0]} for a marathon" in FLAT_README


class TestTheReasons:
    def test_every_reason_of_the_code_is_documented_and_nothing_else(self) -> None:
        documented = {row[0] for row in table_after(section("What cannot be judged"), "Reason")}

        assert documented == {reason.value for reason in Reason}


class TestTheReadme:
    def test_it_names_the_gains_of_the_code(self) -> None:
        assert (
            f"{realism.VDOT_GAIN_PER_WEEK} VDOT a week up to {realism.VDOT_GAIN_MAX:g}"
            in FLAT_README
        )
        assert (
            f"{realism.THRESHOLD_GAIN_PERCENT_PER_WEEK} % a week up to "
            f"{realism.THRESHOLD_GAIN_MAX_PERCENT:g} %"
        ) in FLAT_README

    def test_it_says_that_the_target_stays_the_athletes(self) -> None:
        assert "your own target stays yours" in FLAT_README

    def test_it_links_to_the_page(self) -> None:
        assert "docs/goals.md" in README


@pytest.mark.parametrize("name", ["weekly-plan.md", "season.md"])
def test_the_pages_that_link_to_it_find_it(name: str) -> None:
    text = (ROOT / "docs" / name).read_text()

    assert "goals.md" in text
    assert (ROOT / "docs" / "goals.md").exists()
