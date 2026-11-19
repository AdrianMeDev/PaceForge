# How realistic a goal is

For every active goal that has a target, PaceForge says whether the target is **realistic**,
**ambitious** or **unrealistic**, suggests a target that can be reached by the date, and warns when
the time left is short for the distance (US-4.2). It is worked out by pure functions
(`backend/goals/realism.py`, no database, no Django) fed by `backend/goals/assessing.py`, on every
request, and it is **not stored**. It is a hint: the target of the athlete is never changed, and
the coach is told the judgement, not bound by it.

The numbers are product decisions, not coaching science. Every one of them is a constant in the
tables below (a test keeps this page and the code in step); they are easy to change once there is
experience with them.

## What is judged

| Goal | Judged against | How |
| ---- | -------------- | --- |
| A running race with a distance and a target time | The VDOT of the best time that counts ([athlete profile](../README.md#athlete-profile)) | The VDOT the target time is worth over that distance, against the form plus what it can grow by until the date |
| A threshold goal (FTP or threshold pace) | The value that counts now, from whichever source holds it | The target against the value plus what it can grow by until the date; a pace is judged on the speed |
| Anything else | – | `unknown`, with a reason |

A goal that is not active, and a general goal, has no judgement (`assessment` is `null`).

## The judgement

The form grows by a fixed amount for every whole week until the date, up to a maximum. A target
that asks for no more than the form can reach by then is **realistic** (a target slower than the form
is too); one that asks for up to the extra amount more is **ambitious**; anything more is
**unrealistic**. The **suggested** target is what the form can reach by the date, and the
athlete's own target if that is realistic already. Two numbers closer than a billionth are the same,
so that a rounding error never turns a realistic target into an ambitious one.

| Constant | Value | Meaning |
| -------- | ----- | ------- |
| `VDOT_GAIN_PER_WEEK` | 0.2 | VDOT that a runner can gain for every week until the race. |
| `VDOT_GAIN_MAX` | 5 | The most VDOT that counts as a gain, however far away the race is. |
| `AMBITIOUS_EXTRA_VDOT` | 2 | VDOT above what can be reached that is still ambitious. |
| `THRESHOLD_GAIN_PERCENT_PER_WEEK` | 0.5 | Percent of FTP, or of the speed of the threshold pace, gained per week. |
| `THRESHOLD_GAIN_MAX_PERCENT` | 15 | The most percent that counts as a gain. |
| `AMBITIOUS_EXTRA_PERCENT` | 5 | Percentage points above what can be reached that are still ambitious. |
| `MODEL_MIN_M` | 1500 | The shortest race that is judged, in metres. |
| `MODEL_MAX_M` | 42195 | The longest race that is judged, in metres. |

VDOT is a model of a good race and fits distances from 1.5 km to the marathon; a race outside is
not judged (`out_of_range`). The suggested time is worked out with `athletes.vdot.race_seconds`,
the inverse of the VDOT of a time.

## A short preparation

A running race warns (`prep_short`) when fewer whole weeks are left than its distance asks for.
This is said with or without a target time.

| Distance up to | Weeks |
| -------------- | ----- |
| 5 km | 4 |
| 10 km | 6 |
| Half marathon | 10 |
| Marathon | 16 |

## What cannot be judged

`rating` is `unknown` and `reason` says why. A reason belongs to `unknown` and to nothing else.

| Reason | When |
| ------ | ---- |
| `no_model` | Another discipline (cycling, swimming, triathlon) or a goal without a target to judge. |
| `no_target` | A race without a distance or a target time, or a threshold goal without a value. |
| `out_of_range` | A race over a distance that VDOT does not describe. |
| `no_date` | No date, or a date that has passed. |
| `no_form` | No best time that counts (less than a year old), or no value to start from. |

## Where it is shown

- **Goals page:** every active goal has a badge, a sentence, the numbers behind it, the suggested
  target and the warning for a short preparation. **Edit** a goal and the form offers *Use it* next
  to the time or the value: it only fills the field, nothing is saved until you save, and your own
  target is yours to keep. When a confirmed [season plan](season.md#changes-from-the-confirmed-plan)
  needs attention, the page also shows a read-only adjustment notice that refreshes after saving,
  changing status or priority, or deleting a goal, and links to that confirmed version's **Ask for
  a change** form. Missing plans and unchanged inputs show no hint, and status failures leave
  normal goal editing usable.
- **API:** `GET /api/goals/` and the other goal endpoints give every goal an `assessment` (`rating`,
  `reason`, `current`, `needed`, `suggested`, `weeks`, `prep_short`, `prep_weeks`). `current` and
  `needed` are VDOT for a race, watts for FTP and seconds per kilometre for the pace; `suggested`
  is seconds for a race. Writing a goal ignores it. The queries of a list do not grow with the
  number of goals.
- **The coach:** every goal in the briefing of the [week plan](weekly-plan.md#what-the-coach-is-told)
  and every race in the briefing of the [season](season.md#what-the-coach-is-told) carries the same
  `assessment`; the system prompt says to plan towards the athlete's own target and to plan
  carefully, without promises, when it is unrealistic or the preparation is short.

## Not there yet

Cycling, swimming and triathlon races are not judged, and neither is a race from FTP or from a
power model. The bands are the same for every athlete: age, years of training and the intensity
level are not taken into account. The goals are not judged against the time the athlete has to
train, and nothing is stored, so there is no history of how a target was rated.
