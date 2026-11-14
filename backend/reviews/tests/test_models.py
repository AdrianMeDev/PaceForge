from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from accounts.models import User
from activities.models import Activity
from planning.models import PlannedWorkout, WeeklyPlan
from reviews.matching import CHOOSABLE
from reviews.models import (
    COMMENT_MAX,
    NOTES_MAX,
    SCALE_MAX,
    SCALE_MIN,
    WeekComment,
    WeekFeedback,
    WorkoutReview,
)

pytestmark = pytest.mark.django_db

MONDAY = date(2027, 7, 12)
assert MONDAY.weekday() == 0
START = datetime(2027, 7, 13, 6, 30, tzinfo=UTC)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def make_workout(owner: User, position: int = 0) -> PlannedWorkout:
    """A workout of a confirmed plan: what a review is about."""
    plan = WeeklyPlan.objects.filter(owner=owner, week_start=MONDAY).first()
    if plan is None:
        plan = WeeklyPlan.objects.create(owner=owner, week_start=MONDAY)
    # Not ``create``: a plan that is confirmed takes no more workouts through ``save``.
    (workout,) = PlannedWorkout.objects.bulk_create(
        [
            PlannedWorkout(
                owner=owner,
                plan=plan,
                day=MONDAY + timedelta(days=1),
                position=position,
                sport="running",
                title="Easy run",
                goal="endurance",
                duration_minutes=45,
            )
        ]
    )
    WeeklyPlan.objects.filter(pk=plan.pk).update(status="confirmed", confirmed_at=START)
    return workout


def make_activity(owner: User, offset: int = 0) -> Activity:
    return Activity.objects.create(
        owner=owner,
        source="manual",
        sport="running",
        start_time=START + timedelta(hours=offset),
        timer_seconds=2700,
    )


def rejected_by_database(model: type[Any], **fields: Any) -> str:
    with pytest.raises(IntegrityError) as raised, transaction.atomic():
        model.objects.create(**fields)
    return str(raised.value)


def refused(instance: Any, field: str) -> None:
    with pytest.raises(ValidationError) as raised:
        instance.full_clean(exclude=["owner"])
    assert field in raised.value.message_dict, raised.value.message_dict


class TestWorkoutReview:
    def test_the_statuses_that_can_be_chosen_are_those_of_the_matching(self) -> None:
        assert {value for value, _ in WorkoutReview.Status.choices} == {
            status.value for status in CHOOSABLE
        }

    def test_a_review_with_an_activity_a_status_or_neither(self, alice: User) -> None:
        first, second, third = (make_workout(alice, position) for position in range(3))
        activity = make_activity(alice)

        linked = WorkoutReview.objects.create(owner=alice, workout=first, activity=activity)
        none = WorkoutReview.objects.create(owner=alice, workout=second, no_activity=True)
        set_by_hand = WorkoutReview.objects.create(owner=alice, workout=third, status="partial")

        assert linked.workout.review == linked
        assert linked.activity == activity
        assert activity.workout_reviews.get() == linked
        assert (none.activity, none.status) == (None, "")
        assert (set_by_hand.no_activity, set_by_hand.status) == (False, "partial")
        for review in (linked, none, set_by_hand):
            review.full_clean(exclude=["owner"])

    def test_a_workout_has_one_review(self, alice: User) -> None:
        workout = make_workout(alice)
        WorkoutReview.objects.create(owner=alice, workout=workout)

        message = rejected_by_database(WorkoutReview, owner=alice, workout=workout)

        assert "workout" in message

    def test_an_activity_belongs_to_one_workout(self, alice: User) -> None:
        first, second = make_workout(alice, 0), make_workout(alice, 1)
        activity = make_activity(alice)
        WorkoutReview.objects.create(owner=alice, workout=first, activity=activity)

        message = rejected_by_database(
            WorkoutReview, owner=alice, workout=second, activity=activity
        )

        assert "reviews_one_workout_per_activity" in message

    def test_a_workout_has_an_activity_or_none_not_both(self, alice: User) -> None:
        message = rejected_by_database(
            WorkoutReview,
            owner=alice,
            workout=make_workout(alice),
            activity=make_activity(alice),
            no_activity=True,
        )

        assert "reviews_activity_or_none_not_both" in message
        review = WorkoutReview(
            owner=alice, workout=make_workout(alice, 1), activity=make_activity(alice, 1)
        )
        review.no_activity = True
        refused(review, "no_activity")

    @pytest.mark.parametrize("status", ["done", "partial", "missed", "replaced", ""])
    def test_the_statuses_that_can_be_chosen(self, alice: User, status: str) -> None:
        review = WorkoutReview.objects.create(
            owner=alice, workout=make_workout(alice), status=status
        )

        review.full_clean(exclude=["owner"])

    @pytest.mark.parametrize("status", ["open", "skipped", "DONE"])
    def test_other_statuses_are_refused(self, alice: User, status: str) -> None:
        # ``open`` is only ever computed: it is not something to choose.
        message = rejected_by_database(
            WorkoutReview, owner=alice, workout=make_workout(alice), status=status
        )

        assert "reviews_status_is_known" in message
        refused(WorkoutReview(owner=alice, workout=make_workout(alice, 1), status=status), "status")

    def test_another_users_workout_or_activity_is_refused(self, alice: User, bob: User) -> None:
        refused(WorkoutReview(owner=alice, workout=make_workout(bob)), "workout")
        refused(
            WorkoutReview(owner=alice, workout=make_workout(alice), activity=make_activity(bob)),
            "activity",
        )

    def test_deleting_the_activity_keeps_the_rest_of_the_decision(self, alice: User) -> None:
        activity = make_activity(alice)
        review = WorkoutReview.objects.create(
            owner=alice, workout=make_workout(alice), activity=activity, status="done"
        )

        activity.delete()

        review.refresh_from_db()
        assert review.activity is None
        assert review.status == "done"

    def test_deleting_the_plan_deletes_the_reviews_of_its_workouts(self, alice: User) -> None:
        workout = make_workout(alice)
        WorkoutReview.objects.create(owner=alice, workout=workout, no_activity=True)

        WeeklyPlan.objects.get(pk=workout.plan_id).delete()

        assert WorkoutReview.objects.count() == 0

    def test_deleting_the_user_deletes_their_reviews(self, alice: User, bob: User) -> None:
        WorkoutReview.objects.create(owner=alice, workout=make_workout(alice), status="missed")
        WorkoutReview.objects.create(owner=bob, workout=make_workout(bob), status="missed")

        alice.delete()

        assert WorkoutReview.objects.get().owner == bob

    def test_the_manager_only_gives_a_user_their_own(self, alice: User, bob: User) -> None:
        mine = WorkoutReview.objects.create(owner=alice, workout=make_workout(alice))
        WorkoutReview.objects.create(owner=bob, workout=make_workout(bob))

        assert list(WorkoutReview.objects.for_user(alice)) == [mine]

    def test_the_text_form_holds_no_status_and_no_ids_of_content(self, alice: User) -> None:
        review = WorkoutReview(owner=alice, workout=make_workout(alice), status="missed")

        assert str(review) == f"Review of a workout of user {alice.pk}"


class TestWeekFeedback:
    def test_a_feedback_with_every_scale(self, alice: User) -> None:
        feedback = WeekFeedback.objects.create(
            owner=alice, week_start=MONDAY, fatigue=4, motivation=2, pain=1, notes="Heavy legs"
        )

        feedback.full_clean(exclude=["owner"])
        assert feedback.updated_at is not None

    def test_every_scale_may_be_left_out(self, alice: User) -> None:
        feedback = WeekFeedback.objects.create(owner=alice, week_start=MONDAY)

        feedback.full_clean(exclude=["owner"])
        assert (feedback.fatigue, feedback.motivation, feedback.pain, feedback.notes) == (
            None,
            None,
            None,
            "",
        )

    @pytest.mark.parametrize("field", ["fatigue", "motivation", "pain"])
    @pytest.mark.parametrize("value", [SCALE_MIN, 3, SCALE_MAX])
    def test_a_scale_runs_from_one_to_five(self, alice: User, field: str, value: int) -> None:
        feedback = WeekFeedback.objects.create(owner=alice, week_start=MONDAY, **{field: value})

        feedback.full_clean(exclude=["owner"])

    @pytest.mark.parametrize("field", ["fatigue", "motivation", "pain"])
    @pytest.mark.parametrize("value", [0, SCALE_MAX + 1, 100])
    def test_a_value_outside_the_scale_is_refused(
        self, alice: User, field: str, value: int
    ) -> None:
        assert (SCALE_MIN, SCALE_MAX) == (1, 5)

        message = rejected_by_database(
            WeekFeedback, owner=alice, week_start=MONDAY, **{field: value}
        )

        assert f"reviews_{field}_in_range" in message
        with pytest.raises(ValidationError, match=f"reviews_{field}_in_range"):
            WeekFeedback(owner=alice, week_start=MONDAY, **{field: value}).full_clean(
                exclude=["owner"]
            )

    def test_a_week_starts_on_a_monday(self, alice: User) -> None:
        tuesday = MONDAY + timedelta(days=1)

        message = rejected_by_database(WeekFeedback, owner=alice, week_start=tuesday)

        assert "reviews_feedback_week_is_a_monday" in message
        refused(WeekFeedback(owner=alice, week_start=tuesday), "week_start")

    def test_one_feedback_per_user_and_week(self, alice: User, bob: User) -> None:
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY)
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY)
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY + timedelta(days=7))

        message = rejected_by_database(WeekFeedback, owner=alice, week_start=MONDAY)

        assert "reviews_one_per_week" in message

    def test_the_note_has_a_limit(self, alice: User) -> None:
        assert NOTES_MAX == 500
        WeekFeedback(owner=alice, week_start=MONDAY, notes="n" * NOTES_MAX).full_clean(
            exclude=["owner"]
        )
        refused(WeekFeedback(owner=alice, week_start=MONDAY, notes="n" * (NOTES_MAX + 1)), "notes")

    def test_the_text_form_holds_no_notes(self, alice: User) -> None:
        feedback = WeekFeedback(owner=alice, week_start=MONDAY, notes="secret knee")

        assert "secret" not in str(feedback)
        assert str(feedback) == f"Feedback of user {alice.pk} for the week of {MONDAY}"

    def test_deleting_the_user_deletes_their_feedback(self, alice: User, bob: User) -> None:
        WeekFeedback.objects.create(owner=alice, week_start=MONDAY)
        WeekFeedback.objects.create(owner=bob, week_start=MONDAY)

        alice.delete()

        assert WeekFeedback.objects.get().owner == bob


class TestWeekComment:
    FIELDS: dict[str, Any] = {"comment": "A steady week.", "next_week": "hold"}

    def test_a_comment_of_the_coach(self, alice: User) -> None:
        comment = WeekComment.objects.create(owner=alice, week_start=MONDAY, **self.FIELDS)

        comment.full_clean(exclude=["owner"])
        assert comment.created_at is not None
        assert (comment.comment, comment.next_week) == ("A steady week.", "hold")

    def test_the_limit_is_written_out_on_purpose(self) -> None:
        assert COMMENT_MAX == 600

    def test_a_comment_up_to_the_limit_and_with_several_lines(self, alice: User) -> None:
        for text in ("c" * COMMENT_MAX, "one\ntwo"):
            WeekComment(owner=alice, week_start=MONDAY, comment=text, next_week="hold").full_clean(
                exclude=["owner"]
            )

        refused(
            WeekComment(
                owner=alice, week_start=MONDAY, comment="c" * (COMMENT_MAX + 1), next_week="hold"
            ),
            "comment",
        )

    @pytest.mark.parametrize("word", ["increase", "hold", "reduce"])
    def test_the_three_recommendations(self, alice: User, word: str) -> None:
        comment = WeekComment.objects.create(
            owner=alice, week_start=MONDAY, comment="x", next_week=word
        )

        comment.full_clean(exclude=["owner"])

    @pytest.mark.parametrize("word", ["", "maintain", "INCREASE", "up"])
    def test_any_other_recommendation_is_refused(self, alice: User, word: str) -> None:
        message = rejected_by_database(
            WeekComment, owner=alice, week_start=MONDAY, comment="x", next_week=word
        )

        assert "reviews_next_week_is_known" in message
        refused(
            WeekComment(owner=alice, week_start=MONDAY, comment="x", next_week=word), "next_week"
        )

    def test_a_comment_has_text(self, alice: User) -> None:
        message = rejected_by_database(
            WeekComment, owner=alice, week_start=MONDAY, comment="", next_week="hold"
        )

        assert "reviews_comment_not_empty" in message
        refused(
            WeekComment(owner=alice, week_start=MONDAY, comment="", next_week="hold"), "comment"
        )

    def test_a_week_starts_on_a_monday(self, alice: User) -> None:
        tuesday = MONDAY + timedelta(days=1)

        message = rejected_by_database(WeekComment, owner=alice, week_start=tuesday, **self.FIELDS)

        assert "reviews_comment_week_is_a_monday" in message
        refused(WeekComment(owner=alice, week_start=tuesday, **self.FIELDS), "week_start")

    def test_one_comment_per_user_and_week(self, alice: User, bob: User) -> None:
        WeekComment.objects.create(owner=alice, week_start=MONDAY, **self.FIELDS)
        WeekComment.objects.create(owner=bob, week_start=MONDAY, **self.FIELDS)
        WeekComment.objects.create(
            owner=alice, week_start=MONDAY + timedelta(days=7), **self.FIELDS
        )

        message = rejected_by_database(WeekComment, owner=alice, week_start=MONDAY, **self.FIELDS)

        assert "reviews_one_comment_per_week" in message

    def test_the_text_form_holds_no_comment(self, alice: User) -> None:
        comment = WeekComment(
            owner=alice, week_start=MONDAY, comment="secret knee", next_week="reduce"
        )

        assert "secret" not in str(comment)
        assert str(comment) == f"Comment for user {alice.pk} on the week of {MONDAY}"

    def test_deleting_the_user_deletes_their_comments(self, alice: User, bob: User) -> None:
        WeekComment.objects.create(owner=alice, week_start=MONDAY, **self.FIELDS)
        WeekComment.objects.create(owner=bob, week_start=MONDAY, **self.FIELDS)

        alice.delete()

        assert WeekComment.objects.get().owner == bob
