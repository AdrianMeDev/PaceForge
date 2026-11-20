import json

import pytest

from accounts.models import User
from goals import services as goal_services
from planning.schema import DURATION_MAX, MAX_WORKOUTS
from reviews.briefing import MAX_BYTES, MAX_UNPLANNED, build_briefing, to_json
from reviews.models import WeekComment, WeekFeedback
from reviews.services import week_review

from .builders import MONDAY, NOW, make_activity, make_plan

pytestmark = pytest.mark.django_db

MARKER = "SECRETMARKER"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def briefing(user: User) -> dict:
    return build_briefing(week_review(user, MONDAY))


KEYS = {
    "week_start",
    "today",
    "workouts",
    "unplanned",
    "unplanned_not_shown",
    "sports",
    "total",
    "statuses",
    "done_percent",
    "feedback",
}


class TestTheKeys:
    def test_an_empty_week(self, alice: User) -> None:
        data = briefing(alice)

        assert set(data) == KEYS
        assert (data["week_start"], data["today"]) == ("2026-11-09", "2026-11-14")
        assert data["workouts"] == [] and data["unplanned"] == [] and data["sports"] == []
        assert data["unplanned_not_shown"] == 0
        assert data["done_percent"] is None and data["feedback"] is None
        assert data["statuses"] == {
            "done": 0,
            "partial": 0,
            "missed": 0,
            "replaced": 0,
            "open": 0,
        }
        assert data["total"] == {
            "planned_count": 0,
            "planned_minutes": 0,
            "planned_load": 0,
            "actual_count": 0,
            "actual_minutes": 0,
            "load": 0,
            "loaded_count": 0,
            "rated_count": 0,
        }

    def test_it_is_plain_json_data(self, alice: User) -> None:
        make_plan(alice, workouts=2)
        make_activity(alice, "2026-11-09T07:00", rpe=6)

        data = briefing(alice)

        assert json.loads(json.dumps(data)) == data


class TestTheWorkouts:
    def test_what_was_planned_and_what_was_done(self, alice: User) -> None:
        make_plan(alice, workouts=3)  # Monday, Tuesday, Wednesday; the clock is on Saturday
        make_activity(alice, "2026-11-09T07:00", rpe=6, timer_seconds=3000.0)
        make_activity(alice, "2026-11-10T07:00", sport="cycling", timer_seconds=1800.0)

        first, second, third = briefing(alice)["workouts"]

        assert first == {
            "day": 0,
            "sport": "running",
            "goal": "endurance",
            "planned_minutes": 60,
            "status": "done",
            "done_minutes": 50,
            "rpe": 6,
        }
        assert (second["day"], second["status"], second["done_minutes"], second["rpe"]) == (
            1,
            "replaced",
            30,
            None,
        )
        assert (third["day"], third["status"], third["done_minutes"]) == (2, "missed", None)

    def test_a_workout_whose_day_is_not_over_is_open(self, alice: User) -> None:
        make_plan(alice, workouts=7)

        statuses = [workout["status"] for workout in briefing(alice)["workouts"]]

        assert statuses == ["missed"] * 5 + ["open"] * 2

    @pytest.mark.parametrize(
        ("seconds", "minutes"), [(629, 10), (630, 11), (3600, 60), (29, 0), (None, None)]
    )
    def test_minutes_are_whole_minutes_rounded_half_up(
        self, alice: User, seconds: float | None, minutes: int | None
    ) -> None:
        make_plan(alice, workouts=1)
        make_activity(alice, "2026-11-09T07:00", timer_seconds=seconds, elapsed_seconds=None)

        assert briefing(alice)["workouts"][0]["done_minutes"] == minutes

    def test_the_elapsed_time_stands_in_for_the_timer_time(self, alice: User) -> None:
        make_plan(alice, workouts=1)
        make_activity(alice, "2026-11-09T07:00", timer_seconds=None, elapsed_seconds=1800.0)

        assert briefing(alice)["workouts"][0]["done_minutes"] == 30

    def test_the_figures_per_sport_and_in_all(self, alice: User) -> None:
        make_plan(alice, workouts=2)
        make_activity(alice, "2026-11-09T07:00", rpe=5, timer_seconds=3600.0)

        data = briefing(alice)

        (running,) = data["sports"]
        assert running == {
            "sport": "running",
            "planned_count": 2,
            "planned_minutes": 120,
            "planned_load": 110,
            "actual_count": 1,
            "actual_minutes": 60,
            "load": 50,
            "loaded_count": 1,
            "rated_count": 1,
        }
        assert data["total"]["load"] == 50
        assert data["total"]["planned_load"] == 110
        assert data["total"]["loaded_count"] == 1
        assert data["done_percent"] == 50
        assert data["statuses"]["done"] == 1 and data["statuses"]["missed"] == 1

    def test_load_per_sport_includes_unrated_intervals_activities(self, alice: User) -> None:
        make_plan(alice, workouts=[{"sport": "cycling", "goal": "tempo"}, {}])
        make_activity(alice, "2026-11-09T07:00", sport="cycling", training_load=79.5)
        make_activity(alice, "2026-11-10T07:00", rpe=5)
        make_activity(alice, "2026-11-12T07:00", sport="swimming", training_load=0)

        data = briefing(alice)

        keys = ("planned_load", "load", "loaded_count", "rated_count")
        assert {item["sport"]: tuple(item[key] for key in keys) for item in data["sports"]} == {
            "running": (55, 50, 1, 1),
            "cycling": (75, 80, 1, 0),
            "swimming": (0, 0, 1, 0),
        }
        assert tuple(data["total"][key] for key in keys) == (130, 130, 3, 1)


class TestTheSessionsThatWereNotPlanned:
    def test_they_are_told_with_their_day(self, alice: User) -> None:
        make_plan(alice, workouts=1)
        make_activity(alice, "2026-11-09T07:00")
        make_activity(alice, "2026-11-12T18:00", sport="strength", rpe=7, timer_seconds=1800.0)

        assert briefing(alice)["unplanned"] == [
            {"day": 3, "sport": "strength", "minutes": 30, "rpe": 7}
        ]

    def test_at_most_a_fixed_number_are_told_and_the_rest_is_counted(self, alice: User) -> None:
        for n in range(MAX_UNPLANNED + 3):
            make_activity(alice, f"2026-11-{9 + n // 4:02d}T{6 + n % 4 * 3:02d}:00")

        data = briefing(alice)

        assert len(data["unplanned"]) == MAX_UNPLANNED
        assert data["unplanned_not_shown"] == 3
        days = [entry["day"] for entry in data["unplanned"]]
        assert days == sorted(days)  # the earliest are told

    def test_without_the_cap_nothing_is_left_out(self, alice: User) -> None:
        for n in range(MAX_UNPLANNED):
            make_activity(alice, f"2026-11-{9 + n // 4:02d}T{6 + n % 4 * 3:02d}:00")

        data = briefing(alice)

        assert len(data["unplanned"]) == MAX_UNPLANNED and data["unplanned_not_shown"] == 0


class TestTheFeedback:
    def test_only_the_three_scales_are_told(self, alice: User) -> None:
        WeekFeedback.objects.create(
            owner=alice, week_start=MONDAY, fatigue=4, motivation=2, pain=1, notes="Heavy legs"
        )

        assert briefing(alice)["feedback"] == {"fatigue": 4, "motivation": 2, "pain": 1}

    def test_a_scale_that_was_not_given_is_null(self, alice: User) -> None:
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, notes="only a note")

        assert briefing(alice)["feedback"] == {"fatigue": None, "motivation": None, "pain": None}

    def test_no_feedback_is_null(self, alice: User) -> None:
        assert briefing(alice)["feedback"] is None


class TestWhatIsNeverTold:
    def test_no_free_text_and_no_id_whatever_the_user_wrote(self, alice: User) -> None:
        plan = make_plan(alice, workouts=[{"title": MARKER, "notes": MARKER}] * 2)
        run = make_activity(
            alice,
            "2026-11-09T07:00",
            notes=MARKER,
            source_sport=MARKER,
            manufacturer=MARKER,
            rpe=5,
        )
        other = make_activity(alice, "2026-11-12T07:00", notes=MARKER, sport="other")
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, fatigue=3, notes=MARKER)
        WeekComment.objects.create(owner=alice, week_start=MONDAY, comment=MARKER, next_week="hold")

        text = to_json(briefing(alice))

        assert MARKER not in text
        for ident in (
            plan.pk,
            run.pk,
            other.pk,
            alice.pk,
            *plan.workouts.values_list("pk", flat=True),
        ):
            assert str(ident) not in text
        assert "alice" not in text and "@" not in text

    def test_only_numbers_fixed_words_and_the_two_dates_are_in_it(self, alice: User) -> None:
        make_plan(alice, workouts=2)
        make_activity(alice, "2026-11-09T07:00", rpe=5)
        make_activity(alice, "2026-11-12T07:00", sport="strength")
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, fatigue=3, notes="x")

        strings: list[str] = []

        def collect(value: object) -> None:
            if isinstance(value, str):
                strings.append(value)
            elif isinstance(value, dict):
                for found in value.values():
                    collect(found)
            elif isinstance(value, list):
                for found in value:
                    collect(found)

        collect(briefing(alice))

        assert set(strings) <= {
            "2026-11-09",
            "2026-11-14",
            "running",
            "cycling",
            "swimming",
            "strength",
            "other",
            "endurance",
            "done",
            "partial",
            "missed",
            "replaced",
            "open",
        }

    def test_the_data_of_another_user_is_not_told(self, alice: User, bob: User) -> None:
        make_plan(bob, workouts=3)
        make_activity(bob, "2026-11-09T07:00", training_load=999, rpe=9)
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY, pain=5)

        data = briefing(alice)

        assert data["workouts"] == [] and data["unplanned"] == [] and data["feedback"] is None
        assert data["sports"] == []
        assert all(value == 0 for value in data["total"].values())


class TestTheText:
    def test_the_same_week_is_the_same_text(self, alice: User) -> None:
        make_plan(alice, workouts=3)
        make_activity(alice, "2026-11-09T07:00", rpe=6)

        assert to_json(briefing(alice)) == to_json(briefing(alice))

    def test_the_keys_are_sorted_and_there_are_no_spaces(self, alice: User) -> None:
        text = to_json(briefing(alice))

        assert text.startswith('{"done_percent":null,"feedback":null,')
        assert ", " not in text and ": " not in text

    def test_a_week_at_every_limit_stays_below_the_size_limit(self, alice: User) -> None:
        make_plan(
            alice,
            workouts=[{"duration_minutes": DURATION_MAX, "zone_system": "power", "zone": 7}]
            * MAX_WORKOUTS,
        )
        for n in range(MAX_WORKOUTS):
            make_activity(
                alice,
                f"2026-11-{9 + n % 7:02d}T{6 + n // 7 * 3:02d}:00",
                sport=["running", "cycling", "swimming", "strength", "other"][n % 5],
                rpe=10,
                timer_seconds=86399.0,
                training_load=9999.5,
            )
        for n in range(MAX_UNPLANNED + 20):
            make_activity(alice, f"2026-11-{9 + n % 7:02d}T{18 + n // 7:02d}:{n % 60:02d}", rpe=10)
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY, fatigue=5, motivation=5, pain=5)

        data = briefing(alice)
        text = to_json(data)

        assert data["total"]["planned_load"] == MAX_WORKOUTS * 3480
        assert data["total"]["loaded_count"] == MAX_WORKOUTS + MAX_UNPLANNED + 20
        assert len(text.encode()) < MAX_BYTES
