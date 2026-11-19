# Agent instructions for PaceForge

PaceForge is a self-hosted AI endurance coach: Django 6.1 backend in `backend/`, Angular 22
frontend in `frontend/`, PostgreSQL 17. The open work is in `docs/ROADMAP.md`; how the app
behaves is described in `README.md` and `docs/`.

## Project commands

The backend tests need the PostgreSQL service from `compose.dev.yaml` on `localhost:5432`
(`docker compose -f compose.dev.yaml up -d db mailpit`). They do not need a `.env` file:
`config/settings_test.py` sets test values. If `frontend/node_modules` is missing (for example in
a fresh worktree), run `npm ci` in `frontend/` first.

Backend, from `backend/`:

- Install dependencies with `uv sync`.
- Run a focused test with `uv run pytest planning/tests/test_rules_capacity.py` (or `-k <name>`).
- Run the full suite with `uv run pytest -n auto`.
- Check lint and formatting with `uv run ruff check .` and `uv run ruff format --check .`;
  types with `uv run mypy .`; migrations with
  `DJANGO_SETTINGS_MODULE=config.settings_test uv run python manage.py makemigrations --check --dry-run`
  (the test settings need no `.env`, which a fresh worktree does not have).

Frontend, from `frontend/`:

- Install dependencies with `npm ci`.
- Run the tests with `npx ng test --no-watch`.
- Check lint and formatting with `npm run lint` and `npm run format:check`.
- Build with `npx ng build`.

## Conventions

- Backend: one Django app per area (`planning`, `season`, `chat`, …). Keep views thin; logic
  lives in services, rules and serializers. Every query is scoped to the requesting user, and new
  endpoints get isolation tests (another user's data is never readable or writable).
- Tests sit in `<app>/tests/`. Never call a real AI provider or Intervals.icu in tests; use the
  existing stubs and scripted providers.
- AI output is always parsed and checked by code; the AI never writes data directly. Jobs and the
  chat never confirm a plan or push to Intervals.icu without the athlete's confirmation.
- Migrations: create new ones with `makemigrations`; never edit a migration that is already on
  `main`.
- Frontend: standalone components, signals, `inject()`, `ChangeDetectionStrategy.OnPush`, the new
  control flow (`@if`, `@for` with `track`), strict types, no `any`. One folder per page under
  `src/app/features/`, shared API clients under `src/app/core/`.
- Do not add new dependencies (Python or npm). If a step cannot be done without one, reply with
  `BATON-ROADMAP-PROBLEM: needs dependency <name>` and stop.
- Never read or change `.env` files; never put keys, tokens or personal data into code, tests or
  docs.
- Docs are plain English with short sentences. Update the README section and the matching file
  in `docs/` for every user-visible change.

## Working on a baton step

- Read the assigned step and inspect the files it touches. Implement or repair that step only.
  Preserve partial work from earlier attempts and cover the behavior with the requested tests.
- Use the step's Verify command to check your work locally. Report the checks you ran and their
  outcomes. Baton runs the original Verify command from the working tree and records the result.
- Leave `.agent-plan.md` and Git state to baton and the operator. Change a tracked roadmap only
  when the assigned step calls for it. If the roadmap makes the step impossible, reply with
  `BATON-ROADMAP-PROBLEM: <reason>` and stop.
- For a planning or independent review task, work read-only and return the format requested
  in the baton prompt.

## Commits and publication

Commit messages follow Conventional Commits with a scope, for example
`feat(chat): store the conversation with the coach`. Baton owns commits, pushes and pull requests
during `baton auto`; agents never run Git commands.
