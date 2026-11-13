# Intervals.icu feasibility check (Phase 0)

Checked on 2026-11-12 against the live Intervals.icu API with a personal API key of a test
account. No personal data from the account is recorded here. Short version: reading and writing
works with an API key, workouts written to the calendar reach Zwift and COROS once those are
connected in Intervals.icu, and the connection will use API keys only.

## Decision: API key, no OAuth

PaceForge connects to Intervals.icu with the athlete's **personal API key** (PROJECT_PLAN 5.3).
OAuth (5.1, 5.2) is not planned.

- The project is meant for single athletes who host it themselves and invite one or two
  colleagues, not for a public multi-tenant service.
- OAuth needs a registered and approved Intervals.icu application. That effort does not fit this
  audience, and a self-hosted instance would need its own client credentials anyway.
- Consequence: each user pastes their own key into PaceForge. It is stored encrypted with the
  instance key (see "Instance key" in the README) and never returned to the browser.

Revisit the decision if PaceForge is ever offered as a hosted service for many strangers.

## What was verified

| Point | Result |
| --- | --- |
| Authentication | Works. HTTP Basic, user `API_KEY`, password is the key. Without or with a wrong key the API answers 401. |
| Own account | The athlete id `0` in a path means "the authenticated athlete"; the real id (`i` plus digits) is in the athlete object. |
| Read athlete and zones | Works. Zones and thresholds are per sport group (ride, run, swim, other): `ftp`, `lthr`, `max_hr`, power, heart-rate and pace zones. |
| Read activities | Endpoint answers 200 with the required `oldest`/`newest` parameters. **The test account had no activities, so the structure of a real activity is not verified yet.** |
| Read wellness | Endpoint answers 200; the test account had no wellness data. |
| Write a workout | Works. The workout text is parsed on the server into steps, duration and training load. |
| External ids | Works. Posting the same `external_id` again with `upsert=true` updates the same event (same id, new name) and does not create a duplicate. |
| Delete | Works (`DELETE` on the event). |
| Export files | `download.zwo` returns valid Zwift XML; `download.fit` returns a valid FIT file (header checked). |
| Zwift and COROS sync | Works. After connecting both services in Intervals.icu, the test ride appeared in Zwift and the test run in COROS (confirmed by the project owner on 2026-11-13). Before the connection nothing is pushed: the workouts only exist in the calendar. |
| Rate limits | **Unknown.** No limit headers were returned (Cloudflare sits in front); the API was not stressed. |

## API notes for the implementation

Base URL `https://intervals.icu/api/v1`. All paths below start with `/athlete/{id}`.

| Purpose | Request |
| --- | --- |
| Athlete and settings | `GET /athlete/0`, `GET /athlete/0/sport-settings` |
| Activities | `GET /athlete/0/activities?oldest=YYYY-MM-DD&newest=YYYY-MM-DD` |
| Wellness | `GET /athlete/0/wellness?oldest=…&newest=…` |
| Calendar | `GET /athlete/0/events?oldest=…&newest=…` |
| Create or update workouts | `POST /athlete/0/events/bulk?upsert=true` with a JSON list of events |
| Delete | `DELETE /athlete/0/events/{id}` |
| Zwift and device files | `GET /athlete/0/events/{id}/download.zwo`, `…/download.fit` |

- **A workout event** has `category: "WORKOUT"`, `type` (e.g. `Ride`, `VirtualRide`, `Run`),
  `start_date_local` (`YYYY-MM-DDT00:00:00`), `name`, `external_id` and a text `description` in
  the Intervals workout syntax, for example `- 10m ramp 50-70%`, `- 4m 90-95% LTHR`, repeat blocks
  as `Main set 4x` followed by the steps.
- **External ids are the sync key.** PaceForge should set a stable `external_id` per planned
  workout, so a changed plan updates the calendar entry instead of adding another one.
- **Targets need thresholds.** Percent-of-FTP targets need an FTP, pace targets a threshold pace
  and `% LTHR` an LTHR in the matching sport settings. The test account had no run threshold pace,
  so the run test used heart-rate targets.
- **Keep only what is needed.** The athlete object has about 160 fields, including the email
  address and the state of connected services. Import a fixed list of fields and never store the
  whole object or the raw response.
- **Errors:** 401 means the key is missing, wrong or revoked (show "reconnect"); 422 comes with a
  JSON message about a missing or invalid parameter; use timeouts and back off on 429 or 5xx.
- **The key grants full access** to the account, including writing to the calendar. Store it
  encrypted, never log it, never send it to the browser or an AI provider, and delete it when the
  connection is removed. Users can invalidate a key by creating a new one in Intervals.icu.

## Activities: what the API gives (checked 2026-11-13)

- **Activities that Intervals.icu received from Strava cannot be read through the API.** The list
  and the detail call return a stub with five fields (`id`, `icu_athlete_id`, `source: "STRAVA"`,
  `start_date_local` and a `_note` saying "STRAVA activities are not available via the API");
  the streams answer 422 "Cannot read Strava activities via the API"; the CSV export has no rows
  for them. The test account had 50 activities, all from Strava, none readable.
- **Consequence for the import:** reading activities from Intervals.icu only works for activities
  that reach it by another route (a device connection such as COROS or Garmin, a file upload).
  For an athlete whose history arrives through Strava, importing files is the only way in, so the
  FIT/TCX import comes before the Intervals.icu import. **The importer exists now:** see
  "Activities" in the [README](../README.md#activities) for what it reads, stores and refuses.
- **The CSV export** (`activities.csv`) lists id, start, name, type, moving and elapsed time,
  distance, elevation gain, speeds, heart rate, cadence, calories, power and load columns; it has
  not been checked with readable activities yet.

### Real activity files (checked 2026-11-13, no personal values recorded)

| | FIT (COROS, run) | TCX (COROS, run) |
| --- | --- | --- |
| Size | 165 KB | 1.5 MB |
| Content | file type activity, 1 session, 10 laps, about 3900 records, device info | 1 activity, 6 laps, about 3300 trackpoints |
| Per record | timestamp, distance, heart rate, speed, cadence, power, altitude, GPS position, running dynamics (stance time, vertical oscillation, step length), one developer field | time, distance, heart rate, cadence, altitude, GPS position, speed (in the Garmin ActivityExtension) |
| Not present | sub sport in the session | power, device details beyond the creator name |
| Other | manufacturer and product ids, developer data | no `DOCTYPE` or entities |

- The two files are different runs (about 12.8 km and about 10.4 km), both exported from COROS.
- **For the importer:** every sensor value is optional (it differs by device and file), files can
  reach several MB, TCX must be parsed safely (refuse `DOCTYPE` and entities), and developer
  fields in FIT can be ignored.

## Open checks

- [x] **Zwift:** the test ride reached Zwift (2026-11-13).
- [x] **COROS:** the test run reached COROS (2026-11-13).
- [x] **Activity structure:** checked on 2026-11-13. Strava-sourced activities are not readable
      (see "Activities"); the structure of directly synced activities is still unchecked and only
      matters for the later Intervals.icu import.
- [ ] **Rate limits:** find out the limits for personal keys before an automatic sync runs
      against many users.

Test data left in the test account: two workouts with the external ids `paceforge-test-zwift`
(a virtual ride on 2026-11-14) and `paceforge-test-coros` (a run on 2026-11-15). They can be
deleted in the Intervals.icu calendar; the device checks are done.

## What this means for the plan

- **Phase 2:** provider connection with an API key (5.3), stored with the instance key; import
  with a field whitelist; a "test connection" call (`GET /athlete/0`) when the key is saved. The
  reusable encrypted field that was left out of the encryption work arrives with the first stored
  key.
- **Phase 6:** export through the bulk upsert with `external_id`; the calendar entry and the
  PaceForge plan stay linked by that id. Conflicts (the user edited the event in Intervals.icu)
  need a rule, because an upsert overwrites the event.
- **Phase 3:** zones and thresholds can be read from the sport settings instead of asking the
  user to type them.
