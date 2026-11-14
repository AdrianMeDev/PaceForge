"""The "Week review" section of the README is compared with the code, so that it cannot drift."""

import re
from pathlib import Path
from uuid import UUID

import pytest
from django.urls import reverse

from reviews import matching, services
from reviews.matching import PARTIAL_BELOW_PERCENT, Status
from reviews.models import NOTES_MAX, SCALE_MAX, SCALE_MIN

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


class TestWhatIsNotClaimed:
    def test_the_old_promise_is_gone(self) -> None:
        flat = " ".join(README.split())
        assert "rating them comes with the week review" not in flat

    def test_the_coach_is_not_told_anything_yet(self) -> None:
        assert "Nothing of this is sent to your AI provider yet" in TEXT
