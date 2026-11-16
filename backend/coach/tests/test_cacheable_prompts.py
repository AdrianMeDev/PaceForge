"""The system prompts have to be the same bytes for every athlete and every day, or the cache
silently stops working: it matches a prefix exactly, and one changed byte loses everything after
it. These tests keep a date, a name or a number of the moment out of them."""

import re

import pytest

from planning.prompt import SYSTEM_PROMPT as WEEK
from reviews.prompt import SYSTEM_PROMPT as REVIEW
from season.prompt import SYSTEM_PROMPT as SEASON

PROMPTS = {"week plan": WEEK, "week review": REVIEW, "season plan": SEASON}


@pytest.mark.parametrize("name", PROMPTS)
class TestEveryPrompt:
    def test_it_is_one_fixed_text(self, name: str) -> None:
        assert isinstance(PROMPTS[name], str)
        assert PROMPTS[name].strip() != ""

    def test_it_holds_no_date_or_year(self, name: str) -> None:
        text = PROMPTS[name]

        assert not re.search(r"\d{4}-\d{2}-\d{2}", text)
        assert not re.search(r"\b20\d\d\b", text)

    def test_it_holds_no_address_or_id(self, name: str) -> None:
        text = PROMPTS[name]

        assert "@" not in text
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", text)

    def test_it_has_no_placeholder_left_unfilled(self, name: str) -> None:
        # a format string that was not filled shows its braces; the JSON examples have doubled ones
        assert not re.search(r"\{[a-z_]+\}", PROMPTS[name])
