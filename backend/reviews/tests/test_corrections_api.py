import json
from datetime import timedelta
from http import HTTPStatus
from typing import Any
from uuid import UUID, uuid4

import pytest

from accounts.models import User
from accounts.tests.conftest import AuthApi
from goals import services as goal_services
from planning.models import PlannedWorkout
from reviews.models import WorkoutReview

from .builders import MONDAY, NOW, make_activity, make_plan
from .conftest import make_user, signed_in

pytestmark = pytest.mark.django_db

MARKER = "SECRETMARKER"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return make_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return make_user("bob@example.com")


def url(workout: PlannedWorkout | UUID | str, monday: Any = MONDAY) -> str:
    ident = workout.pk if isinstance(workout, PlannedWorkout) else workout
    return f"/api/reviews/weeks/{monday}/workouts/{ident}/"


def decide(
    user: User, workout: PlannedWorkout | UUID | str, monday: Any = MONDAY, **form: Any
) -> Any:
    return signed_in(user).call("PUT", url(workout, monday), form)


def body(response: Any) -> Any:
    return json.loads(response.content)


def workouts_of(data: Any) -> dict[str, Any]:
    return {workout["id"]: workout for workout in data["workouts"]}


@pytest.fixture
def week(alice: User) -> tuple[PlannedWorkout, PlannedWorkout]:
    """Two workouts, on Monday and Tuesday, in a week of which all but two days are over."""
    plan = make_plan(alice, workouts=2)
    first, second = plan.workouts.all()
    return first, second


class TestLinking:
    def test_the_user_links_an_activity_to_a_workout(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, second = week
        run = make_activity(alice, "2026-11-09T07:00")
        later = make_activity(alice, "2026-11-12T07:00", timer_seconds=1800.0)

        response = decide(alice, second, activity=str(later.pk))

        assert response.status_code == HTTPStatus.OK
        shown = workouts_of(body(response))
        assert shown[str(first.pk)]["activity_id"] == str(run.pk)
        assert shown[str(second.pk)]["activity_id"] == str(later.pk)
        assert shown[str(second.pk)]["activity_origin"] == "user"
        assert shown[str(second.pk)]["status"] == "partial"  # 30 of 60 minutes
        review = WorkoutReview.objects.get()
        assert (review.workout, review.activity, review.no_activity, review.status) == (
            second,
            later,
            False,
            "",
        )

    def test_the_answer_is_the_whole_week_as_the_get_shows_it(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        run = make_activity(alice, "2026-11-09T07:00")

        answer = body(decide(alice, week[1], activity=str(run.pk)))

        api = signed_in(alice)
        assert answer == body(api.call("GET", f"/api/reviews/weeks/{MONDAY}/"))
        assert answer["comparison"]["statuses"]["missed"] == 1  # the first one lost its activity

    def test_an_activity_the_automatic_match_gave_to_another_workout_can_be_taken(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, second = week
        run = make_activity(alice, "2026-11-09T07:00")

        shown = workouts_of(body(decide(alice, second, activity=str(run.pk))))

        assert shown[str(first.pk)]["activity_id"] is None
        assert shown[str(first.pk)]["status"] == "missed"
        assert shown[str(second.pk)]["activity_id"] == str(run.pk)

    def test_a_decision_is_replaced_by_the_next_one(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, _ = week
        one = make_activity(alice, "2026-11-10T07:00")
        two = make_activity(alice, "2026-11-11T07:00")

        decide(alice, first, activity=str(one.pk))
        decide(alice, first, activity=str(two.pk), status="done")

        review = WorkoutReview.objects.get()
        assert (review.activity, review.status) == (two, "done")

    def test_the_activity_that_was_let_go_is_free_for_another_workout(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, second = week
        one = make_activity(alice, "2026-11-10T07:00")
        decide(alice, first, activity=str(one.pk))

        assert decide(alice, second, activity=str(one.pk)).status_code == HTTPStatus.CONFLICT
        decide(alice, first, no_activity=True)

        assert decide(alice, second, activity=str(one.pk)).status_code == HTTPStatus.OK


class TestSayingThereIsNone:
    def test_no_activity_belongs_to_the_workout(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, _ = week
        make_activity(alice, "2026-11-09T07:00")

        shown = workouts_of(body(decide(alice, first, no_activity=True)))[str(first.pk)]

        assert (shown["activity_id"], shown["activity_origin"], shown["status"]) == (
            None,
            "user",
            "missed",
        )
        assert WorkoutReview.objects.get().no_activity is True

    def test_missed_can_be_said_for_a_workout_with_an_activity(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, _ = week
        make_activity(alice, "2026-11-09T07:00")

        shown = workouts_of(body(decide(alice, first, status="missed")))[str(first.pk)]

        assert (shown["status"], shown["status_origin"], shown["activity_id"]) == (
            "missed",
            "user",
            None,
        )


class TestStatus:
    @pytest.mark.parametrize("status", ["done", "partial", "replaced"])
    def test_a_status_for_a_workout_with_an_activity(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout], status: str
    ) -> None:
        first, _ = week
        make_activity(alice, "2026-11-09T07:00")

        shown = workouts_of(body(decide(alice, first, status=status)))[str(first.pk)]

        assert (shown["status"], shown["status_origin"]) == (status, "user")
        assert WorkoutReview.objects.get().status == status

    @pytest.mark.parametrize("status", ["done", "partial", "replaced"])
    def test_that_describes_an_activity_is_refused_without_one_and_nothing_changes(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout], status: str
    ) -> None:
        first, _ = week
        WorkoutReview.objects.create(owner=alice, workout=first, status="missed")

        response = decide(alice, first, status=status)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"status": ["This status needs an activity. Link one first."]}
        assert WorkoutReview.objects.get().status == "missed"

    def test_it_is_refused_with_no_activity_too(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, _ = week
        make_activity(alice, "2026-11-09T07:00")

        response = decide(alice, first, no_activity=True, status="done")

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert WorkoutReview.objects.count() == 0

    def test_a_status_with_a_link_in_the_same_request(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, _ = week
        run = make_activity(alice, "2026-11-13T07:00")

        response = decide(alice, first, activity=str(run.pk), status="replaced")

        assert response.status_code == HTTPStatus.OK
        assert WorkoutReview.objects.get().status == "replaced"


class TestBackToAutomatic:
    def test_an_empty_form_removes_the_decision(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, _ = week
        run = make_activity(alice, "2026-11-09T07:00")
        decide(alice, first, no_activity=True)

        shown = workouts_of(body(decide(alice, first)))[str(first.pk)]

        assert WorkoutReview.objects.count() == 0
        assert (shown["activity_id"], shown["activity_origin"]) == (str(run.pk), "auto")

    def test_the_same_with_the_fields_written_out(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, _ = week
        decide(alice, first, status="missed")

        decide(alice, first, activity=None, no_activity=False, status="")

        assert WorkoutReview.objects.count() == 0

    def test_it_is_fine_when_there_was_no_decision(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        assert decide(alice, week[0]).status_code == HTTPStatus.OK


class TestRefusals:
    def test_an_activity_of_another_week_is_refused(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        old = make_activity(alice, (MONDAY - timedelta(days=3)).isoformat() + "T07:00")

        response = decide(alice, week[0], activity=str(old.pk))

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"activity": ["Choose an activity of this week."]}
        assert WorkoutReview.objects.count() == 0

    def test_another_users_activity_and_one_that_does_not_exist_look_the_same(
        self, alice: User, bob: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        theirs = make_activity(bob, "2026-11-09T07:00")

        for ident in (theirs.pk, uuid4()):
            response = decide(alice, week[0], activity=str(ident))

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert body(response) == {"activity": ["Choose an activity of this week."]}
        assert WorkoutReview.objects.count() == 0

    def test_an_activity_that_belongs_to_another_workout_by_hand_is_a_conflict(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        first, second = week
        run = make_activity(alice, "2026-11-09T07:00")
        decide(alice, first, activity=str(run.pk))

        response = decide(alice, second, activity=str(run.pk))

        assert response.status_code == HTTPStatus.CONFLICT
        assert body(response) == {
            "detail": "This activity is already assigned to another workout.",
            "code": "activity_taken",
        }
        assert WorkoutReview.objects.get().workout == first

    def test_a_workout_of_another_user_does_not_exist_and_is_left_alone(
        self, alice: User, bob: User
    ) -> None:
        theirs = make_plan(bob, workouts=1).workouts.get()

        response = decide(alice, theirs, no_activity=True)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "workout_not_found"
        assert WorkoutReview.objects.count() == 0

    def test_a_workout_that_is_not_in_the_confirmed_plan_of_the_week(self, alice: User) -> None:
        old = make_plan(alice, status="superseded", workouts=1).workouts.get()
        draft = make_plan(alice, status="draft", workouts=1).workouts.get()
        elsewhere = make_plan(alice, MONDAY - timedelta(weeks=1), workouts=1).workouts.get()

        for workout in (old, draft, elsewhere, uuid4()):
            assert decide(alice, workout, no_activity=True).status_code == HTTPStatus.NOT_FOUND
        assert WorkoutReview.objects.count() == 0

    @pytest.mark.parametrize(
        "week_text",
        ["2026-11-10", "2026-11-16", "2026-10-05", "2026-02-30", "nonsense", "20261109"],
    )
    def test_a_week_that_cannot_be_reviewed_is_a_404(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout], week_text: str
    ) -> None:
        response = decide(alice, week[0], week_text, no_activity=True)

        assert response.status_code == HTTPStatus.NOT_FOUND
        assert body(response)["code"] == "week_not_reviewable"
        assert WorkoutReview.objects.count() == 0

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("activity", "not-an-id"),
            ("activity", 5),
            ("activity", True),
            ("activity", ["x"]),
            ("no_activity", "true"),
            ("no_activity", 1),
            ("no_activity", None),
            ("status", "open"),
            ("status", "skipped"),
            ("status", "DONE"),
            ("status", 5),
            ("status", True),
            ("status", None),
        ],
    )
    def test_a_field_that_does_not_fit_is_refused_and_nothing_changes(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout], field: str, value: Any
    ) -> None:
        first, _ = week
        WorkoutReview.objects.create(owner=alice, workout=first, status="missed")

        response = decide(alice, first, **{field: value})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert field in body(response)
        assert WorkoutReview.objects.get().status == "missed"

    def test_an_activity_and_none_together_are_refused(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        run = make_activity(alice, "2026-11-09T07:00")

        response = decide(alice, week[0], activity=str(run.pk), no_activity=True)

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "no_activity" in body(response)
        assert WorkoutReview.objects.count() == 0

    @pytest.mark.parametrize("extra", ["workout_id", "owner", "id", "title", "statuss"])
    def test_a_field_that_is_not_part_of_the_form_is_refused(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout], extra: str
    ) -> None:
        first, _ = week
        WorkoutReview.objects.create(owner=alice, workout=first, status="missed")

        response = decide(alice, first, status="", **{extra: "x"})

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert body(response) == {"non_field_errors": ["Only the fields of this form can be sent."]}
        assert WorkoutReview.objects.get().status == "missed"  # a typo does not reset it

    def test_a_body_that_is_no_object_is_refused(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT",
            url(week[0]),
            data=json.dumps(["done"]),
            content_type="application/json",
            headers={"X-CSRFToken": api._csrf_token()},
        )

        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_nothing_of_the_input_is_repeated_in_an_error(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        for form in (
            {"activity": MARKER, "no_activity": MARKER, "status": MARKER},
            {MARKER: MARKER},
            {"status": MARKER},
        ):
            response = decide(alice, week[0], **form)

            assert response.status_code == HTTPStatus.BAD_REQUEST
            assert MARKER not in response.content.decode()


class TestAccess:
    def test_anonymous_visitors_are_refused(
        self, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        response = AuthApi().call("PUT", url(week[0]), {"no_activity": True})

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert WorkoutReview.objects.count() == 0

    def test_a_put_without_the_csrf_token_is_refused(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout]
    ) -> None:
        api = signed_in(alice)

        response = api.client.generic(
            "PUT",
            url(week[0]),
            data=json.dumps({"no_activity": True}),
            content_type="application/json",
        )

        assert response.status_code == HTTPStatus.FORBIDDEN
        assert WorkoutReview.objects.count() == 0

    @pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE"])
    def test_other_methods_are_not_allowed(
        self, alice: User, week: tuple[PlannedWorkout, PlannedWorkout], method: str
    ) -> None:
        response = signed_in(alice).call(method, url(week[0]), {})

        assert response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
