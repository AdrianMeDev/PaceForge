# Week plan: format and validation rules

A **week plan** is what the coach proposes and the user confirms: the workouts of one week
(Monday to Sunday) with their intensity targets and, where useful, an interval structure. This
page describes the format that every plan must have, what is checked before a plan can be
confirmed, and where each limit lives. It is the contract with the coach: the coach has to answer
in exactly this format, and nothing the coach writes is trusted before it has been
read by the strict parser and passed the checks.

Status: the data model, the parser, the checks, the storage, the drafting with the user's own
coach, the API, the **Week plan** page and the sending to Intervals.icu exist
(`backend/planning/`, `/planning` in the app). Drafting is described in
[Drafting with the coach](#drafting-with-the-coach), sending in
[Sending to Intervals.icu](#sending-to-intervalsicu).

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
| `exercises` | no | The exercises of a **strength** workout, in the order they are done: a list of at most 15 exercises. Any other sport with exercises is an error. |

A **segment**:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `kind` | yes | `warmup`, `steady`, `work`, `recovery` or `cooldown`. |
| `seconds` | yes | 1 to 86400. |
| `repeat` | no | How often the segment is done in a row, 1 to 50, default 1. |
| `zone_system`, `zone` | no | The target. Both or neither. |

An **exercise**:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `name` | yes | One line of 1 to 60 characters, free text ("Goblet squat"). The checks never read it. |
| `region` | yes | What it trains: `legs`, `core`, `upper_body` or `full_body`. |
| `equipment` | yes | What it needs: `gym`, `dumbbells` or `bodyweight`. |
| `sets` | yes | 1 to 10. |
| `reps`, `seconds` | one of them | Repetitions per set (1 to 100) **or** the length of a hold in seconds (5 to 600), such as a plank. Exactly one of the two. |
| `rpe` | no | How hard, 1 to 10. |
| `rest_seconds` | no | The rest between sets, 0 to 600 seconds. |

**Text.** Text is trimmed and the length is counted after trimming. A title is one line. Control
characters are refused everywhere (line breaks are allowed in `notes` and `rationale` only), and so
are the line and paragraph separators and the characters that reorder text on screen. A text that
is not text, such as a number, is refused instead of being turned into text.

**Lineage.** A stored workout also has a `lineage`: which training it is across the versions of a
week. A version made from another one (changed by hand, restored) keeps the lineage of the workouts
it copies, a new workout gets a new one. It is **not part of the format**: it is never read from an
answer (an answer that has one is refused as an unknown field) and it does not make two workouts
different. It is in the answer of the API (see [The API](#the-api)) and decides which event of the
Intervals.icu calendar a workout is sent to.

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

For the share of easy minutes only running, cycling and swimming count; strength counts neither
way. A workout without segments is easy or not as a whole (moderate is not easy). A workout with
segments counts segment by segment, each by its share of the segments' time applied to the
duration: a segment is easy if its zone is 2 or less; without a zone a warm-up, recovery or
cool-down is easy and any other segment is as easy as the workout itself (its goal and its own
zone). A share is told rounded down, and a week exactly at the limit passes.

## What the checks know

Each plan is checked against the facts of its user for that week, collected when the check runs:

- **Time.** The minutes per weekday that the user offers (an empty weekday is 0, not "free"), a day
  inside a vacation, an illness or another absence offers 0 (where absences overlap, the illness is
  named before the vacation), and the weekly budget caps what the week adds up to.
- **Double days and parts of the day.** For each weekday whether two workouts are allowed and which
  parts of the day (morning, afternoon, evening) are open. Without a choice two workouts are allowed
  and every part is open. A day of absence keeps the choice of its weekday.
- **Sports.** What the athlete said about each sport: a role (goal, secondary, supplementary) and
  the least and the most sessions a week. Only the sessions are checked (`sessions_out_of_range`,
  a warning); the role is for the coach. The strength focus (legs, core, upper body, full body)
  makes every strength workout **without exercises** count as leg training for legs and full body;
  with exercises their regions decide. A strength workout that trains the legs on the day before a
  key run is a warning (`legs_before_key_run`).
- **The wishes for a week.** On how many days the athlete wants to train at most, the least they
  want to train in a week, and the weekday of the long run and of the long ride. Each is optional
  and a missing one is never checked. They only produce warnings (`too_many_training_days`,
  `below_minimum_minutes`, `long_session_elsewhere`), never an error.
- **Body and training data.** Age, sex, weight, resting heart rate, years of training per sport,
  strength experience and equipment, as the athlete entered them. They are for the coach only: no
  rule checks anything against them.
- **Best times and VDOT.** The running best times of the athlete and the VDOT of the one that
  counts, for the coach only; no rule checks a plan against them. They move the running pace zones
  (a recent best time gives the threshold pace after a typed-in value), and the zones are checked
  as before.
- **Fixed appointments.** Sessions that happen every week: weekday, sport, minutes and optionally
  a part of the day. The coach is told to plan them; a plan without one is a warning
  (`fixed_session_missing`), not an error.
- **Limitations.** The athlete's current injuries and limitations, each a body part from a fixed
  list and the sports it affects. A workout in an affected sport is a warning (`limited_sport`),
  not an error. Healed entries are not in the context.
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
| `slot_outside_window` | error | A workout whose time of day is not an open part of its weekday (training time page). A workout without a time of day is not checked. |
| `same_slot` | error | Two workouts of one day in the same part of the day. The later one is named. |
| `slot_missing` | warning | A day with several workouts of which one has no time of day. Named once per day. |
| `day_in_absence` | error | A workout on a day of vacation, illness or another absence. |
| `week_over_capacity` | error | The week adds up to more than the user offers, the weekly budget included. |
| `too_many_hard_days` | error | More hard days than the limit. A day counts once. |
| `volume_jump` | error | The planned minutes are above the error limit of the reference (the recent average, or the typical week if that is higher). |
| `two_hard_in_a_day` | error | Two hard workouts on one day. Named once per day, at the second hard one. |
| `quality_not_first` | warning | On a day with two running, cycling or swimming workouts that both have a time of day, an easy one comes before a moderate or hard one. Strength is left out. Named once per day, at the easy one. |
| `limited_sport` | warning | A workout in a sport that a current limitation affects (training time page). Named at the sport of the workout, once per workout, with the body part of the newest limitation that affects it. A limitation without sports affects no particular sport and is never named. |
| `too_many_training_days` | warning | More days with a workout than the athlete wants to train on. Fewer days are fine. |
| `below_minimum_minutes` | warning | Fewer minutes than the least the athlete wants to train in a week, as far as the week offers it (the bar is the lower of that minimum and what the week offers). |
| `long_session_elsewhere` | warning | For running and cycling, if the athlete named a day for the long session: the longest workout of that sport is on another day (with a tie one of the longest on that day is enough). Named at the `day` of the longest workout. Not said if the week has no workout of the sport or if that day is an absence or offers no minutes. |
| `sessions_out_of_range` | warning | A sport has fewer sessions in the week than the least the athlete wants of it, or more than the most. Only sports with such a wish are looked at. Named once per sport, at the plan as a whole. |
| `legs_before_key_run` | warning | A strength workout that trains the legs on the day before a key run, that is a hard run or the longest run of the week (with a tie, each of the longest). A strength workout trains the legs if one of its exercises has the region `legs` or `full_body` (whatever the strength focus); without exercises it does if the strength focus is legs or full body. Named at the strength workout, once. Only days of the week are compared. |
| `fixed_session_missing` | warning | A session that happens every week (training time page) is not in the plan: the day has no workout of its sport, in its part of the day if one was named (a workout without a time of day fits any part of the day). A workout covers one session only. The minutes are not checked. Named once per session, at the plan as a whole. Not said for a day of absence or a day that offers no minutes. |
| `exercises_not_strength` | error | A workout of another sport than strength has exercises. Named once per workout, at its `exercises`. |
| `exercise_needs_equipment` | warning | An exercise needs a gym, or dumbbells, and the athlete did not list that equipment (training time and athlete pages): a gym is the only thing that provides a gym, dumbbells are provided by dumbbells and by a gym, body weight always fits. Named once per exercise, at its `equipment`. Not said if the athlete listed no equipment. |
| `hard_days_in_a_row` | warning | A hard day directly after a hard day. |
| `no_free_day` | warning | Every day of the week has a workout. |
| `many_workouts_in_a_day` | error | More workouts on a day than the limit (two). Named once per day, at the first one too many. |
| `double_day_not_allowed` | error | A second workout on a weekday that the athlete did not allow two workouts on (training time page). Named once per day, at the second workout. |
| `duplicate_workout` | warning | The same sport, goal and duration twice on a day. |
| `volume_increase` | warning | The planned minutes are above the warning limit of the reference (the recent average, or the typical week if that is higher). |
| `easy_share_low` | warning | Less of the endurance minutes are easy than the intensity level asks for. |

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
| `MAX_WORKOUTS_PER_DAY` | 2 | Most workouts on a day; a third is an error. |
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
| `MAX_EXERCISES` | 15 | Exercises of a strength workout. |
| `EXERCISE_NAME_MAX` | 60 | Characters of the name of an exercise. |
| `SETS_MAX` | 10 | Sets of an exercise. |
| `REPS_MAX` | 100 | Repetitions per set. |
| `HOLD_SECONDS_MIN` | 5 | Shortest hold of an exercise, in seconds. |
| `HOLD_SECONDS_MAX` | 600 | Longest hold of an exercise, in seconds. |
| `RPE_MAX` | 10 | Highest RPE of an exercise. |
| `REST_SECONDS_MAX` | 600 | Longest rest between sets, in seconds. |

The progression rule compares without rounding the reference: with the weeks 100 and 101 (average
100.5) a limit of 130 percent is 130.65, so 130 planned minutes pass and 131 do not. A week exactly at a limit
passes it. There is no absolute allowance: a recent average of 60 minutes makes a 100-minute week an
error, unless the athlete has given a typical week that is higher. With a recent average of 108 and
a typical week of 360 minutes the limits of "intensive" (130 and 150 percent) are 468 (warning above)
and 540 (error above) instead of 140 and 162. The message of a finding says which of the two was the reference.

## The intensity levels

How many hard days a week may have, the two progression limits and the share of easy minutes are
not constants: they come from the intensity level the athlete chose on the training time page
(`availability/intensity.py`, "normal" unless chosen otherwise) and reach the rules with the context
(`PlanContext.limits`). Each of the four can be replaced by an own value of the athlete (hard days 0
to 4, warning 100 to 200, error 100 to 300, easy share 50 to 100; the warning limit below the error
limit). The limits that count are those when a plan is checked: when it is drafted, checked in the
editor or confirmed. The coach is told them in the briefing (`limits`), never in the system prompt.

| Level | Hard days (at most) | Progression warning above (%) | Progression error above (%) | Easy share (at least, %) |
| ----- | ------------------- | ----------------------------- | --------------------------- | ------------------------ |
| `relaxed` | 1 | 115 | 130 | 85 |
| `normal` | 2 | 120 | 140 | 80 |
| `intensive` | 3 | 130 | 150 | 75 |

The percentages are of the reference above, as before. "intensive" has the limits that applied to
every athlete before there were levels.

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
| `days` | Seven entries from Monday: the date, the minutes on offer, the kind of absence, `double_allowed` (whether two workouts may be on that weekday) and `slots` (the parts of the day that are open on it, in the order of the day). |
| `weekly_budget_minutes` | The weekly budget, none if not set. |
| `weekly_minutes_available` | What the week offers in all, the budget applied. |
| `zone_systems` | For each zone system the athlete can use: sport, threshold and the zone table. |
| `goals` | The active goals by `priority` – `main` (A), `secondary` (B), `preparation` (C, a race on the way) – then the nearest date. |
| `goals_not_shown` | How many active goals were left out because of the limit. |
| `recent_weeks_minutes` | Minutes done in each of the up to 4 weeks before, latest first. |
| `typical_weekly_minutes` | What the athlete calls a normal week, in minutes; `null` if not given (or 0). The progression rule's reference is the higher of this and the recent average. |
| `sports` | The sports the athlete wants in a plan (all four if none was chosen), in the order of the format. |
| `stretching` | Whether stretching may be added to sessions (`stretching_minutes`), never as a session. |
| `sport_preferences` | For every sport the athlete said something about: the `sport`, its `role` (`goal`, `secondary` or `supplementary`, `null` for none) and the least and the most sessions a week they want of it (`sessions_min`, `sessions_max`, `null` for no wish). A sport they said nothing about is not listed. |
| `strength_focus` | What strength training is for: `legs`, `core`, `upper_body` or `full_body`; `null` if not said. |
| `training_days` | On how many days of the week the athlete wants to train at most; `null` if they have no wish. |
| `min_weekly_minutes` | The least the athlete wants to train in a week, in minutes (never above the weekly budget); `null` if they have no wish. |
| `long_days` | For running and cycling, if the athlete named a weekday for the long session: the `sport` and the `date` of that day in the week to plan. Empty if there is none. |
| `athlete` | What the athlete told about their body and training ([athlete page](../README.md)): the `age` in years (the year of the week minus the birth year, so it can be one too high before the birthday; the birth year itself is **not** sent), `sex` (`female`, `male`, `other`), `weight_kg`, `resting_hr`, `training_years` (the `sport` and the whole `years` of each sport they named), `strength_experience` (`beginner`, `advanced`) and `strength_equipment` (`gym`, `home`, `dumbbells`). `null` or an empty list for what was not said. Numbers and fixed words, no text of the athlete. |
| `best_times` | The athlete's running best times, in the order 5 km, 10 km, half marathon, marathon (only the ones they entered): the `distance` (`5k`, `10k`, `half_marathon`, `marathon`), the time in `seconds`, the `date` of the race, the `vdot` it is worth, `recent` (the race is less than a year old, so it can count) and `counts` (the threshold pace comes from this one). |
| `vdot` | The VDOT of the best time that counts, or `null` if none does: a measure of the athlete's running form (see the [athlete profile](../README.md)). |
| `fixed_sessions` | The sessions that happen every week at a fixed time ([training time page](../README.md)), by day and part of the day: the `date` of the day in the week to plan, the `sport`, the `minutes` and the `slot` (`morning`, `afternoon`, `evening`; `null` if none was named). Fixed words and numbers, no name. Empty if there are none. |
| `limits` | The limits of the rules that follow from the athlete's [intensity level](#the-intensity-levels): `max_hard_days`, `progression_warning_percent`, `progression_error_percent`, `easy_share_percent`. They are here and not in the system prompt, so that the prompt is the same for every athlete. |
| `limitations` | The current injuries and limitations, the newest first, at most 10: `body_part` (a fixed word: foot, ankle, achilles, calf, shin, knee, thigh, hip, back, shoulder, other) and the `sports` it affects (none listed: no particular sport). Healed ones are not told. No text of the athlete. |
| `limitations_text` | What the athlete wrote in the free text about their limitations, cut to `LIMITATIONS_TEXT_MAX_TOLD` characters, **only if they switched on "Send this text to my AI coach"**; otherwise `null`. Free text: the system prompt says that it is data and never instructions. |
| `limitations_not_shown` | How many current limitations were left out because of the limit. |
| `previous_week_plan` | The confirmed plan of the week before: day, sport, goal, minutes. |
| `previous_week_review` | How the week before went, from the [week review](../README.md#week-review): the number of workouts by status, the minutes planned and done, the sessions that were not planned, how many sessions were rated and their mean RPE, the three scales of the week feedback (`null` if none was given) and `next_week`, the recommendation of a review of that week by the coach (`increase`, `hold`, `reduce`; `null` if none was asked for). Numbers and one fixed word, no text of the user or of the coach. `null` if the week before has not begun or has nothing in it. |

What is **never** sent: names, e-mail addresses, ids, the title or notes of past plans, the names
or descriptions of activities and the provider setup. The limitations of the training time page are
told as a body part and sports from a fixed list; the free text next to them is **only** sent if the
athlete switches that on, and then as `limitations_text`.

The title and notes of a goal (and `limitations_text`, if allowed) are free text. They are sent as
JSON strings, the notes cut to `GOAL_NOTES_MAX` characters and the limitations text to
`LIMITATIONS_TEXT_MAX_TOLD`, and the system prompt says that they are data and never instructions.
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
| `LIMITATIONS_TEXT_MAX_TOLD` | 150 | Characters of the free text about limitations that are sent, if the athlete allows it. |
| `MAX_LIMITATIONS_TOLD` | 10 | Current limitations told to the coach (the newest first); the rest is counted. |
| `MAX_BYTES` | 24000 | The most the briefing may take (UTF-8), checked in the tests. |

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
| `POST /api/planning/weeks/<Monday>/check/` | The checks for a plan that was changed by hand, as `valid`, `findings` and `order`; nothing is stored and no provider is asked. Not limited. |
| `GET /api/planning/plans/<id>/` | One plan with its workouts; a draft comes with its checks. |
| `POST /api/planning/plans/<id>/revise/` | 201 with a new draft made from that plan, from the same body as the check: the plan changed by hand (see below). Only a draft or a confirmed plan can be changed. |
| `POST /api/planning/plans/<id>/restore/` | 201 with a new draft that brings back a version that was replaced or discarded: the same workouts and rationale, `parent` that version, the `reason` "Restored from version N". Its checks are those of today. |
| `POST /api/planning/plans/<id>/confirm/` | The confirmed plan, or the findings if it has errors. With `{"push": true}` the week is sent to Intervals.icu right after (a problem with that is part of the answer, the plan stays confirmed). |
| `POST /api/planning/plans/<id>/push/` | Sends a confirmed plan to the Intervals.icu calendar of the user; the plan with the result per workout. Limited to 10 a minute per user. |
| `POST /api/planning/plans/<id>/discard/` | The discarded plan. |

**Checking a plan that was changed by hand.** `POST /api/planning/weeks/<Monday>/check/` takes a
plan in the format of [The format](#the-format) for that week, with one addition: a workout may have a
`lineage` (the lineage of the workout it was made from, or `null` for a new one). It is read by
the same strict parser and checked against what the user can do and has done *now*. The answer is
`valid`, the `findings` and `order`: the findings number the workouts as they are stored (by day,
then by time of day, then as sent), and `order[i]` is the place in the body of the workout that is
the `i`-th of them. Nothing is stored, no provider is asked and the number of requests is not
limited: it is how the planning page shows the findings after every change.

**Storing a plan that was changed by hand.** `POST /api/planning/plans/<id>/revise/` takes the
same body as the check and stores it as the next version of the week: a **draft** with `parent` the
plan in the address and the `reason` "Changed by hand". That plan is not touched: a confirmed plan
is never changed, a change is a new version, which is confirmed (and sent) as any other. A workout
with a `lineage` is the workout of that plan with it, changed or moved; a workout without one is
new; a workout of that plan that is not in the body is taken out. A `lineage` that is not one of
the workouts of the plan in the address is refused, and so is a week that cannot be planned. The
rationale of the plan in the address is kept, the one in the body is ignored. The draft is stored
also if the checks find errors in it, so that the user sees what is wrong; it cannot be confirmed.

**Restoring a version.** `POST /api/planning/plans/<id>/restore/` copies a plan that was replaced
(`superseded`) or `discarded` into the next version of its week, as a draft: the same workouts with
their lineages, the same rationale, `parent` that version and the `reason` "Restored from version
N". A draft is a draft already and a confirmed plan can be changed with `revise`, so only those two
statuses can be restored. The copy is checked again with what the user can do now, so it may have
errors that the old version did not; it is confirmed and sent like any other draft, and nothing
changes before that. Like changing, it is for the weeks that can be planned.

Every workout of a plan has a `lineage` (its identity across the versions of the week, see
[The format](#the-format)). Every workout and every segment of a plan has a `target`: the range of its zone as it is *now*
(`low`, `high` and a `unit` of `W`, `bpm` or `s/km`; for pace `low` is the faster end), or `null`
without a zone or without the threshold for it. A confirmed plan has an `export` (how many
workouts are `synced`, `failed` or `not_sent`, and how many events of an `older` version are still
in the calendar) and every workout an `export` of its own (`status`, `error_code`, `pushed_at`);
for any other plan these are `null`. An answer of the two sending endpoints has a `push` with what
the sending did (see [Sending to Intervals.icu](#sending-to-intervalsicu)).

Errors have a fixed text and a `code`; nothing the provider or the coach said is in one. A 429
without a code is the limit of PaceForge itself.

| Code | Status | When |
| ---- | ------ | ---- |
| `week_not_plannable` | 404 | The week is not one of the weeks that can be planned (also: not a date). |
| `not_found` | 404 | There is no such plan. |
| `not_configured` | 409 | The user has not set up an AI provider. |
| `no_time` | 409 | The week offers no training time at all; the coach is not asked and nothing is recorded. |
| `not_a_draft` | 409 | Only a draft can be confirmed or discarded. |
| `not_restorable` | 409 | Only a version that was replaced or discarded can be restored (`restore`). |
| `not_revisable` | 409 | Only a draft or a confirmed plan can be changed (`revise`); an older version has to be restored first. |
| `not_confirmed` | 409 | Only a confirmed plan can be sent to Intervals.icu. |
| `not_connected` | 409 | The user has not connected Intervals.icu. |
| `not_usable` | 422 | The coach gave no readable plan, even after the repair; the problems come along. |
| `invalid_plan` | 422 | The plan that was sent for a check cannot be read (the format, a lineage that is no id or is used twice, a plan for another week); the problems come along. |
| `not_confirmable` | 422 | The plan has errors; the findings come along. |
| `rate_limited` | 429 | The provider asked to slow down (`retry_after` in seconds, if it said). |
| `invalid_key` | 502 | The provider (or Intervals.icu) refused the key. |
| `not_allowed` | 502 | The address is no longer on the operator's list. |
| `unexpected` | 502 | The provider (or Intervals.icu) answered in an unexpected way. |
| `unavailable` | 503 | The provider could not be reached. |

## Sending to Intervals.icu

A confirmed plan can be sent to the Intervals.icu calendar of the user (`planning/export.py` makes
the events, `planning/push.py` sends them). It happens **only on request**: with **Send to
Intervals.icu** on a confirmed plan, or by ticking **Send the week to Intervals.icu right away**
when confirming. It uses the API key the user connected (see the README, section Connections).

**One event per workout.**

| Field of the event | Value |
| ------------------ | ----- |
| `category` | `WORKOUT` |
| `type` | `Run`, `Ride`, `Swim` or `WeightTraining`, by the sport. |
| `name` | The title of the workout. |
| `start_date_local` | The day and a start time: 07:00 for `morning`, 12:00 for `afternoon`, 18:00 for `evening`, 00:00 (all day) without a time of day. |
| `external_id` | `paceforge-<lineage of the workout>`: the key at Intervals.icu, so that the same workout is updated and never added twice, also when a new version of the week has moved it. |
| `description` | The workout in the syntax of Intervals.icu (below). |
| `moving_time` | Strength only: the duration in seconds. |

**The description.** Every segment is a block: a heading (`Warmup`, `Steady`, `Work`, `Recovery`,
`Cooldown`, with `<n>x` when the segment is repeated) and one step. Targets are **absolute** and
come from the thresholds of the user at the time of sending (the same numbers as on the plan page):
watts as `138-188w`, heart rate as `145-152bpm`, pace as `5:12-5:41/km Pace`. A zone for which the
user has no threshold stays in the text (`Power zone 3`) and has no target. A workout without
segments is one step. Strength is a line of text and no steps: after it come the exercises, one
numbered comment line each (`1. Goblet squat: 3 sets of 10, RPE 7, rest 1:30`; a hold is
`3 sets of 45 s`). A line starts with its number and never with `-`, and the name is one line, so
Intervals.icu reads none of them as a step or a repeat block. Stretching is a line after the
workout, and the notes of the coach come first as one comment line.

```
Note: Keep the first rep easy

Warmup
- 10m 100-138w

Work 4x
- 5m 263-300w

Recovery 4x
- 3m 100-138w

Stretching: 10 min after the workout.
```

A segment that is repeated is written as it is stored (four work parts, then four recoveries), so
that the times add up as in PaceForge.

**Free text is data.** Notes are joined into a single line that starts with a word and never ends
in `<n>x`, so Intervals.icu cannot read them as a step or a repeat. Titles go into the name, which
is not parsed.

**Sending again, new versions, conflicts.** Sending the same plan again updates the same events.
The key of an event is the **lineage** of its workout (see [The format](#the-format)). A version
of a week that was made from another one (changed by hand, restored) keeps the lineage of the
workouts it copies: sending it **updates their events**, also where a workout was moved to another
day, creates the events of workouts that were added and removes those of workouts that were taken
out (PaceForge remembers the events in `WorkoutExport`). A version that the coach drafted anew has
new workouts and so new lineages: sending it removes the events of the version it replaces. A
workout that was sent before there were lineages is its own lineage, so its event is found again. **PaceForge wins:** what the user changed in an event in Intervals.icu is overwritten, and an
event the user deleted there comes back. An event that is gone at Intervals.icu counts as removed.

**One workout at a time.** Each workout is sent on its own, so each has its own result. One that
Intervals.icu does not accept (`rejected`) does not keep the others from arriving. If Intervals.icu
cannot be reached (`unavailable`) the rest is not tried, is marked failed and nothing is removed;
sending again tries again. A key that Intervals.icu refuses stops everything and marks the
connection invalid. The `error_code` is one of `rejected`, `unavailable` and `unexpected`: never
what Intervals.icu said. Nothing holds a lock while the calls are made (sending is idempotent).

## What is deliberately not checked

- The **free text** about limitations on the training time page cannot be checked by a machine.
  It is **not sent to the coach** unless the athlete switches that on (then its first
  `LIMITATIONS_TEXT_MAX_TOLD` characters, as data and never as instructions). What the rules use are
  the structured entries (body part and sports), not the text.
- The **fixed appointments** are checked for their sport, their weekday and their part of the day,
  not for their minutes, and a workout without a time of day fits any of their parts of the day.
  They have no name or other text, so nothing of the athlete is repeated in a finding. Only
  weekly appointments exist; a session on one date has no place in the rules.
- The **exercises** are checked for their numbers (the format), for the sport of their workout and for
  the equipment they need. The **name** is free text of the coach and is never read by a rule, so
  the `region` and the `equipment` are taken as the coach says them: "Barbell squat" with
  `bodyweight` is not caught. The sets, the repetitions and the RPE are not judged either. Nothing
  asks for exercises: an older or hand-changed workout may have none, and the legs rule then falls
  back to the strength focus. In the export the name is a comment line, never a step.
- The **time of day** is only an order (morning, afternoon, evening), not a clock time: two
  workouts on one day add up. The athlete can say which parts of the day are open on each weekday
  (`slot_outside_window`), but a workout without a time of day is not held to them, and the time
  you have is still given per day.
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
