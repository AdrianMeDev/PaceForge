# The season skeleton

The **skeleton** of a season is what the code works out before anyone asks a coach for anything:
the weeks from today up to the last A or B race, the **phase** of every week, which weeks are
recovery weeks and how many **minutes** to aim for in each. It is the frame the main plan will be
filled into (the stories call it "Gerüst"); the week plan does not read it yet.

It is worked out on every request from what the athlete has now, by pure functions
(`backend/season/skeleton.py`, no database, no Django) fed by `backend/season/inputs.py`, and it is
**not stored**. The numbers are product decisions, not coaching science; every one of them is a
constant and is in the tables below (a test keeps this page and the code in step).

## What it is made from

| Input | Where it comes from |
| ----- | ------------------- |
| The first week | The Monday of the week that today is in, in the time zone of the athlete. |
| The races | The **active** goals of the kind race with a date: A (`main`), B (`secondary`) and C (`preparation`). A goal of another kind has no day to work towards. |
| What each week offers | The minutes of the weekdays added up, an absence taken out, the weekly budget applied ([Training time](../README.md#training-time)). |
| The reference week | The higher of the average of the last four weeks of training and the normal week the athlete gave, the same reference as the progression rule of the checks. |
| The intensity level | `relaxed`, `normal` or `intensive`. It sets the ramp and the rhythm of the recovery weeks. |

## The weeks

The skeleton has one week for each week from the first week to the week of the **last A or B race**,
at most `MAX_WEEKS`. If the last race lies further away, the skeleton stops after `MAX_WEEKS` and
says so (`truncated`). With **no** A or B race there are `ROLLING_WEEKS` weeks of base and build and
no taper (`rolling`). C races only mark their week.

The **main race** is the A race; with none, the latest B race. The phases of the weeks up to it are
counted **back from it**:

1. The **taper** comes first and ends in the race week. Its length depends on the race.
2. The **specific** phase takes `SPECIFIC_SHARE` of the weeks before the taper (at least
   `SPECIFIC_MIN_WEEKS`, at most `SPECIFIC_MAX_WEEKS`). Its volume stays where it is.
3. The **build** takes `BUILD_SHARE` of them.
4. The **base** takes the rest.

So a short preparation loses its base first and never its taper. With fewer than
`MIN_WEEKS_FOR_BASE` weeks before the taper there is no base; with fewer than
`MIN_WEEKS_FOR_BUILD` there is only the specific phase. A stretch shorter than the taper is all taper.

### The taper by the race

| Discipline | Up to | Taper weeks | Up to | Taper weeks | Longer |
| ---------- | ----- | ----------- | ----- | ----------- | ------ |
| `running` | 10 000 m | 1 | 21 100 m | 2 | 3 |
| `cycling` | 100 000 m | 1 | 200 000 m | 2 | 3 |
| `triathlon` | 51 500 m | 1 | 113 000 m | 2 | 3 |

Swimming, a race without a distance and a discipline that is not known have one week.

### Other races

- A **B race before the main race** gets a mini taper: its week is `MINI_TAPER_PERCENT` of what it
  would be.
- After the main race, if a **B race follows**, comes one **transition** week (rest), then a build
  of its own up to that race, with the taper of that race. This repeats for every later B race. A
  race in the transition week itself only marks it.
- A **C race** is trained through: it is listed in its week and changes nothing else.

## The minutes

| Level | Ramp (percent a week) | A recovery week every |
| ----- | --------------------- | --------------------- |
| `relaxed` | 5 | 3rd week |
| `normal` | 8 | 4th week |
| `intensive` | 10 | 4th week |

- The first week is the **reference week** of the athlete. Without one it is half of what the first
  week with time offers (`START_SHARE_PERCENT`), at least `START_MINUTES_MIN` minutes.
- Every following week of the **base** and the **build** adds the ramp of the level to the week
  before. In the **specific** phase the volume stays. No week goes above the best week on offer.
- Every 3rd or 4th week of a stretch is a **recovery week** at `RECOVERY_PERCENT` of the volume
  reached. There is none in the taper and none right before it; the count starts again after a
  transition week. A week without time (an absence) builds nothing but counts for this rhythm.
- A **taper** week is a share of the last full week, by the length of the taper:

| Taper weeks | First week | Second | Third (the race week last) |
| ----------- | ---------- | ------ | -------------------------- |
| 1 | 50 % | | |
| 2 | 70 % | 45 % | |
| 3 | 80 % | 65 % | 45 % |

- The **transition** week is `TRANSITION_PERCENT` of the last full week; the build after it starts
  at `RESTART_PERCENT` of that level.
- Every week is capped by what it offers. A week without time has a target of 0.
- The **peak** is the highest target of all weeks.

## The limits

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `MAX_WEEKS` | 52 | Weeks of the longest skeleton. |
| `ROLLING_WEEKS` | 12 | Weeks of a skeleton without a race. |
| `SPECIFIC_SHARE` | 0.25 | Share of the weeks before the taper that the specific phase gets. |
| `BUILD_SHARE` | 0.35 | Share of the weeks before the taper that the build gets. |
| `SPECIFIC_MIN_WEEKS` | 2 | Fewest weeks of the specific phase. |
| `SPECIFIC_MAX_WEEKS` | 6 | Most weeks of the specific phase. |
| `MIN_WEEKS_FOR_BASE` | 6 | Weeks before the taper from which there is a base. |
| `MIN_WEEKS_FOR_BUILD` | 3 | Weeks before the taper from which there is a build. |
| `RECOVERY_PERCENT` | 65 | A recovery week in percent of the volume reached. |
| `MINI_TAPER_PERCENT` | 80 | The week of a B race before the main race, in percent. |
| `TRANSITION_PERCENT` | 50 | The week after the main race, in percent of the last full week. |
| `RESTART_PERCENT` | 80 | Where the build after the transition starts, in percent of that level. |
| `START_SHARE_PERCENT` | 50 | Without a reference week: the share of the first week on offer. |
| `START_MINUTES_MIN` | 60 | Without a reference week: the least the first week aims for. |

## The format of a filled season

The coach fills the skeleton by answering with one object (`season/schema.py`, read by one strict
parser that reports every problem by its path and never repeats a value of the answer). Only the
fields below exist; an unknown field is refused. A whole number is a JSON integer.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `weeks` | yes | A list of at most `MAX_WEEKS` weeks. |
| `rationale` | no | Why the season looks like this: up to `RATIONALE_MAX` characters, line breaks allowed. |

A **week**:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `week_start` | yes | The Monday of the week. Whether the weeks are those of the skeleton is a matter of the checks. |
| `minutes` | yes | An object: for any of `running`, `cycling`, `swimming` and `strength` the minutes of the week, 0 to `WEEK_MINUTES_MAX`. A sport that is left out has none. |
| `focus` | yes | What the week is about: `recovery`, `endurance`, `tempo`, `threshold`, `vo2max` or `race_specific`. |
| `reason` | yes | One line of 1 to `REASON_MAX` characters. |
| `key_sessions` | no | The sessions the week stands on: a list of at most `MAX_KEY_SESSIONS`. |

A **key session**:

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `sport` | yes | `running`, `cycling`, `swimming` or `strength`. |
| `kind` | yes | `long`, `tempo`, `threshold`, `vo2max`, `race_pace`, `strength` or `race`. |
| `minutes` | yes | 1 to `KEY_SESSION_MINUTES_MAX`. |
| `detail` | no | A few words of the coach ("3 x 10 min"): one line of up to `DETAIL_MAX` characters. Only ever shown as text. |

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `RATIONALE_MAX` | 1000 | Characters of the rationale of the season. |
| `REASON_MAX` | 300 | Characters of the reason of a week. |
| `DETAIL_MAX` | 60 | Characters of the detail of a key session. |
| `MAX_KEY_SESSIONS` | 3 | Key sessions of a week. |
| `WEEK_MINUTES_MAX` | 10080 | Minutes of one sport in a week: all of them. |
| `KEY_SESSION_MINUTES_MAX` | 1440 | Minutes of a key session: a day. |

## What the coach is told

The coach gets a **briefing** (`season/briefing.py`): a fixed set of keys, as JSON, built from the
skeleton and from the briefing of the [week plan](weekly-plan.md#what-the-coach-is-told), so the
sports, the facts, the best times and the limitations are told in the same words and under the
same rules as there. A test fails if a key is added without being listed here.

| Key | What it holds |
| --- | ------------- |
| `today` | The day it is for the athlete. |
| `rolling`, `truncated` | There is no race to work towards (twelve weeks of base and build), or the last race lies beyond a year and the skeleton stops. |
| `peak_minutes` | The highest target of all weeks. |
| `weeks` | The skeleton: for every week `week_start`, `phase`, `recovery`, `target_minutes`, `capacity_minutes` and `race_dates`. |
| `races`, `races_not_shown` | The races in the weeks, by day, at most `MAX_RACES_TOLD`: `date`, `priority`, `discipline`, `distance_m` and the `title`, cut to `RACE_TITLE_TOLD_MAX` characters. The title is the athlete's own text and is data, never instructions. |
| `sports`, `sport_preferences`, `strength_focus` | As in the week plan. |
| `athlete`, `best_times`, `vdot` | As in the week plan: the age (never the birth year), the facts of the athlete, the running form. |
| `limits`, `limitations`, `limitations_not_shown` | As in the week plan: the limits of the intensity level and the current limitations (body part and sports, no text). |
| `typical_weekly_minutes`, `recent_weeks_minutes`, `weekly_budget_minutes` | The normal week, the recent weeks and the weekly budget. |

What is **never** sent: the name, the e-mail address, ids, the notes of goals, the activities, the
free text about limitations and anything of other users.

The system prompt is the same for every athlete: it names the format and the checks with their
constants and says how to read the phases. The answer may take `SEASON_MAX_TOKENS` tokens; one
that is cut off is not used.

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `MAX_RACES_TOLD` | 20 | Races told to the coach, the earliest first; the rest is counted. |
| `RACE_TITLE_TOLD_MAX` | 60 | Characters of the title of a race that are told. |
| `MAX_BYTES` | 24000 | The most the JSON of a briefing may take (UTF-8, every free-text character at six bytes). A test builds the worst case. |
| `SEASON_MAX_TOKENS` | 16000 | The most the coach may write for a season. |

## The checks

The coach may ignore the skeleton it is given, so every filled season is checked by code
(`season/rules.py`). A finding has a stable `code`, a `path` into the plan and a fixed text made
from numbers, dates and the words of the format; nothing the coach wrote is repeated in one. An
**error** makes the plan unfit to confirm, a **warning** is for the athlete to weigh. The
findings and the report are those of the [week plan](weekly-plan.md).

| Code | Severity | What it says |
| ---- | -------- | ------------ |
| `weeks_mismatch` | error | The plan does not have exactly the weeks of the skeleton, in its order: once for the number of weeks (at `weeks`) and once at the first week that is not the one asked for. |
| `sport_not_selected` | error | A week has minutes in a sport that the athlete did not choose. Once per sport and week, at the minutes of that sport. |
| `minutes_outside_target` | error | The minutes of all sports of a week add up to less or more than the target of the skeleton allows (`WINDOW_PERCENT` percent either way). A week with a target of 0 has no minutes. |
| `minutes_above_capacity` | error | A week has more minutes than it offers (an absence offers nothing, the weekly budget caps it). |
| `key_session_sport_missing` | error | A key session in a sport that has no minutes that week. At the session. |
| `key_sessions_too_long` | error | The key sessions of one sport add up to more than the minutes of that sport in the week. Once per sport and week. |
| `race_week_without_race` | warning | A week with a race (of any priority) has no key session of the kind `race`. |

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `WINDOW_PERCENT` | 10 | How far the minutes of a week may differ from its target, in percent, either way (rounded towards the target). |

## The API

`GET /api/season/` answers the skeleton of the signed-in user and writes nothing. The answer has
`rolling`, `truncated`, `main_race` (or `null`), `peak_minutes` and `weeks`. A **week** has
`week_start` (a Monday), `phase` (`base`, `build`, `specific`, `taper` or `transition`), `recovery`,
`target_minutes`, `capacity_minutes` and `races`. A **race** has `date`, `priority` (`main`,
`secondary` or `preparation`), `discipline`, `distance_m` and `title` (the athlete's own text).

## Not there yet

The skeleton knows minutes only: no load, no split by sport, no key sessions, no reason for a week.
Those come when the coach fills the weeks. The week plan does not read it, there is no timeline or
chart, nothing is stored or confirmed, and the realism check of a goal time (US-4.2) is not part
of it.
