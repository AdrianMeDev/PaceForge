"""The "Dashboard" section of the README is compared with the code, so that it cannot drift."""

import re
from pathlib import Path

from django.urls import reverse

from coach.services import USAGE_DAYS
from dashboard import overview

ROOT = Path(__file__).resolve().parents[3]
README = (ROOT / "README.md").read_text()
_FOUND = re.search(r"^## Dashboard\n(.*?)(?=^## |\Z)", README, re.S | re.M)
assert _FOUND, "no section 'Dashboard' in the README"
SECTION = _FOUND.group(1)
# The section with every run of white space as one space, for sentences that the file wraps.
TEXT = " ".join(SECTION.split())


class TestTheNumbers:
    def test_the_weeks_of_the_chart(self) -> None:
        # Written out on purpose: a change of the constant must change the text.
        assert overview.CHART_WEEKS == 8
        assert "the minutes you trained in each of the last 8 weeks" in TEXT
        assert "`CHART_WEEKS` in `backend/dashboard/overview.py`" in TEXT
        assert overview.__file__.endswith("backend/dashboard/overview.py")

    def test_the_latest_activities(self) -> None:
        assert overview.RECENT_ACTIVITIES == 3
        assert "the latest 3 activities" in TEXT
        assert "`RECENT_ACTIVITIES` in the same file" in TEXT

    def test_the_days_of_the_coach_usage(self) -> None:
        assert USAGE_DAYS == 30
        assert "in the last 30 days" in TEXT


class TestTheRules:
    def test_the_week_to_close(self) -> None:
        assert "the current week on a Sunday" in TEXT
        assert "otherwise last week" in TEXT

    def test_the_request(self) -> None:
        assert reverse("dashboard") == "/api/dashboard/"
        assert "`GET /api/dashboard/`" in TEXT

    def test_every_block_is_described(self) -> None:
        for block in (
            "Next workout",
            "This week",
            "Close the week",
            "Season",
            "Main goal",
            "Last 8 weeks",
            "Coach",
            "Wellness",
        ):
            assert f"- **{block}:**" in SECTION
