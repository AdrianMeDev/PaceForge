"""The "Week review" section of the README is compared with the code, so that it cannot drift."""

import re
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from django.conf import settings
from django.urls import reverse

from accounts.models import User
from coach.models import AIUsageRecord
from planning.briefing import build_briefing
from reviews import matching, models, services
from reviews.briefing import MAX_UNPLANNED
from reviews.commenting import ATTEMPTS
from reviews.matching import PARTIAL_BELOW_PERCENT, Status
from reviews.models import COMMENT_MAX, NOTES_MAX, SCALE_MAX, SCALE_MIN
from reviews.prompt import NEXT_WEEK_WORDS

ROOT = Path(__file__).resolve().parents[3]
README = (ROOT / "README.md").read_text()
_FOUND = re.search(r"^## Week review\n(.*?)(?=^## |\Z)", README, re.S | re.M)
assert _FOUND, "no section 'Week review' in the README"
SECTION = _FOUND.group(1)
# The section with every run of white space as one space, for sentences that the file wraps.
TEXT = " ".join(SECTION.split())


class TestTheNumbers:
    def test_the_limit_between_done_and_partial(self) -> None:
        assert f"at least {PARTIAL_BELOW_PERCENT} % of the planned minutes" in TEXT
        assert "`PARTIAL_BELOW_PERCENT` in `backend/reviews/matching.py`" in TEXT
        assert matching.__file__.endswith("backend/reviews/matching.py")

    def test_the_weeks_that_can_be_reviewed(self) -> None:
        # Written out on purpose: a change of the constant must change the text.
        assert services.REVIEW_WEEKS == 4
        assert "the current week and the four before it can be reviewed" in TEXT
        assert "`REVIEW_WEEKS` in `backend/reviews/services.py`" in TEXT
        assert services.__file__.endswith("backend/reviews/services.py")

    def test_the_scales_and_the_notes(self) -> None:
        assert (SCALE_MIN, SCALE_MAX, NOTES_MAX) == (1, 5, 500)
        assert "each from 1 to 5" in TEXT
        assert TEXT.count("up to 500 characters") == 2  # the note of a session and of the week


class TestTheStatuses:
    @pytest.mark.parametrize("status", list(Status))
    def test_every_status_is_in_the_table(self, status: Status) -> None:
        assert f"| **{status.value.capitalize()}**" in SECTION

    def test_what_needs_an_activity(self) -> None:
        assert services.NEEDS_AN_ACTIVITY == {"done", "partial", "replaced"}
        assert "Setting **Done**, **Partial** or **Replaced** needs an activity" in TEXT

    def test_open_cannot_be_chosen(self) -> None:
        assert Status.OPEN not in matching.CHOOSABLE
        assert "it cannot be chosen by hand" in TEXT


class TestTheApi:
    MONDAY = "MONDAY"
    ID = UUID(int=1)

    def written(self, address: str) -> str:
        """An address of the code as the README writes it, with placeholders."""
        return address.replace(self.MONDAY, "<Monday>").replace(str(self.ID), "<id>")

    def test_every_request_is_written_as_the_code_has_it(self) -> None:
        week = {"week": self.MONDAY}
        requests = {
            ("GET", "/api/reviews/weeks/"): reverse("reviews-weeks"),
            ("GET", "/api/reviews/weeks/<Monday>/"): reverse("reviews-week", kwargs=week),
            ("PUT", "/api/reviews/weeks/<Monday>/workouts/<id>/"): reverse(
                "reviews-correction", kwargs={**week, "workout_id": self.ID}
            ),
            ("PUT", "/api/reviews/weeks/<Monday>/feedback/"): reverse(
                "reviews-feedback", kwargs=week
            ),
            ("POST", "/api/reviews/weeks/<Monday>/comment/"): reverse(
                "reviews-comment", kwargs=week
            ),
            ("PATCH", "/api/activities/<id>/"): reverse(
                "activity-detail", kwargs={"pk": str(self.ID)}
            ),
        }
        for (method, written), from_code in requests.items():
            assert self.written(from_code) == written
            assert f"`{method} {written}`" in TEXT

    def test_the_fields_of_the_forms(self) -> None:
        assert "`activity`, `no_activity`, `status`" in TEXT
        assert "`fatigue`, `motivation`, `pain`, `notes`" in TEXT
        assert "`rpe` and `notes`" in TEXT


class TestTheCoachsComment:
    def test_the_limit_of_the_comment(self) -> None:
        assert COMMENT_MAX == 600
        assert "of up to 600 characters (`COMMENT_MAX` in `backend/reviews/models.py`)" in TEXT
        assert Path(models.__file__).as_posix().endswith("backend/reviews/models.py")

    def test_the_limit_of_the_sessions_that_were_not_planned(self) -> None:
        assert MAX_UNPLANNED == 20
        assert "(at most `MAX_UNPLANNED`, the rest is only counted)" in TEXT
        assert "`backend/reviews/briefing.py`" in TEXT

    def test_the_recommendations_are_worded_as_the_page_words_them(self) -> None:
        page = (ROOT / "frontend/src/app/features/review/review-format.ts").read_text()
        words = {
            "increase": "increase the volume a little",
            "hold": "keep the volume about the same",
            "reduce": "reduce the volume",
        }

        assert set(words) == set(NEXT_WEEK_WORDS)
        for sentence in words.values():
            assert f"'{sentence}'" in page, sentence
            assert f"*{sentence}*" in TEXT, sentence

    def test_the_limit_of_asking_is_the_one_of_the_settings(self) -> None:
        framework: Any = settings.REST_FRAMEWORK

        assert framework["DEFAULT_THROTTLE_RATES"]["review_comment"] == "5/min"
        assert "limited to 5 a minute per user" in TEXT

    def test_a_comment_costs_one_request_or_two(self) -> None:
        assert ATTEMPTS == 2
        assert "a comment costs one request, or two if the coach had to correct its answer" in TEXT

    def test_the_usage_is_counted_under_its_own_purpose(self) -> None:
        assert AIUsageRecord.Purpose.WEEK_REVIEW.value == "week_review"
        assert AIUsageRecord.Purpose.WEEK_REVIEW.label == "Week review"
        assert 'the purpose "week review" is stored with each record' in TEXT

    def test_nothing_is_sent_when_there_is_nothing_to_look_back_on(self) -> None:
        assert "has nothing to look back on: nothing is sent then" in TEXT

    def test_the_coachs_own_text_is_never_sent_back(self) -> None:
        assert "**never sent back** to the coach" in TEXT
        assert "there is no free text in it at all" in TEXT

    @pytest.mark.django_db
    def test_the_key_of_the_week_plan_is_named_in_both_places(self) -> None:
        user = User.objects.create_user("docs@example.com")

        assert "previous_week_review" in build_briefing(user, date(2027, 7, 12))
        assert "`previous_week_review`" in TEXT
        assert "previous_week_review" in (ROOT / "docs" / "weekly-plan.md").read_text()

    def test_the_week_plan_section_says_what_it_is_told_about_the_week_before(self) -> None:
        assert "how that week went (see [Week review](#week-review))" in " ".join(README.split())


class TestTheCorrectionsOfANewVersion:
    def test_they_move_with_their_workouts(self) -> None:
        assert (
            "when a changed version of the week is confirmed, your corrections move to the "
            "workouts that are the same training"
        ) in TEXT

    def test_the_old_sentence_is_gone(self) -> None:
        assert "starts without your corrections" not in " ".join(README.split())


class TestWhatIsNotClaimed:
    def test_the_old_promise_is_gone(self) -> None:
        flat = " ".join(README.split())
        assert "rating them comes with the week review" not in flat

    def test_nothing_says_any_more_that_the_coach_is_told_nothing(self) -> None:
        flat = " ".join(README.split())
        assert "Nothing of this is sent to your AI provider yet" not in flat
        assert "The plan is that the coach will be told" not in flat
