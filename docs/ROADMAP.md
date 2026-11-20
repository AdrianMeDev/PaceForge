# Roadmap: PaceForge
Updated: 2026-11-20

## Vision
A self-hosted AI endurance coach: a season plan up to the race, a concrete week from it that goes to
Intervals.icu, a week review with actual data and changes by message. Each athlete brings their own
AI key; several people can share one instance without seeing each other's data.

## Scope
- **Done (stages 1–7a of `PROJECT_PLAN.md` §15.4):** accounts with invitation, MFA and isolation;
  Intervals.icu key and thresholds; FIT/TCX/GPX and Strava import; profile, VDOT zones, limitations;
  goals A/B/C with realism check (running); training time, intensity levels, double days, fixed
  sessions; season skeleton and AI season plan with versions and change requests; AI week plan with
  checks, hand editing, versions and push to Intervals; week review with coach comment; coach chat
  for the current week; dashboard with get-started steps; PWA.
- **Open (this roadmap):** activity and wellness sync from Intervals, load per workout, season plan
  that reacts to changes, illness and other weeks in the chat, background jobs, cost per month and
  model per task, editing a workout's structure, production deployment, backup, data export and
  account deletion, invitations by email.
- **Later:** drag and drop on the week plan, realism check for cycling/swim/triathlon races,
  workout library as inspiration, Gemini adapter, passkeys, managed mode, planned training blocks.
- **Not planned:** OAuth for Intervals.icu (API key, §15.3), pushing a week without confirmation.

## Architecture
- **Stack:** Django 6.1 (JSON views), django-allauth with MFA, PostgreSQL 17; Angular 22
  (standalone, signals); uv and npm; Docker Compose for development.
- **Components:** `backend/` apps `accounts`, `integrations` (Intervals), `activities`, `athletes`,
  `goals`, `availability`, `season`, `planning` (week plan, checks, push), `reviews`, `chat`,
  `coach` (AI provider, usage), `dashboard`, `core` (encryption, isolation); `frontend/` one feature
  folder per page.
- **Core data:** User → Athlete profile, Goals, Training time, Activities, Season plan versions,
  Week plan versions → Workouts (lineage, Intervals `external_id`), Week reviews, Chat messages,
  AI usage records.
- **Integrations:** Intervals.icu REST (API key per user), Anthropic and OpenAI-compatible AI
  providers (per-user key), SMTP.

## Decisions
| # | Decision | Why | Alternative |
|---|---|---|---|
| 1 | Minutes stay the basis of all checks; load is an added estimate per workout | Checks and season already work in minutes (§15.3.4) | Switch checks to TSS |
| 2 | Background jobs as management commands run by a scheduler container, no broker | No new infrastructure for a small instance | Celery with Redis |
| 3 | Jobs never push to Intervals and never confirm a plan | Push only after confirmation (§15.3.8) | Optional auto-push |
| 4 | The chat changes plans only through actions run by code, always as a new draft | Same safety as week and season plans | Free rewriting by the LLM |
| 5 | Checks against real providers and the real Intervals API stay manual (see below) | They need the athlete's keys and cost money | Recorded fixtures only |

## Risks & unknowns
| Risk | Impact | Mitigation |
|---|---|---|
| Intervals rate limits for personal keys unknown | Sync and jobs get blocked | M1 backs off on 429; manual check before M7 |
| No real-provider test of week, season and chat yet | Plans fail on real models | Manual checks below before relying on M5–M7 |
| Load estimate for strength and Run vs Ride weighting is rough | Misleading numbers | Shown as estimate, never used to block a plan |
| Jobs must always run in the right user's context | Data leak between users | Isolation tests per job in M7 |

## Milestones

### M1 [x] Activities from Intervals.icu
- **Goal:** Activities synced to Intervals.icu (not Strava-sourced) appear in PaceForge by button.
- **Includes:** fetch the last 8–12 weeks (setting), map sport/date/duration/distance/load/HR/pace/power, duplicate check with file imports, last sync and error on the connection, sync button on the Activities page, back-off on 429/5xx, docs.
- **Done when:** with a stubbed Intervals API, a sync imports activities once (a second sync adds none), duplicates of uploaded files are skipped, the connection shows the last sync; tests green.
- **Depends on:** –
- **Size:** M

### M2 [x] Load per workout
- **Goal:** Every planned workout and every activity has a load value shown next to the minutes.
- **Includes:** estimated load for endurance workouts from duration and zones, for strength from duration × RPE; load of activities from Intervals or duration × RPE; planned vs done load on the week plan, week review and season chart; docs.
- **Done when:** the week plan and review show planned and done load per sport; checks still work on minutes; tests green.
- **Depends on:** M1
- **Size:** M

### M3 [x] Run volume rises slower than cycling
- **Goal:** The volume increase check is applied per sport, with a stricter limit for running.
- **Includes:** per-sport reference (last four weeks), running limit below the general one per intensity level, new warning code, coach briefing and docs.
- **Done when:** a week that keeps total minutes but jumps in running gets the new warning; tests green.
- **Depends on:** –
- **Size:** S

### M4 [x] Season plan reacts to changes
- **Goal:** The athlete is told when the confirmed season plan no longer fits and can ask for an update.
- **Includes:** detect changed goals, new FTP or best time, larger changes of training time since the confirmed plan; hint on Season, Goals and Profile pages with a link to "Ask for a change"; after several weeks of strong deviation in the week review, a proposal to adjust the season.
- **Done when:** changing an A race date shows the hint until a new plan is confirmed; three weak weeks show the proposal; tests green.
- **Depends on:** –
- **Size:** M

### M5 [x] Illness in the coach chat
- **Goal:** "I am sick" in the chat leads to a new draft with paused days and a careful return.
- **Includes:** `mark_sick` action (symptoms above/below the neck, fever, expected days), affected days paused, return rules (easy and shorter first, no intensity for the first days), doctor hint for fever, illness stored as absence and visible in the season; confirmed draft removes workouts in Intervals.
- **Done when:** with a scripted provider, a sick message creates a draft without intensity in the return days and an absence; tests green.
- **Depends on:** –
- **Size:** L

### M6 [x] Chat for other weeks and the season
- **Goal:** The chat can change the next weeks and turn longer changes into a season change request.
- **Includes:** actions for a named week (e.g. business trip next week), `replan_from` that hands a longer absence to the season change request, more than one week in one answer refused clearly, docs.
- **Done when:** "only running next week" creates a draft for next week; a three-week absence creates a season draft; tests green.
- **Depends on:** M5
- **Size:** L

### M7 [x] Background jobs
- **Goal:** Sync, the Sunday draft of next week and the week review run on their own.
- **Includes:** management commands per job looping over users in their own context, scheduler service in Compose, a job log per user, settings to turn each job off, sync before drafting; never confirm or push.
- **Done when:** running the scheduler once syncs, drafts and reviews for two users without mixing data; isolation tests green.
- **Depends on:** M1
- **Size:** L

### M8 [x] Wellness and readiness
- **Goal:** Sleep, HRV, resting HR and weight from Intervals inform the coach and the dashboard.
- **Includes:** wellness sync with activities, dashboard tile with the trend, short summary in the week and chat briefing, warning when recovery is clearly worse than usual.
- **Done when:** synced wellness shows on the dashboard and reaches the briefing; tests green.
- **Depends on:** M1
- **Size:** M

### M9 [x] Cost per month and model per task
- **Goal:** The athlete sees what the coach costs and can use a cheaper model for week and chat.
- **Includes:** optional price per million input/output/cached tokens per model, monthly cost on the AI page, separate model for week plan and chat (season model exists), docs.
- **Done when:** with prices set, the AI page shows cost per month; week and chat use their own model when set; tests green.
- **Depends on:** –
- **Size:** M

### M10 [x] Edit a workout's structure
- **Goal:** The athlete can change the segments and intervals of a workout by hand.
- **Includes:** segment editor (warm-up, blocks with repeats, cool-down, zone, duration) on the Week plan page, checks after each change, saved as a new draft, push updates the same Intervals event.
- **Done when:** changing 3×10 min to 4×8 min saves a new draft that passes the checks; tests green.
- **Depends on:** –
- **Size:** M

### M11 [x] Production deployment
- **Goal:** A new person can run PaceForge on a VPS with HTTPS from the docs.
- **Includes:** `compose.prod.yaml` with Caddy (HTTPS), backend, frontend, PostgreSQL, scheduler; production settings from environment; first setup without database edits; registration closed/invite only documented; update and migration docs.
- **Done when:** `docker compose -f compose.prod.yaml config` is valid, a CI job builds the images, the setup doc covers install to first login.
- **Depends on:** M7
- **Size:** M

### M12 [x] Backup and restore
- **Goal:** The database can be backed up encrypted and restored, with the instance key kept apart.
- **Includes:** backup command or service (pg_dump, encrypted), retention, restore procedure, a test that restores into an empty database, docs.
- **Done when:** the restore test passes and the docs describe backup, key storage and restore.
- **Depends on:** M11
- **Size:** M

### M13 [x] Data export and account deletion
- **Goal:** Each user can download their data and delete their account.
- **Includes:** JSON export of profile, goals, activities, plans, reviews and chat; account deletion with confirmation and MFA, removing keys and data (Intervals stays untouched); admin cannot be left without an admin.
- **Done when:** export contains only the user's data; deletion removes all of it; isolation tests green.
- **Depends on:** –
- **Size:** M

### M14 [~] Invitations by email
- **Goal:** The admin page sends the invitation link by email.
- **Includes:** send and resend from the admin page, mail template, expired invitations shown, docs.
- **Done when:** creating an invitation sends one email (Mailpit in development); tests green.
- **Depends on:** –
- **Size:** S

### M15 [ ] Status docs up to date
- **Goal:** README and `PROJECT_PLAN.md` describe what works today and point to this roadmap.
- **Includes:** rewrite the README's "What works today / Not there yet", replace the stage table in `PROJECT_PLAN.md` §15.4 with a pointer to `docs/ROADMAP.md`.
- **Done when:** no README statement contradicts the code; docs only.
- **Depends on:** M1, M2, M3, M4, M5, M6, M7, M8, M9, M10, M11, M12, M13, M14
- **Size:** S

## Manual checks (not for unattended runs)
- [ ] Week plan, season plan and chat against a real Anthropic and an OpenAI-compatible provider.
- [ ] Push to the real Intervals.icu API: pace targets, strength event, Ride vs VirtualRide (Zwift).
- [ ] Intervals.icu rate limits for personal keys (before M7 runs for several users).
- [ ] M1 and M8 against a real Intervals account (activity and wellness fields).

## Definition of done (every milestone)
- Backend: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy .`, migrations up to
  date, `uv run pytest -n auto` (needs the PostgreSQL service from `compose.dev.yaml`).
- Frontend: `npm run format:check`, `npm run lint`, `npx ng test --no-watch`, `npx ng build`.
- Every query scoped to the requesting user; new endpoints have isolation tests.
- No AI provider or Intervals call in tests (stubs or scripted providers only).
- README section and `docs/` updated for every user-visible change.

## Changelog
- 2026-11-20: M13 completed — per-user JSON export (`GET /api/me/export/`, no keys, passwords, activity files or other users' data) and account deletion (`POST /api/me/delete/`, with email, password and MFA code, last active administrator protected, Intervals.icu and AI providers untouched, sessions ended), both on the Security page with 5 requests per minute, and the guide in `docs/account-data.md`
- 2026-11-20: M12 completed — encrypted database backups (`backup_db`, `run_backups` and an off-by-default `backup` service in `compose.prod.yaml`, AES-256-GCM with its own `BACKUP_ENCRYPTION_KEY`), retention by day and week, `restore_db` into an empty database with an end-to-end test, and the guide in `docs/backup-and-restore.md`
- 2026-11-20: M11 completed — production deployment stack (`compose.prod.yaml`, Caddy with automatic HTTPS, non-root backend and frontend containers, `scheduler` service, `/api/health/`, production settings via `APP_DOMAIN`, CI container validation/build, and end-to-end VPS deployment docs)
- 2026-11-19: M10 completed — segment editor on the Week plan page (warm-up, repeated blocks, cool-down, duration, zone, reordering, removing structure) with automatic duration calculation, checks after each change, new draft on save, and updating the same Intervals.icu event on push
- 2026-11-19: M9 completed — optional per-model prices (input, output and cached input per million tokens), monthly usage and estimated cost in the athlete's time zone on the Connections page, and separate optional models for the week plan and coach chat
- 2026-11-19: M8 completed — daily wellness (sleep, HRV, resting HR and weight) synced from Intervals.icu with activities, shown on the dashboard with 7-day vs 28-day trends and recovery warnings, and passed to week and chat briefings
- 2026-11-19: M7 completed — background jobs run sync, the Sunday week review and the next week's draft in a scheduler container (no broker); each athlete turns each job off and reads a log of their own runs, and jobs only ever create drafts (never confirm, never push to Intervals.icu)
- 2026-11-19: M6 completed — the chat changes a week the athlete names (this week or one of the next four that has a plan), refuses more than one week per answer with a fixed reply, and hands a longer absence (`replan_from`, 7 to 120 days) to the season: the absence is noted and a season draft around it is made and linked from the answer
- 2026-11-19: M5 completed — `mark_sick` in the chat (symptoms, fever, days) pauses the sick days, plans a 2- or 4-day easy return without intensity, notes the illness as an absence and appends the fever hint; the season marks illness weeks; a confirmed draft removes the paused workouts in Intervals.icu
- 2026-11-19: M4 completed — season change hints on Season, Goals and Profile, three-week deviation proposal with evidence weeks in Week review, and change requests drafted from current inputs
- 2026-11-19: M2 completed — unified activity load (Intervals or duration × RPE), workout load estimates, and planned vs done load across week plan, week review and season chart
- 2026-11-19: M1 completed — sync non-Strava activities from Intervals.icu (last 8–12 weeks, duplicate check, last sync & error on connection, Activities page button)
- 2026-11-19: roadmap created from `PROJECT_PLAN.md` §15 and the user stories, checked against `main` (905fee0)
- 2026-11-19: M3 done (Per-sport run volume check)
