# Week plan: format and validation rules

A **week plan** is what the coach proposes and the user confirms: the workouts of one week
(Monday to Sunday) with their intensity targets and, where useful, an interval structure. This
page describes the format that every plan must have, what is checked before a plan can be
confirmed, and where each limit lives. It is the contract with the coach: the coach has to answer
in exactly this format (milestone 4c), and nothing the coach writes is trusted before it has been
read by the strict parser and passed the checks.

Status: the data model, the parser, the checks and the storage exist (`backend/planning/`). There
is no screen and no API yet, and nothing calls the coach with it.

Plausibility is not coaching advice. The rules below stop plans that cannot be done (no time, an
illness, a zone the athlete has no threshold for) and plans that are obviously unwise (five hard
days, a doubled volume). They do not say that a plan is *good*.

## Example

```json
{
  "week_start": "2027-07-12",
  "rationale": "A calm week to build the base: two rides, one run with intervals.",
  "workouts": [
    {
      "day": "2027-07-13",
      "sport": "cycling",
      "title": "Endurance ride",
      "goal": "endurance",
      "duration_minutes": 90,
      "zone_system": "power",
      "zone": 2,
      "segments": [
        { "kind": "steady", "seconds": 5400, "zone_system": "power", "zone": 2 }
      ]
    },
    {
      "day": "2027-07-15",
      "sport": "running",
      "title": "Threshold intervals",
      "goal": "threshold",
      "duration_minutes": 69,
      "notes": "Keep the recoveries really easy.",
      "segments": [
        { "kind": "warmup", "seconds": 900, "zone_system": "pace", "zone": 1 },
        { "kind": "work", "seconds": 480, "repeat": 4, "zone_system": "pace", "zone": 4 },
        { "kind": "recovery", "seconds": 180, "repeat": 4, "zone_system": "pace", "zone": 1 },
        { "kind": "cooldown", "seconds": 600, "zone_system": "pace", "zone": 1 }
      ]
    },
    {
      "day": "2027-07-17",
      "sport": "cycling",
      "title": "Long ride",
      "goal": "endurance",
      "duration_minutes": 150,
      "zone_system": "power",
      "zone": 2
    }
  ]
}
```

## The format

Only the fields below exist; an unknown field is refused. Types are exact: a whole number is a
JSON integer (not `90.0`, not `"90"`, not `true`). Dates are `YYYY-MM-DD` and must exist.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `week_start` | yes | The Monday of the week. |
| `rationale` | no | Why the week looks like this: text of up to 1000 characters, line breaks allowed. |
| `workouts` | yes | A list of at most 28 workouts, an empty list is a rest week. |

A **workout**:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `day` | yes | The day of the workout (whether it lies in the week is a matter of the checks). |
| `sport` | yes | `running`, `cycling`, `swimming` or `strength`. |
| `title` | yes | One line of 1 to 100 characters. |
| `goal` | yes | `recovery`, `endurance`, `tempo`, `threshold`, `vo2max`, `strength` or `other`. |
| `duration_minutes` | yes | 1 to 1440. |
| `zone_system`, `zone` | no | The target of the whole session. Both or neither. |
| `notes` | no | Up to 500 characters, line breaks allowed. |
| `segments` | no | The interval structure: a list of at most 40 segments. |

A **segment**:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `kind` | yes | `warmup`, `steady`, `work`, `recovery` or `cooldown`. |
| `seconds` | yes | 1 to 86400. |
| `repeat` | no | How often the segment is done in a row, 1 to 50, default 1. |
| `zone_system`, `zone` | no | The target. Both or neither. |

**Text.** Text is trimmed and the length is counted after trimming. A title is one line. Control
characters are refused everywhere (line breaks are allowed in `notes` and `rationale` only), and so
are the line and paragraph separators and the characters that reorder text on screen. A text that
is not text, such as a number, is refused instead of being turned into text.

**Errors.** The parser reports *every* problem at once, each with its path
(`workouts[2].segments[0].seconds`). One mistake is one problem: a missing field is reported once.
No message repeats anything that was sent; an unknown field is named only if it looks like a name.

## Zone systems

Intensity is given as a zone of a zone system. The zones are those of the profile (see the README,
section Athlete profile). A system is only valid if it fits the sport **and** the athlete has the
threshold for it; nothing is invented.

| System | Zones | Sports | Needs |
| ------ | ----- | ------ | ----- |
| `power` | 7 | cycling | the FTP for cycling |
| `heart_rate` | 5 | cycling, running | the lactate threshold heart rate or the maximum heart rate of that sport |
| `pace` | 5 | running | the threshold pace for running |

Swimming and strength have no zones: they carry no `zone_system`. A threshold of one sport says
nothing about the other (a cyclist's FTP does not open power zones for running, a run's maximum
heart rate does not open heart rate zones for cycling). A zone number that does not exist in its
system is a format error; a system that does not fit the sport, or for which there is no
threshold, is a finding of the checks.

## How hard a workout is

For the rhythm rules a workout is **hard** if its goal is `threshold` or `vo2max`, or if the
highest zone of the session and its segments is 4 or more, whatever the system. It is **easy** if
that zone is 2 or less or there is none. Everything else is **moderate**.

## What the checks know

Each plan is checked against the facts of its user for that week, collected when the check runs:

- **Time.** The minutes per weekday that the user offers (an empty weekday is 0, not "free"), a day
  inside a vacation, an illness or another absence offers 0 (where absences overlap, the illness is
  named before the vacation), and the weekly budget caps what the week adds up to.
- **Zones.** Which zone systems the athlete has a threshold for (typed in, read from Intervals.icu
  or estimated, in any case).
- **Recent volume.** The minutes of each of the up to 4 calendar weeks before the plan's week in
  which the athlete has an activity with a duration (timer time, elapsed time as a fallback), the
  weeks cut in the user's time zone. Weeks without such an activity are left out, not counted as
  zero. Without any, the progression rule is skipped.

## The rules

A finding has a stable `code`, a `path` into the plan and a fixed message made from numbers, weekday
names and fixed words only. An **error** makes the plan unfit to confirm; a **warning** is for the
user to weigh.

| Code | Severity | The rule |
| ---- | -------- | -------- |
| `outside_week` | error | A workout lies outside the week of the plan. |
| `segments_mismatch` | error | The segments (seconds times repeats) differ from the duration by more than the tolerance. Workouts without segments are not checked. |
| `zone_system_not_for_sport` | error | A zone system that does not fit the sport (workout or segment). |
| `zone_system_unavailable` | error | The athlete has no threshold for that system in that sport. |
| `day_over_capacity` | error | The workouts of a day add up to more than the day offers. The workout that tips the day is named. |
| `day_in_absence` | error | A workout on a day of vacation, illness or another absence. |
| `week_over_capacity` | error | The week adds up to more than the user offers, the weekly budget included. |
| `too_many_hard_days` | error | More hard days than the limit. A day counts once. |
| `volume_jump` | error | The planned minutes are above the error limit of the recent average. |
| `hard_days_in_a_row` | warning | A hard day directly after a hard day. |
| `no_free_day` | warning | Every day of the week has a workout. |
| `many_workouts_in_a_day` | warning | More workouts on a day than the limit. |
| `duplicate_workout` | warning | The same sport, goal and duration twice on a day. |
| `volume_increase` | warning | The planned minutes are above the warning limit of the recent average. |

Workouts outside the week are ignored by every rule except `outside_week`. Nothing is checked
against the next or the previous week, so Sunday and the following Monday are not "in a row".

## The limits

The limits are constants in one place each, so that they can be read and changed there
(`planning/rules.py` for the rules, `planning/schema.py` for the format). They are product
decisions, not coaching science; better ones will come from using the feature.

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `DURATION_TOLERANCE_SECONDS` | 60 | How far the segments may differ from the duration. |
| `HARD_FROM_ZONE` | 4 | From this zone on a workout is hard. |
| `EASY_UP_TO_ZONE` | 2 | Up to this zone a workout is easy. |
| `MAX_HARD_DAYS` | 3 | Hard days a week. |
| `MAX_WORKOUTS_PER_DAY` | 2 | Workouts a day before the warning. |
| `PROGRESSION_WARNING_PERCENT` | 130 | Planned minutes in percent of the recent average: warning above. |
| `PROGRESSION_ERROR_PERCENT` | 150 | Planned minutes in percent of the recent average: error above. |
| `TITLE_MAX` | 100 | Characters of a title. |
| `NOTES_MAX` | 500 | Characters of notes. |
| `RATIONALE_MAX` | 1000 | Characters of the rationale. |
| `DURATION_MAX` | 1440 | Minutes of a workout. |
| `MAX_WORKOUTS` | 28 | Workouts of a week. |
| `MAX_SEGMENTS` | 40 | Segments of a workout. |
| `SEGMENT_SECONDS_MAX` | 86400 | Seconds of a segment. |
| `REPEAT_MAX` | 50 | Repeats of a segment. |

The progression rule compares without rounding the average: with the weeks 100 and 101 (average
100.5) 130 percent is 130.65, so 130 planned minutes pass and 131 do not. A week exactly at a limit
passes it. There is no absolute allowance yet: a recent average of 60 minutes makes a 100-minute
week an error.

## Saving, versions and confirming

A plan is stored as a **draft**. A draft is stored even if the checks have things to say, so that
the user can be shown what is wrong. Its statuses:

| Status | Meaning |
| ------ | ------- |
| `draft` | Stored, not yet agreed. Only a draft can be confirmed or discarded. |
| `confirmed` | Agreed. At most one version of a week is confirmed. |
| `superseded` | Was confirmed and has been replaced by a newer confirmed version. |
| `discarded` | Thrown away before it was confirmed. |

- **Versions.** Every plan of a week has a version number that counts up (discarded versions count
  too). A change is a **new version** of the same week with the version it replaces (`parent`) and a
  short reason; a plan that is not a draft is never changed, and neither are its workouts.
- **Confirming** validates the plan *again*, with the facts of that moment (an absence added after
  the draft was saved counts). Any error refuses it and changes nothing; warnings do not. When it
  works, the version that was confirmed before becomes `superseded`. Two confirmations of the same
  week at once queue up.
- **Reading back.** A stored plan goes through the strict parser again, so what is read is always
  valid. Workouts come by day and, within a day, in the order they were given. Validate the plan in
  this order (`planning.services.canonical`) so that the paths of the findings are the places in
  what is stored.
- Everything belongs to one user: another user's plan, version or workout does not exist for them.

## What is deliberately not checked

- The **limitations** the user wrote on the training time page are free text. A machine cannot
  check them; they go to the coach as context, where they are data and never instructions.
- There is **no time of day**: two workouts on one day add up, they cannot overlap.
- Whether a plan is *good* training: the rules only keep out what is impossible or plainly unwise.
- Anything about the weeks before or after the plan beyond the recent average.

## From code

```python
from planning import services
from planning.schema import parse_week_plan

week = services.canonical(parse_week_plan(answer_of_the_coach))   # PlanFormatError if not valid
draft = services.save_draft(user, week, reason="Knee hurts", parent=previous_id)
report = services.validate(user, draft.pk)                        # errors and warnings
confirmed = services.confirm(user, draft.pk)                      # PlanNotConfirmable with errors
```

## How it is tested

The format and the rules have tests on both sides of every limit, a fuzz test that feeds random
garbage to the parser and random plans to the checks (nothing but a plan or a format error comes
out, nothing raises), tests that no title or note is ever repeated in a message, and mutation tests
for every rule. The example, the limits, the rules and the zone systems of **this page** are
compared with the code by `backend/planning/tests/test_docs.py`, so that the page cannot drift.
