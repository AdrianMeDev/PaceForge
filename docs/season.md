# The season skeleton

The **skeleton** of a season is what the code works out before anyone asks a coach for anything:
the weeks from today up to the last A or B race, the **phase** of every week, which weeks are
recovery weeks and how many **minutes** to aim for in each. It is the frame the main plan will be
filled into (the stories call it "Gerüst"); the week plan follows the confirmed plan that was made
from it (see below).

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
| `races`, `races_not_shown` | The races in the weeks, by day, at most `MAX_RACES_TOLD`: `date`, `priority`, `discipline`, `distance_m` and the `title`, cut to `RACE_TITLE_TOLD_MAX` characters. The title is the athlete's own text and is data, never instructions. Each race has an `assessment` as the goals of the week plan do (`null` without a goal on that day with that priority): whether its target time is realistic. |
| `sports`, `sport_preferences`, `strength_focus` | As in the week plan. |
| `athlete`, `best_times`, `vdot` | As in the week plan: the age (never the birth year), the facts of the athlete, the running form. |
| `limits`, `limitations`, `limitations_not_shown` | As in the week plan: the limits of the intensity level and the current limitations (body part and sports, no text). |
| `typical_weekly_minutes`, `recent_weeks_minutes`, `weekly_budget_minutes` | The normal week, the recent weeks and the weekly budget. |

**A change request** (a version that is made from another on the athlete's wish) is told with the
current briefing, including current sports, and two more keys: `current_plan`
(the old season for comparison, in the format of the answer) and `change_request` (the wish, a JSON
string). The system prompt is the same: it says that then the season is not filled from scratch,
that the answer has exactly the current briefing's weeks in order, and that unaffected overlapping
weeks should stay as they are where they still fit. Every rule still applies. The wish is data
and never an instruction about the rules, the format or the task. Like a title of a race it is a
request to the model, not a guarantee; what
it cannot do is get a plan past the parser and the checks.

What is **never** sent: the name, the e-mail address, ids, the notes of goals, the activities, the
free text about limitations and anything of other users.

The system prompt is the same for every athlete: it names the format and the checks with their
constants and says how to read the phases. The answer may take `SEASON_MAX_TOKENS` tokens; one
that is cut off is not used. The prompt holds no date, no name and no number of the moment, so
that Anthropic's [prompt cache](../README.md#ai-coach-bring-your-own-key) can read it; a test keeps
it that way.

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `MAX_RACES_TOLD` | 20 | Races told to the coach, the earliest first; the rest is counted. |
| `RACE_TITLE_TOLD_MAX` | 60 | Characters of the title of a race that are told. |
| `MAX_BYTES` | 24000 | The most the JSON of a briefing may take (UTF-8, every free-text character at six bytes). A test builds the worst case. |
| `SEASON_MAX_TOKENS` | 16000 | The most the coach may write for a season. |
| `CHANGE_MAX_BYTES` | 200000 | The most the message that asks for a change may take (UTF-8, a year of weeks at every limit, four bytes to a character, the longest wish). A test builds the worst case. |

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

## The filled plans

`season/generation.py` asks the coach (`Purpose.SEASON_PLAN`, the season model if the athlete gave
one), reads the answer with the strict parser, checks it against the skeleton and stores the best
plan as a draft:

- **Answers.** One answer and up to `ATTEMPTS` in all. If an answer cannot be read, was cut off or
  has errors, the coach is told the problems (fixed texts, the message of the week plan) and may
  try again. The plan with the fewest errors wins, a tie goes to the later answer; an unreadable
  later answer or a provider that fails later does not lose a readable plan.
- **Nothing to fill.** If no week offers any time, nothing is asked and nothing is paid
  (`no_time`).
- **Stored with its frame.** A version (`SeasonPlanVersion`) holds the weeks, the rationale, the
  skeleton and the sports it was made for. It is read back through the parser again and checked
  against **its own** skeleton, not the one of today.
- **Original inputs.** Before asking the coach, generation collects a versioned `input_snapshot`:
  active goals in id order, effective cycling FTP, best times in distance order and typical
  weekly minutes. Goal and race dates are included; notes and creation or update timestamps are
  excluded. FTP stores only the effective number. Best times keep their distance, seconds and
  race date without a moving age window. Missing FTP and typical minutes are `null`; missing
  goals and best times are empty lists. Confirmation keeps this snapshot. Restore requests copy
  the original snapshot, including `null` when unknown. Change requests capture current inputs
  before the first provider call and keep them across repair rounds. Changes during the call
  remain detectable after confirmation against that captured baseline. Confirmed snapshots are
  immutable with the plan content. Legacy versions stay readable with `input_snapshot: null`.
- **Status.** `draft`, `confirmed`, `superseded` or `discarded`; at most one confirmed plan per
  user. Confirming a draft with errors is refused. The content of a plan that is not a draft is
  never changed.
- **Changing on request.** `change` asks the coach to change a `confirmed` version or a draft as
  the athlete wishes (`request`, at most `REQUEST_MAX` characters, plain text with line breaks,
  checked before anything is sent) and stores the answer as the next version, a draft: `parent` the
  version it comes from, the reason `Changed on request from version N`, the wish in `request`, and
  **the current skeleton, sports and captured inputs**. The old plan is comparison data in
  `current_plan`. The briefing's current weeks, race dates, targets, capacities and sports take
  precedence. The coach must return exactly those weeks in order, adding new weeks and omitting
  old weeks outside the current frame. It preserves unaffected overlapping weeks where they
  still fit the current frame and rules. No current capacity returns `no_time` before any
  provider call. It asks like drafting (the same loop, up to `ATTEMPTS` answers, the best wins)
  and refuses a version that was replaced or discarded
  (`PlanNotChangeable`). An answer equal to the old plan with the same frame and input snapshot
  is not stored (`PlanUnchanged`). A changed frame or input baseline permits a new draft even
  with identical content. The calls count as usage all the same. The old version is not touched.
  The Season page compares the new
  version with its `parent` (`compareSeasons`, a pure function): minutes of each sport, the total,
  the focus, key sessions added and dropped and the reason, week by week, and the rationale.
  The comparison also lists calendar weeks added to or removed from the frame. The table,
  timeline and chart show the new draft's stored frame.
- **Restoring.** `restore` brings back a `superseded` or `discarded` version as the next version, a
  draft: the same weeks and rationale, **its own skeleton and sports** (not today's), `parent` the
  version it comes from and the reason `Restored from version N`. The old version is not touched,
  the confirmed one stays confirmed until the copy is, and a draft or the confirmed version is
  refused (`PlanNotRestorable`). No coach is asked.

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `ATTEMPTS` | 3 | Answers of the coach for one season: one try and two repairs. |
| `REQUEST_MAX` | 500 | Characters of a change request. |

## Changes from the confirmed plan

The Season, Goals, Profile and Week review pages show an adjustment notice when the confirmed plan
needs attention. On **Goals**, it reloads right after saving, changing status or priority, or
deleting a goal. On **Profile**, it reloads after threshold saves, switching back to an automatic
value, Intervals.icu sync (including automatic sync on open) and best-time changes. On **Week
review**, it also lists the three formatted evidence weeks when `training_deviation` applies and
reloads after switching weeks, saving a workout correction, rating a session or refreshing the
week list. Missing plans and unchanged inputs show no hint, and status failures leave normal
editing and review usable. Follow **Ask for a change to confirmed version N** to open that
version's **Ask for a change** form. A link from another page works the same way. It selects the
named confirmed version even if a draft or an older version was open. After loading, the request
field gets focus. A link to a version that is no longer confirmed shows a message. Opening the
form makes no coach call.

Write your request and submit it to create a draft against the current weeks and inputs.
Read the comparison, including added and removed weeks, before confirming it yourself.
Drafting, provider failure and discard leave the notice in place. Successful confirmation
reloads the status. It hides the notice only when the confirmed replacement fits current inputs.
If no current week offers training time, the form links to Training time and keeps your text
for another attempt.

`season/reassessment.py` compares current inputs with the confirmed version's original
`input_snapshot` and the capacities in its stored skeleton. The baseline belongs to drafting,
not confirmation. Only the signed-in user's confirmed version and inputs count.

The endpoint returns a list of stable reason codes in this order, with each code at most once.
The reasons contain no goal titles, notes, input values or other user text.

| Code | Meaning |
| ---- | ------- |
| `baseline_unknown` | The original inputs are unknown. Legacy versions have a null snapshot. An incomplete snapshot or an unsupported snapshot version also counts as unknown. This is the only reason returned in that case. Historical inputs are never guessed. |
| `goals_changed` | Active goals were added, removed or edited. Meaningful fields are id, kind, title, priority, target date, discipline, distance, target time, metric and target value. Achieving or dropping an active goal removes it from the comparison; activating one adds it. Notes, bookkeeping timestamps and edits to inactive goals do not count. |
| `ftp_changed` | The effective cycling FTP number changed, including adding or removing it. The existing source priority applies. Changing an overridden source, its metadata or its source without changing the effective number does not count. |
| `best_times_changed` | Stored best times changed by distance, seconds or race date, including additions and removals. Update timestamps and moving age windows do not count. |
| `training_time_changed` | Typical weekly minutes or at least one remaining calendar week's capacity changed by both thresholds below. Capacity includes weekday minutes, absences and the weekly budget. |
| `training_deviation` | Each of the latest three completed local weeks has actual minutes below 70% or above 130% of its confirmed weekly planned minutes. The three evidence Mondays are returned in `deviation_weeks`. |

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `TIME_CHANGE_PERCENT` | 20 | Minimum absolute change as a percentage of the original minutes. |
| `TIME_CHANGE_MINUTES` | 60 | Minimum absolute change in minutes. Both thresholds must be met. |

The thresholds include their boundaries and apply to increases and decreases. From zero, a
change needs at least 60 minutes. Unspecified typical minutes count as zero for this comparison.
Capacity is compared on the same calendar dates in the stored skeleton. Remaining weeks include
the full current Monday-to-Sunday week in the athlete's time zone. Completed weeks and dates
outside the original season do not count. Moving into a new week alone never creates a reason.
Saving identical values does not count. Several changed weeks still give one time reason.

Reading, drafting, restoring or discarding never acknowledges a hint. Each read compares with the
confirmed version again. Confirming a current replacement clears the reasons. Confirming an
outdated replacement retains the differences from its original inputs and capacities. A legacy
hint lasts until a replacement with known, current inputs is confirmed. No plan content changes.

`season/deviation.py` uses the same user-scoped `reviews.services.week_summary` as the week
review. It checks only the latest three completed Monday-to-Sunday weeks in the athlete's time
zone. It never searches older weeks for a streak. All three weeks must be in the confirmed
season's stored skeleton and start at or after its confirmation instant. A week that contains
the confirmation is excluded unless confirmation was exactly at its local Monday midnight.
The current, unfinished week never counts.

Each week's actual duration must be strictly below 70% or strictly above 130% of its confirmed
weekly workout minutes. The direction can differ between weeks. Exactly 70% and 130% do not
count. Duration uses timer seconds, falling back to elapsed seconds only when timer time is
missing. The comparison keeps sub-minute precision. All activities count, including unmatched
activities and other sports. A week without activities has zero actual minutes. A missing
confirmed weekly plan, zero planned minutes, a week inside the bounds or any activity with
unknown duration breaks the sequence. Another athlete's training never contributes.

`deviation_weeks` contains the three evidence Mondays as ISO dates, oldest first, only when
`training_deviation` is returned. Otherwise it is empty. A new season confirmation resets the
eligible window, including when restoring old content. Three new full weeks must finish before
another proposal can appear. Reading, drafting, restoring or discarding alone does not reset it.
The reason is a proposal only. It never drafts, confirms or exports training automatically.

### Athlete walkthrough

1. **Input change (A race moved):** Edit an active A race date on **Goals** (or update FTP or best
   times on **Profile**). The adjustment notice appears immediately without touching the confirmed
   season.
2. **Repeated deviation (three weak weeks):** After three consecutive completed local weeks below
   70% or above 130% of confirmed planned minutes, open **Week review**. The notice explains the
   deviation and lists the three evidence weeks.
3. **Open the change form:** Follow **Ask for a change to confirmed version N**. PaceForge opens
   that confirmed version on **Season** and focuses the request box without calling the coach.
4. **Draft and review:** Submit your change request. The coach drafts a new version against the
   current skeleton, race dates, capacities and sports while comparing against the old plan.
   Drafting or discarding keeps the notice in place.
5. **Confirm explicitly:** Inspect the week-by-week comparison (including added and removed weeks)
   and confirm the draft yourself. Confirmation supersedes the previous version, clears hints
   covered by the new baseline and resets the three-week deviation window.

### Acceptance checklist

- Moving an A race date shows `goals_changed` on Goals and Season until a current replacement is
  confirmed; discarding or leaving a draft unconfirmed keeps the hint, and confirming an outdated
  draft retains hints for later changes.
- Effective FTP changes, best-time changes and qualifying training-time changes show the matching
  reasons; identical saves, inactive goals, overridden FTP candidates and week rollover do not.
- Three consecutive completed local weeks strictly below 70% or above 130% of confirmed weekly
  planned minutes show `training_deviation` and the three evidence weeks in Week review; two weeks,
  an interrupted streak, an unfinished week, missing plans, zero planned minutes or unknown
  durations do not.
- Following the notice opens **Ask for a change** for the named confirmed version without making
  any AI call; only explicit submission drafts and only explicit confirmation changes the season.
- `GET /api/season/reassessment/` is authenticated, read-only, user-scoped and isolated across
  users, with no external AI or Intervals.icu calls.

## The week plan follows the season

`season/weeks.py` gives the week plan the week it is about: `confirmed_weeks` reads the
**confirmed** plan of the user (never a draft, a replaced or a discarded one) with one query and
returns, for each Monday that lies in the skeleton **that plan was made for**, the facts of the
week: the phase, recovery, the minutes the skeleton aims for and the week offers, the races, and
what the coach filled in. A plan that cannot be read counts as no season week, so planning a week
never fails because of it.

What the week plan does with it is in [the weekly plan](weekly-plan.md): the coach is told the week
(`season_week`), three checks warn (`season_minutes_off`, `season_sport_missing`,
`season_key_session_missing`, warnings only) and `GET /api/planning/weeks/` gives every week its
`season`. The text of the coach in it (`reason`, `detail`) goes back to the coach as data, and only
ever to the page as text.

## The timeline, the chart and the minutes done

The Season page draws the skeleton it shows (the one of the open version, else today's) as a
**timeline** (one cell a week: phase colour and two letters, `R` for a recovery week, the letter of
each race, the current week outlined) and as a **chart** of stacked bars with a **Minutes** /
**Load** toggle (the plan's minutes or `planned_load` by sport, else the aim of the skeleton in
minutes mode), with hours or load points on a round axis of at most six steps. For the confirmed
plan, begun weeks show a narrower bar beside the plan for `done` minutes or `done_load`. The
geometry is in pure functions (`timelineCells`, `chartLayout`) that the specs test; the SVG is
drawn by hand without a library.

`timelineCells` takes the live season's `absences` and marks **illness** only. `illnessDays` of a
cell is how many of that week's seven days lie inside at least one illness period (0 if none). A
cell with a mark carries `data-illness="true"`, an `Ill` badge and, in its label and tooltip,
`Illness, 1 day` or `Illness, 3 days` after the phase. Vacation and other absences leave the cell
unmarked. The Season page passes the live season's absences, also while a stored version's week is
shown (a stored skeleton has none).

`season/done.py` counts the minutes done for the chart. `done_minutes(user, mondays)` adds up the
activities of each calendar week (Monday to Sunday) in the **time zone of the athlete**, by sport
(`other` for any sport the plan does not have), the timer time and else the elapsed time, an
activity with neither not at all; it adds the seconds first and rounds the minutes half up. It takes
two queries, the time zone and the activities, however many weeks. `plan_detail` gives it only to the
**confirmed** version and only for the weeks that have begun (the current one with what is done so
far); every other week and version has `done: null`.

`done_week_totals(user, mondays)` returns both minutes and load in the same two queries. The
season API uses it; the dashboard keeps using `done_minutes`. Load adds the rounded load of
each activity, preferring Intervals `training_load`, else duration and RPE on the unified scale.
Unknown load adds zero. A load can count even when the activity has no duration.

`season/load.py` estimates planned load with one user-scoped query for all weeks. A confirmed
weekly plan supplies its workout estimates from `planning.load`, including zones, segments and
strength exercise RPE. It replaces the whole season estimate for that week. An empty confirmed
week has zero load. Draft, replaced and discarded weekly plans do not contribute.

Without a confirmed weekly plan, key sessions consume the season's sport minutes at the matching
goal rate from `planning.load`. Long sessions and remaining endurance minutes use the endurance
rate. Race pace and race sessions use the threshold rate. Strength uses the default strength RPE.
Each sport rounds half up once. In invalid drafts, key sessions are capped to the remaining sport
minutes and sessions in absent sports add nothing. Load is read-only; checks still use minutes.

## The API

`GET /api/season/reassessment/` requires authentication and returns `confirmed_plan_id` (the
confirmed version's UUID string, or `null`), `reasons` (the codes above) and `deviation_weeks`
(the three evidence Mondays as ISO dates, oldest first, or `[]` without `training_deviation`).
Without a confirmed plan both lists are empty, even if drafts exist.
The endpoint has no user or plan selector. It writes nothing and makes no coach or Intervals.icu
call. Write methods are refused. Reading it repeatedly never clears a reason.

The shared frontend `SeasonChangeNotice` validates the response through `SeasonApi.reassessment()`.
It explains each input change or training deviation and hides when no reasons exist. It exposes
the active `deviationWeeks` and projects optional page context (such as Week review's evidence
weeks) inside the notice. It reads the version list to name the matching confirmed version in a
link to `/season?change=<id>#season-change`. If that version is no longer confirmed, status is
unavailable and Retry reads it again. Other status failures also offer Retry. An expired session
shows a sign-in link. Parents can call `reload()` after a change. Reloading clears the old notice
and ignores late results from earlier reads or a destroyed component. No load drafts or confirms a
plan.

`GET /api/season/` answers the skeleton of the signed-in user and writes nothing. The filled plans are at `/api/season/plans/`: `GET` lists the versions (`id`, `version`, `status`, `reason`, `week_count`, `created_at`, `confirmed_at`), `POST generate/` drafts one (`201` with the plan, limited to 3 a minute), `GET <id>/` reads one and `POST <id>/confirm/` and `POST <id>/discard/` decide on a draft and `POST <id>/change/` with `{"request": "…"}` asks the coach to change a version as the athlete wishes (`201` with the new draft; `400` with the messages of the field `request`; `404`; `409` `not_changeable`, `no_time` or `not_configured`; `422` `unchanged` or `not_usable`; the codes of the provider; limited to 3 a minute together with drafting), and `POST <id>/restore/` brings back a replaced or discarded version as a new draft (`201` with the plan; `409` `not_restorable` for any other). A plan has `rationale`, `parent`, the `skeleton` it was made for, its `weeks` (the format with a `total_minutes` and `done`: for the **confirmed** version and the weeks that have begun the minutes the athlete trained by sport, `[{sport, minutes}]`, `other` for activities of no sport of the plan, `[]` for a week without any; `null` for every other week and version) and, for a draft, a `report` of `valid` and `findings`. Errors have a fixed text, a `code` and, where it helps, `problems` or `findings`. The answer has
`rolling`, `truncated`, `main_race` (or `null`), `peak_minutes`, `weeks` and `absences`. A
**week** has `week_start` (a Monday), `phase` (`base`, `build`, `specific`, `taper` or
`transition`), `recovery`, `target_minutes`, `capacity_minutes` and `races`. A **race** has `date`,
`priority` (`main`, `secondary` or `preparation`), `discipline`, `distance_m` and `title` (the
athlete's own text). `absences` are the user's own periods that overlap the weeks of the skeleton,
by start date: `kind` (`illness`, `vacation` or `other`), `start_date` and `end_date`, both
included. All three kinds are listed; the answer never says which week they touch, the client
works that out. One query reads them, scoped to the user (`season/absences.py`); another user's
periods are never in the answer. An **illness** can come from the chat: `mark_sick` stores it with
`availability.absences.note_illness`, which extends an overlapping or adjacent illness instead of
adding a second one, so the season shows one period for one illness. A longer absence can come from the chat too:
`replan_from` stores it with `availability.absences.note_absence` (kind `vacation` or `other`,
7 to 120 days, merged only with touching or overlapping periods of the same kind) and asks for a
season draft around it (`season.generation.change`, parent the newest draft or confirmed version,
request written by the code), which the athlete confirms or discards here. The draft is stored
before anything is confirmed, and the chat answer that made it links to this page. If the user has
no season version, only the absence is stored; if the season change fails, the absence stays and
the chat answer says so. The chat never confirms a season or pushes anything. The note of a period is never
part of the answer, and the stored skeleton of a plan stays as it was: the absences are only told,
never kept with a version.

Each filled week also has `planned_load`, a sport-to-load object like its `minutes`, and
`total_planned_load`, the sum of that object's values. `done_load` follows the same availability
as `done`: `[{sport, load}]` for begun weeks of the confirmed season, `null` otherwise. Only
positive done sport totals are listed. A week without known positive load has `done_load: []`.

## Not there yet

The skeleton itself knows minutes only. The coach adds the split by sport, the key sessions and the
reasons, and the Season page shows, drafts, confirms and discards them, with a timeline and a chart
for minutes and load. Whether a goal time is realistic is judged separately (see
[goals](goals.md)); the coach is told it with every race.
