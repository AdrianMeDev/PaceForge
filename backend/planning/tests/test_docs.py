"""The page ``docs/weekly-plan.md`` is compared with the code, so that it cannot drift."""

import ast
import dataclasses
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.urls import get_resolver

from accounts.models import User
from availability.intensity import LEVEL_LIMITS
from availability.models import SESSIONS_PER_WEEK_MAX, SPORTS, BodyPart
from availability.serializers import MAX_LIMITATIONS, availability_data
from coach import views as coach_views
from coach.endpoints import parse_base_urls
from coach.providers.openai_compatible import JSON_MODE_HOSTS
from coach.providers.transport import TIMEOUT_SECONDS
from planning import briefing, editing, generation, models, prompt, rules, schema
from planning.briefing import build_briefing
from planning.context import PlanContext
from planning.rules import SPORT_ZONE_SYSTEMS
from planning.schema import Sport, ZoneSystem, parse_week_plan
from planning.validation import validate_week
from planning.views import NO_TIME

ROOT = Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs" / "weekly-plan.md").read_text()
README = (ROOT / "README.md").read_text()
# The same with every run of white space as one space, for sentences that the file wraps.
FLAT_README = " ".join(README.split())


def section(heading: str) -> str:
    """The text of a ``##`` section of the page, up to the next one."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", DOC, re.S | re.M)
    assert match, f"no section {heading!r}"
    return match.group(1)


def subsection(heading: str) -> str:
    """The text of a ``###`` section of the page, up to the next heading."""
    match = re.search(rf"^### {re.escape(heading)}\n(.*?)(?=^#{{2,3}} |\Z)", DOC, re.S | re.M)
    assert match, f"no subsection {heading!r}"
    return match.group(1)


def integer_constants(module: object) -> dict[str, int]:
    """The ``NAME = 123`` assignments of a module's own source (not what it imports)."""
    tree = ast.parse(Path(module.__file__).read_text())  # type: ignore[attr-defined]
    found = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.isupper()
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
            and not isinstance(node.value.value, bool)
        ):
            found[node.targets[0].id] = node.value.value
    return found


def rows(text: str) -> list[list[str]]:
    """The body rows of the tables in ``text``, cells without backticks."""
    found = []
    for line in text.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        found.append([cell.strip().replace("`", "") for cell in line.strip("|").split("|")])
    return [
        row
        for row in found
        if row[0]
        not in {"Field", "Code", "Constant", "System", "Status", "Key", "Endpoint", "Level"}
    ]


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
            stretching=True,
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


class TestTheIntensityLevels:
    def test_the_table_has_the_limits_of_every_level(self) -> None:
        documented = {
            row[0]: (int(row[1]), int(row[2]), int(row[3]), int(row[4]), int(row[5]))
            for row in rows(section("The intensity levels"))
        }

        assert documented == {
            level.value: (
                limits.max_hard_days,
                limits.progression_warning_percent,
                limits.progression_error_percent,
                limits.easy_share_percent,
                limits.run_progression_warning_percent,
            )
            for level, limits in LEVEL_LIMITS.items()
        }


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
        assert len(rules.ALL_CHECKS) == 30
        assert len(self.in_the_code()) == 36


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

    def test_every_field_of_a_workout_and_a_segment_is_named_on_the_page(self) -> None:
        text = section("The format")

        for dataclass in (schema.Workout, schema.Segment, schema.Exercise):
            for field in dataclasses.fields(dataclass):
                assert f"`{field.name}`" in text, field.name

    def test_the_enums_named_on_the_page_are_those_of_the_code(self) -> None:
        text = section("The format")

        for enum in (
            schema.Sport,
            schema.Goal,
            schema.SegmentKind,
            schema.Slot,
            schema.ExerciseRegion,
            schema.ExerciseEquipment,
        ):
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


class TestTheNote:
    def test_the_limit_of_the_note_is_the_one_in_the_code(self) -> None:
        text = " ".join(section("Drafting with the coach").split())

        assert models.NOTE_MAX == 300
        assert "up to 300 characters (`NOTE_MAX` in `backend/planning/models.py`)" in text
        assert Path(models.__file__).as_posix().endswith("backend/planning/models.py")

    def test_the_page_says_the_note_is_data_and_never_an_instruction(self) -> None:
        text = " ".join(section("Drafting with the coach").split())

        assert "never an instruction about the rules, the format or the task" in text
        assert prompt.SYSTEM_PROMPT.count("never an instruction about these rules") == 1


class TestTheBriefing:
    @pytest.mark.django_db
    def test_the_table_lists_exactly_the_keys_the_coach_is_told(self) -> None:
        user = User.objects.create_user("docs@example.com")

        told = set(build_briefing(user, date(2027, 7, 12)))

        assert {row[0] for row in rows(subsection("What the coach is told"))} == told

    @pytest.mark.django_db
    def test_the_limits_keys_are_documented(self) -> None:
        user = User.objects.create_user("docs-limits@example.com")
        limits = build_briefing(user, date(2027, 7, 12))["limits"]
        table = {row[0]: row[1] for row in rows(subsection("What the coach is told"))}

        for key in limits:
            assert re.search(rf"\b{re.escape(key)}\b", table["limits"]), key

    def test_the_page_names_what_is_never_sent(self) -> None:
        text = subsection("What the coach is told")

        for word in ("limitations", "e-mail", "never"):
            assert word in text, word


class TestTheDraftingLimits:
    MODULES = (briefing, generation, prompt)

    def test_every_documented_limit_has_the_value_in_the_code(self) -> None:
        code = {k: v for module in self.MODULES for k, v in integer_constants(module).items()}

        documented = {r[0]: int(r[1]) for r in rows(subsection("The drafting limits"))}

        for name, value in documented.items():
            assert code[name] == value, name

    def test_every_limit_of_the_drafting_is_documented(self) -> None:
        code = {name for module in self.MODULES for name in integer_constants(module)}

        assert code == {r[0] for r in rows(subsection("The drafting limits"))}

    def test_the_time_a_draft_may_take_is_attempts_times_the_timeout(self) -> None:
        text = subsection("Time and the web server")

        assert generation.ATTEMPTS * TIMEOUT_SECONDS == 120
        assert "60 seconds" in text
        assert "= 120" in text
        assert "150 seconds" in text


class TestTheApi:
    def in_the_code(self) -> set[tuple[str, str]]:
        found = set()
        resolver: Any = get_resolver()
        for pattern in resolver.url_patterns:
            if "planning" not in str(pattern.pattern):
                continue
            for inner in pattern.url_patterns:
                path = "/api/planning/" + re.sub(r"<[a-z]+:[a-z_]+>", "<>", str(inner.pattern))
                view: Any = inner.callback
                for method in view.view_class.http_method_names:
                    if method in {"get", "post"}:
                        found.add((method.upper(), path))
        return found

    def test_the_table_lists_every_endpoint_with_its_method(self) -> None:
        text = subsection("The API")
        documented = set()
        for row in rows(text[: text.index("| Code |")]):
            method, path = row[0].split(" ", 1)
            documented.add((method, re.sub(r"<[A-Za-z]+>", "<>", path)))

        assert documented == self.in_the_code()

    def test_the_table_lists_every_error_with_its_status(self) -> None:
        source = (Path(rules.__file__).parent / "views.py").read_text()
        # The answers to provider errors are shared with other endpoints: they live in coach.views.
        provider_source = Path(coach_views.__file__).read_text()
        code = {
            (code, status)
            for status, code in re.findall(
                r'_error\(\s*status\.HTTP_(\d+)_[A-Z_]+,\s*"([a-z_]+)"', source
            )
        } | {
            (code, status)
            for status, code in re.findall(
                r'_problem\(\s*status\.HTTP_(\d+)_[A-Z_]+,\s*"([a-z_]+)"', provider_source
            )
        }

        text = subsection("The API")
        error_table = text[text.index("| Code |") :]
        documented = {(row[0], row[1]) for row in rows(error_table)}

        assert documented == code

    def test_the_limit_of_requests_is_the_documented_one(self) -> None:
        framework: Any = settings.REST_FRAMEWORK
        rate = framework["DEFAULT_THROTTLE_RATES"]["planning_generate"]

        assert rate == "5/min"
        assert "5 a minute" in subsection("The API")


class TestTheJsonMode:
    def test_the_page_lists_the_hosts_of_the_code(self) -> None:
        match = re.search(r"JSON output is requested from these hosts: (.*?)\.\n", DOC, re.S)
        assert match, "no list of hosts"

        assert set(re.findall(r"`([^`]+)`", match.group(1))) == set(JSON_MODE_HOSTS)

    def test_the_readme_names_every_such_host(self) -> None:
        for host in JSON_MODE_HOSTS:
            assert f"https://{host}" in README, host


class TestTheReadmeExamples:
    def lines(self) -> list[str]:
        return re.findall(r"^AI_ALLOWED_BASE_URLS=(.+)$", README, re.M)

    def test_there_are_examples(self) -> None:
        assert len(self.lines()) >= 2

    def test_every_address_of_every_example_is_accepted_by_the_code(self) -> None:
        for line in self.lines():
            entries = line.split(",")

            assert len(parse_base_urls("AI_ALLOWED_BASE_URLS", entries)) == len(entries), line

    def test_the_examples_show_the_services_that_the_form_names(self) -> None:
        text = "\n".join(self.lines())

        assert "https://api.deepseek.com" in text
        assert "https://openrouter.ai/api/v1" in text


class TestTheReadmeOnTheTypicalWeek:
    def test_the_api_line_names_every_field_the_api_answers_with(self) -> None:
        for key in availability_data(None, []):
            assert f"`{key}`" in README, key

    def test_the_constant_that_sets_the_share_is_named_with_its_file(self) -> None:
        assert "`TYPICAL_VOLUME_PERCENT` in `backend/planning/rules.py`" in FLAT_README
        assert rules.TYPICAL_VOLUME_PERCENT == 100
        assert "(100 counts the whole week" in FLAT_README

    def test_the_message_for_a_week_without_time_is_the_one_of_the_server(self) -> None:
        assert NO_TIME.startswith("You have no training time for this week.")
        assert '"You have no training time for this week."' in FLAT_README

    def test_the_form_label_is_the_one_of_the_page(self) -> None:
        page = (ROOT / "frontend/src/app/features/availability/availability-page.html").read_text()

        assert re.search(r"<h2[^>]*>\s*A normal week\s*</h2>", page)
        assert "**A normal week.**" in FLAT_README
        assert "enter **A normal week**" in FLAT_README

    def test_the_free_text_is_said_to_stay_home_unless_the_switch_is_on(self) -> None:
        assert "it is there for the coach" not in FLAT_README
        assert "it is not sent to the coach either" not in FLAT_README
        assert "By default it is not sent to the coach" in FLAT_README
        assert "Tick **Send this text to my AI coach**" in FLAT_README

    def test_the_switch_has_the_words_of_the_page(self) -> None:
        page = (ROOT / "frontend/src/app/features/availability/availability-page.html").read_text()

        assert "Send this text to my AI coach" in page
        assert "**Send this text to my AI coach**" in FLAT_README

    def test_the_number_of_characters_is_the_one_of_the_briefing_and_of_the_page(self) -> None:
        script = (ROOT / "frontend/src/app/features/availability/availability-page.ts").read_text()
        match = re.search(r"LIMITATIONS_TEXT_TOLD = (\d+);", script)

        assert match
        assert int(match.group(1)) == briefing.LIMITATIONS_TEXT_MAX_TOLD
        assert f"**first {briefing.LIMITATIONS_TEXT_MAX_TOLD} characters**" in FLAT_README
        assert f"(then its first {briefing.LIMITATIONS_TEXT_MAX_TOLD} characters)" in FLAT_README

    def test_the_list_of_injuries_is_described_as_the_code_has_it(self) -> None:
        assert f"at most {MAX_LIMITATIONS} entries" in FLAT_README
        assert f"the newest {briefing.MAX_LIMITATIONS_TOLD}" in FLAT_README
        for part in BodyPart:
            assert part.label.lower().split()[0] in FLAT_README.lower(), part


class TestTheReadmeOnSportPreferences:
    PAGE = (ROOT / "frontend/src/app/features/availability/sport-preferences.html").read_text()
    SCRIPT = (ROOT / "frontend/src/app/features/availability/sport-preferences.ts").read_text()

    def test_the_words_of_the_page_are_the_words_of_the_readme(self) -> None:
        assert "What strength training is for" in self.PAGE
        assert "**What strength training is for**" in FLAT_README
        for label in ("Goal sport", "Secondary sport", "Supplementary"):
            assert f"label: '{label}'" in self.SCRIPT, label
            assert f"**{label}**" in FLAT_README, label
        for label in ("Legs", "Core", "Upper body", "Full body"):
            assert f"label: '{label}'" in self.SCRIPT, label
            assert f"**{label}**" in FLAT_README, label

    def test_the_number_of_sessions_is_the_one_of_the_code(self) -> None:
        assert f"SESSIONS_MAX = {SESSIONS_PER_WEEK_MAX};" in self.SCRIPT
        assert f"from 0 to {SESSIONS_PER_WEEK_MAX}" in FLAT_README

    def test_the_two_warnings_are_named_in_the_checks_page(self) -> None:
        for code in ("sessions_out_of_range", "legs_before_key_run"):
            assert f"`{code}`" in DOC, code


class TestTheReadmeOnTheWishesForAWeek:
    HTML = (ROOT / "frontend/src/app/features/availability/week-wishes.html").read_text()

    def test_the_labels_of_the_page_are_the_words_of_the_readme(self) -> None:
        for label in (
            "Days a week you want to train on, at most",
            "Least you want to train in a week",
            "Day of your long run",
            "Day of your long ride",
        ):
            assert label in self.HTML, label
            assert f"**{label}**" in FLAT_README, label

    def test_the_three_warnings_are_named_in_the_checks_page(self) -> None:
        for code in ("too_many_training_days", "below_minimum_minutes", "long_session_elsewhere"):
            assert f"`{code}`" in DOC, code


class TestTheReadmeOnSportsAndDoubleDays:
    PAGE = (ROOT / "frontend/src/app/features/availability/availability-page.html").read_text()

    def test_the_labels_of_the_page_are_the_words_of_the_readme(self) -> None:
        for label in ("Sports for your plan", "Add stretching to sessions"):
            assert label in self.PAGE, label
        assert "**Add stretching to sessions**" in FLAT_README
        assert "<legend>Sports for your plan</legend>" in self.PAGE

    def test_the_four_sports_are_named_as_the_page_names_them(self) -> None:
        for name in ("Running", "Cycling", "Swimming", "Strength / gym"):
            assert f"**{name}**" in FLAT_README, name
        assert len(SPORTS) == 4

    def test_the_three_times_of_day_are_those_of_the_format(self) -> None:
        for slot in schema.Slot:
            assert f"**{slot.value}**" in FLAT_README, slot

    def test_stretching_is_said_to_be_never_a_session_and_to_cost_no_time(self) -> None:
        assert "never a session of its own" in FLAT_README
        assert "uses up none of your minutes" in FLAT_README
        assert "+ 10 min stretching" in FLAT_README

    def test_the_time_is_given_per_day_and_the_parts_of_the_day_are_known_to_the_coach(
        self,
    ) -> None:
        assert "given **per day**" in FLAT_README
        assert "knows from the Training time page in which parts of the day you can train" in (
            FLAT_README
        )
        assert "does not know that you can only train in the evening" not in FLAT_README

    def test_the_words_of_the_day_options_are_those_of_the_page(self) -> None:
        options = (ROOT / "frontend/src/app/features/availability/day-options.html").read_text()
        script = (ROOT / "frontend/src/app/features/availability/day-options.ts").read_text()

        assert re.search(r"<h2[^>]*>\s*Parts of the day and two sessions\s*</h2>", self.PAGE)
        assert "**Parts of the day and two sessions.**" in FLAT_README
        assert "Two sessions" in options and "**Two sessions**" in FLAT_README
        for label in ("Morning", "Afternoon", "Evening"):
            assert f"label: '{label}'" in script, label
            assert f"**{label}**" in FLAT_README, label

    def test_the_format_page_says_what_the_fields_mean(self) -> None:
        text = section("The format")

        assert f"0 to {schema.STRETCHING_MAX}" in text
        assert "**never a workout of its own**" in " ".join(text.split())
        assert "`stretching_minutes`" in text and "`slot`" in text

    def test_the_old_sentence_about_no_time_of_day_is_gone(self) -> None:
        assert "There is **no time of day**" not in DOC


class TestTheReadmeTable:
    def row(self, name: str) -> str:
        (line,) = [r for r in README.splitlines() if r.startswith(f"| {name} ")]
        return line

    def test_the_table_has_the_addresses_that_the_examples_and_the_form_use(self) -> None:
        assert "`https://api.deepseek.com`" in self.row("DeepSeek")
        assert "`https://openrouter.ai/api/v1`" in self.row("OpenRouter")

    def test_the_addresses_of_the_table_are_accepted_by_the_code(self) -> None:
        for name in ("DeepSeek", "OpenRouter"):
            (address,) = re.findall(r"`(https?://[^`]+)`", self.row(name))

            assert parse_base_urls("AI_ALLOWED_BASE_URLS", [address]) == (address,)


class TestTheReadme:
    def test_it_points_to_the_page(self) -> None:
        assert "docs/weekly-plan.md" in README

    def test_it_describes_the_week_plan_page(self) -> None:
        assert "## Week plan" in README
        assert "/planning" in README
        assert "Drafting with the coach" in README

    def test_the_page_exists_and_is_not_empty(self) -> None:
        assert len(DOC) > 3000


def test_the_page_names_the_function_that_drafts() -> None:
    assert "planning.generation.generate(user, monday)" in DOC
    assert callable(generation.generate)


def test_the_page_names_every_public_service_function() -> None:
    from planning import services

    for name in ("save_draft", "canonical", "validate", "confirm"):
        assert f"services.{name}" in DOC, name
        assert callable(getattr(services, name))


@pytest.mark.parametrize("word", ["Monday", "superseded", "tolerance"])
def test_a_few_words_that_the_page_must_keep(word: str) -> None:
    assert word in DOC


class TestTheReadmeOnChangingAPlan:
    FRONTEND = ROOT / "frontend" / "src" / "app" / "features" / "planning"

    def test_the_reasons_of_a_change_and_of_a_restored_version_are_those_of_the_code(self) -> None:
        assert editing.REASON == "Changed by hand"
        assert f'(its reason is "{editing.REASON}")' in FLAT_README
        assert '(its reason is "Restored from version N")' in FLAT_README

    @pytest.mark.parametrize(
        ("file", "label"),
        [
            ("planning-page.html", "Change this plan"),
            ("plan-editor.html", "Save as a new version"),
            ("plan-editor.html", "Discard changes"),
            ("planning-page.html", "Make this the new draft"),
            ("workout-form.html", "Remove the interval structure"),
        ],
    )
    def test_every_button_the_readme_names_is_one_of_the_page(self, file: str, label: str) -> None:
        assert label in (self.FRONTEND / file).read_text(), label
        assert f"**{label}**" in FLAT_README or f"*{label}*" in FLAT_README, label

    def test_it_says_that_there_is_no_drag_and_drop(self) -> None:
        assert "(there is no drag and drop)" in FLAT_README

    def test_it_says_that_a_confirmed_plan_is_never_changed_and_errors_can_be_saved(self) -> None:
        assert "a confirmed plan is never changed" in FLAT_README
        assert "A plan with errors can be saved too; it only cannot be confirmed" in FLAT_README

    def test_it_says_what_a_change_does_to_the_calendar_and_the_week_review(self) -> None:
        assert "**updates its event** in your calendar" in FLAT_README
        assert "moves with it to the new version when that is confirmed" in FLAT_README

    def test_the_page_of_the_api_names_the_three_endpoints(self) -> None:
        for path in ("/check/", "/revise/", "/restore/"):
            assert "/api/planning/" in DOC and path in DOC, path


class TestLoadEstimation:
    def test_the_load_constants_match_the_code(self) -> None:
        from activities import load as activity_load
        from planning import load

        table = {row[0]: row[1] for row in rows(section("Estimating workout load"))}

        assert table["FIVE_ZONE_LOAD_PER_HOUR"] == ", ".join(
            str(v) for v in load.FIVE_ZONE_LOAD_PER_HOUR
        )
        assert table["POWER_LOAD_PER_HOUR"] == ", ".join(str(v) for v in load.POWER_LOAD_PER_HOUR)
        for goal, rate in load.GOAL_LOAD_PER_HOUR.items():
            assert int(table[f"GOAL_LOAD_PER_HOUR ({goal.value})"]) == rate, goal
        assert int(table["DEFAULT_STRENGTH_RPE"]) == load.DEFAULT_STRENGTH_RPE
        assert int(table["RPE_LOAD_PER_HOUR"]) == activity_load.RPE_LOAD_PER_HOUR

    def test_the_api_documents_read_only_load_fields_and_minute_checks(self) -> None:
        text = subsection("The API")

        for field in (
            "estimated_load",
            "load",
            "sports",
            "total",
            "planned_minutes",
            "done_minutes",
            "planned_load",
            "done_load",
        ):
            assert f"`{field}`" in text, field
        assert "All planning checks still use minutes." in " ".join(text.split())

    def test_the_readme_describes_unified_load_and_planned_vs_done(self) -> None:
        for phrase in (
            "Planned vs done load",
            "estimated_load",
            "training_load",
            "All planning checks still use minutes.",
        ):
            assert phrase in FLAT_README, phrase
