# Background jobs

PaceForge does three things on its own, for every athlete on the instance, without anyone
pressing a button:

1. **Sync activities** (`sync`) pulls new activities and daily wellness from Intervals.icu.
2. **Week review** (`week_review`) lets the coach comment on the week that is ending.
3. **Draft next week** (`week_draft`) lets the coach draft the week after the current one.

The jobs are management commands that run in one scheduler container. There is no broker: one
small instance needs nothing but the database. The three jobs run for one athlete in this order:
**sync**, then **week review**, then **week draft**. The draft runs after the review so the
comment's `next_week` reaches the briefing. The draft command also syncs first, unless the sync job
is turned off.

Every job is scoped to its athlete. It uses the athlete's own Intervals.icu key and their own AI
coach, so no one else's data is read or written. A job **never confirms** a plan and **never
pushes** to Intervals.icu. The draft stays a draft, whatever the rules say about it; only the
athlete confirms, and only a confirmed plan is sent to Intervals.icu.

## When the jobs run

The scheduler (`run_scheduler`) loops over every active account, ordered by `pk`, and runs what is
due. Between rounds it sleeps `JOBS_INTERVAL_MINUTES`.

- The **sync** is due when the last `done` sync is at least `JOBS_SYNC_HOURS` old. It does not
  sync more often than that, so a busy instance does not hammer Intervals.icu.
- The **review** and the **draft** are due on the athlete's local Sunday from `JOBS_SUNDAY_HOUR`
  o'clock until the end of that day. The time of day is the athlete's own: it comes from their
  profile time zone, so two athletes in different time zones get their Sunday jobs at their own
  Sunday evening.
- A weekly job runs **once** for a week: a `done` or `skipped` run settles the week, and after
  `MAX_FAILED_TRIES` (3) failed attempts it stops being tried again. This caps the cost of a week
  that keeps failing.
- A job the athlete turned off is never due. A due draft brings a sync with it, so the draft sees
  the latest activities and daily wellness.

## Turning the jobs off

Every athlete has three switches on the **Automation** page (under **Settings** in the
navigation): **Sync activities**, **Week review** and **Draft next week**. All three are **on by
default**; a new account without any settings row counts as "all on". Turning a job off only stops
it from starting: it never undoes anything the job already did.

An operator can turn the whole scheduler off in development by not starting the `scheduler`
profile, or by stopping its container (name the service, or the whole stack stops):

```bash
docker compose -f compose.dev.yaml --profile scheduler up -d scheduler   # start it
docker compose -f compose.dev.yaml --profile scheduler stop scheduler    # stop it
docker compose -f compose.dev.yaml --profile scheduler rm -sf scheduler  # stop and remove it
```

## The log

Every attempt is one row in the job log, shown on the **Automation** page (the newest 50 runs).
Each row has a fixed outcome and, when a run did not simply succeed, a fixed code. Neither the log
nor any output of the commands ever holds a word from the coach or from Intervals.icu; the
`counts` are numbers only.

| Code | Meaning |
| ---- | ------- |
| `not_connected` | No Intervals.icu connection |
| `invalid_key` | The Intervals.icu key was refused |
| `intervals_unavailable` | Intervals.icu did not answer |
| `no_coach` | No coach configured |
| `provider_error` | The coach did not answer |
| `plan_not_usable` | The plan did not pass the checks |
| `comment_not_usable` | The comment was not usable |
| `no_time` | No training time known |
| `nothing_to_review` | Nothing to review |
| `already_planned` | Next week is already planned |
| `unexpected` | Unexpected error |

A run that simply succeeded has an empty code; the table lists the codes that explain a `skipped`
or `failed` run. The same fixed sentences are shown on the Automation page, so the athlete never
sees text from a coach answer.

## Settings

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `JOBS_SYNC_HOURS` | `6` | Hours between two syncs of the scheduler (whole number from 1 to 24). |
| `JOBS_SUNDAY_HOUR` | `18` | Hour on Sunday, in the athlete's time zone, from which the review and the draft run (0 to 23). |
| `JOBS_INTERVAL_MINUTES` | `15` | Minutes the scheduler sleeps between two rounds (whole number from 1 to 60). |

A value outside its range stops Django at startup.

## Running the jobs by hand

The scheduler can also run one round, and each job has its own command. All of them print counts
only, never personal data.

```bash
# One scheduler round (due jobs only), on the real clock or a fixed one:
uv run python manage.py run_scheduler --once
uv run python manage.py run_scheduler --once --now 2026-11-22T18:30:00+01:00

# Each job for every active account, or one account only with --email:
uv run python manage.py sync_activities
uv run python manage.py review_weeks
uv run python manage.py draft_next_week
```

`--now` is only for trying the scheduler out; it is not for normal runs.

## Development

The scheduler runs in a separate Compose service under the `scheduler` profile, so the documented
`docker compose -f compose.dev.yaml up -d db mailpit` is unchanged. The service mounts the
repository, points `DATABASE_URL` at the `db` service and runs `uv run python manage.py
run_scheduler`. It shares the database with the Django server you run locally.
