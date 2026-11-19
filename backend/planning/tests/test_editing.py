import copy
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from availability.models import WeekdayMinutes
from goals import services as goal_services
from planning import services
from planning.editing import (
    REASON,
    PlanNotRestorable,
    PlanNotRevisable,
    check,
    read_edited_plan,
    restore,
    revise,
)
from planning.generation import WeekNotPlannable
from planning.models import PlannedWorkout, WeeklyPlan
from planning.schema import (
    PlanFormatError,
    Segment,
    SegmentKind,
    Slot,
    WeekPlan,
    ZoneSystem,
    to_json,
)
from planning.services import PlanNotConfirmable, PlanNotFound
from reviews.models import WorkoutReview

from .test_services import good_week, prepared, workout

# A fixed id for the tests that are parametrized: the id is part of the name of a test, and
# every worker of a parallel run has to collect the same names.
UNKNOWN_ID = UUID("0195f3a0-0000-7000-8000-000000000001")

pytestmark = pytest.mark.django_db

# A Wednesday: the week that can be edited first starts on Monday the 12th.
NOW = datetime(2027, 7, 14, 12, 0, tzinfo=UTC)
THIS_WEEK = date(2027, 7, 12)
MARKER = "SECRETMARKER"


@pytest.fixture(autouse=True)
def _clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(goal_services, "_utc_now", lambda: NOW)


@pytest.fixture
def alice() -> User:
    return prepared(User.objects.create_user("alice@example.com"))


def body(plan: WeekPlan | None = None, **lineages: UUID | None) -> dict[str, Any]:
    """The plan as JSON; ``w0=…`` adds a ``lineage`` to the first workout, and so on."""
    data = to_json(plan or good_week(THIS_WEEK))
    for name, lineage in lineages.items():
        data["workouts"][int(name[1:])]["lineage"] = None if lineage is None else str(lineage)
    return data


def problems_of(data: object, monday: date = THIS_WEEK) -> list[tuple[str, str]]:
    with pytest.raises(PlanFormatError) as raised:
        read_edited_plan(data, monday)
    return [(p.path, p.message) for p in raised.value.problems]


class TestReadingAnEditedPlan:
    def test_a_plan_as_the_coach_would_give_it_has_no_lineages(self) -> None:
        edited = read_edited_plan(body(), THIS_WEEK)

        assert edited.plan == good_week(THIS_WEEK)
        assert [w.lineage for w in edited.plan.workouts] == [None] * 4
        assert edited.order == (0, 1, 2, 3)

    def test_the_lineage_stays_with_its_workout(self) -> None:
        first, second = uuid4(), uuid4()

        edited = read_edited_plan(body(w0=first, w2=second), THIS_WEEK)

        assert [w.lineage for w in edited.plan.workouts] == [first, None, second, None]

    def test_a_null_lineage_is_a_new_workout(self) -> None:
        edited = read_edited_plan(body(w1=None), THIS_WEEK)

        assert edited.plan.workouts[1].lineage is None

    def test_the_workouts_come_in_the_stored_order_and_say_where_they_were(self) -> None:
        late, early = uuid4(), uuid4()
        week = WeekPlan(
            THIS_WEEK,
            (
                workout(THIS_WEEK, 4, 30, title="Friday"),
                workout(THIS_WEEK, 0, 30, title="Monday evening", slot=Slot.EVENING),
                workout(THIS_WEEK, 0, 30, title="Monday morning", slot=Slot.MORNING),
            ),
        )

        edited = read_edited_plan(body(week, w0=late, w1=early), THIS_WEEK)

        assert [w.title for w in edited.plan.workouts] == [
            "Monday morning",
            "Monday evening",
            "Friday",
        ]
        assert edited.order == (2, 1, 0)
        assert [w.lineage for w in edited.plan.workouts] == [None, early, late]

    def test_the_input_is_not_changed(self) -> None:
        data = body(w0=uuid4())
        before = copy.deepcopy(data)

        read_edited_plan(data, THIS_WEEK)

        assert data == before

    def test_the_rationale_is_kept(self) -> None:
        assert read_edited_plan(body(), THIS_WEEK).plan.rationale == "Build the base"


class TestRefusingAnEditedPlan:
    @pytest.mark.parametrize(
        "value",
        [
            "not-an-id",
            "",
            5,
            True,
            ["x"],
            {"a": 1},
            str(UNKNOWN_ID).upper(),
            "{" + str(UNKNOWN_ID) + "}",
        ],
    )
    def test_a_lineage_that_is_no_id(self, value: Any) -> None:
        data = body()
        data["workouts"][1]["lineage"] = value

        assert problems_of(data) == [("workouts[1].lineage", "A lineage is an id or null.")]

    def test_a_lineage_used_twice(self) -> None:
        same = uuid4()

        assert problems_of(body(w0=same, w3=same)) == [
            ("workouts[3].lineage", "A lineage can only be used once.")
        ]

    def test_a_plan_for_another_week(self) -> None:
        data = body(good_week(THIS_WEEK + timedelta(days=7)))

        assert problems_of(data) == [
            ("week_start", "The plan must be for the week that starts on 2027-07-12.")
        ]

    def test_every_problem_is_reported_at_once_those_of_the_format_too(self) -> None:
        data = body()
        data["workouts"][0]["lineage"] = "nope"
        data["workouts"][1]["duration_minutes"] = 0
        data["workouts"][2]["sport"] = "chess"

        paths = [path for path, _ in problems_of(data)]

        assert paths == [
            "workouts[0].lineage",
            "workouts[1].duration_minutes",
            "workouts[2].sport",
        ]

    @pytest.mark.parametrize("data", [None, [], "plan", 5, {}, {"workouts": "x"}])
    def test_something_that_is_no_plan(self, data: object) -> None:
        assert problems_of(data)  # reported, never a crash

    def test_a_field_that_is_not_part_of_the_format(self) -> None:
        data = body()
        data["workouts"][0]["colour"] = "red"

        assert problems_of(data) == [("workouts[0].colour", "Unknown field.")]

    def test_nothing_of_the_input_is_repeated(self) -> None:
        data = body()
        data["workouts"][0]["lineage"] = MARKER
        data["workouts"][1]["title"] = MARKER + "\x00"
        data["workouts"][2]["sport"] = MARKER
        data["rationale"] = 5
        data[MARKER + " !"] = MARKER  # a key that does not look like a name is not named

        assert MARKER not in repr(problems_of(data))


class TestChecking:
    def test_a_good_plan_has_nothing_to_point_out(self, alice: User) -> None:
        checked = check(alice, THIS_WEEK, body())

        assert checked.report.valid
        assert checked.report.findings == ()
        assert checked.order == (0, 1, 2, 3)

    def test_a_workout_on_a_day_with_no_time_is_an_error(self, alice: User) -> None:
        week = WeekPlan(THIS_WEEK, (workout(THIS_WEEK, 1, 60),))  # Tuesday offers nothing

        checked = check(alice, THIS_WEEK, body(week))

        assert not checked.report.valid
        assert {f.code for f in checked.report.errors} == {"day_over_capacity"}
        assert [f.path for f in checked.report.errors] == ["workouts[0]"]

    def test_warnings_do_not_make_a_plan_invalid(self, alice: User) -> None:
        week = WeekPlan(THIS_WEEK, tuple(workout(THIS_WEEK, o, 30) for o in (0, 2, 4, 5)))
        week = WeekPlan(THIS_WEEK, (*week.workouts, workout(THIS_WEEK, 0, 30, slot=Slot.MORNING)))

        checked = check(alice, THIS_WEEK, body(week))

        assert checked.report.valid

    def test_the_findings_name_the_workouts_in_the_stored_order(self, alice: User) -> None:
        week = WeekPlan(
            THIS_WEEK,
            (
                workout(THIS_WEEK, 1, 60, title="Tuesday"),  # an error: Tuesday offers nothing
                workout(THIS_WEEK, 0, 30, title="Monday"),
            ),
        )

        checked = check(alice, THIS_WEEK, body(week))

        assert checked.order == (1, 0)
        assert [f.path for f in checked.report.errors] == ["workouts[1]"]  # Tuesday is the second

    def test_it_is_checked_against_what_the_user_can_do_now(self, alice: User) -> None:
        assert check(alice, THIS_WEEK, body()).report.valid

        WeekdayMinutes.objects.filter(owner=alice, weekday=0).update(minutes=0)

        assert not check(alice, THIS_WEEK, body()).report.valid

    def test_the_time_of_another_user_is_not_used(self, alice: User) -> None:
        bob = User.objects.create_user("bob@example.com")  # offers no time at all

        assert check(alice, THIS_WEEK, body()).report.valid
        assert not check(bob, THIS_WEEK, body()).report.valid

    def test_nothing_is_stored(self, alice: User) -> None:
        check(alice, THIS_WEEK, body(w0=uuid4()))

        assert not WeeklyPlan.objects.exists()
        assert not PlannedWorkout.objects.exists()

    def test_it_takes_the_same_number_of_queries_however_large_the_plan(self, alice: User) -> None:
        small = WeekPlan(THIS_WEEK, (workout(THIS_WEEK, 0, 30),))
        with CaptureQueriesContext(connection) as few:
            check(alice, THIS_WEEK, body(small))
        with CaptureQueriesContext(connection) as many:
            check(alice, THIS_WEEK, body())

        assert len(few) == len(many)

    @pytest.mark.parametrize("offset", [-7, 35, 3])
    def test_a_week_that_cannot_be_planned(self, alice: User, offset: int) -> None:
        monday = THIS_WEEK + timedelta(days=offset)

        with pytest.raises(WeekNotPlannable):
            check(alice, monday, body(good_week(monday)))

    def test_a_plan_that_is_no_plan_raises_the_format_error(self, alice: User) -> None:
        with pytest.raises(PlanFormatError):
            check(alice, THIS_WEEK, {"workouts": []})

    def test_changing_interval_segments_from_3x10_to_4x8_passes_checks(self, alice: User) -> None:
        week = WeekPlan(
            THIS_WEEK,
            (
                workout(
                    THIS_WEEK,
                    0,
                    52,
                    segments=(
                        Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                        Segment(SegmentKind.WORK, 480, 4, ZoneSystem.POWER, 4),
                        Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
                    ),
                ),
            ),
        )

        checked = check(alice, THIS_WEEK, body(week))

        assert checked.report.valid
        assert checked.report.errors == ()

    def test_segments_that_do_not_add_up_to_duration_report_segments_mismatch(
        self, alice: User
    ) -> None:
        week = WeekPlan(
            THIS_WEEK,
            (
                workout(
                    THIS_WEEK,
                    0,
                    60,
                    segments=(
                        Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                        Segment(SegmentKind.WORK, 480, 4, ZoneSystem.POWER, 4),
                    ),
                ),
            ),
        )

        checked = check(alice, THIS_WEEK, body(week))

        assert not checked.report.valid
        assert [(f.code, f.path) for f in checked.report.errors] == [
            ("segments_mismatch", "workouts[0].segments")
        ]

    def test_a_segment_with_an_out_of_range_zone_is_refused(self, alice: User) -> None:
        data = body(
            WeekPlan(
                THIS_WEEK,
                (
                    workout(
                        THIS_WEEK,
                        0,
                        20,
                        segments=(Segment(SegmentKind.WORK, 1200, 1, ZoneSystem.POWER, 4),),
                    ),
                ),
            )
        )
        data["workouts"][0]["segments"][0]["zone"] = 8

        assert problems_of(data) == [("workouts[0].segments[0].zone", "Must be between 1 and 7.")]

    def test_a_segment_with_an_unavailable_zone_system_reports_an_error(self, alice: User) -> None:
        week = WeekPlan(
            THIS_WEEK,
            (
                workout(
                    THIS_WEEK,
                    0,
                    20,
                    segments=(Segment(SegmentKind.WORK, 1200, 1, ZoneSystem.HEART_RATE, 2),),
                ),
            ),
        )

        checked = check(alice, THIS_WEEK, body(week))

        assert not checked.report.valid
        assert [(f.code, f.path) for f in checked.report.errors] == [
            ("zone_system_unavailable", "workouts[0].segments[0].zone_system")
        ]

    def test_adding_and_removing_segments_passes_when_duration_matches(self, alice: User) -> None:
        added = WeekPlan(
            THIS_WEEK,
            (
                workout(
                    THIS_WEEK,
                    0,
                    40,
                    segments=(
                        Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                        Segment(SegmentKind.WORK, 600, 2, ZoneSystem.POWER, 4),
                        Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
                    ),
                ),
            ),
        )
        removed = WeekPlan(
            THIS_WEEK,
            (
                workout(
                    THIS_WEEK,
                    0,
                    30,
                    segments=(
                        Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                        Segment(SegmentKind.WORK, 600, 2, ZoneSystem.POWER, 4),
                    ),
                ),
            ),
        )

        assert check(alice, THIS_WEEK, body(added)).report.valid
        assert check(alice, THIS_WEEK, body(removed)).report.valid


def confirmed(user: User, week: WeekPlan | None = None) -> WeeklyPlan:
    plan = services.save_draft(user, week or good_week(THIS_WEEK), reason="Drafted by the coach")
    return services.confirm(user, plan.pk)


def workouts_of(plan: WeeklyPlan) -> list[PlannedWorkout]:
    return list(PlannedWorkout.objects.filter(plan=plan).order_by("day", "position", "id"))


def sent_as_stored(plan: WeeklyPlan, user: User) -> dict[str, Any]:
    """The plan as the page would send it back: every workout with its lineage."""
    data = to_json(services.load(user, plan.pk))
    for item, row in zip(data["workouts"], workouts_of(plan), strict=True):
        item["lineage"] = str(row.lineage)
    return data


class TestStoringAChange:
    def test_a_change_is_a_new_draft_made_from_the_version_it_started_from(
        self, alice: User
    ) -> None:
        old = confirmed(alice)

        newer = revise(alice, old.pk, sent_as_stored(old, alice))

        assert (newer.status, newer.version, newer.parent_id) == ("draft", 2, old.pk)
        assert (newer.reason, newer.week_start) == (REASON, THIS_WEEK)
        assert REASON == "Changed by hand"

    def test_the_version_it_was_made_from_is_not_touched(self, alice: User) -> None:
        old = confirmed(alice)
        before = services.load(alice, old.pk)
        data = sent_as_stored(old, alice)
        data["workouts"][0]["title"] = "Changed"

        revise(alice, old.pk, data)

        old.refresh_from_db()
        assert old.status == "confirmed"
        assert services.load(alice, old.pk) == before

    def test_a_workout_that_was_moved_keeps_its_lineage(self, alice: User) -> None:
        old = confirmed(
            alice, WeekPlan(THIS_WEEK, (workout(THIS_WEEK, 0, 30), workout(THIS_WEEK, 2, 30)))
        )
        first = workouts_of(old)[0]
        data = sent_as_stored(old, alice)
        data["workouts"][0]["day"] = (THIS_WEEK + timedelta(days=4)).isoformat()
        data["workouts"][0]["slot"] = "evening"

        newer = revise(alice, old.pk, data)

        moved = PlannedWorkout.objects.get(plan=newer, lineage=first.lineage)
        assert moved.day == THIS_WEEK + timedelta(days=4)
        assert moved.slot == "evening"
        assert moved.pk != first.pk

    def test_a_workout_that_was_changed_keeps_its_lineage(self, alice: User) -> None:
        old = confirmed(alice)
        target = workouts_of(old)[1]
        data = sent_as_stored(old, alice)
        data["workouts"][1].update(title="Longer", duration_minutes=75, notes="More", zone=3)

        newer = revise(alice, old.pk, data)

        changed = PlannedWorkout.objects.get(plan=newer, lineage=target.lineage)
        assert (changed.title, changed.duration_minutes, changed.notes, changed.zone) == (
            "Longer",
            75,
            "More",
            3,
        )

    def test_a_workout_that_is_not_sent_back_is_taken_out(self, alice: User) -> None:
        old = confirmed(alice)
        gone = workouts_of(old)[3]
        data = sent_as_stored(old, alice)
        del data["workouts"][3]

        newer = revise(alice, old.pk, data)

        assert PlannedWorkout.objects.filter(plan=newer).count() == 3
        assert not PlannedWorkout.objects.filter(plan=newer, lineage=gone.lineage).exists()

    def test_a_workout_without_a_lineage_is_new(self, alice: User) -> None:
        old = confirmed(alice, WeekPlan(THIS_WEEK, (workout(THIS_WEEK, 0, 30),)))
        known = {row.lineage for row in workouts_of(old)}
        data = sent_as_stored(old, alice)
        data["workouts"].append(
            to_json(WeekPlan(THIS_WEEK, (workout(THIS_WEEK, 2, 30),)))["workouts"][0]
        )

        newer = revise(alice, old.pk, data)

        added = PlannedWorkout.objects.get(plan=newer, day=THIS_WEEK + timedelta(days=2))
        assert added.lineage not in known and added.lineage is not None
        assert PlannedWorkout.objects.filter(plan=newer).count() == 2

    def test_the_rationale_of_the_version_is_kept_and_the_one_sent_is_ignored(
        self, alice: User
    ) -> None:
        old = confirmed(alice)
        data = sent_as_stored(old, alice)
        data["rationale"] = "Something else"

        newer = revise(alice, old.pk, data)

        assert newer.rationale == "Build the base"

    def test_a_draft_can_be_changed_too_and_stays_as_it_is(self, alice: User) -> None:
        draft = services.save_draft(alice, good_week(THIS_WEEK))

        newer = revise(alice, draft.pk, sent_as_stored(draft, alice))

        draft.refresh_from_db()
        assert (draft.status, newer.parent_id, newer.version) == ("draft", draft.pk, 2)

    def test_a_plan_with_errors_is_stored_but_cannot_be_confirmed(self, alice: User) -> None:
        old = confirmed(alice)
        data = sent_as_stored(old, alice)
        data["workouts"][0]["day"] = (THIS_WEEK + timedelta(days=1)).isoformat()  # Tuesday: no time

        newer = revise(alice, old.pk, data)

        assert not services.validate(alice, newer.pk).valid
        with pytest.raises(PlanNotConfirmable):
            services.confirm(alice, newer.pk)

    def test_confirming_the_change_replaces_the_version_it_started_from(self, alice: User) -> None:
        old = confirmed(alice)

        newer = services.confirm(alice, revise(alice, old.pk, sent_as_stored(old, alice)).pk)

        old.refresh_from_db()
        assert (old.status, newer.status) == ("superseded", "confirmed")
        assert [w.lineage for w in workouts_of(newer)] == [w.lineage for w in workouts_of(old)]

    def test_revising_segments_from_3x10_to_4x8_passes_checks_and_keeps_lineage(
        self, alice: User
    ) -> None:
        old = confirmed(
            alice,
            WeekPlan(
                THIS_WEEK,
                (
                    workout(
                        THIS_WEEK,
                        0,
                        50,
                        segments=(
                            Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                            Segment(SegmentKind.WORK, 600, 3, ZoneSystem.POWER, 4),
                            Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
                        ),
                    ),
                ),
            ),
        )
        target = workouts_of(old)[0]
        data = sent_as_stored(old, alice)
        data["workouts"][0]["duration_minutes"] = 52
        data["workouts"][0]["segments"][1] = {
            "kind": "work",
            "seconds": 480,
            "repeat": 4,
            "zone_system": "power",
            "zone": 4,
        }

        assert check(alice, THIS_WEEK, data).report.valid
        newer = revise(alice, old.pk, data)

        changed = PlannedWorkout.objects.get(plan=newer, lineage=target.lineage)
        assert changed.pk != target.pk
        assert changed.duration_minutes == 52
        loaded = services.load(alice, newer.pk).workouts[0]
        assert loaded.segments == (
            Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
            Segment(SegmentKind.WORK, 480, 4, ZoneSystem.POWER, 4),
            Segment(SegmentKind.COOLDOWN, 600, 1, ZoneSystem.POWER, 1),
        )
        assert services.validate(alice, newer.pk).valid

    def test_adding_and_removing_segments_via_revise_keeps_lineage(self, alice: User) -> None:
        old = confirmed(
            alice,
            WeekPlan(
                THIS_WEEK,
                (
                    workout(
                        THIS_WEEK,
                        0,
                        30,
                        segments=(
                            Segment(SegmentKind.WARMUP, 600, 1, ZoneSystem.POWER, 2),
                            Segment(SegmentKind.WORK, 600, 2, ZoneSystem.POWER, 4),
                        ),
                    ),
                ),
            ),
        )
        lineage = workouts_of(old)[0].lineage
        data = sent_as_stored(old, alice)
        data["workouts"][0]["duration_minutes"] = 40
        data["workouts"][0]["segments"].append(
            {"kind": "cooldown", "seconds": 600, "repeat": 1, "zone_system": "power", "zone": 1}
        )

        with_added = revise(alice, old.pk, data)

        assert [s.kind for s in services.load(alice, with_added.pk).workouts[0].segments] == [
            SegmentKind.WARMUP,
            SegmentKind.WORK,
            SegmentKind.COOLDOWN,
        ]
        assert PlannedWorkout.objects.get(plan=with_added, lineage=lineage).duration_minutes == 40

        removed_data = sent_as_stored(with_added, alice)
        removed_data["workouts"][0]["duration_minutes"] = 30
        del removed_data["workouts"][0]["segments"][2]

        with_removed = revise(alice, with_added.pk, removed_data)

        assert [s.kind for s in services.load(alice, with_removed.pk).workouts[0].segments] == [
            SegmentKind.WARMUP,
            SegmentKind.WORK,
        ]
        assert PlannedWorkout.objects.get(plan=with_removed, lineage=lineage).duration_minutes == 30


class TestRefusingAChange:
    def stored(self) -> int:
        return WeeklyPlan.objects.count() + PlannedWorkout.objects.count()

    def test_a_lineage_that_is_not_one_of_the_plan_is_refused_by_its_place_in_the_body(
        self, alice: User
    ) -> None:
        old = confirmed(alice)
        data = sent_as_stored(old, alice)
        data["workouts"][0], data["workouts"][2] = data["workouts"][2], data["workouts"][0]
        data["workouts"][1]["lineage"] = str(uuid4())
        count = self.stored()

        with pytest.raises(PlanFormatError) as raised:
            revise(alice, old.pk, data)

        assert [(p.path, p.message) for p in raised.value.problems] == [
            ("workouts[1].lineage", "This workout is not in the plan that is changed.")
        ]
        assert self.stored() == count

    def test_a_lineage_of_another_version_of_the_week_is_refused(self, alice: User) -> None:
        old = confirmed(alice)
        newer = services.confirm(
            alice, services.save_draft(alice, good_week(THIS_WEEK), parent=old.pk).pk
        )
        data = sent_as_stored(old, alice)  # the lineages of the version that is superseded now

        with pytest.raises(PlanFormatError):
            revise(alice, newer.pk, data)

    def test_the_workouts_of_another_user_are_not_reachable(self, alice: User) -> None:
        bob = prepared(User.objects.create_user("bob@example.com"))
        theirs = confirmed(bob)
        data = sent_as_stored(theirs, bob)

        with pytest.raises(PlanFormatError):
            revise(alice, confirmed(alice).pk, data)
        with pytest.raises(PlanNotFound):
            revise(alice, theirs.pk, data)

    @pytest.mark.parametrize("status", ["superseded", "discarded"])
    def test_an_older_version_is_restored_before_it_is_changed(
        self, alice: User, status: str
    ) -> None:
        old = confirmed(alice)
        data = sent_as_stored(old, alice)
        if status == "superseded":
            services.confirm(
                alice, services.save_draft(alice, good_week(THIS_WEEK), parent=old.pk).pk
            )
        else:
            gone = services.save_draft(alice, good_week(THIS_WEEK))
            services.discard(alice, gone.pk)
            old, data = gone, sent_as_stored(gone, alice)
        count = self.stored()

        with pytest.raises(PlanNotRevisable):
            revise(alice, old.pk, data)

        assert self.stored() == count

    def test_a_week_that_can_no_longer_be_planned(self, alice: User) -> None:
        last_week = THIS_WEEK - timedelta(days=7)
        old = services.save_draft(alice, good_week(last_week))
        data = sent_as_stored(old, alice)

        with pytest.raises(WeekNotPlannable):
            revise(alice, old.pk, data)

    def test_a_plan_for_another_week(self, alice: User) -> None:
        old = confirmed(alice)
        data = sent_as_stored(old, alice)
        data["week_start"] = (THIS_WEEK + timedelta(days=7)).isoformat()

        with pytest.raises(PlanFormatError) as raised:
            revise(alice, old.pk, data)

        assert [p.path for p in raised.value.problems] == ["week_start"]

    def test_a_doubled_lineage_and_a_broken_field_are_reported_together(self, alice: User) -> None:
        old = confirmed(alice)
        data = sent_as_stored(old, alice)
        data["workouts"][1]["lineage"] = data["workouts"][0]["lineage"]
        data["workouts"][2]["duration_minutes"] = 0

        with pytest.raises(PlanFormatError) as raised:
            revise(alice, old.pk, data)

        assert [p.path for p in raised.value.problems] == [
            "workouts[1].lineage",
            "workouts[2].duration_minutes",
        ]


class TestRestoring:
    def two_versions(self, user: User) -> tuple[WeeklyPlan, WeeklyPlan]:
        old = confirmed(user)
        newer = services.save_draft(user, good_week(THIS_WEEK, "Second"), parent=old.pk)
        return old, services.confirm(user, newer.pk)

    def test_a_replaced_version_comes_back_as_the_next_draft(self, alice: User) -> None:
        old, current = self.two_versions(alice)

        again = restore(alice, old.pk)

        assert (again.status, again.version, again.parent_id) == ("draft", 3, old.pk)
        assert again.reason == "Restored from version 1"
        assert again.rationale == "Build the base"
        assert again.week_start == THIS_WEEK

    def test_it_has_the_same_workouts_with_the_same_lineages(self, alice: User) -> None:
        old, _ = self.two_versions(alice)

        again = restore(alice, old.pk)

        assert services.load(alice, again.pk) == services.load(alice, old.pk)
        assert [w.lineage for w in workouts_of(again)] == [w.lineage for w in workouts_of(old)]
        assert {w.pk for w in workouts_of(again)}.isdisjoint({w.pk for w in workouts_of(old)})

    def test_the_versions_it_was_made_from_and_the_current_one_are_not_touched(
        self, alice: User
    ) -> None:
        old, current = self.two_versions(alice)

        restore(alice, old.pk)

        old.refresh_from_db()
        current.refresh_from_db()
        assert (old.status, current.status) == ("superseded", "confirmed")

    def test_a_discarded_version_can_be_restored_too(self, alice: User) -> None:
        draft = services.save_draft(alice, good_week(THIS_WEEK))
        services.discard(alice, draft.pk)

        again = restore(alice, draft.pk)

        assert (again.status, again.reason) == ("draft", "Restored from version 1")
        assert services.load(alice, again.pk) == services.load(alice, draft.pk)

    @pytest.mark.parametrize("which", ["draft", "confirmed"])
    def test_a_draft_and_a_confirmed_plan_are_not_restored(self, alice: User, which: str) -> None:
        plan = services.save_draft(alice, good_week(THIS_WEEK))
        if which == "confirmed":
            plan = services.confirm(alice, plan.pk)
        count = WeeklyPlan.objects.count()

        with pytest.raises(PlanNotRestorable):
            restore(alice, plan.pk)

        assert WeeklyPlan.objects.count() == count

    def test_it_is_checked_again_with_what_the_user_can_do_now(self, alice: User) -> None:
        old, _ = self.two_versions(alice)
        WeekdayMinutes.objects.filter(owner=alice, weekday=0).update(minutes=0)

        again = restore(alice, old.pk)

        assert not services.validate(alice, again.pk).valid
        with pytest.raises(PlanNotConfirmable):
            services.confirm(alice, again.pk)

    def test_a_week_that_can_no_longer_be_planned(self, alice: User) -> None:
        past = THIS_WEEK - timedelta(days=7)
        old = services.save_draft(alice, good_week(past))
        services.discard(alice, old.pk)

        with pytest.raises(WeekNotPlannable):
            restore(alice, old.pk)

    def test_the_plan_of_another_user_does_not_exist(self, alice: User) -> None:
        bob = prepared(User.objects.create_user("bob@example.com"))
        theirs = services.save_draft(bob, good_week(THIS_WEEK))
        services.discard(bob, theirs.pk)

        with pytest.raises(PlanNotFound):
            restore(alice, theirs.pk)

    def test_confirming_it_replaces_the_current_version_and_keeps_what_the_user_said(
        self, alice: User
    ) -> None:
        old = confirmed(alice)
        # The current version was made from the first one by a change: the same trainings.
        current = services.confirm(alice, revise(alice, old.pk, sent_as_stored(old, alice)).pk)
        row = workouts_of(current)[0]
        WorkoutReview.objects.create(owner=alice, workout=row, status="missed")

        restored = services.confirm(alice, restore(alice, old.pk).pk)

        current.refresh_from_db()
        assert (current.status, restored.status) == ("superseded", "confirmed")
        review = WorkoutReview.objects.get()
        assert review.workout.plan_id == restored.pk
        assert review.workout.lineage == row.lineage
