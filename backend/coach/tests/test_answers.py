import pytest

from coach.answers import AnswerFormatError, read_json_object

LIMIT = 1000
MARKER = "SECRETMARKER"


def refused(text: str, limit: int = LIMIT) -> str:
    with pytest.raises(AnswerFormatError) as raised:
        read_json_object(text, limit)
    return str(raised.value)


class TestWhatIsAccepted:
    def test_one_object(self) -> None:
        assert read_json_object('{"a": 1, "b": [true, null, "x"]}', LIMIT) == {
            "a": 1,
            "b": [True, None, "x"],
        }

    def test_white_space_around_it(self) -> None:
        assert read_json_object('  \n{"a": 1}\n\n ', LIMIT) == {"a": 1}

    @pytest.mark.parametrize("fence", ["```json", "```"])
    def test_one_code_fence_around_it(self, fence: str) -> None:
        assert read_json_object(f'{fence}\n{{"a": 1}}\n```', LIMIT) == {"a": 1}

    def test_the_same_key_in_different_objects(self) -> None:
        assert read_json_object('{"a": {"x": 1}, "b": {"x": 2}}', LIMIT) == {
            "a": {"x": 1},
            "b": {"x": 2},
        }

    def test_text_that_looks_like_markup_is_just_text(self) -> None:
        assert read_json_object('{"a": "<b>hi</b>"}', LIMIT) == {"a": "<b>hi</b>"}

    def test_exactly_the_limit(self) -> None:
        text = '{"a": "' + "x" * (LIMIT - len('{"a": ""}')) + '"}'
        assert len(text) == LIMIT

        assert read_json_object(text, LIMIT)


class TestWhatIsRefused:
    def test_an_answer_that_is_too_long(self) -> None:
        text = '{"a": "' + "x" * LIMIT + '"}'

        assert refused(text) == "The answer is too long."

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "ok",
            f"Here you go: {{{'"a"'}: 1}}",
            '{"a": 1} Hope that helps!',
            '[{"a": 1}]',
            '"a"',
            "42",
            "null",
            '```json\n{"a": 1}\n``` and more',
            'text\n```json\n{"a": 1}\n```',
        ],
    )
    def test_anything_but_one_object(self, text: str) -> None:
        assert refused(text) == (
            "The answer is not one JSON object. Send the object and nothing else."
        )

    def test_a_repeated_key(self) -> None:
        assert refused('{"a": 1, "a": 2}') == "A key is given twice in the same object."
        assert refused('{"a": {"x": 1, "x": 2}}') == "A key is given twice in the same object."

    @pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
    def test_numbers_json_does_not_have(self, constant: str) -> None:
        assert refused(f'{{"a": {constant}}}') == "NaN and Infinity are not allowed."

    def test_two_objects_are_broken_json(self) -> None:
        assert refused('{"a": 1}{"b": 2}').startswith("The answer is not valid JSON (Extra data")

    def test_json_that_is_broken_says_where_in_numbers_only(self) -> None:
        message = refused('{"a": 1,}')

        assert message.startswith("The answer is not valid JSON (")
        assert message.endswith(").")

    def test_a_number_that_is_too_big(self) -> None:
        assert refused('{"a": ' + "9" * 5000 + "}", limit=10_000) == (
            "The answer holds a number or a nesting that cannot be read."
        )

    def test_nesting_that_is_too_deep(self) -> None:
        text = '{"a": ' + "[" * 100_000 + "]" * 100_000 + "}"

        assert refused(text, limit=1_000_000) == (
            "The answer holds a number or a nesting that cannot be read."
        )

    @pytest.mark.parametrize(
        "text",
        [
            f'{{"a": "{MARKER}"',
            f'{{"{MARKER}": 1, "{MARKER}": 2}}',
            f"{MARKER} {{}}",
            f'{{"a": {MARKER}}}',
            f'{{"a": "{MARKER}" ' + "x" * LIMIT + "}",
        ],
    )
    def test_nothing_of_the_answer_is_repeated(self, text: str) -> None:
        assert MARKER not in refused(text)
