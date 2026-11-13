import itertools
import math
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from athletes.models import ThresholdValue
from athletes.thresholds import Value, candidates, clear_manual, effective, set_manual

pytestmark = pytest.mark.django_db

Sport = ThresholdValue.Sport
Metric = ThresholdValue.Metric
Source = ThresholdValue.Source

# One distinct value per source, so that the test can tell which one counted.
VALUE_OF: dict[str, float] = {
    Source.MANUAL: 250.0,
    Source.INTERVALS: 262.0,
    Source.ESTIMATED: 241.0,
}


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


@pytest.fixture
def bob() -> User:
    return User.objects.create_user("bob@example.com")


def hold(
    owner: User,
    source: str,
    *,
    sport: str = Sport.RIDE,
    metric: str = Metric.FTP,
    value: float | None = None,
) -> ThresholdValue:
    return ThresholdValue.objects.create(
        owner=owner,
        sport=sport,
        metric=metric,
        source=source,
        value=VALUE_OF[source] if value is None else value,
        basis=f"basis of {source}",
    )


def ftp(user: User) -> Value | None:
    return effective(user, Sport.RIDE, Metric.FTP)


SUBSETS = [
    combination
    for size in range(1, 4)
    for combination in itertools.combinations(
        [Source.MANUAL, Source.INTERVALS, Source.ESTIMATED], size
    )
]


class TestWhichValueCounts:
    def test_without_any_value_nothing_counts(self, alice: User) -> None:
        assert ftp(alice) is None
        assert candidates(alice, Sport.RIDE, Metric.FTP) == []

    @pytest.mark.parametrize("present", SUBSETS)
    def test_the_order_is_manual_then_intervals_then_estimated(
        self, alice: User, present: tuple[str, ...]
    ) -> None:
        for source in present:
            hold(alice, source)
        expected = next(
            source
            for source in (Source.MANUAL, Source.INTERVALS, Source.ESTIMATED)
            if source in present
        )

        found = ftp(alice)

        assert found is not None
        assert found.source == expected
        assert found.value == VALUE_OF[expected]
        assert found.basis == f"basis of {expected}"

    def test_the_candidates_come_in_that_order_and_all_of_them(self, alice: User) -> None:
        for source in (Source.ESTIMATED, Source.MANUAL, Source.INTERVALS):  # stored in no order
            hold(alice, source)

        found = candidates(alice, Sport.RIDE, Metric.FTP)

        assert [(c.source, c.value) for c in found] == [
            ("manual", 250.0),
            ("intervals", 262.0),
            ("estimated", 241.0),
        ]
        assert found[0] == effective(alice, Sport.RIDE, Metric.FTP)

    def test_other_thresholds_do_not_count(self, alice: User) -> None:
        hold(alice, Source.MANUAL, sport=Sport.RIDE, metric=Metric.LTHR, value=165)
        hold(alice, Source.MANUAL, sport=Sport.RUN, metric=Metric.LTHR, value=170)

        assert ftp(alice) is None
        assert effective(alice, Sport.RIDE, Metric.LTHR).value == 165  # type: ignore[union-attr]
        assert effective(alice, Sport.RUN, Metric.LTHR).value == 170  # type: ignore[union-attr]

    def test_the_values_of_another_user_are_never_considered(self, alice: User, bob: User) -> None:
        hold(bob, Source.MANUAL)
        hold(bob, Source.INTERVALS)

        assert ftp(alice) is None
        assert candidates(alice, Sport.RIDE, Metric.FTP) == []
        hold(alice, Source.ESTIMATED)
        assert ftp(alice).source == Source.ESTIMATED  # type: ignore[union-attr]


class TestSettingYourOwnValue:
    def test_it_is_stored_as_manual(self, alice: User) -> None:
        stored = set_manual(alice, Sport.RIDE, Metric.FTP, 250)

        assert (stored.owner, stored.sport, stored.metric) == (alice, "ride", "ftp")
        assert (stored.source, stored.value, stored.basis) == ("manual", 250.0, "")
        assert ThresholdValue.objects.count() == 1
        assert ftp(alice).source == Source.MANUAL  # type: ignore[union-attr]

    def test_a_second_value_replaces_the_first(self, alice: User) -> None:
        first = set_manual(alice, Sport.RIDE, Metric.FTP, 250)

        second = set_manual(alice, Sport.RIDE, Metric.FTP, 260)

        assert second.pk == first.pk
        assert ThresholdValue.objects.count() == 1
        assert ftp(alice).value == 260  # type: ignore[union-attr]

    def test_it_wins_over_the_other_sources_and_leaves_them_alone(self, alice: User) -> None:
        intervals = hold(alice, Source.INTERVALS)
        estimated = hold(alice, Source.ESTIMATED)
        before = [(row.pk, row.value, row.basis, row.updated_at) for row in (intervals, estimated)]

        set_manual(alice, Sport.RIDE, Metric.FTP, 255)

        after = [
            (row.pk, row.value, row.basis, row.updated_at)
            for row in ThresholdValue.objects.filter(pk__in=[intervals.pk, estimated.pk]).order_by(
                "pk"
            )
        ]
        assert after == before
        assert [c.source for c in candidates(alice, Sport.RIDE, Metric.FTP)] == [
            "manual",
            "intervals",
            "estimated",
        ]

    def test_it_changes_nothing_for_other_thresholds_or_users(self, alice: User, bob: User) -> None:
        theirs = hold(bob, Source.MANUAL)
        other = hold(alice, Source.MANUAL, sport=Sport.RIDE, metric=Metric.LTHR, value=165)

        set_manual(alice, Sport.RIDE, Metric.FTP, 255)

        theirs.refresh_from_db()
        other.refresh_from_db()
        assert theirs.value == 250
        assert other.value == 165

    @pytest.mark.parametrize(
        ("given", "stored"), [(250, 250), (250.4, 250), (250.5, 251), (250.6, 251), ("250", 250)]
    )
    def test_the_value_is_rounded_to_a_whole_number_half_up(
        self, alice: User, given: Any, stored: float
    ) -> None:
        assert set_manual(alice, Sport.RIDE, Metric.FTP, given).value == stored

    def test_the_pace_is_stored_in_seconds_per_kilometre(self, alice: User) -> None:
        assert set_manual(alice, Sport.RUN, Metric.THRESHOLD_PACE, 299.6).value == 300

    @pytest.mark.parametrize(
        ("sport", "metric", "value", "field"),
        [
            (Sport.RUN, Metric.FTP, 250, "metric"),
            (Sport.RIDE, Metric.THRESHOLD_PACE, 300, "metric"),
            (Sport.RIDE, Metric.FTP, 29.9, "value"),
            (Sport.RIDE, Metric.FTP, 2000.1, "value"),
            (Sport.RIDE, Metric.FTP, 0, "value"),
            (Sport.RIDE, Metric.FTP, -250, "value"),
            (Sport.RIDE, Metric.LTHR, 251, "value"),
            (Sport.RUN, Metric.THRESHOLD_PACE, 119, "value"),
            (Sport.RIDE, Metric.FTP, math.nan, "value"),
            (Sport.RIDE, Metric.FTP, math.inf, "value"),
            (Sport.RIDE, Metric.FTP, "abc", "value"),
            (Sport.RIDE, Metric.FTP, None, "value"),
            ("swim", Metric.FTP, 250, "sport"),
            (Sport.RIDE, "vo2max", 250, "metric"),
        ],
    )
    def test_a_refused_value_stores_nothing(
        self, alice: User, sport: str, metric: str, value: Any, field: str
    ) -> None:
        with pytest.raises(ValidationError) as raised:
            set_manual(alice, sport, metric, value)

        assert field in raised.value.message_dict
        assert not ThresholdValue.objects.exists()

    def test_a_refused_value_keeps_the_earlier_one(self, alice: User) -> None:
        set_manual(alice, Sport.RIDE, Metric.FTP, 250)

        with pytest.raises(ValidationError):
            set_manual(alice, Sport.RIDE, Metric.FTP, 5000)

        assert ftp(alice).value == 250  # type: ignore[union-attr]


class TestGoingBackToAutomatic:
    def test_clearing_falls_back_to_the_next_source(self, alice: User) -> None:
        hold(alice, Source.MANUAL)
        hold(alice, Source.INTERVALS)
        hold(alice, Source.ESTIMATED)

        assert clear_manual(alice, Sport.RIDE, Metric.FTP) is True
        assert ftp(alice).source == Source.INTERVALS  # type: ignore[union-attr]
        ThresholdValue.objects.filter(source=Source.INTERVALS).delete()
        assert ftp(alice).source == Source.ESTIMATED  # type: ignore[union-attr]
        ThresholdValue.objects.filter(source=Source.ESTIMATED).delete()
        assert ftp(alice) is None

    def test_clearing_what_is_not_there_says_so(self, alice: User) -> None:
        hold(alice, Source.INTERVALS)

        assert clear_manual(alice, Sport.RIDE, Metric.FTP) is False
        assert ThresholdValue.objects.count() == 1

    def test_clearing_touches_only_the_own_manual_value_of_that_threshold(
        self, alice: User, bob: User
    ) -> None:
        hold(alice, Source.MANUAL)
        hold(alice, Source.INTERVALS)
        hold(alice, Source.MANUAL, sport=Sport.RIDE, metric=Metric.LTHR, value=165)
        theirs = hold(bob, Source.MANUAL)

        clear_manual(alice, Sport.RIDE, Metric.FTP)

        assert ThresholdValue.objects.filter(owner=alice).count() == 2
        assert ThresholdValue.objects.filter(pk=theirs.pk).exists()


class TestHeartRates:
    def setting(self, user: User, metric: str, value: float, sport: str = Sport.RIDE) -> Any:
        return set_manual(user, sport, metric, value)

    @pytest.mark.parametrize("first", [Metric.LTHR, Metric.MAX_HR])
    def test_the_threshold_may_not_be_above_the_maximum_in_either_order(
        self, alice: User, first: str
    ) -> None:
        if first == Metric.MAX_HR:
            self.setting(alice, Metric.MAX_HR, 180)
            with pytest.raises(ValidationError) as raised:
                self.setting(alice, Metric.LTHR, 181)
            assert raised.value.message_dict["value"] == [
                "Cannot be above the maximum heart rate (180 bpm)."
            ]
        else:
            self.setting(alice, Metric.LTHR, 170)
            with pytest.raises(ValidationError) as raised:
                self.setting(alice, Metric.MAX_HR, 169)
            assert raised.value.message_dict["value"] == [
                "Cannot be below the lactate threshold heart rate (170 bpm)."
            ]
        assert ThresholdValue.objects.count() == 1  # the refused one was not stored

    @pytest.mark.parametrize("first", [Metric.LTHR, Metric.MAX_HR])
    def test_equal_values_are_fine_in_either_order(self, alice: User, first: str) -> None:
        second = Metric.MAX_HR if first == Metric.LTHR else Metric.LTHR
        self.setting(alice, first, 180)

        self.setting(alice, second, 180)

        assert ThresholdValue.objects.count() == 2

    def test_the_check_uses_the_rounded_value(self, alice: User) -> None:
        self.setting(alice, Metric.MAX_HR, 180)

        self.setting(alice, Metric.LTHR, 180.4)  # rounds to 180

    def test_the_sports_do_not_affect_each_other(self, alice: User) -> None:
        self.setting(alice, Metric.MAX_HR, 150, sport=Sport.RIDE)

        self.setting(alice, Metric.LTHR, 170, sport=Sport.RUN)

        assert ThresholdValue.objects.count() == 2

    def test_a_value_from_intervals_counts_for_the_check(self, alice: User) -> None:
        hold(alice, Source.INTERVALS, metric=Metric.MAX_HR, value=175)

        with pytest.raises(ValidationError):
            self.setting(alice, Metric.LTHR, 180)

    def test_an_estimate_never_blocks_an_entry(self, alice: User) -> None:
        hold(alice, Source.ESTIMATED, metric=Metric.MAX_HR, value=165)

        self.setting(alice, Metric.LTHR, 170)

        assert effective(alice, Sport.RIDE, Metric.LTHR).value == 170  # type: ignore[union-attr]

    def test_the_manual_value_of_the_other_one_counts_over_intervals(self, alice: User) -> None:
        hold(alice, Source.INTERVALS, metric=Metric.MAX_HR, value=175)
        self.setting(alice, Metric.MAX_HR, 190)

        self.setting(alice, Metric.LTHR, 185)  # against 190, not against 175

    def test_replacing_a_value_is_checked_too(self, alice: User) -> None:
        self.setting(alice, Metric.MAX_HR, 180)
        self.setting(alice, Metric.LTHR, 170)

        with pytest.raises(ValidationError):
            self.setting(alice, Metric.LTHR, 185)

        assert effective(alice, Sport.RIDE, Metric.LTHR).value == 170  # type: ignore[union-attr]

    def test_the_values_of_another_user_do_not_count(self, alice: User, bob: User) -> None:
        self.setting(bob, Metric.MAX_HR, 150)

        self.setting(alice, Metric.LTHR, 170)

    def test_other_metrics_are_not_compared(self, alice: User) -> None:
        self.setting(alice, Metric.MAX_HR, 150)

        set_manual(alice, Sport.RIDE, Metric.FTP, 300)
