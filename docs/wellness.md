# Wellness and readiness

PaceForge syncs four daily wellness metrics from Intervals.icu, shows their 7-day trend on the
dashboard, and passes a short summary to the AI coach in the week plan and chat briefings.

## Synced fields and ranges

When you sync from Intervals.icu (**Sync from Intervals.icu** on the Activities page, or the
`sync` background job), PaceForge calls `GET /athlete/0/wellness?oldest=YYYY-MM-DD&newest=YYYY-MM-DD`
for the last `INTERVALS_SYNC_WEEKS` weeks (default `12`) up to `today` in your profile time zone.

Only the calendar date and four numeric metrics are kept; every other field in the Intervals.icu
response is discarded. A day where all four metrics are missing is not stored.

| Intervals.icu field | PaceForge field | Unit | Client parse range | Database constraint |
| --- | --- | --- | --- | --- |
| `id` (`YYYY-MM-DD`) | `day` | Calendar date | `YYYY-MM-DD` | Unique per `(owner, day)` |
| `sleepSecs` | `sleep_minutes` | Minutes (rounded) | `> 0` to `86400` s | `1` to `1440` |
| `hrv` | `hrv` | ms (rMSSD) | `> 0` to `500.0` | `1` to `300` |
| `restingHR` | `resting_hr` | bpm (whole number) | `20` to `300` | `25` to `120` |
| `weight` | `weight_kg` | kg | `20.0` to `300.0` | `25` to `300` |

Values outside the client parse range are treated as missing. Re-syncing the same day updates the
row only if at least one metric changed, leaving `updated_at` untouched otherwise.

## Summary windows and trends

`wellness_summary` (`backend/wellness/summary.py`) compares two non-overlapping windows relative to
`today` in your profile time zone:

- **Recent window:** the last `7` days (`[today - 6 days, today]`), requiring at least `3`
  non-null readings (`RECENT_MIN_READINGS`) for a metric's `recent` mean to be reported.
- **Baseline window:** the `28` days before the recent window (`[today - 34 days, today - 7 days]`),
  requiring at least `7` non-null readings (`BASELINE_MIN_READINGS`) for a metric's `baseline` mean
  to be reported.

Each window mean is rounded to one decimal place in JSON output (`wellness_data`). If a window has
fewer than its minimum readings, its mean is `null`.

When both `recent` and `baseline` are present, `trend` is:

- `"up"` when `recent > baseline`
- `"down"` when `recent < baseline`
- `"flat"` when `recent == baseline`

Otherwise `trend` is `null`.

## Recovery warning rules

A recovery warning is triggered when at least one tracked recovery metric has both `recent` and
`baseline` means and is clearly worse than usual:

- **`low_sleep`:** recent sleep mean is at least `10%` below the baseline mean
  (`baseline - recent >= baseline * 0.10`).
- **`low_hrv`:** recent HRV mean is at least `10%` below the baseline mean
  (`baseline - recent >= baseline * 0.10`).
- **`high_resting_hr`:** recent resting heart rate mean is at least `4` bpm above the baseline mean
  (`recent >= baseline + 4`).

`weight` is reported with its recent mean, baseline mean and trend, and never triggers a recovery
warning. `warning` is `true` when `warning_signals` is non-empty, and `false` otherwise.

## Dashboard and briefing shapes

The serialized `wellness` object (`wellness_data`) has this shape:

```json
{
  "sleep": { "recent": 390.0, "baseline": 450.0, "trend": "down" },
  "hrv": { "recent": 55.2, "baseline": 62.0, "trend": "down" },
  "resting_hr": { "recent": 54.0, "baseline": 49.5, "trend": "up" },
  "weight": { "recent": 70.1, "baseline": 70.0, "trend": "up" },
  "warning": true,
  "warning_signals": ["low_sleep", "low_hrv", "high_resting_hr"]
}
```

- **Dashboard (`GET /api/dashboard/`):** `wellness` is `null` when no metric has enough recent
  readings (at least 3 in the last 7 days). When `wellness` is present, the **Wellness and
  readiness** tile displays each metric's 7-day mean, its trend arrow and baseline comparison when
  available, and a warning banner naming any active `warning_signals`.
- **Week plan and coach chat briefings:** `wellness` is included as the serialized summary object
  (with `null` means/trends for metrics without enough readings). The coach uses it as advisory
  recovery context.

## Privacy boundaries

- **Strict field whitelist:** Only `id`, `sleepSecs`, `hrv`, `restingHR` and `weight` are read from
  Intervals.icu. Free-text fields (such as comments, notes, soreness or mood) are never stored or
  forwarded.
- **User isolation:** Every `DailyWellness` query is scoped to the requesting user
  (`DailyWellness.objects.for_user(user)`). One user's wellness is never readable or writable by
  another.
- **Coach data:** The AI coach only receives the aggregated 7-day and 28-day means, trend words and
  warning signals—never raw daily rows or free text.
- **Job logs:** Background sync logs record only numeric counts (`wellness_synced`), never metric
  values or Intervals.icu text.
