import pytest
from django.db import IntegrityError, transaction

from accounts.models import User
from chat.models import COACH_TEXT_MAX, USER_TEXT_MAX, ChatMessage
from reviews.tests.builders import make_plan
from season.models import SeasonPlanVersion

pytestmark = pytest.mark.django_db


def say(owner: User, role: str, text: str = "Hello", **fields: object) -> ChatMessage:
    return ChatMessage.objects.create(owner=owner, role=role, text=text, **fields)


def make_season(owner: User, version: int = 1) -> SeasonPlanVersion:
    return SeasonPlanVersion.objects.create(owner=owner, version=version)


class TestTheConversation:
    def test_is_read_in_the_order_it_was_written(self, alice: User) -> None:
        first = say(alice, "user", "Tuesday no time")
        second = say(alice, "coach", "Done")
        third = say(alice, "user", "Thanks")

        assert list(ChatMessage.objects.for_user(alice)) == [first, second, third]

    def test_is_only_the_own_conversation(self, alice: User, bob: User) -> None:
        mine = say(alice, "user")
        say(bob, "user")

        assert list(ChatMessage.objects.for_user(alice)) == [mine]

    def test_deleting_the_user_deletes_the_messages(self, alice: User) -> None:
        say(alice, "user")

        alice.delete()

        assert ChatMessage.objects.count() == 0


class TestWhatAMessageHolds:
    def test_a_message_of_the_coach_can_name_the_draft_and_the_changes(self, alice: User) -> None:
        plan = make_plan(alice, status="draft")

        message = say(alice, "coach", "Moved.", plan=plan, changes=["Run on Tue moved to Wed"])

        message.refresh_from_db()
        assert message.plan == plan
        assert message.changes == ["Run on Tue moved to Wed"]

    def test_the_message_stays_when_the_draft_is_deleted(self, alice: User) -> None:
        plan = make_plan(alice, status="draft")
        message = say(alice, "coach", "Moved.", plan=plan, changes=["x"])

        plan.delete()

        message.refresh_from_db()
        assert message.plan is None
        assert message.changes == ["x"]

    def test_a_message_of_the_coach_can_name_the_season_draft_and_the_changes(
        self, alice: User
    ) -> None:
        season = make_season(alice, 3)

        message = say(
            alice, "coach", "Moved.", season_plan=season, changes=["Absence handed to season"]
        )

        message.refresh_from_db()
        assert message.season_plan == season
        assert message.changes == ["Absence handed to season"]

    def test_the_message_stays_when_the_season_draft_is_deleted(self, alice: User) -> None:
        season = make_season(alice)
        message = say(alice, "coach", "Moved.", season_plan=season, changes=["x"])

        season.delete()

        message.refresh_from_db()
        assert message.season_plan is None
        assert message.changes == ["x"]

    def test_only_the_coach_changes_a_plan(self, alice: User) -> None:
        plan = make_plan(alice, status="draft")
        season = make_season(alice)

        with pytest.raises(IntegrityError), transaction.atomic():
            say(alice, "user", plan=plan)
        with pytest.raises(IntegrityError), transaction.atomic():
            say(alice, "user", season_plan=season)
        with pytest.raises(IntegrityError), transaction.atomic():
            say(alice, "user", changes=["x"])

    def test_the_role_is_one_of_the_two(self, alice: User) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            say(alice, "system")


class TestTheLength:
    def test_the_athlete_may_write_up_to_the_limit(self, alice: User) -> None:
        say(alice, "user", "x" * USER_TEXT_MAX)

        assert ChatMessage.objects.count() == 1

    def test_a_longer_message_of_the_athlete_is_refused(self, alice: User) -> None:
        with pytest.raises(IntegrityError), transaction.atomic():
            say(alice, "user", "x" * (USER_TEXT_MAX + 1))

    def test_the_coach_may_answer_longer(self, alice: User) -> None:
        say(alice, "coach", "x" * COACH_TEXT_MAX)

        assert ChatMessage.objects.count() == 1
