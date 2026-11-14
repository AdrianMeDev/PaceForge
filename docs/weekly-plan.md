# Week plan: format and validation rules

A **week plan** is what the coach proposes and the user confirms: the workouts of one week
(Monday to Sunday) with their intensity targets and, where useful, an interval structure. This
page describes the format that every plan must have, what is checked before a plan can be
confirmed, and where each limit lives. It is the contract with the coach: the coach has to answer
in exactly this format, and nothing the coach writes is trusted before it has been
read by the strict parser and passed the checks.

Status: the data model, the parser, the checks, the storage, the drafting with the user's own
coach, the API and the **Week plan** page exist (`backend/planning/`, `/planning` in the app).
Drafting is described in [Drafting with the coach](#drafting-with-the-coach).

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
      "slot": "morning",
      "stretching_minutes": 10,
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
| `slot` | no | When on the day: `morning`, `afternoon` or `evening`. Only the order is meant, not a clock time. |
| `stretching_minutes` | no | Stretching added to this workout, 0 to 60 minutes (0 or left out: none). Never a workout of its own, and not part of the training time. |
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

**Time of day and stretching.** `slot` says when on the day a workout is: `morning`, `afternoon` or
`evening`. It is an order and no clock time. Several workouts on one day are welcome (an easy run
in the morning, a ride in the afternoon), each with a time of its own; the stored order of a day
follows the times of day (a workout without one comes last). `stretching_minutes` adds stretching
to a workout. Stretching is **never a workout of its own**: it is not a sport, it is not part of
`duration_minutes`, it uses up no minutes of the day or the week, it does not count for the
progression rule and it is not a training day. It is only allowed if the athlete switched it on.

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
- **Sports and stretching.** The sports the athlete ticked (all four if none was chosen) and whether
  stretching may be added to sessions. Stretching minutes are not a workout and not time: they do
  not use up the minutes of a day or a week and do not count for the progression rule.
- **Zones.** Which zone systems the athlete has a threshold for (typed in, read from Intervals.icu
  or estimated, in any case).
- **Recent volume.** The minutes of each of the up to 4 calendar weeks before the plan's week in
  which the athlete has an activity with a duration (timer time, elapsed time as a fallback), the
  weeks cut in the user's time zone. Weeks without such an activity are left out, not counted as
  zero. Without any (and without a typical week, next), the progression rule is skipped.
- **The typical week.** What the athlete calls a normal week of training, entered on the training
  time page (optional). It is a reference and not a limit, and it adds no time to the days. The
  progression rule uses the **higher** of the recent average and the typical week
  (`TYPICAL_VOLUME_PERCENT` of it), so that someone coming back from a break is not held to the few
  weeks since. It is the athlete's own word and their responsibility.

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
| `sport_not_selected` | error | A workout in a sport the athlete did not tick on the training time page. |
| `stretching_not_wanted` | error | Stretching minutes on a workout although stretching is switched off. |
| `same_slot` | error | Two workouts of one day in the same part of the day. The later one is named. |
| `slot_missing` | warning | A day with several workouts of which one has no time of day. Named once per day. |
| `day_in_absence` | error | A workout on a day of vacation, illness or another absence. |
| `week_over_capacity` | error | The week adds up to more than the user offers, the weekly budget included. |
| `too_many_hard_days` | error | More hard days than the limit. A day counts once. |
| `volume_jump` | error | The planned minutes are above the error limit of the reference (the recent average, or the typical week if that is higher). |
| `hard_days_in_a_row` | warning | A hard day directly after a hard day. |
| `no_free_day` | warning | Every day of the week has a workout. |
| `many_workouts_in_a_day` | warning | More workouts on a day than the limit. |
| `duplicate_workout` | warning | The same sport, goal and duration twice on a day. |
| `volume_increase` | warning | The planned minutes are above the warning limit of the reference (the recent average, or the typical week if that is higher). |

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
| `PROGRESSION_WARNING_PERCENT` | 130 | Planned minutes in percent of the reference: warning above. |
| `PROGRESSION_ERROR_PERCENT` | 150 | Planned minutes in percent of the reference: error above. |
| `TYPICAL_VOLUME_PERCENT` | 100 | How much of the typical week counts as a reference (100: all of it). A lower number, say 70, makes the first weeks back more careful. |
| `TITLE_MAX` | 100 | Characters of a title. |
| `NOTES_MAX` | 500 | Characters of notes. |
| `RATIONALE_MAX` | 1000 | Characters of the rationale. |
| `DURATION_MAX` | 1440 | Minutes of a workout. |
| `MAX_WORKOUTS` | 28 | Workouts of a week. |
| `MAX_SEGMENTS` | 40 | Segments of a workout. |
| `SEGMENT_SECONDS_MAX` | 86400 | Seconds of a segment. |
| `REPEAT_MAX` | 50 | Repeats of a segment. |
| `STRETCHING_MAX` | 60 | Minutes of stretching added to one workout. |

The progression rule compares without rounding the reference: with the weeks 100 and 101 (average
100.5) 130 percent is 130.65, so 130 planned minutes pass and 131 do not. A week exactly at a limit
passes it. There is no absolute allowance: a recent average of 60 minutes makes a 100-minute week an
error, unless the athlete has given a typical week that is higher. With a recent average of 108 and
a typical week of 360 minutes the limits are 468 (warning above) and 540 (error above) instead of
140 and 162. The message of a finding says which of the two was the reference.

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

## Drafting with the coach

`planning.generation.generate(user, monday)` asks the user's own AI provider for a draft of a week:

1. A **briefing** is built from the data of the user (below) and sent with the fixed system prompt
   (`planning/prompt.py`), which describes the format and the rules above. If the week offers no
   training time at all (no minutes on any day, a weekly budget of 0, or away all week) nothing is
   sent: there is nothing to plan, and the answer is `no_time` (below).
2. The answer has to be **one JSON object** and nothing else (one code fence around it is
   tolerated). It is read by the strict parser; a repeated key, `NaN`, a huge number or an answer
   of more than the answer limit is refused, and so is a plan for another week.
3. The plan is checked with the rules, against what the user can do **after** the answer came in
   (they may have changed their time while the provider was thinking).
4. If the answer could not be read, was cut off, or the plan has errors, the coach is told **once**
   what was wrong (paths and fixed texts, never a word of its own answer) and may try again. There
   is no third try. The better of the two answers is kept: a readable plan beats an unreadable one,
   fewer errors beat more, a tie goes to the later answer.
5. The plan is stored as a **draft** (`reason`: "Drafted by the coach"), also with errors, so that
   the user sees what is wrong. If no answer could be read, nothing is stored and the user is told
   to try again.

No database transaction is held while the provider answers. Every call that reached the provider
is a usage record with the purpose `weekly_plan` (facts only, never text); a draft costs one call,
or two with a repair.

**JSON mode.** A plan is asked for with `json_output`. A provider that has a JSON mode and is on
the short list of `JSON_MODE_HOSTS` (`coach/providers/openai_compatible.py`) gets
`response_format: {"type": "json_object"}`; everything else ignores the flag, and the answer is read
strictly in any case. JSON output is requested from these hosts: `api.deepseek.com`. The
connection check never asks for it.

### What the coach is told

The briefing is a fixed set of keys (`planning/briefing.py`); a test fails if a key is added
without this page.

| Key | Meaning |
| --- | ------- |
| `week_start` | The Monday of the week to plan. |
| `today` | The day it is for the user, in their time zone. |
| `days` | Seven entries (date, minutes on offer, kind of absence) from Monday. |
| `weekly_budget_minutes` | The weekly budget, none if not set. |
| `weekly_minutes_available` | What the week offers in all, the budget applied. |
| `zone_systems` | For each zone system the athlete can use: sport, threshold and the zone table. |
| `goals` | The active goals, the main goal first, then the nearest date. |
| `goals_not_shown` | How many active goals were left out because of the limit. |
| `recent_weeks_minutes` | Minutes done in each of the up to 4 weeks before, latest first. |
| `typical_weekly_minutes` | What the athlete calls a normal week, in minutes; `null` if not given (or 0). The progression rule's reference is the higher of this and the recent average. |
| `sports` | The sports the athlete wants in a plan (all four if none was chosen), in the order of the format. |
| `stretching` | Whether stretching may be added to sessions (`stretching_minutes`), never as a session. |
| `previous_week_plan` | The confirmed plan of the week before: day, sport, goal, minutes. |

What is **never** sent: names, e-mail addresses, ids, the title or notes of past plans, the names
or descriptions of activities, the limitations of the training time page and the provider setup.
The title and notes of a goal are free text. They are sent as JSON strings, the notes cut to
`GOAL_NOTES_MAX` characters, and the system prompt says that they are data and never instructions.
That is a request to the model, not a guarantee: a model may still be swayed by what is in them.
What it cannot do is get a plan past the parser and the rules.

### The drafting limits

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `WEEKS_AHEAD` | 4 | Weeks after the current one that can be planned. |
| `ATTEMPTS` | 2 | Calls for one draft: one try and one repair. |
| `PLAN_MAX_TOKENS` | 8000 | The most the coach may write for a plan; an answer cut off is not used. |
| `MAX_ANSWER_CHARS` | 200000 | The longest answer that is read at all. |
| `MAX_LISTED` | 20 | Problems listed in a repair message; the rest is only counted. |
| `MAX_GOALS` | 5 | Active goals told to the coach. |
| `GOAL_NOTES_MAX` | 300 | Characters of the notes of a goal that are sent. |
| `MAX_BYTES` | 20000 | The most the briefing may take (UTF-8), checked in the tests. |

### Time and the web server

Drafting is **synchronous**: the request waits for the provider. A call may take up to 60 seconds
per step of the connection, so a draft with a repair can take about `ATTEMPTS` times 60 = 120
seconds. Everything in front of PaceForge has to allow that: set the read timeout of a reverse
proxy (for nginx `proxy_read_timeout`) and the timeout of the application server's workers to at
least 150 seconds. Otherwise the request is cut off while the call to the provider (and its cost)
goes on, and the user sees an error although a draft may have been stored; the versions list shows
it. A proxy that replaces a 502 or 503 by a page of its own hides the reason from the app, which
then shows a general text for that kind of problem.

### The API

All of it needs a signed-in user, and every plan is looked up among the plans of that user: the
plan of another user does not exist (404, the same answer as for an unknown id).

| Endpoint | Answer |
| -------- | ------ |
| `GET /api/planning/weeks/` | The weeks that can be planned, each with its versions, newest first. |
| `POST /api/planning/weeks/<Monday>/generate/` | 201 with the new draft; limited to 5 a minute per user. |
| `GET /api/planning/plans/<id>/` | One plan with its workouts; a draft comes with its checks. |
| `POST /api/planning/plans/<id>/confirm/` | The confirmed plan, or the findings if it has errors. |
| `POST /api/planning/plans/<id>/discard/` | The discarded plan. |

Errors have a fixed text and a `code`; nothing the provider or the coach said is in one. A 429
without a code is the limit of PaceForge itself.

| Code | Status | When |
| ---- | ------ | ---- |
| `week_not_plannable` | 404 | The week is not one of the weeks that can be planned (also: not a date). |
| `not_found` | 404 | There is no such plan. |
| `not_configured` | 409 | The user has not set up an AI provider. |
| `no_time` | 409 | The week offers no training time at all; the coach is not asked and nothing is recorded. |
| `not_a_draft` | 409 | Only a draft can be confirmed or discarded. |
| `not_usable` | 422 | The coach gave no readable plan, even after the repair; the problems come along. |
| `not_confirmable` | 422 | The plan has errors; the findings come along. |
| `rate_limited` | 429 | The provider asked to slow down (`retry_after` in seconds, if it said). |
| `invalid_key` | 502 | The provider refused the key. |
| `not_allowed` | 502 | The address is no longer on the operator's list. |
| `unexpected` | 502 | The provider answered in an unexpected way. |
| `unavailable` | 503 | The provider could not be reached. |

## What is deliberately not checked

- The **limitations** the user wrote on the training time page are free text. A machine cannot
  check them, and they are **not sent to the coach** either: they are free text about the body of
  the user. The only free text the coach sees is the title and notes of the goals.
- The **time of day** is only an order (morning, afternoon, evening), not a clock time: two
  workouts on one day add up, and PaceForge does not know that you can only train in the evening,
  because the time you have is given per day. A plan can put the morning on a day when you are not
  free then.
- Whether a plan is *good* training: the rules only keep out what is impossible or plainly unwise.
- Anything about the weeks before or after the plan beyond the recent average and the typical week.

## From code

```python
from planning import services
from planning.schema import parse_week_plan

week = services.canonical(parse_week_plan(answer_of_the_coach))   # PlanFormatError if not valid
draft = services.save_draft(user, week, reason="Knee hurts", parent=previous_id)
report = services.validate(user, draft.pk)                        # errors and warnings
confirmed = services.confirm(user, draft.pk)                      # PlanNotConfirmable with errors

# or let the coach of the user draft the week (provider errors, PlanNotUsable and
# WeekNotPlannable are raised); the result has the stored draft and its report
from planning.generation import generate
result = generate(user, monday)
```

## How it is tested

The format and the rules have tests on both sides of every limit, a fuzz test that feeds random
garbage to the parser and random plans to the checks (nothing but a plan or a format error comes
out, nothing raises), tests that no title or note is ever repeated in a message, and mutation tests
for every rule. The example, the limits, the rules and the zone systems of **this page** are
compared with the code by `backend/planning/tests/test_docs.py`, so that the page cannot drift:
so are the keys of the briefing, the drafting limits, the endpoints and the error codes.
Drafting is tested with a provider that answers from a script, so that every path (a repair, two
unreadable answers, a provider that fails on the second call) is run without a network.
