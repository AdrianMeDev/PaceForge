"""The page ``docs/background-jobs.md`` is compared with the code, so that it cannot drift."""

import re
from pathlib import Path

from django.conf import settings

from jobs.models import Code, Job
from jobs.schedule import MAX_FAILED_TRIES

ROOT = Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs" / "background-jobs.md").read_text()
README = (ROOT / "README.md").read_text()
FLAT_DOC = " ".join(DOC.split())
FLAT_README = " ".join(README.split())

# The three management commands that the page documents, by the name a user passes to manage.py.
COMMANDS = ("run_scheduler", "sync_activities", "review_weeks", "draft_next_week")

# The settings the scheduler reads, with their range in the page.
DEFAULTS = {
    "JOBS_SYNC_HOURS": (settings.JOBS_SYNC_HOURS, "1 to 24"),
    "JOBS_SUNDAY_HOUR": (settings.JOBS_SUNDAY_HOUR, "0 to 23"),
    "JOBS_INTERVAL_MINUTES": (settings.JOBS_INTERVAL_MINUTES, "1 to 60"),
}


def rows_in(text: str, first_cell: str) -> list[list[str]]:
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


class TestTheJobs:
    def test_the_page_names_every_job_in_the_order_they_run(self) -> None:
        names = [job.value for job in Job]

        assert names == ["sync", "week_review", "week_draft"]
        assert "sync" in DOC and "week_review" in DOC and "week_draft" in DOC
        assert FLAT_DOC.index("sync") < FLAT_DOC.index("week review")
        assert FLAT_DOC.index("week review") < FLAT_DOC.index("week draft")


class TestTheCodes:
    def test_the_page_names_every_code(self) -> None:
        for code in Code.values:
            assert f"`{code}`" in DOC, code

    def test_the_page_names_no_other_code(self) -> None:
        documented = {row[0] for row in rows_in(DOC, "Code")}

        assert documented == set(Code.values)


class TestTheDefaults:
    def test_the_page_gives_the_default_and_the_range_of_each_setting(self) -> None:
        rows = {row[0]: row for row in rows_in(DOC, "Variable")}

        for name, (default, between) in DEFAULTS.items():
            assert rows[name][1] == str(default), name
            assert between in rows[name][2], name

    def test_the_defaults_match_the_code(self) -> None:
        for name, (default, _between) in DEFAULTS.items():
            assert getattr(settings, name) == default, name


class TestTheCommands:
    def test_the_page_gives_every_command_with_manage_py(self) -> None:
        for command in COMMANDS:
            assert f"python manage.py {command}" in DOC, command

    def test_every_command_exists_in_the_code(self) -> None:
        from django.core.management import find_commands

        commands = set(find_commands(str(Path(settings.BASE_DIR) / "jobs" / "management")))

        assert set(COMMANDS) <= commands


class TestTheSafetyWords:
    def test_the_page_never_confirms_and_never_pushes(self) -> None:
        assert "**never confirms**" in FLAT_DOC
        assert "**never pushes**" in FLAT_DOC

    def test_the_page_says_the_log_holds_numbers_and_fixed_words_only(self) -> None:
        assert "numbers only" in FLAT_DOC or "numbers are" in FLAT_DOC
        assert "ever holds a word from the coach" in FLAT_DOC
        assert "Intervals.icu" in FLAT_DOC

    def test_the_failed_cap_is_the_one_of_the_code(self) -> None:
        assert f"`MAX_FAILED_TRIES` ({MAX_FAILED_TRIES})" in FLAT_DOC
        assert MAX_FAILED_TRIES == 3


class TestTheReadme:
    def test_it_points_to_the_page(self) -> None:
        assert "docs/background-jobs.md" in README

    def test_it_names_the_automation_page(self) -> None:
        assert "/settings/automation" in README
        assert "Automation" in README

    def test_it_names_the_three_settings(self) -> None:
        for name in DEFAULTS:
            assert f"`{name}`" in README, name

    def test_the_readme_string_of_each_setting_matches_the_page(self) -> None:
        readme = re.search(r"^## Configuration\n(.*?)^## ", README, re.S | re.M)
        assert readme, "no Configuration section"
        for name in DEFAULTS:
            assert f"`{name}`" in readme.group(1), name
