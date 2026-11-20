# Audit: PaceForge

Updated: 2026-11-20 · Base: aba6129

## Scope

All 834 files tracked at `aba6129`: 815 to review, 19 skipped (symlinks, binary, oversized, lockfiles, possible secrets).

## Inventory

### ./ [x]

- [-] `.env.example` – possible secret
- [-] `.env.prod.example` – possible secret
- [x] `.gitignore` – 0 findings
- [x] `AGENTS.md` – 0 findings
- [x] `CLAUDE.md` – 0 findings
- [-] `README.md` – too large
- [x] `compose.dev.yaml` – 1 finding
- [x] `compose.prod.yaml` – 3 findings

### .github/workflows/ [x]

- [x] `.github/workflows/ci.yml` – 5 findings

### backend/ [x]

- [x] `backend/.dockerignore` – 0 findings
- [x] `backend/Dockerfile` – 2 findings
- [x] `backend/entrypoint.sh` – 1 finding
- [x] `backend/manage.py` – 0 findings
- [x] `backend/pyproject.toml` – 0 findings
- [-] `backend/uv.lock` – lockfile

### backend/accounts/ [x]

- [x] `backend/accounts/__init__.py` – 0 findings
- [x] `backend/accounts/adapters.py` – 0 findings
- [x] `backend/accounts/apps.py` – 0 findings
- [x] `backend/accounts/forms.py` – 1 finding
- [x] `backend/accounts/managers.py` – 0 findings
- [x] `backend/accounts/mfa_adapter.py` – 0 findings
- [x] `backend/accounts/models.py` – 0 findings
- [x] `backend/accounts/permissions.py` – 0 findings
- [x] `backend/accounts/serializers.py` – 0 findings
- [x] `backend/accounts/throttles.py` – 2 findings
- [x] `backend/accounts/urls.py` – 0 findings
- [x] `backend/accounts/views.py` – 4 findings

### backend/accounts/management/ [x]

- [x] `backend/accounts/management/__init__.py` – 0 findings

### backend/accounts/management/commands/ [x]

- [x] `backend/accounts/management/commands/__init__.py` – 0 findings
- [x] `backend/accounts/management/commands/reset_mfa.py` – 2 findings
- [x] `backend/accounts/management/commands/setup_admin.py` – 2 findings

### backend/accounts/migrations/ [x]

- [x] `backend/accounts/migrations/0001_initial.py` – 0 findings
- [x] `backend/accounts/migrations/0002_userinvitation.py` – 0 findings
- [x] `backend/accounts/migrations/0003_encrypt_mfa_secrets.py` – 3 findings
- [x] `backend/accounts/migrations/0004_userinvitation_sent_at.py` – 0 findings
- [x] `backend/accounts/migrations/__init__.py` – 0 findings

### backend/accounts/services/ [x]

- [x] `backend/accounts/services/__init__.py` – 0 findings
- [x] `backend/accounts/services/deletion.py` – 2 findings
- [x] `backend/accounts/services/export.py` – 2 findings
- [x] `backend/accounts/services/invitations.py` – 3 findings
- [x] `backend/accounts/services/mfa.py` – 0 findings

### backend/accounts/tests/ [x]

- [x] `backend/accounts/tests/__init__.py` – 0 findings
- [x] `backend/accounts/tests/conftest.py` – 0 findings
- [x] `backend/accounts/tests/test_account_endpoints.py` – 0 findings
- [x] `backend/accounts/tests/test_auth.py` – 2 findings
- [x] `backend/accounts/tests/test_deletion_service.py` – 4 findings
- [x] `backend/accounts/tests/test_emails.py` – 0 findings
- [x] `backend/accounts/tests/test_export_service.py` – 1 finding
- [x] `backend/accounts/tests/test_invitation_api.py` – 0 findings
- [x] `backend/accounts/tests/test_invitations.py` – 0 findings
- [x] `backend/accounts/tests/test_me.py` – 0 findings
- [x] `backend/accounts/tests/test_mfa.py` – 0 findings
- [x] `backend/accounts/tests/test_mfa_encryption.py` – 1 finding
- [x] `backend/accounts/tests/test_mfa_enforcement.py` – 2 findings
- [x] `backend/accounts/tests/test_models.py` – 0 findings
- [x] `backend/accounts/tests/test_registration.py` – 2 findings
- [x] `backend/accounts/tests/test_reset_mfa.py` – 0 findings
- [x] `backend/accounts/tests/test_setup_admin.py` – 0 findings

### backend/activities/ [x]

- [x] `backend/activities/__init__.py` – 0 findings
- [x] `backend/activities/apps.py` – 0 findings
- [x] `backend/activities/duplicates.py` – 0 findings
- [x] `backend/activities/efforts.py` – 0 findings
- [x] `backend/activities/load.py` – 0 findings
- [x] `backend/activities/models.py` – 0 findings
- [x] `backend/activities/pagination.py` – 0 findings
- [x] `backend/activities/serializers.py` – 0 findings
- [x] `backend/activities/services.py` – 1 finding
- [x] `backend/activities/strava.py` – 3 findings
- [x] `backend/activities/sync.py` – 0 findings
- [x] `backend/activities/throttles.py` – 0 findings
- [x] `backend/activities/urls.py` – 0 findings
- [x] `backend/activities/views.py` – 7 findings

### backend/activities/management/ [x]

- [x] `backend/activities/management/__init__.py` – 0 findings

### backend/activities/management/commands/ [x]

- [x] `backend/activities/management/commands/__init__.py` – 0 findings
- [x] `backend/activities/management/commands/backfill_best_efforts.py` – 2 findings
- [x] `backend/activities/management/commands/import_strava.py` – 1 finding

### backend/activities/migrations/ [x]

- [x] `backend/activities/migrations/0001_initial.py` – 0 findings
- [x] `backend/activities/migrations/0002_activity_best_efforts.py` – 0 findings
- [x] `backend/activities/migrations/0003_manual_activities.py` – 0 findings
- [x] `backend/activities/migrations/0004_gpx_source.py` – 0 findings
- [x] `backend/activities/migrations/0005_intervals_sync_fields.py` – 0 findings
- [x] `backend/activities/migrations/__init__.py` – 0 findings

### backend/activities/parsing/ [x]

- [x] `backend/activities/parsing/__init__.py` – 3 findings
- [x] `backend/activities/parsing/compressed.py` – 0 findings
- [x] `backend/activities/parsing/fit.py` – 1 finding
- [x] `backend/activities/parsing/gpx.py` – 1 finding
- [x] `backend/activities/parsing/series.py` – 3 findings
- [x] `backend/activities/parsing/tcx.py` – 3 findings
- [x] `backend/activities/parsing/types.py` – 0 findings
- [x] `backend/activities/parsing/values.py` – 0 findings

### backend/activities/tests/ [x]

- [x] `backend/activities/tests/__init__.py` – 0 findings
- [x] `backend/activities/tests/conftest.py` – 0 findings
- [x] `backend/activities/tests/fit_builder.py` – 2 findings
- [x] `backend/activities/tests/gpx_builder.py` – 1 finding
- [x] `backend/activities/tests/tcx_builder.py` – 2 findings
- [x] `backend/activities/tests/test_activities_api.py` – 1 finding
- [x] `backend/activities/tests/test_best_efforts_storage.py` – 3 findings
- [x] `backend/activities/tests/test_compressed.py` – 2 findings
- [x] `backend/activities/tests/test_duplicates.py` – 1 finding
- [x] `backend/activities/tests/test_efforts.py` – 0 findings
- [x] `backend/activities/tests/test_fit_parser.py` – 2 findings
- [x] `backend/activities/tests/test_gpx_parser.py` – 1 finding
- [x] `backend/activities/tests/test_load.py` – 0 findings
- [x] `backend/activities/tests/test_manual_api.py` – 5 findings
- [x] `backend/activities/tests/test_models.py` – 1 finding
- [x] `backend/activities/tests/test_rating_api.py` – 0 findings
- [x] `backend/activities/tests/test_series.py` – 1 finding
- [x] `backend/activities/tests/test_services.py` – 2 findings
- [x] `backend/activities/tests/test_strava.py` – 2 findings
- [x] `backend/activities/tests/test_strava_import.py` – 3 findings
- [x] `backend/activities/tests/test_sync.py` – 3 findings
- [x] `backend/activities/tests/test_tcx_parser.py` – 7 findings

### backend/athletes/ [x]

- [x] `backend/athletes/__init__.py` – 0 findings
- [x] `backend/athletes/apps.py` – 0 findings
- [x] `backend/athletes/best_times.py` – 1 finding
- [x] `backend/athletes/estimates.py` – 2 findings
- [x] `backend/athletes/facts.py` – 0 findings
- [x] `backend/athletes/models.py` – 1 finding
- [x] `backend/athletes/serializers.py` – 1 finding
- [x] `backend/athletes/sync.py` – 0 findings
- [x] `backend/athletes/thresholds.py` – 4 findings
- [x] `backend/athletes/urls.py` – 0 findings
- [x] `backend/athletes/vdot.py` – 2 findings
- [x] `backend/athletes/views.py` – 2 findings
- [x] `backend/athletes/zones.py` – 0 findings

### backend/athletes/migrations/ [x]

- [x] `backend/athletes/migrations/0001_initial.py` – 2 findings
- [x] `backend/athletes/migrations/0002_body_and_training_data.py` – 1 finding
- [x] `backend/athletes/migrations/0003_best_time.py` – 1 finding
- [x] `backend/athletes/migrations/__init__.py` – 0 findings

### backend/athletes/tests/ [x]

- [x] `backend/athletes/tests/__init__.py` – 0 findings
- [x] `backend/athletes/tests/conftest.py` – 0 findings
- [x] `backend/athletes/tests/test_athlete_api.py` – 9 findings
- [x] `backend/athletes/tests/test_best_times.py` – 0 findings
- [x] `backend/athletes/tests/test_estimates.py` – 1 finding
- [x] `backend/athletes/tests/test_models.py` – 2 findings
- [x] `backend/athletes/tests/test_sync.py` – 5 findings
- [x] `backend/athletes/tests/test_threshold_estimates.py` – 3 findings
- [x] `backend/athletes/tests/test_thresholds.py` – 3 findings
- [x] `backend/athletes/tests/test_vdot.py` – 1 finding
- [x] `backend/athletes/tests/test_zones.py` – 0 findings

### backend/availability/ [x]

- [x] `backend/availability/__init__.py` – 0 findings
- [x] `backend/availability/absences.py` – 5 findings
- [x] `backend/availability/apps.py` – 0 findings
- [x] `backend/availability/capacity.py` – 1 finding
- [x] `backend/availability/fixed_sessions.py` – 0 findings
- [x] `backend/availability/intensity.py` – 0 findings
- [x] `backend/availability/limitations.py` – 1 finding
- [x] `backend/availability/models.py` – 1 finding
- [x] `backend/availability/preferences.py` – 0 findings
- [x] `backend/availability/serializers.py` – 3 findings
- [x] `backend/availability/urls.py` – 0 findings
- [x] `backend/availability/views.py` – 6 findings

### backend/availability/migrations/ [x]

- [x] `backend/availability/migrations/0001_initial.py` – 0 findings
- [x] `backend/availability/migrations/0002_typical_weekly_minutes.py` – 0 findings
- [x] `backend/availability/migrations/0003_sports_and_stretching.py` – 1 finding
- [x] `backend/availability/migrations/0004_intensity_level.py` – 1 finding
- [x] `backend/availability/migrations/0005_double_days_and_time_windows.py` – 1 finding
- [x] `backend/availability/migrations/0006_limitation.py` – 1 finding
- [x] `backend/availability/migrations/0007_share_limitations_text.py` – 0 findings
- [x] `backend/availability/migrations/0008_week_wishes.py` – 0 findings
- [x] `backend/availability/migrations/0009_sport_preferences.py` – 0 findings
- [x] `backend/availability/migrations/0010_fixed_session.py` – 0 findings
- [x] `backend/availability/migrations/__init__.py` – 0 findings

### backend/availability/tests/ [x]

- [x] `backend/availability/tests/__init__.py` – 0 findings
- [x] `backend/availability/tests/conftest.py` – 0 findings
- [x] `backend/availability/tests/test_absences.py` – 1 finding
- [x] `backend/availability/tests/test_capacity.py` – 2 findings
- [x] `backend/availability/tests/test_fixed_sessions_api.py` – 1 finding
- [x] `backend/availability/tests/test_intensity.py` – 1 finding
- [x] `backend/availability/tests/test_limitations_api.py` – 3 findings
- [x] `backend/availability/tests/test_models.py` – 2 findings
- [x] `backend/availability/tests/test_periods_api.py` – 4 findings
- [x] `backend/availability/tests/test_preferences.py` – 2 findings
- [x] `backend/availability/tests/test_settings_api.py` – 4 findings

### backend/chat/ [x]

- [x] `backend/chat/__init__.py` – 0 findings
- [x] `backend/chat/actions.py` – 9 findings
- [x] `backend/chat/apps.py` – 0 findings
- [x] `backend/chat/briefing.py` – 0 findings
- [x] `backend/chat/models.py` – 0 findings
- [x] `backend/chat/prompt.py` – 1 finding
- [x] `backend/chat/serializers.py` – 0 findings
- [x] `backend/chat/services.py` – 2 findings
- [x] `backend/chat/throttles.py` – 0 findings
- [x] `backend/chat/urls.py` – 0 findings
- [x] `backend/chat/views.py` – 0 findings

### backend/chat/migrations/ [x]

- [x] `backend/chat/migrations/0001_initial.py` – 2 findings
- [x] `backend/chat/migrations/0002_chatmessage_season_plan.py` – 1 finding
- [x] `backend/chat/migrations/__init__.py` – 0 findings

### backend/chat/tests/ [x]

- [x] `backend/chat/tests/__init__.py` – 0 findings
- [x] `backend/chat/tests/conftest.py` – 0 findings
- [x] `backend/chat/tests/test_actions.py` – 2 findings
- [x] `backend/chat/tests/test_api.py` – 2 findings
- [x] `backend/chat/tests/test_briefing.py` – 2 findings
- [x] `backend/chat/tests/test_models.py` – 0 findings
- [x] `backend/chat/tests/test_prompt.py` – 2 findings
- [x] `backend/chat/tests/test_services.py` – 8 findings

### backend/coach/ [x]

- [x] `backend/coach/__init__.py` – 0 findings
- [x] `backend/coach/answers.py` – 2 findings
- [x] `backend/coach/apps.py` – 0 findings
- [x] `backend/coach/endpoints.py` – 0 findings
- [x] `backend/coach/models.py` – 1 finding
- [x] `backend/coach/pricing.py` – 2 findings
- [x] `backend/coach/serializers.py` – 2 findings
- [x] `backend/coach/services.py` – 2 findings
- [x] `backend/coach/throttles.py` – 1 finding
- [x] `backend/coach/urls.py` – 0 findings
- [x] `backend/coach/views.py` – 0 findings

### backend/coach/migrations/ [x]

- [x] `backend/coach/migrations/0001_initial.py` – 1 finding
- [x] `backend/coach/migrations/0002_aiusagerecord.py` – 0 findings
- [x] `backend/coach/migrations/0003_usage_purpose_weekly_plan.py` – 0 findings
- [x] `backend/coach/migrations/0004_usage_purpose_week_review.py` – 0 findings
- [x] `backend/coach/migrations/0005_season_model.py` – 0 findings
- [x] `backend/coach/migrations/0006_usage_cache_tokens.py` – 0 findings
- [x] `backend/coach/migrations/0007_alter_aiusagerecord_purpose.py` – 0 findings
- [x] `backend/coach/migrations/0008_week_and_chat_model.py` – 0 findings
- [x] `backend/coach/migrations/0009_model_price.py` – 0 findings
- [x] `backend/coach/migrations/__init__.py` – 0 findings

### backend/coach/providers/ [x]

- [x] `backend/coach/providers/__init__.py` – 0 findings
- [x] `backend/coach/providers/anthropic.py` – 0 findings
- [x] `backend/coach/providers/base.py` – 0 findings
- [x] `backend/coach/providers/openai_compatible.py` – 1 finding
- [x] `backend/coach/providers/transport.py` – 2 findings

### backend/coach/tests/ [x]

- [x] `backend/coach/tests/__init__.py` – 0 findings
- [x] `backend/coach/tests/conftest.py` – 0 findings
- [x] `backend/coach/tests/fake_providers.py` – 0 findings
- [x] `backend/coach/tests/test_answers.py` – 2 findings
- [x] `backend/coach/tests/test_anthropic.py` – 0 findings
- [x] `backend/coach/tests/test_cacheable_prompts.py` – 0 findings
- [x] `backend/coach/tests/test_costs_api.py` – 1 finding
- [x] `backend/coach/tests/test_endpoints.py` – 1 finding
- [x] `backend/coach/tests/test_models.py` – 2 findings
- [x] `backend/coach/tests/test_openai_compatible.py` – 1 finding
- [x] `backend/coach/tests/test_pricing.py` – 0 findings
- [x] `backend/coach/tests/test_provider_api.py` – 5 findings
- [x] `backend/coach/tests/test_services.py` – 5 findings

### backend/config/ [x]

- [x] `backend/config/__init__.py` – 0 findings
- [x] `backend/config/asgi.py` – 0 findings
- [x] `backend/config/settings.py` – 5 findings
- [x] `backend/config/settings_test.py` – 2 findings
- [x] `backend/config/urls.py` – 0 findings
- [x] `backend/config/wsgi.py` – 0 findings

### backend/core/ [x]

- [x] `backend/core/__init__.py` – 0 findings
- [x] `backend/core/apps.py` – 0 findings
- [x] `backend/core/backup.py` – 8 findings
- [x] `backend/core/backup_crypto.py` – 0 findings
- [x] `backend/core/checks.py` – 0 findings
- [x] `backend/core/encryption.py` – 0 findings
- [x] `backend/core/fields.py` – 0 findings
- [x] `backend/core/models.py` – 0 findings
- [x] `backend/core/permissions.py` – 0 findings
- [x] `backend/core/testing.py` – 0 findings
- [x] `backend/core/views.py` – 0 findings

### backend/core/management/ [x]

- [x] `backend/core/management/__init__.py` – 0 findings

### backend/core/management/commands/ [x]

- [x] `backend/core/management/commands/__init__.py` – 0 findings
- [x] `backend/core/management/commands/backup_db.py` – 0 findings
- [x] `backend/core/management/commands/restore_db.py` – 2 findings
- [x] `backend/core/management/commands/run_backups.py` – 1 finding

### backend/core/tests/ [x]

- [x] `backend/core/tests/__init__.py` – 0 findings
- [x] `backend/core/tests/test_backup_crypto.py` – 1 finding
- [x] `backend/core/tests/test_backup_restore_e2e.py` – 2 findings
- [x] `backend/core/tests/test_backup_service.py` – 2 findings
- [x] `backend/core/tests/test_docs.py` – 0 findings
- [x] `backend/core/tests/test_encryption.py` – 1 finding
- [x] `backend/core/tests/test_fields.py` – 0 findings
- [x] `backend/core/tests/test_health.py` – 0 findings
- [x] `backend/core/tests/test_owned.py` – 0 findings
- [x] `backend/core/tests/test_production_settings.py` – 0 findings
- [x] `backend/core/tests/test_restore_command.py` – 5 findings
- [x] `backend/core/tests/test_run_backups.py` – 1 finding

### backend/core/tests/sample/ [x]

- [x] `backend/core/tests/sample/__init__.py` – 0 findings
- [x] `backend/core/tests/sample/apps.py` – 0 findings
- [x] `backend/core/tests/sample/models.py` – 0 findings
- [x] `backend/core/tests/sample/urls.py` – 0 findings
- [x] `backend/core/tests/sample/views.py` – 2 findings

### backend/core/tests/sample/migrations/ [x]

- [x] `backend/core/tests/sample/migrations/0001_initial.py` – 0 findings
- [x] `backend/core/tests/sample/migrations/0002_credential.py` – 1 finding
- [x] `backend/core/tests/sample/migrations/__init__.py` – 0 findings

### backend/dashboard/ [x]

- [x] `backend/dashboard/__init__.py` – 0 findings
- [x] `backend/dashboard/apps.py` – 0 findings
- [x] `backend/dashboard/overview.py` – 1 finding
- [x] `backend/dashboard/serializers.py` – 0 findings
- [x] `backend/dashboard/setup.py` – 0 findings
- [x] `backend/dashboard/summary.py` – 2 findings
- [x] `backend/dashboard/urls.py` – 0 findings
- [x] `backend/dashboard/views.py` – 1 finding

### backend/dashboard/tests/ [x]

- [x] `backend/dashboard/tests/__init__.py` – 0 findings
- [x] `backend/dashboard/tests/conftest.py` – 0 findings
- [x] `backend/dashboard/tests/test_api.py` – 1 finding
- [x] `backend/dashboard/tests/test_docs.py` – 0 findings
- [x] `backend/dashboard/tests/test_overview.py` – 1 finding
- [x] `backend/dashboard/tests/test_setup.py` – 0 findings
- [x] `backend/dashboard/tests/test_summary.py` – 0 findings

### backend/goals/ [x]

- [x] `backend/goals/__init__.py` – 0 findings
- [x] `backend/goals/apps.py` – 0 findings
- [x] `backend/goals/assessing.py` – 0 findings
- [x] `backend/goals/models.py` – 0 findings
- [x] `backend/goals/realism.py` – 0 findings
- [x] `backend/goals/serializers.py` – 2 findings
- [x] `backend/goals/services.py` – 0 findings
- [x] `backend/goals/urls.py` – 0 findings
- [x] `backend/goals/views.py` – 0 findings

### backend/goals/migrations/ [x]

- [x] `backend/goals/migrations/0001_initial.py` – 2 findings
- [x] `backend/goals/migrations/0002_priority_preparation.py` – 0 findings
- [x] `backend/goals/migrations/__init__.py` – 0 findings

### backend/goals/tests/ [x]

- [x] `backend/goals/tests/__init__.py` – 0 findings
- [x] `backend/goals/tests/conftest.py` – 0 findings
- [x] `backend/goals/tests/test_assessing.py` – 1 finding
- [x] `backend/goals/tests/test_docs.py` – 1 finding
- [x] `backend/goals/tests/test_goals_api.py` – 4 findings
- [x] `backend/goals/tests/test_models.py` – 1 finding
- [x] `backend/goals/tests/test_realism.py` – 2 findings
- [x] `backend/goals/tests/test_services.py` – 2 findings

### backend/integrations/ [x]

- [x] `backend/integrations/__init__.py` – 0 findings
- [x] `backend/integrations/apps.py` – 0 findings
- [x] `backend/integrations/intervals.py` – 6 findings
- [x] `backend/integrations/models.py` – 0 findings
- [x] `backend/integrations/serializers.py` – 0 findings
- [x] `backend/integrations/services.py` – 3 findings
- [x] `backend/integrations/throttles.py` – 0 findings
- [x] `backend/integrations/urls.py` – 0 findings
- [x] `backend/integrations/views.py` – 1 finding

### backend/integrations/migrations/ [x]

- [x] `backend/integrations/migrations/0001_initial.py` – 0 findings
- [x] `backend/integrations/migrations/0002_intervals_sync_fields.py` – 0 findings
- [x] `backend/integrations/migrations/__init__.py` – 0 findings

### backend/integrations/tests/ [x]

- [x] `backend/integrations/tests/__init__.py` – 0 findings
- [x] `backend/integrations/tests/conftest.py` – 0 findings
- [x] `backend/integrations/tests/fake_intervals.py` – 0 findings
- [x] `backend/integrations/tests/test_connection_api.py` – 1 finding
- [x] `backend/integrations/tests/test_intervals.py` – 6 findings
- [x] `backend/integrations/tests/test_models.py` – 0 findings
- [x] `backend/integrations/tests/test_services.py` – 0 findings

### backend/jobs/ [x]

- [x] `backend/jobs/__init__.py` – 0 findings
- [x] `backend/jobs/apps.py` – 0 findings
- [x] `backend/jobs/models.py` – 1 finding
- [x] `backend/jobs/runner.py` – 5 findings
- [x] `backend/jobs/schedule.py` – 3 findings
- [x] `backend/jobs/serializers.py` – 0 findings
- [x] `backend/jobs/services.py` – 2 findings
- [x] `backend/jobs/urls.py` – 0 findings
- [x] `backend/jobs/views.py` – 2 findings

### backend/jobs/management/ [x]

- [x] `backend/jobs/management/__init__.py` – 0 findings

### backend/jobs/management/commands/ [x]

- [x] `backend/jobs/management/commands/__init__.py` – 0 findings
- [x] `backend/jobs/management/commands/draft_next_week.py` – 2 findings
- [x] `backend/jobs/management/commands/review_weeks.py` – 0 findings
- [x] `backend/jobs/management/commands/run_scheduler.py` – 1 finding
- [x] `backend/jobs/management/commands/sync_activities.py` – 1 finding

### backend/jobs/migrations/ [x]

- [x] `backend/jobs/migrations/0001_initial.py` – 3 findings
- [x] `backend/jobs/migrations/__init__.py` – 0 findings

### backend/jobs/tests/ [x]

- [x] `backend/jobs/tests/__init__.py` – 0 findings
- [x] `backend/jobs/tests/conftest.py` – 1 finding
- [x] `backend/jobs/tests/test_api.py` – 0 findings
- [x] `backend/jobs/tests/test_commands.py` – 3 findings
- [x] `backend/jobs/tests/test_docs.py` – 3 findings
- [x] `backend/jobs/tests/test_models.py` – 0 findings
- [x] `backend/jobs/tests/test_runner_sync.py` – 2 findings
- [x] `backend/jobs/tests/test_runner_weekly.py` – 2 findings
- [x] `backend/jobs/tests/test_schedule.py` – 5 findings

### backend/planning/ [x]

- [x] `backend/planning/__init__.py` – 0 findings
- [x] `backend/planning/apps.py` – 0 findings
- [x] `backend/planning/briefing.py` – 2 findings
- [x] `backend/planning/context.py` – 1 finding
- [x] `backend/planning/editing.py` – 0 findings
- [x] `backend/planning/export.py` – 0 findings
- [x] `backend/planning/generation.py` – 1 finding
- [x] `backend/planning/load.py` – 2 findings
- [x] `backend/planning/models.py` – 3 findings
- [x] `backend/planning/prompt.py` – 1 finding
- [x] `backend/planning/push.py` – 2 findings
- [x] `backend/planning/rules.py` – 5 findings
- [x] `backend/planning/schema.py` – 4 findings
- [x] `backend/planning/serializers.py` – 0 findings
- [x] `backend/planning/services.py` – 0 findings
- [x] `backend/planning/targets.py` – 0 findings
- [x] `backend/planning/throttles.py` – 0 findings
- [x] `backend/planning/urls.py` – 0 findings
- [x] `backend/planning/validation.py` – 0 findings
- [x] `backend/planning/views.py` – 4 findings

### backend/planning/migrations/ [x]

- [x] `backend/planning/migrations/0001_initial.py` – 1 finding
- [x] `backend/planning/migrations/0002_time_of_day_and_stretching.py` – 0 findings
- [x] `backend/planning/migrations/0003_workoutexport.py` – 0 findings
- [x] `backend/planning/migrations/0004_plannedworkout_lineage.py` – 1 finding
- [x] `backend/planning/migrations/0005_exercises.py` – 0 findings
- [x] `backend/planning/migrations/0006_weeklyplan_note.py` – 0 findings
- [x] `backend/planning/migrations/__init__.py` – 0 findings

### backend/planning/tests/ [x]

- [x] `backend/planning/tests/__init__.py` – 0 findings
- [x] `backend/planning/tests/conftest.py` – 0 findings
- [x] `backend/planning/tests/fake_calendar.py` – 0 findings
- [x] `backend/planning/tests/scripted.py` – 1 finding
- [-] `backend/planning/tests/test_api.py` – too large
- [-] `backend/planning/tests/test_briefing.py` – too large
- [x] `backend/planning/tests/test_context.py` – 3 findings
- [x] `backend/planning/tests/test_docs.py` – 5 findings
- [x] `backend/planning/tests/test_editing.py` – 4 findings
- [x] `backend/planning/tests/test_export.py` – 2 findings
- [x] `backend/planning/tests/test_generation.py` – 3 findings
- [x] `backend/planning/tests/test_load.py` – 1 finding
- [x] `backend/planning/tests/test_migration_lineage.py` – 0 findings
- [x] `backend/planning/tests/test_models.py` – 3 findings
- [x] `backend/planning/tests/test_prompt.py` – 2 findings
- [x] `backend/planning/tests/test_push.py` – 4 findings
- [x] `backend/planning/tests/test_rules_capacity.py` – 4 findings
- [-] `backend/planning/tests/test_rules_rhythm.py` – too large
- [x] `backend/planning/tests/test_rules_season.py` – 2 findings
- [x] `backend/planning/tests/test_schema.py` – 4 findings
- [x] `backend/planning/tests/test_services.py` – 3 findings
- [x] `backend/planning/tests/test_targets.py` – 0 findings
- [x] `backend/planning/tests/test_validation.py` – 1 finding

### backend/reviews/ [x]

- [x] `backend/reviews/__init__.py` – 0 findings
- [x] `backend/reviews/apps.py` – 0 findings
- [x] `backend/reviews/briefing.py` – 1 finding
- [x] `backend/reviews/commenting.py` – 0 findings
- [x] `backend/reviews/comparison.py` – 0 findings
- [x] `backend/reviews/matching.py` – 0 findings
- [x] `backend/reviews/models.py` – 1 finding
- [x] `backend/reviews/prompt.py` – 1 finding
- [x] `backend/reviews/serializers.py` – 1 finding
- [x] `backend/reviews/services.py` – 1 finding
- [x] `backend/reviews/throttles.py` – 1 finding
- [x] `backend/reviews/urls.py` – 0 findings
- [x] `backend/reviews/views.py` – 6 findings

### backend/reviews/migrations/ [x]

- [x] `backend/reviews/migrations/0001_initial.py` – 2 findings
- [x] `backend/reviews/migrations/0002_weekcomment.py` – 1 finding
- [x] `backend/reviews/migrations/0003_weekfeedback_verdict.py` – 0 findings
- [x] `backend/reviews/migrations/__init__.py` – 0 findings

### backend/reviews/tests/ [x]

- [x] `backend/reviews/tests/__init__.py` – 0 findings
- [x] `backend/reviews/tests/builders.py` – 0 findings
- [x] `backend/reviews/tests/conftest.py` – 0 findings
- [x] `backend/reviews/tests/test_api.py` – 2 findings
- [x] `backend/reviews/tests/test_briefing.py` – 1 finding
- [x] `backend/reviews/tests/test_carry_over.py` – 1 finding
- [x] `backend/reviews/tests/test_comment_api.py` – 2 findings
- [x] `backend/reviews/tests/test_commenting.py` – 2 findings
- [x] `backend/reviews/tests/test_comparison.py` – 1 finding
- [x] `backend/reviews/tests/test_corrections_api.py` – 1 finding
- [x] `backend/reviews/tests/test_docs.py` – 1 finding
- [x] `backend/reviews/tests/test_feedback_api.py` – 3 findings
- [x] `backend/reviews/tests/test_matching.py` – 0 findings
- [x] `backend/reviews/tests/test_models.py` – 1 finding
- [x] `backend/reviews/tests/test_prompt.py` – 2 findings
- [x] `backend/reviews/tests/test_services.py` – 1 finding

### backend/season/ [x]

- [x] `backend/season/__init__.py` – 0 findings
- [x] `backend/season/absences.py` – 0 findings
- [x] `backend/season/apps.py` – 0 findings
- [x] `backend/season/briefing.py` – 2 findings
- [x] `backend/season/deviation.py` – 0 findings
- [x] `backend/season/done.py` – 1 finding
- [x] `backend/season/generation.py` – 1 finding
- [x] `backend/season/inputs.py` – 0 findings
- [x] `backend/season/load.py` – 0 findings
- [x] `backend/season/models.py` – 1 finding
- [x] `backend/season/prompt.py` – 1 finding
- [x] `backend/season/reassessment.py` – 0 findings
- [x] `backend/season/rules.py` – 0 findings
- [x] `backend/season/schema.py` – 1 finding
- [x] `backend/season/serializers.py` – 0 findings
- [x] `backend/season/services.py` – 0 findings
- [x] `backend/season/skeleton.py` – 2 findings
- [x] `backend/season/snapshots.py` – 0 findings
- [x] `backend/season/storage.py` – 1 finding
- [x] `backend/season/throttles.py` – 1 finding
- [x] `backend/season/urls.py` – 0 findings
- [x] `backend/season/views.py` – 2 findings
- [x] `backend/season/weeks.py` – 2 findings

### backend/season/migrations/ [x]

- [x] `backend/season/migrations/0001_initial.py` – 1 finding
- [x] `backend/season/migrations/0002_plan_request.py` – 0 findings
- [x] `backend/season/migrations/0003_plan_input_snapshot.py` – 1 finding
- [x] `backend/season/migrations/__init__.py` – 0 findings

### backend/season/tests/ [x]

- [x] `backend/season/tests/__init__.py` – 0 findings
- [x] `backend/season/tests/conftest.py` – 0 findings
- [x] `backend/season/tests/test_api.py` – 2 findings
- [x] `backend/season/tests/test_briefing.py` – 3 findings
- [x] `backend/season/tests/test_deviation.py` – 1 finding
- [x] `backend/season/tests/test_docs.py` – 2 findings
- [x] `backend/season/tests/test_done.py` – 0 findings
- [x] `backend/season/tests/test_generation.py` – 4 findings
- [x] `backend/season/tests/test_inputs.py` – 0 findings
- [x] `backend/season/tests/test_load.py` – 1 finding
- [x] `backend/season/tests/test_models.py` – 1 finding
- [x] `backend/season/tests/test_plans_api.py` – 3 findings
- [x] `backend/season/tests/test_prompt.py` – 2 findings
- [x] `backend/season/tests/test_reassessment.py` – 1 finding
- [x] `backend/season/tests/test_reassessment_acceptance.py` – 3 findings
- [x] `backend/season/tests/test_reassessment_api.py` – 1 finding
- [x] `backend/season/tests/test_rules.py` – 3 findings
- [x] `backend/season/tests/test_schema.py` – 3 findings
- [x] `backend/season/tests/test_services.py` – 0 findings
- [x] `backend/season/tests/test_skeleton.py` – 1 finding
- [x] `backend/season/tests/test_snapshots.py` – 1 finding
- [x] `backend/season/tests/test_weeks.py` – 3 findings

### backend/templates/account/email/ [x]

- [x] `backend/templates/account/email/unknown_account_message.txt` – 0 findings

### backend/templates/accounts/email/ [x]

- [x] `backend/templates/accounts/email/invitation_message.txt` – 0 findings
- [x] `backend/templates/accounts/email/invitation_subject.txt` – 0 findings

### backend/tests/ [x]

- [x] `backend/tests/test_database.py` – 0 findings
- [x] `backend/tests/test_health.py` – 0 findings

### backend/wellness/ [x]

- [x] `backend/wellness/__init__.py` – 0 findings
- [x] `backend/wellness/apps.py` – 0 findings
- [x] `backend/wellness/models.py` – 0 findings
- [x] `backend/wellness/summary.py` – 4 findings
- [x] `backend/wellness/sync.py` – 4 findings

### backend/wellness/migrations/ [x]

- [x] `backend/wellness/migrations/0001_initial.py` – 0 findings
- [x] `backend/wellness/migrations/__init__.py` – 0 findings

### backend/wellness/tests/ [x]

- [x] `backend/wellness/tests/__init__.py` – 0 findings
- [x] `backend/wellness/tests/test_models.py` – 1 finding
- [x] `backend/wellness/tests/test_summary.py` – 1 finding
- [x] `backend/wellness/tests/test_sync.py` – 0 findings

### deploy/ [x]

- [x] `deploy/Caddyfile` – 2 findings

### docs/ [x]

- [x] `docs/ROADMAP.md` – 2 findings
- [x] `docs/account-data.md` – 0 findings
- [x] `docs/background-jobs.md` – 1 finding
- [x] `docs/backup-and-restore.md` – 2 findings
- [x] `docs/coach.md` – 1 finding
- [x] `docs/deployment.md` – 2 findings
- [x] `docs/goals.md` – 0 findings
- [x] `docs/invitations.md` – 4 findings
- [x] `docs/phase0-intervals.md` – 1 finding
- [x] `docs/season.md` – 0 findings
- [-] `docs/weekly-plan.md` – too large
- [x] `docs/wellness.md` – 3 findings

### frontend/ [x]

- [x] `frontend/.dockerignore` – 0 findings
- [x] `frontend/.editorconfig` – 0 findings
- [x] `frontend/.gitignore` – 0 findings
- [x] `frontend/.postcssrc.json` – 0 findings
- [x] `frontend/.prettierrc` – 0 findings
- [x] `frontend/Caddyfile` – 3 findings
- [x] `frontend/Dockerfile` – 1 finding
- [x] `frontend/README.md` – 0 findings
- [x] `frontend/angular.json` – 0 findings
- [x] `frontend/eslint.config.js` – 0 findings
- [x] `frontend/ngsw-config.json` – 0 findings
- [-] `frontend/package-lock.json` – lockfile
- [x] `frontend/package.json` – 0 findings
- [x] `frontend/proxy.conf.json` – 0 findings
- [x] `frontend/tsconfig.app.json` – 0 findings
- [x] `frontend/tsconfig.json` – 0 findings
- [x] `frontend/tsconfig.spec.json` – 0 findings

### frontend/public/ [x]

- [-] `frontend/public/apple-touch-icon.png` – binary or not UTF-8
- [-] `frontend/public/favicon.ico` – binary or not UTF-8
- [-] `frontend/public/logo.png` – binary or not UTF-8
- [x] `frontend/public/manifest.webmanifest` – 0 findings

### frontend/public/icons/ [x]

- [-] `frontend/public/icons/icon-192.png` – binary or not UTF-8
- [-] `frontend/public/icons/icon-512.png` – binary or not UTF-8
- [-] `frontend/public/icons/icon-maskable-512.png` – binary or not UTF-8

### frontend/src/ [x]

- [x] `frontend/src/index.html` – 0 findings
- [x] `frontend/src/main.ts` – 1 finding
- [x] `frontend/src/styles.css` – 4 findings

### frontend/src/app/ [x]

- [x] `frontend/src/app/app.config.ts` – 0 findings
- [x] `frontend/src/app/app.html` – 0 findings
- [x] `frontend/src/app/app.routes.spec.ts` – 2 findings
- [x] `frontend/src/app/app.routes.ts` – 1 finding
- [x] `frontend/src/app/app.spec.ts` – 0 findings
- [x] `frontend/src/app/app.ts` – 0 findings
- [x] `frontend/src/app/manifest.spec.ts` – 0 findings
- [x] `frontend/src/app/ngsw-config.spec.ts` – 1 finding
- [x] `frontend/src/app/styles.d.ts` – 1 finding
- [x] `frontend/src/app/styles.spec.ts` – 3 findings

### frontend/src/app/core/activities/ [x]

- [x] `frontend/src/app/core/activities/activities-api.spec.ts` – 4 findings
- [x] `frontend/src/app/core/activities/activities-api.ts` – 3 findings
- [x] `frontend/src/app/core/activities/activities-models.ts` – 1 finding

### frontend/src/app/core/admin/ [x]

- [x] `frontend/src/app/core/admin/invitations-api.spec.ts` – 2 findings
- [x] `frontend/src/app/core/admin/invitations-api.ts` – 2 findings
- [x] `frontend/src/app/core/admin/invitations-models.ts` – 0 findings

### frontend/src/app/core/api/ [x]

- [x] `frontend/src/app/core/api/api-providers.spec.ts` – 0 findings
- [x] `frontend/src/app/core/api/api-providers.ts` – 0 findings
- [x] `frontend/src/app/core/api/coach-replies.ts` – 4 findings

### frontend/src/app/core/athlete/ [x]

- [x] `frontend/src/app/core/athlete/athlete-api.spec.ts` – 2 findings
- [x] `frontend/src/app/core/athlete/athlete-api.ts` – 6 findings
- [x] `frontend/src/app/core/athlete/athlete-models.ts` – 0 findings

### frontend/src/app/core/auth/ [x]

- [x] `frontend/src/app/core/auth/auth-api.spec.ts` – 1 finding
- [x] `frontend/src/app/core/auth/auth-api.ts` – 4 findings
- [x] `frontend/src/app/core/auth/auth-guards.spec.ts` – 1 finding
- [x] `frontend/src/app/core/auth/auth-guards.ts` – 0 findings
- [x] `frontend/src/app/core/auth/auth-models.ts` – 0 findings
- [x] `frontend/src/app/core/auth/auth-store.spec.ts` – 2 findings
- [x] `frontend/src/app/core/auth/auth-store.ts` – 2 findings

### frontend/src/app/core/auth/testing/ [x]

- [x] `frontend/src/app/core/auth/testing/auth-store-stub.ts` – 3 findings

### frontend/src/app/core/availability/ [x]

- [-] `frontend/src/app/core/availability/availability-api.spec.ts` – too large
- [x] `frontend/src/app/core/availability/availability-api.ts` – 6 findings
- [x] `frontend/src/app/core/availability/availability-models.ts` – 2 findings

### frontend/src/app/core/chat/ [x]

- [x] `frontend/src/app/core/chat/chat-api.spec.ts` – 2 findings
- [x] `frontend/src/app/core/chat/chat-api.ts` – 2 findings
- [x] `frontend/src/app/core/chat/chat-models.ts` – 0 findings

### frontend/src/app/core/coach/ [x]

- [x] `frontend/src/app/core/coach/coach-api.spec.ts` – 1 finding
- [x] `frontend/src/app/core/coach/coach-api.ts` – 5 findings
- [x] `frontend/src/app/core/coach/coach-models.ts` – 1 finding

### frontend/src/app/core/dashboard/ [x]

- [x] `frontend/src/app/core/dashboard/dashboard-api.spec.ts` – 2 findings
- [x] `frontend/src/app/core/dashboard/dashboard-api.ts` – 6 findings
- [x] `frontend/src/app/core/dashboard/dashboard-models.ts` – 0 findings

### frontend/src/app/core/goals/ [x]

- [x] `frontend/src/app/core/goals/goals-api.spec.ts` – 2 findings
- [x] `frontend/src/app/core/goals/goals-api.ts` – 3 findings
- [x] `frontend/src/app/core/goals/goals-models.ts` – 1 finding

### frontend/src/app/core/integrations/ [x]

- [x] `frontend/src/app/core/integrations/intervals-api.spec.ts` – 1 finding
- [x] `frontend/src/app/core/integrations/intervals-api.ts` – 2 findings
- [x] `frontend/src/app/core/integrations/intervals-models.ts` – 0 findings

### frontend/src/app/core/jobs/ [x]

- [x] `frontend/src/app/core/jobs/jobs-api.spec.ts` – 2 findings
- [x] `frontend/src/app/core/jobs/jobs-api.ts` – 5 findings
- [x] `frontend/src/app/core/jobs/jobs-models.ts` – 0 findings

### frontend/src/app/core/network/ [x]

- [x] `frontend/src/app/core/network/online-status.spec.ts` – 0 findings
- [x] `frontend/src/app/core/network/online-status.ts` – 2 findings

### frontend/src/app/core/planning/ [x]

- [-] `frontend/src/app/core/planning/planning-api.spec.ts` – too large
- [x] `frontend/src/app/core/planning/planning-api.ts` – 3 findings
- [x] `frontend/src/app/core/planning/planning-models.ts` – 1 finding

### frontend/src/app/core/review/ [x]

- [x] `frontend/src/app/core/review/review-api.spec.ts` – 2 findings
- [x] `frontend/src/app/core/review/review-api.ts` – 3 findings
- [x] `frontend/src/app/core/review/review-models.ts` – 1 finding

### frontend/src/app/core/season/ [x]

- [x] `frontend/src/app/core/season/season-api.spec.ts` – 6 findings
- [x] `frontend/src/app/core/season/season-api.ts` – 8 findings
- [x] `frontend/src/app/core/season/season-models.ts` – 0 findings

### frontend/src/app/core/theme/ [x]

- [x] `frontend/src/app/core/theme/theme-store.spec.ts` – 1 finding
- [x] `frontend/src/app/core/theme/theme-store.ts` – 1 finding

### frontend/src/app/core/update/ [x]

- [x] `frontend/src/app/core/update/update-notice.spec.ts` – 1 finding
- [x] `frontend/src/app/core/update/update-notice.ts` – 0 findings

### frontend/src/app/features/activities/ [x]

- [x] `frontend/src/app/features/activities/activities-page.css` – 2 findings
- [x] `frontend/src/app/features/activities/activities-page.html` – 1 finding
- [x] `frontend/src/app/features/activities/activities-page.spec.ts` – 3 findings
- [x] `frontend/src/app/features/activities/activities-page.ts` – 1 finding
- [x] `frontend/src/app/features/activities/activity-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/activities/activity-format.ts` – 0 findings
- [x] `frontend/src/app/features/activities/manual-activity-form.css` – 0 findings
- [x] `frontend/src/app/features/activities/manual-activity-form.html` – 0 findings
- [x] `frontend/src/app/features/activities/manual-activity-form.spec.ts` – 0 findings
- [x] `frontend/src/app/features/activities/manual-activity-form.ts` – 0 findings
- [x] `frontend/src/app/features/activities/manual-activity-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/activities/manual-activity-format.ts` – 1 finding

### frontend/src/app/features/admin/ [x]

- [x] `frontend/src/app/features/admin/invitations-page.css` – 0 findings
- [x] `frontend/src/app/features/admin/invitations-page.html` – 0 findings
- [x] `frontend/src/app/features/admin/invitations-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/admin/invitations-page.ts` – 1 finding

### frontend/src/app/features/athlete/ [x]

- [x] `frontend/src/app/features/athlete/appearance-panel.css` – 0 findings
- [x] `frontend/src/app/features/athlete/appearance-panel.html` – 0 findings
- [x] `frontend/src/app/features/athlete/appearance-panel.spec.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/appearance-panel.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/athlete-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/athlete-format.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/athlete-page.css` – 0 findings
- [x] `frontend/src/app/features/athlete/athlete-page.html` – 0 findings
- [x] `frontend/src/app/features/athlete/athlete-page.spec.ts` – 1 finding
- [x] `frontend/src/app/features/athlete/athlete-page.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/best-times-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/best-times-format.ts` – 1 finding
- [x] `frontend/src/app/features/athlete/best-times-panel.html` – 0 findings
- [x] `frontend/src/app/features/athlete/best-times-panel.spec.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/best-times-panel.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/body-data-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/body-data-format.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/body-data-panel.css` – 0 findings
- [x] `frontend/src/app/features/athlete/body-data-panel.html` – 0 findings
- [x] `frontend/src/app/features/athlete/body-data-panel.spec.ts` – 0 findings
- [x] `frontend/src/app/features/athlete/body-data-panel.ts` – 1 finding

### frontend/src/app/features/auth/ [x]

- [x] `frontend/src/app/features/auth/login-mfa-page.html` – 0 findings
- [x] `frontend/src/app/features/auth/login-mfa-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/auth/login-mfa-page.ts` – 1 finding
- [x] `frontend/src/app/features/auth/login-page.html` – 0 findings
- [x] `frontend/src/app/features/auth/login-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/auth/login-page.ts` – 3 findings
- [x] `frontend/src/app/features/auth/password-match.ts` – 0 findings
- [x] `frontend/src/app/features/auth/password-reset-page.html` – 0 findings
- [x] `frontend/src/app/features/auth/password-reset-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/auth/password-reset-page.ts` – 0 findings
- [x] `frontend/src/app/features/auth/password-reset-request-page.html` – 0 findings
- [x] `frontend/src/app/features/auth/password-reset-request-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/auth/password-reset-request-page.ts` – 0 findings
- [x] `frontend/src/app/features/auth/signup-page.html` – 0 findings
- [x] `frontend/src/app/features/auth/signup-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/auth/signup-page.ts` – 0 findings
- [x] `frontend/src/app/features/auth/verify-email-page.html` – 0 findings
- [x] `frontend/src/app/features/auth/verify-email-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/auth/verify-email-page.ts` – 0 findings

### frontend/src/app/features/automation/ [x]

- [x] `frontend/src/app/features/automation/automation-page.css` – 0 findings
- [x] `frontend/src/app/features/automation/automation-page.html` – 0 findings
- [x] `frontend/src/app/features/automation/automation-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/automation/automation-page.ts` – 0 findings

### frontend/src/app/features/availability/ [x]

- [x] `frontend/src/app/features/availability/availability-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/availability-format.ts` – 0 findings
- [x] `frontend/src/app/features/availability/availability-page.css` – 0 findings
- [x] `frontend/src/app/features/availability/availability-page.html` – 0 findings
- [x] `frontend/src/app/features/availability/availability-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/availability-page.ts` – 1 finding
- [x] `frontend/src/app/features/availability/day-options.css` – 0 findings
- [x] `frontend/src/app/features/availability/day-options.html` – 0 findings
- [x] `frontend/src/app/features/availability/day-options.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/day-options.ts` – 0 findings
- [x] `frontend/src/app/features/availability/fixed-sessions-panel.css` – 0 findings
- [x] `frontend/src/app/features/availability/fixed-sessions-panel.html` – 0 findings
- [x] `frontend/src/app/features/availability/fixed-sessions-panel.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/fixed-sessions-panel.ts` – 1 finding
- [x] `frontend/src/app/features/availability/intensity-settings.css` – 0 findings
- [x] `frontend/src/app/features/availability/intensity-settings.html` – 0 findings
- [x] `frontend/src/app/features/availability/intensity-settings.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/intensity-settings.ts` – 0 findings
- [x] `frontend/src/app/features/availability/limitations-panel.css` – 0 findings
- [x] `frontend/src/app/features/availability/limitations-panel.html` – 0 findings
- [x] `frontend/src/app/features/availability/limitations-panel.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/limitations-panel.ts` – 1 finding
- [x] `frontend/src/app/features/availability/period-form.css` – 0 findings
- [x] `frontend/src/app/features/availability/period-form.html` – 0 findings
- [x] `frontend/src/app/features/availability/period-form.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/period-form.ts` – 0 findings
- [x] `frontend/src/app/features/availability/periods-panel.css` – 0 findings
- [x] `frontend/src/app/features/availability/periods-panel.html` – 0 findings
- [x] `frontend/src/app/features/availability/periods-panel.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/periods-panel.ts` – 1 finding
- [x] `frontend/src/app/features/availability/provider-line.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/provider-line.ts` – 0 findings
- [x] `frontend/src/app/features/availability/sport-preferences.css` – 0 findings
- [x] `frontend/src/app/features/availability/sport-preferences.html` – 0 findings
- [x] `frontend/src/app/features/availability/sport-preferences.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/sport-preferences.ts` – 0 findings
- [x] `frontend/src/app/features/availability/week-wishes.css` – 0 findings
- [x] `frontend/src/app/features/availability/week-wishes.html` – 0 findings
- [x] `frontend/src/app/features/availability/week-wishes.spec.ts` – 0 findings
- [x] `frontend/src/app/features/availability/week-wishes.ts` – 0 findings

### frontend/src/app/features/chat/ [x]

- [x] `frontend/src/app/features/chat/chat-page.html` – 1 finding
- [x] `frontend/src/app/features/chat/chat-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/chat/chat-page.ts` – 0 findings

### frontend/src/app/features/connections/ [x]

- [x] `frontend/src/app/features/connections/ai-costs-panel.css` – 0 findings
- [x] `frontend/src/app/features/connections/ai-costs-panel.html` – 0 findings
- [x] `frontend/src/app/features/connections/ai-costs-panel.spec.ts` – 1 finding
- [x] `frontend/src/app/features/connections/ai-costs-panel.ts` – 0 findings
- [x] `frontend/src/app/features/connections/ai-provider-panel.css` – 0 findings
- [x] `frontend/src/app/features/connections/ai-provider-panel.html` – 0 findings
- [x] `frontend/src/app/features/connections/ai-provider-panel.spec.ts` – 1 finding
- [x] `frontend/src/app/features/connections/ai-provider-panel.ts` – 2 findings
- [x] `frontend/src/app/features/connections/connections-page.css` – 0 findings
- [x] `frontend/src/app/features/connections/connections-page.html` – 0 findings
- [x] `frontend/src/app/features/connections/connections-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/connections/connections-page.ts` – 0 findings
- [x] `frontend/src/app/features/connections/known-endpoints.spec.ts` – 0 findings
- [x] `frontend/src/app/features/connections/known-endpoints.ts` – 0 findings

### frontend/src/app/features/dashboard/ [x]

- [x] `frontend/src/app/features/dashboard/dashboard-page.html` – 0 findings
- [x] `frontend/src/app/features/dashboard/dashboard-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/dashboard-page.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/minutes-chart.spec.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/minutes-chart.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/setup-checklist.spec.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/setup-checklist.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/stat-tile.spec.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/stat-tile.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/wellness-tile.spec.ts` – 0 findings
- [x] `frontend/src/app/features/dashboard/wellness-tile.ts` – 0 findings

### frontend/src/app/features/goals/ [x]

- [x] `frontend/src/app/features/goals/goal-form.css` – 0 findings
- [x] `frontend/src/app/features/goals/goal-form.html` – 0 findings
- [x] `frontend/src/app/features/goals/goal-form.spec.ts` – 0 findings
- [x] `frontend/src/app/features/goals/goal-form.ts` – 1 finding
- [x] `frontend/src/app/features/goals/goal-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/goals/goal-format.ts` – 0 findings
- [x] `frontend/src/app/features/goals/goals-page.css` – 0 findings
- [x] `frontend/src/app/features/goals/goals-page.html` – 0 findings
- [x] `frontend/src/app/features/goals/goals-page.spec.ts` – 1 finding
- [x] `frontend/src/app/features/goals/goals-page.ts` – 0 findings

### frontend/src/app/features/planning/ [x]

- [x] `frontend/src/app/features/planning/edit-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/planning/edit-format.ts` – 1 finding
- [x] `frontend/src/app/features/planning/plan-day.css` – 0 findings
- [x] `frontend/src/app/features/planning/plan-day.html` – 0 findings
- [x] `frontend/src/app/features/planning/plan-day.spec.ts` – 0 findings
- [x] `frontend/src/app/features/planning/plan-day.ts` – 0 findings
- [x] `frontend/src/app/features/planning/plan-editor.css` – 0 findings
- [x] `frontend/src/app/features/planning/plan-editor.html` – 0 findings
- [x] `frontend/src/app/features/planning/plan-editor.spec.ts` – 0 findings
- [x] `frontend/src/app/features/planning/plan-editor.ts` – 1 finding
- [x] `frontend/src/app/features/planning/plan-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/planning/plan-format.ts` – 0 findings
- [x] `frontend/src/app/features/planning/planning-page.css` – 0 findings
- [x] `frontend/src/app/features/planning/planning-page.html` – 0 findings
- [-] `frontend/src/app/features/planning/planning-page.spec.ts` – too large
- [x] `frontend/src/app/features/planning/planning-page.ts` – 1 finding
- [x] `frontend/src/app/features/planning/segment-editor.css` – 0 findings
- [x] `frontend/src/app/features/planning/segment-editor.html` – 0 findings
- [x] `frontend/src/app/features/planning/segment-editor.spec.ts` – 0 findings
- [x] `frontend/src/app/features/planning/segment-editor.ts` – 0 findings
- [x] `frontend/src/app/features/planning/workout-form.css` – 0 findings
- [x] `frontend/src/app/features/planning/workout-form.html` – 0 findings
- [x] `frontend/src/app/features/planning/workout-form.spec.ts` – 0 findings
- [x] `frontend/src/app/features/planning/workout-form.ts` – 1 finding

### frontend/src/app/features/review/ [x]

- [x] `frontend/src/app/features/review/coach-comment.css` – 0 findings
- [x] `frontend/src/app/features/review/coach-comment.html` – 0 findings
- [x] `frontend/src/app/features/review/coach-comment.spec.ts` – 0 findings
- [x] `frontend/src/app/features/review/coach-comment.ts` – 0 findings
- [x] `frontend/src/app/features/review/review-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/review/review-format.ts` – 0 findings
- [x] `frontend/src/app/features/review/review-page.css` – 0 findings
- [x] `frontend/src/app/features/review/review-page.html` – 0 findings
- [x] `frontend/src/app/features/review/review-page.spec.ts` – 1 finding
- [x] `frontend/src/app/features/review/review-page.ts` – 0 findings
- [x] `frontend/src/app/features/review/session-rating.css` – 0 findings
- [x] `frontend/src/app/features/review/session-rating.html` – 0 findings
- [x] `frontend/src/app/features/review/session-rating.spec.ts` – 0 findings
- [x] `frontend/src/app/features/review/session-rating.ts` – 0 findings
- [x] `frontend/src/app/features/review/week-feedback-form.css` – 0 findings
- [x] `frontend/src/app/features/review/week-feedback-form.html` – 0 findings
- [x] `frontend/src/app/features/review/week-feedback-form.spec.ts` – 0 findings
- [x] `frontend/src/app/features/review/week-feedback-form.ts` – 1 finding

### frontend/src/app/features/season/ [x]

- [x] `frontend/src/app/features/season/season-chart.css` – 0 findings
- [x] `frontend/src/app/features/season/season-chart.spec.ts` – 1 finding
- [x] `frontend/src/app/features/season/season-chart.ts` – 1 finding
- [x] `frontend/src/app/features/season/season-compare.spec.ts` – 0 findings
- [x] `frontend/src/app/features/season/season-compare.ts` – 0 findings
- [x] `frontend/src/app/features/season/season-format.spec.ts` – 0 findings
- [x] `frontend/src/app/features/season/season-format.ts` – 0 findings
- [x] `frontend/src/app/features/season/season-page.css` – 0 findings
- [x] `frontend/src/app/features/season/season-page.html` – 0 findings
- [-] `frontend/src/app/features/season/season-page.spec.ts` – too large
- [x] `frontend/src/app/features/season/season-page.ts` – 2 findings
- [x] `frontend/src/app/features/season/season-timeline.css` – 0 findings
- [x] `frontend/src/app/features/season/season-timeline.spec.ts` – 0 findings
- [x] `frontend/src/app/features/season/season-timeline.ts` – 0 findings

### frontend/src/app/features/security/ [x]

- [x] `frontend/src/app/features/security/data-export-panel.html` – 0 findings
- [x] `frontend/src/app/features/security/data-export-panel.spec.ts` – 1 finding
- [x] `frontend/src/app/features/security/data-export-panel.ts` – 0 findings
- [x] `frontend/src/app/features/security/delete-account-panel.html` – 0 findings
- [x] `frontend/src/app/features/security/delete-account-panel.spec.ts` – 1 finding
- [x] `frontend/src/app/features/security/delete-account-panel.ts` – 1 finding
- [x] `frontend/src/app/features/security/security-page.css` – 0 findings
- [x] `frontend/src/app/features/security/security-page.html` – 0 findings
- [x] `frontend/src/app/features/security/security-page.spec.ts` – 0 findings
- [x] `frontend/src/app/features/security/security-page.ts` – 0 findings

### frontend/src/app/layout/ [x]

- [x] `frontend/src/app/layout/navigation.spec.ts` – 0 findings
- [x] `frontend/src/app/layout/navigation.ts` – 0 findings
- [x] `frontend/src/app/layout/shell.css` – 2 findings
- [x] `frontend/src/app/layout/shell.html` – 0 findings
- [x] `frontend/src/app/layout/shell.spec.ts` – 0 findings
- [x] `frontend/src/app/layout/shell.ts` – 0 findings

### frontend/src/app/shared/ [x]

- [x] `frontend/src/app/shared/confirm-dialog.spec.ts` – 1 finding
- [x] `frontend/src/app/shared/confirm-dialog.ts` – 1 finding
- [x] `frontend/src/app/shared/icon.spec.ts` – 0 findings
- [x] `frontend/src/app/shared/icon.ts` – 0 findings
- [x] `frontend/src/app/shared/page-header.spec.ts` – 0 findings
- [x] `frontend/src/app/shared/page-header.ts` – 0 findings
- [x] `frontend/src/app/shared/qr-code.spec.ts` – 0 findings
- [x] `frontend/src/app/shared/qr-code.ts` – 0 findings
- [x] `frontend/src/app/shared/season-change-notice.spec.ts` – 0 findings
- [x] `frontend/src/app/shared/season-change-notice.ts` – 1 finding
- [x] `frontend/src/app/shared/version-chips.spec.ts` – 0 findings
- [x] `frontend/src/app/shared/version-chips.ts` – 0 findings

### frontend/src/app/testing/ [x]

- [x] `frontend/src/app/testing/dom.ts` – 1 finding

## Findings

F1 · warning · security · compose.dev.yaml:10 – compose.dev.yaml falls back to the hard-coded database password 'paceforge-dev' when POSTGRES_PASSWORD is unset, so the known credential is used by default.
F2 · warning · security · compose.prod.yaml:33 – compose.prod.yaml interpolates POSTGRES_PASSWORD unencoded into DATABASE_URL, so a password with reserved URL characters such as '@', ':' or '/' breaks the connection string or changes the parsed host.
F3 · informational · security · compose.prod.yaml:28 – compose.prod.yaml passes the whole .env file to the backend, scheduler and backup containers, so services that need only a few values also receive every secret.
F4 · informational · smell · compose.prod.yaml:33 – compose.prod.yaml repeats the same DATABASE_URL construction in the backend, scheduler and backup services, so a change to the connection format has to be made in three places.
F5 · warning · security · .github/workflows/ci.yml:37 – A Fernet-format ENCRYPTION_KEY is committed in plain text; if this value is ever reused outside CI, data encrypted with it can be decrypted by anyone with repository access.
F6 · informational · security · .github/workflows/ci.yml:36 – DJANGO_SECRET_KEY is hard-coded in the workflow; it is labelled throw-away, but it lives in version control and should be generated per run or stored as a secret.
F7 · informational · smell · .github/workflows/ci.yml:25 – The database password is hard-coded in the service definition and repeated in DATABASE_URL, so the same credential is maintained in two places that can drift apart.
F8 · warning · security · .github/workflows/ci.yml:55 – The PostgreSQL apt signing key is downloaded with sudo curl and trusted without verifying its fingerprint, so a tampered download would be installed as a trusted repository key.
F9 · informational · security · .github/workflows/ci.yml:110 – The postgres and caddy container images are referenced by mutable tag rather than digest, so the content behind them can change without a workflow change.
F10 · informational · security · backend/Dockerfile:2 – Both build stages use the mutable tag ghcr.io/astral-sh/uv:python3.14-trixie-slim without a digest pin, so the base image contents can change between builds.
F11 · informational · smell · backend/Dockerfile:44 – The HEALTHCHECK logic is a long inline Python one-liner that is hard to read and cannot be unit-tested.
F12 · informational · smell · backend/entrypoint.sh:8 – AUTO_MIGRATE defaults to true, so every web container runs migrate at startup and concurrent replicas can race on schema changes.
F13 · warning · security · backend/accounts/throttles.py:13 – InvitationEmailThrottle limits each admin account only, using the process-local cache, so it does not cap how many invitation emails reach one address as its docstring claims; several admins or several worker processes can each send within the limit.
F14 · warning · smell · backend/accounts/views.py:183 – DELETE_ERRORS[type(error)] raises KeyError for any AccountDeletionError subclass not in the mapping, so the request fails with a 500 instead of a handled 4xx response.
F15 · informational · smell · backend/accounts/views.py:84 – The assert isinstance(request.user, User) guard is repeated in four views and asserts are stripped under python -O, so the user type narrowing should come from one shared helper or permission.
F16 · informational · smell · backend/accounts/views.py:185 – logout(request._request) reaches into DRF's private _request attribute instead of using the public request API.
F17 · informational · security · backend/accounts/views.py:131 – AccountExportView, MeView and AccountDeleteView declare no permission_classes and rely on the global default, so the authentication requirement for these endpoints is not visible in this file.
F18 · informational · smell · backend/accounts/forms.py:21 – The REGISTRATION_MODE "invite_only" check is duplicated between this form and AccountAdapter.save_user as a raw string, so a mismatch in one place would silently skip invitation validation.
F19 · informational · smell · backend/accounts/throttles.py:7 – The same rate-limit docstring sentence is copied into all three throttle classes.
F20 · informational · security · backend/accounts/management/commands/reset_mfa.py:32 – The reset removes the second factor but leaves existing sessions valid, so a session an attacker obtained before a compromise-driven reset survives it.
F21 · informational · security · backend/accounts/management/commands/reset_mfa.py:29 – The command changes account security state but writes no audit record of who ran it or for which account beyond stdout.
F22 · warning · security · backend/accounts/management/commands/setup_admin.py:49 – The administrator-exists check runs outside any lock, so concurrent runs can both pass the re-check inside the transaction and create two administrators despite the comment implying otherwise.
F23 · informational · security · backend/accounts/management/commands/setup_admin.py:42 – The password read from an environment variable is visible to same-user processes via /proc/<pid>/environ and is inherited by child processes, which the help text does not mention.
F24 · warning · smell · backend/accounts/migrations/0003_encrypt_mfa_secrets.py:14 – The historical migration imports the live application module core.encryption, so later changes to PREFIX, encrypt or decrypt would silently change what this already-written migration does on fresh or rolled-back databases.
F25 · informational · security · backend/accounts/migrations/0003_encrypt_mfa_secrets.py:49 – The reverse path of decrypt_secrets writes TOTP secrets and recovery-code seeds back to the database in clear text, so rolling back this migration reintroduces the exposure it was meant to fix.
F26 · informational · security · backend/accounts/migrations/0003_encrypt_mfa_secrets.py:45 – The encrypt pass skips any stored value that starts with PREFIX, so a clear-text secret that happens to begin with that prefix would remain unencrypted without any error or log.
F27 · warning · security · backend/accounts/services/export.py:127 – The integrations section exports ProviderConnection without an exclude list, although the module says credentials must be excluded, so any token stored in a plain field ends up in the export.
F28 · informational · security · backend/accounts/services/deletion.py:77 – delete_account checks the password and MFA code with no attempt limit in this code, so brute force depends on a rate limit elsewhere that is not visible here.
F29 · informational · security · backend/accounts/services/invitations.py:71 – consume_invitation accepts email=None, so a leaked token can be redeemed by any account when the caller omits the email binding.
F30 · informational · security · backend/accounts/services/invitations.py:106 – build_invitation_url trusts a caller-supplied base_url, so invitation links point to an attacker's host if a caller derives it from the request Host header.
F31 · informational · smell · backend/accounts/services/deletion.py:61 – _delete_sessions decodes every unexpired session in the table on each deletion, so the cost grows with all users rather than the one account being deleted.
F32 · informational · smell · backend/accounts/services/invitations.py:40 – Token generation and TTL defaulting are duplicated between create_invitation and resend_invitation.
F33 · informational · smell · backend/accounts/services/export.py:79 – build_user_export loads all records of a user into memory and serialises them in one json.dumps call, which can get large for long activity histories.
F34 · warning · smell · backend/accounts/tests/test_deletion_service.py:34 – owned_models() uses OwnedModel.__subclasses__(), which returns only direct subclasses, so the deletion-completeness test silently skips any owned model that subclasses another concrete model.
F35 · warning · smell · backend/accounts/tests/test_deletion_service.py:26 – make_user and populate are imported from test_export_service instead of living in conftest, while other_user, add_secrets and enable_totp duplicate similar setup, and PASSWORD is redefined with a different value in several modules.
F36 · informational · smell · backend/accounts/tests/test_deletion_service.py – The parametrized wrong-code test accepts either InvalidMfaCodeError or MfaRequiredError, so a regression that changes the error for a blank code would still pass.
F37 · informational · smell · backend/accounts/tests/test_deletion_service.py – The test_expired_sessions_of_others_are_left_alone setup calls sign_in(bob) twice and only the second session is expired, which makes the intent hard to follow.
F38 · informational · smell · backend/accounts/tests/test_auth.py:104 – test_password_reset_flow accepts either HTTP 200 or 401 for the reset call, so the test does not pin down the expected result of the reset endpoint.
F39 · informational · smell · backend/accounts/tests/test_auth.py – test_password_reset_does_not_reveal_unknown_emails passes vacuously if no mail is sent, because it only asserts the absence of a reset link and never checks that a message was sent.
F40 · informational · smell · backend/accounts/tests/test_export_service.py – The assertions that no 'str(pk)' appears in the export text are prone to false positives when primary keys are small integers, since digits from dates, weights and other fields can match.
F41 · warning · smell · backend/accounts/tests/test_mfa_enforcement.py:27 – HttpResponse is imported only under TYPE_CHECKING but is used in the runtime annotation of admin_requests, so the module raises NameError at import on Python versions before 3.14.
F42 · warning · smell · backend/accounts/tests/test_mfa_enforcement.py:22 – The helper revoke_url creates a new invitation as a side effect, so its name hides that it has side effects and misleads readers about what the test sets up.
F43 · informational · smell · backend/accounts/tests/test_mfa_encryption.py – The teardown of the before_the_migration fixture duplicates the migrate_forward() helper instead of calling it.
F44 · informational · smell · backend/accounts/tests/test_registration.py – The error_codes helper is duplicated in test_registration.py, and types_of is duplicated in test_reset_mfa.py, instead of being shared through conftest.
F45 · informational · smell · backend/accounts/tests/test_registration.py – Status codes are compared as bare integers (400, 401) here while the rest of the suite uses HTTPStatus, which makes the assertions less readable.
F46 · warning · smell · backend/activities/strava.py:202 – A recording whose filename is longer than 1000 characters is read as a session without a recording and entered by hand, instead of being counted as unreadable.
F47 · warning · security · backend/activities/strava.py:386 – Every list line re-reads, unpacks, parses and hashes its recording before the duplicate check, so one file named on 100,000 lines multiplies the work of a single import request with no total limit.
F48 · informational · security · backend/activities/strava.py:230 – The number reader treats any comma as a decimal comma, so an English thousands separator such as 1,234.5 silently becomes 1.2345 instead of being rejected.
F49 · informational · smell · backend/activities/services.py – The find-duplicate, insert-in-transaction, and retry-on-IntegrityError block is repeated in import_activity, enter_activity and the sync module, so the race handling can drift apart.
F50 · warning · security · backend/activities/views.py:115 – The import view passes `str(error)` from `ActivityFileError` straight into the response, although the `_refused` docstring says nothing from the file is echoed and the texts are fixed; any parser message that includes file content is reflected to the caller.
F51 · informational · security · backend/activities/views.py:113 – The duplicate response returns `existing_id` of the matched activity, which leaks another user's activity ID if duplicate detection in `services` is not scoped to the requesting user.
F52 · informational · security · backend/activities/views.py:43 – `_user` relies on an `assert` to narrow `request.user` to `User`, and `python -O` strips asserts, so a misconfigured permission class would silently return an anonymous user typed as `User`.
F53 · warning · smell · backend/activities/views.py:133 – `ManualActivityView.post` does not call `refresh_estimates_safely` as `ActivityImportView.post` does, so manual entries may leave estimates stale unless `enter_activity` handles it, and the side effect's placement is inconsistent across views.
F54 · informational · smell · backend/activities/views.py:113 – The `DuplicateActivityError` handling is copied verbatim in the import and manual views, so the refusal logic is duplicated in two places.
F55 · informational · smell · backend/activities/views.py:105 – The upload size is checked in the view at line 105 and again through `services.FileTooLargeError` at line 110, so the same limit is enforced in two places.
F56 · informational · smell · backend/activities/views.py:17 – The module-level alias `integrations` for `integrations.services` is misleading next to the `integrations.views` and `integrations.intervals` imports, which use the package name directly.
F57 · warning · smell · backend/activities/management/commands/backfill_best_efforts.py:40 – The stored file is looked up with a separate query for each activity (N+1); fetch the files with select_related or a prefetch before the loop.
F58 · informational · smell · backend/activities/management/commands/backfill_best_efforts.py:45 – best_efforts_of returns None for failure and an empty result for no usable series, so the two cases are only told apart by the caller's branching.
F59 · informational · smell · backend/activities/management/commands/import_strava.py:27 – The email-to-account lookup and its CommandError are duplicated from backfill_best_efforts.py; move them into a shared helper.
F60 · warning · security · backend/activities/parsing/gpx.py – In gpx.py `_moment`, the UTC conversion via `values.moment` sits outside the `try`, so a timestamp such as 0001-01-01T00:00:00+01:00 raises OverflowError, which `feed` does not catch, so the upload fails with an unhandled exception instead of InvalidFileError.
F61 · warning · security · backend/activities/parsing/tcx.py:91 – tcx.py `_moment` catches only ValueError, and `_elapsed` adds up to 30 days to the start time, so dates near year 1 or 9999 raise OverflowError that escapes `feed` as an unhandled exception.
F62 · warning · security · backend/activities/parsing/series.py – `_text_number` accepts 'nan' and 'inf', and the series readers apply no plausibility bounds to power, distance or heart rate, unlike values.py, so non-finite or absurd values reach the Sample objects.
F63 · warning · smell · backend/activities/parsing/series.py – `tcx_series` and `fit_series` skip the single-activity and single-session checks that `parse_tcx` and `parse_fit` enforce, so a multi-activity or multi-session file yields one merged time series.
F64 · warning · smell · backend/activities/parsing/fit.py – `parse_fit` wraps the whole reader in `except Exception`, turning any bug in this module into 'damaged or incomplete', whereas tcx.py re-raises IndexError and KeyError to avoid exactly this.
F65 · warning · smell · backend/activities/parsing/series.py – `fit_series` repeats the FIT reading loop, the header and message caps and the error mapping of `parse_fit`, so every fix to one reader must be made in both places.
F66 · informational · smell · backend/activities/parsing/tcx.py:70 – The unparenthesised `except expat.ExpatError, UnicodeError:` is only valid from Python 3.14, so on older interpreters the module fails to import.
F67 · informational · smell · backend/activities/parsing/tcx.py – `_Reader.start` in tcx.py is a long elif chain of about ten branches that mixes element counting, depth checks and capture selection, which makes it hard to follow and test.
F68 · informational · smell · backend/activities/parsing/__init__.py – `parse_activity_file` and `parse_series` duplicate the FIT and XML dispatch logic and its error message.
F69 · informational · smell · backend/activities/parsing/__init__.py:26 – The comment about what may precede the first '<' describes `_XML_PREFIXES` but sits above `_GPX_ROOT`, which makes it misleading.
F70 · informational · smell · backend/activities/parsing/__init__.py – `_is_gpx` searches the first 4096 bytes for '<gpx', so a TCX file with that text in a comment is routed to the GPX reader and rejected as not a GPX file.
F71 · warning · smell · backend/activities/tests/test_compressed.py:124 – The bomb test types `settings` as `object` and silences the resulting attribute error with `# type: ignore[attr-defined]`, which hides a typing problem instead of fixing the fixture annotation.
F72 · warning · smell · backend/activities/tests/test_compressed.py:148 – The size-limit test repeats the same `settings: object` plus `# type: ignore[attr-defined]` pattern, so the typing workaround is duplicated.
F73 · informational · smell · backend/activities/tests/test_best_efforts_storage.py – The `alice` and `bob` fixtures are duplicated across test modules, and this module creates users without the `EmailAddress` record that the shared `make_user` helper in conftest.py creates.
F74 · informational · smell · backend/activities/tests/test_activities_api.py – The `alice` and `bob` fixtures duplicate the same definitions in other test modules instead of reusing a shared fixture.
F75 · informational · smell · backend/activities/tests/test_best_efforts_storage.py – The `hard_ride` helper re-imports `datetime`, `UTC` and `timedelta` inside the function even though the module already imports `datetime` and `UTC` at the top.
F76 · informational · smell · backend/activities/tests/test_best_efforts_storage.py – The test ends with `assert untouched.owner == bob`, which checks a fixture detail and does not verify the refresh behaviour under test.
F77 · informational · smell · backend/activities/tests/fit_builder.py – The `activity_file` builder is a long function with sixteen parameters and several branches, which makes it hard to follow and to change safely.
F78 · informational · smell · backend/activities/tests/fit_builder.py – The `_width` helper accepts a `value` argument that it never uses.
F79 · informational · smell · backend/activities/tests/tcx_builder.py – The `_optional` helper receives the same string as both `tag` and `wrapper` for the heart-rate elements, so the `wrapper` parameter adds no information and its name is misleading.
F80 · informational · smell · backend/activities/tests/tcx_builder.py – The `big_document` helper is not used by any of the test files provided and may be dead code.
F81 · informational · smell · backend/activities/tests/gpx_builder.py – The `gpx_document` and `point` helpers are not used by any of the test files provided, so this module may be dead code.
F82 · warning · smell · backend/activities/tests/test_manual_api.py:315 – The race test's fake find_duplicate uses `next(answers, None) or real(...)`, so the first call falls through to the real lookup, which finds the existing row; the insert-race path is never exercised despite the test name.
F83 · warning · smell · backend/activities/tests/test_duplicates.py:108 – The assertion only checks that find_duplicate returns a truthy value rather than comparing it to the expected activity, so a wrong match would still pass.
F84 · informational · smell · backend/activities/tests/test_manual_api.py:2 – The `date` import from datetime is unused in this module.
F85 · informational · smell · backend/activities/tests/test_fit_parser.py:65 – A `# type: ignore[union-attr]` comment suppresses a type error instead of narrowing the Optional value, which the project conventions discourage without justification.
F86 · informational · smell · backend/activities/tests/test_fit_parser.py:86 – A `# type: ignore[type-var]` comment is placed on the sorted() call instead of addressing the underlying typing issue.
F87 · informational · smell · backend/activities/tests/test_manual_api.py:329 – `pytest.raises(Exception, ...)` is overly broad and would accept any exception whose message contains the substring; Django's IntegrityError should be asserted instead.
F88 · informational · smell · backend/activities/tests/test_manual_api.py:88 – The sport loop builds times as `f"0{number}:00"`, which yields invalid times like "010:00" once there are ten or more sports, so the test would fail for a reason unrelated to the feature.
F89 · informational · smell · backend/activities/tests/test_manual_api.py – The test for the import rate limit never asserts the status codes of its import posts, so a broken import endpoint could still pass.
F90 · informational · security · backend/activities/tests/test_gpx_parser.py – Gzip-compressed uploads are accepted in import_activity, but no test checks a decompressed-size cap, leaving decompression-bomb exposure unverified.
F91 · warning · smell · backend/activities/tests/test_services.py:184 – test_a_duplicate_of_someone_else_is_not_reported claims in its docstring that the error must not reveal another user's activity id, but it never inspects a DuplicateActivityError and only asserts the import succeeded, so that property is untested.
F92 · informational · security · backend/activities/tests/test_services.py – The _import_settings test helper hard-codes a Fernet-format ENCRYPTION_KEY and a DJANGO_SECRET_KEY literal, which is harmless in tests but risks being copied into non-test configuration.
F93 · informational · smell · backend/activities/tests/test_models.py – TestEnteredByHand.test_the_same_start_and_sport_is_still_one_activity and TestOwnership.test_a_user_cannot_hold_two_activities_with_the_same_start_and_sport check the same unique constraint, and test_a_hash_is_still_used_once_per_user repeats the duplicate-import check, so these tests are duplicated.
F94 · informational · smell · backend/activities/tests/test_series.py – The same `import activities.parsing.series as series` followed by monkeypatching of module constants is repeated in four test functions, which duplicates setup logic that could be a fixture.
F95 · warning · smell · backend/activities/tests/test_sync.py – test_any_other_value_fails_at_startup only asserts returncode != 0, so an import error or crash would pass as a correct range check; it should also assert the expected error message.
F96 · warning · smell · backend/activities/tests/test_strava_import.py – The test uses the untyped parameter `settings: object` with `# type: ignore[attr-defined]` on the assignment instead of pytest-django's typed settings fixture, suppressing the type checker rather than fixing the annotation.
F97 · warning · smell · backend/activities/tests/test_strava_import.py – test_a_path_that_does_not_exist expects the 'not a ZIP' error for a missing file, so the test codifies a broad error message that hides the real cause (file not found).
F98 · informational · smell · backend/activities/tests/test_strava.py – test_the_distance_with_a_decimal_comma_is_kilometres_where_it_is_the_only_one builds a header list with a placeholder 'Zeit' and then overwrites index 5, which makes the intended column layout unclear.
F99 · informational · smell · backend/activities/tests/test_strava.py – TestTheReadme reads README.md with read_text() without an encoding at class-definition time, so the result depends on the platform locale and a missing file breaks test collection.
F100 · informational · smell · backend/activities/tests/test_strava_import.py – The module imports the helpers `export` and `line` from the sibling test module test_strava, coupling the two test files to each other's internals.
F101 · informational · smell · backend/activities/tests/test_sync.py – test_a_second_sync_imports_nothing is duplicated almost verbatim in TestService and TestEndpoint.
F102 · informational · smell · backend/activities/tests/test_sync.py – test_it_is_not_taken_for_an_activity_id has a name that does not match its body, which only asserts a 200 status for POST.
F103 · warning · smell · backend/activities/tests/test_tcx_parser.py:431 – The unparenthesised `except InvalidFileError, UnsupportedFileError:` is valid only on Python 3.14+ (PEP 758), so on 3.11-3.13 this whole test module fails with a SyntaxError.
F104 · warning · smell · backend/activities/tests/test_tcx_parser.py – The entity-bomb test asserts a wall-clock limit (`time.perf_counter() - started < 1.0`), which makes the test flaky on slow or loaded CI machines.
F105 · warning · smell · backend/activities/tests/test_tcx_parser.py – The memory tests assert hard tracemalloc peak thresholds (20 MB, 5 MB), which depend on the Python version and platform and can fail without any regression in the parser.
F106 · informational · smell · backend/activities/tests/test_tcx_parser.py – The `tracemalloc.start()` / `try` / `get_traced_memory()` / `finally: tracemalloc.stop()` block is copied three times and should be a shared helper or fixture.
F107 · informational · smell · backend/activities/tests/test_tcx_parser.py – `test_the_elapsed_time_is_empty_when_nothing_says_how_long_it_lasted` accepts either `0.0` or `None`, so the intended behaviour is left undefined and the test would pass for either.
F108 · informational · smell · backend/activities/tests/test_tcx_parser.py – `test_the_file_an_entity_points_to_is_never_read_or_shown` only checks that the error text lacks the secret, so it passes even if the parser did read the file, despite the test name claiming it was never read.
F109 · informational · smell · backend/activities/tests/test_tcx_parser.py – `test_a_bug_in_the_reader_would_not_pass_for_a_bad_file` monkeypatches the private `tcx._Reader.start`, coupling the test to parser internals that may be refactored away.
F110 · informational · security · backend/athletes/thresholds.py:115 – whole_number accepts numeric strings such as "250" because Django's FloatField coerces them, although its docstring promises a real-number check, and sync passes unchecked Intervals.icu values to it.
F111 · warning · smell · backend/athletes/thresholds.py:4 – The module docstring gives the source order as typed, then Intervals.icu, then estimate, omitting the best-time source that PRIORITY places between typed and Intervals.icu.
F112 · warning · smell · backend/athletes/serializers.py – _body_and_training duplicates facts.body_and_training, so the mapping from a profile to body and training data exists twice and can drift apart.
F113 · warning · smell · backend/athletes/estimates.py – refresh_estimates repeats the reconcile loop of sync_from_intervals (load stored rows, delete missing ones, update_or_create changed ones) instead of sharing one helper.
F114 · warning · smell · backend/athletes/vdot.py – The positive-finite-number check is written four times: vdot._usable, zones._usable, estimates._positive, and inline in AthleteProfile.clean.
F115 · informational · smell · backend/athletes/vdot.py:49 – race_seconds is not used by any of the given files, so it is dead code unless another module calls it.
F116 · warning · smell · backend/athletes/views.py:57 – Two concurrent first PATCH requests both see no profile and both insert one; the second save violates the one-profile-per-owner constraint and returns a 500 instead of updating.
F117 · informational · smell · backend/athletes/estimates.py – refresh_estimates_safely catches every Exception, so an import silently keeps stale estimates and the logged traceback is the only signal.
F118 · informational · smell · backend/athletes/best_times.py:26 – The Entry dataclass field named date shadows the imported date type inside the class body, which makes the annotation and later uses easy to misread.
F119 · informational · smell · backend/athletes/thresholds.py:60 – candidates and all_candidates both build Value objects from ThresholdValue rows and append the best-time pace the same way, so the logic is duplicated.
F120 · informational · smell · backend/athletes/models.py – Validation uses the server's local date.today() while best_times counts recency with a UTC date, so a race on the day boundary can be judged differently by the two.
F121 · informational · security · backend/athletes/thresholds.py:96 – set_manual checks the other heart rate outside the transaction that writes the value, so a concurrent change can let the LTHR end up above the maximum heart rate.
F122 · informational · security · backend/athletes/views.py:37 – The views set no permission_classes and rely on the project's default DRF permission, which is not in these files, so the authentication requirement is not visible here.
F123 · warning · security · backend/athletes/migrations/0001_initial.py:43 – On PostgreSQL a NaN float satisfies the athletes_value_positive check (value > 0), and ThresholdValue.value has no upper bound, so non-finite or absurd thresholds can be stored.
F124 · informational · smell · backend/athletes/migrations/0001_initial.py:3 – The migration imports athletes.models at runtime for validate_time_zone, so changing or removing that validator in application code can break migration history.
F125 · informational · security · backend/athletes/migrations/0002_body_and_training_data.py:65 – The athleteprofile birth_year check only enforces a lower bound (>= 1900), so future birth years up to the PositiveSmallIntegerField maximum are accepted at the database level.
F126 · informational · security · backend/athletes/migrations/0003_best_time.py:28 – The besttime date check only enforces a lower bound (>= 1900), so dates in the future are accepted at the database level.
F127 · warning · smell · backend/athletes/tests/test_athlete_api.py – test_the_answer_has_no_ids_and_no_owner checks str(alice.pk) and str(bob.pk) as substrings of the response text, so a small primary key such as 1 matches dates and other digits, making the test fail or pass depending on the database state.
F128 · warning · smell · backend/athletes/tests/test_athlete_api.py – test_values_of_other_sources_belong_to_their_user_too searches the raw JSON bytes for b"311", which microsecond timestamps in the same response can contain, so the test is flaky. This is the same substring problem the file's own numbers_in helper was written to avoid.
F129 · informational · smell · backend/athletes/tests/test_athlete_api.py – test_the_key_never_appears checks for b"i1" as a substring, which is too short to prove the athlete ID is absent and can match unrelated text.
F130 · informational · smell · backend/athletes/tests/test_athlete_api.py – test_the_time_of_the_last_sync_is_shown imports django.utils.timezone locally although the module already imports it at the top.
F131 · informational · smell · backend/athletes/tests/test_athlete_api.py – The local variable named connection in test_a_key_that_is_refused_is_a_409_and_the_connection_needs_attention shadows the imported django.db.connection used by other tests in the same module.
F132 · informational · smell · backend/athletes/tests/test_athlete_api.py – The raw client PUT with the X-CSRFToken header is copied verbatim into three refusal tests instead of being extracted into a helper.
F133 · informational · smell · backend/athletes/tests/test_athlete_api.py – test_a_field_that_is_not_usable_is_refused_and_changes_nothing picks its companion field and value through nested conditionals, which obscures what each parametrized case actually asserts.
F134 · informational · smell · backend/athletes/tests/test_athlete_api.py – test_deleting_the_typed_value_falls_back_to_automatic uses an unparenthesized conditional expression as its assertion, which is hard to read and can hide the intended check.
F135 · informational · smell · backend/athletes/tests/test_athlete_api.py – The TestIntervals.connect method shares its name with the module-level connect() helper, which makes calls to either one easy to confuse.
F136 · informational · security · backend/athletes/tests/test_sync.py:16 – Test fixtures use hard-coded API-key-looking literals (KEY and the per-user keys), which secret scanners may flag even though they are dummy values.
F137 · warning · smell · backend/athletes/tests/test_sync.py – TestSecrets.test_failures_do_not_show_them_either uses pytest.raises(Exception) with a noqa suppression, so any exception type passes and the test cannot tell whether the intended error was raised.
F138 · informational · smell · backend/athletes/tests/test_sync.py – The untouched() helper takes a connection parameter it never uses, and setup_values() is annotated as returning tuple[Any, Any], which weakens the typing the rest of the file relies on.
F139 · warning · smell · backend/athletes/tests/test_sync.py – test_a_value_outside_what_a_person_can_do_is_not_stored computes the sport and the counterpart entry with nested conditional expressions that compare lists, which is hard to read and makes the intended case unclear.
F140 · informational · smell · backend/athletes/tests/test_models.py – The alice and bob fixtures are duplicated across test_estimates.py, test_sync.py and test_models.py, and test_models.py creates users with User.objects.create_user while the others use make_user, so the fixtures should live in conftest.
F141 · informational · smell · backend/athletes/tests/test_models.py – The threshold(), clean() and refused() helpers repeat the same create-or-validate pattern in several places, with the module-level refused() duplicating the TestBestTimes.refused method.
F142 · informational · smell · backend/athletes/tests/test_estimates.py – The module-level _counter = iter(range(1, 10_000)) is shared state across all tests, so it raises StopIteration once more than 9999 activities are created in one session and makes the tests depend on execution order.
F143 · warning · smell · backend/athletes/tests/test_sync.py – Assertions on wall-clock ordering (second > first in test_the_time_of_the_sync_moves_every_time and updated_at moves after time.sleep(0.01)) can fail on coarse clocks or slow CI, making these tests flaky.
F144 · warning · smell · backend/athletes/tests/test_thresholds.py – The test branches on `first` inside its body, so the two orderings are not separate cases and a failure does not name the order that broke; split it into explicit parametrized cases with their expected messages.
F145 · warning · smell · backend/athletes/tests/test_thresholds.py – The `alice` and `bob` fixtures are duplicated and create users inconsistently: this file calls `User.objects.create_user` directly while test_threshold_estimates.py uses `make_user` from conftest.
F146 · warning · smell · backend/athletes/tests/test_threshold_estimates.py – `test_the_maximum_heart_rate_estimate_works_as_before` duplicates the `activity()` helper's Activity creation with a literal `source="fit_file"` instead of the enum, because the helper cannot set `max_heart_rate`; extend the helper rather than repeating the setup.
F147 · informational · smell · backend/athletes/tests/test_threshold_estimates.py – The module-level `_counter = iter(range(1, 100_000))` is shared mutable state that raises StopIteration after 99,999 calls; use `itertools.count()` or a per-test source of unique hashes.
F148 · informational · smell · backend/athletes/tests/test_threshold_estimates.py – `test_every_basis_says_it_is_a_lower_bound_and_names_the_period` tests basis constants but sits inside `TestTogetherWithTheOtherSources`, and `test_the_maximum_heart_rate_estimate_works_as_before` names no concrete behaviour, so both names and placements mislead.
F149 · informational · smell · backend/athletes/tests/test_thresholds.py – `# type: ignore[union-attr]` is repeated in assertions to read `.value` and `.source` from an Optional result, where an explicit `assert found is not None` as used elsewhere in the suite would keep the type checker honest.
F150 · informational · smell · backend/athletes/tests/test_vdot.py – `test_the_races_of_vdot_50_in_the_published_tables` is duplicated with the same parametrization in both `TestVdot` and `TestRaceSeconds`, so the published-table data is maintained in two places.
F151 · warning · security · backend/availability/absences.py:32 – note_absence accepts an end date before the start date without error when an overlapping period of the same kind exists, because the min/max merge produces a valid period that passes full_clean and the invalid input is silently saved.
F152 · warning · security · backend/availability/absences.py:37 – The MAX_PERIODS check and the period write are not atomic or locked, so concurrent requests can exceed the limit, and the read-modify-write merge can lose updates from a concurrent extension.
F153 · warning · smell · backend/availability/absences.py:29 – The merge loop extends only the first overlapping or adjacent period of the same kind and returns, so a bridging extension can leave overlapping periods, contrary to the docstring's promise that repeated reports do not pile up periods.
F154 · informational · smell · backend/availability/absences.py:4 – The docstring says nothing is stored when the user is at the limit, but an overlapping period is still extended at the limit.
F155 · informational · smell · backend/availability/absences.py:13 – A domain service imports the MAX_PERIODS constant from the serializers module, which couples business logic to the API layer.
F156 · informational · smell · backend/availability/limitations.py:22 – current_limitations re-implements the sport filtering of Limitation.affected_sports and repeats the isinstance check inside the comprehension for every sport.
F157 · informational · smell · backend/availability/models.py – The sports list validation is copied verbatim into AvailabilitySettings.clean and Limitation.clean, so the two rules can drift apart.
F158 · informational · smell · backend/availability/capacity.py:102 – week_capacity is about 50 lines and unpacks a 14-column row through positional slices (rest[:4], rest[4:], wishes, (level, *own)), which makes the mapping between query columns and fields hard to verify.
F159 · warning · security · backend/availability/views.py:56 – The availability settings are read before the transaction and used for validation, so concurrent PATCH requests can each validate against stale values and save a combination that breaks the minimum/budget or limit rules.
F160 · warning · smell · backend/availability/serializers.py – PeriodSerializer.validate reads error.message_dict from a model clean() call, which raises AttributeError for a plain non-field ValidationError and turns a user input error into a 500 response.
F161 · informational · security · backend/availability/serializers.py – The count-then-create limit checks for periods, limitations and fixed sessions are not atomic, so concurrent requests can exceed MAX_PERIODS, MAX_LIMITATIONS or MAX_FIXED_SESSIONS.
F162 · warning · smell · backend/availability/views.py:54 – AvailabilityView.patch is about 70 lines and handles weekday rows, sport preferences and settings in one transaction block, which makes it hard to test and change in parts.
F163 · warning · smell · backend/availability/views.py:96 – The settings_fields list repeats field names from AvailabilityInput, so a new serializer field that is not added here is validated and then silently not saved.
F164 · informational · smell · backend/availability/serializers.py:240 – The same three-message error_messages dict is copied into about eight WholeNumberField declarations, so a wording change has to be made in many places.
F165 · informational · smell · backend/availability/views.py – The lookup_value_regex comment says a non-UUID id never reaches the database, but the pattern only checks length and the hex-and-hyphen character set.
F166 · informational · smell · backend/availability/views.py – The LimitationViewSet comment says ids are time-ordered, which holds only for time-sortable UUIDs, so ordering by -id is otherwise arbitrary.
F167 · informational · smell · backend/availability/views.py – The string literals "current" and "morning"/"afternoon"/"evening" repeat values of LimitationStatus and SLOTS instead of using those enums and constants, so a rename would silently break the ordering.
F168 · warning · security · backend/availability/migrations/0004_intensity_level.py:50 – The progression warning and error percent fields have overlapping ranges (100-200 and 100-300) and no constraint enforcing warning <= error, so a warning of 200 with an error of 100 is accepted.
F169 · informational · security · backend/availability/migrations/0003_sports_and_stretching.py:16 – The sports JSON list on AvailabilitySettings has no database-level validation of its values, so its contents depend entirely on form or serializer code that is not in this set.
F170 · informational · security · backend/availability/migrations/0006_limitation.py:23 – The sports JSON list on Limitation has no database-level validation of its values, so its contents depend entirely on form or serializer code that is not in this set.
F171 · informational · smell · backend/availability/migrations/0005_double_days_and_time_windows.py:22 – Migration 0005 imports availability.models and uses default_slots as a callable default, so renaming or changing that function will break loading of this historical migration.
F172 · warning · smell · backend/availability/tests/test_intensity.py – In test_intensity.py, test_both_ends_of_a_range_are_fine silently adds 1 to the lower bound of progression_error_percent, so the advertised minimum of 100 from range_message is never tested and is refused for the default levels, whose warning limits are 115 to 130.
F173 · informational · smell · backend/availability/tests/test_capacity.py – The 'takes N queries' assertions (len(queries) == 3) are repeated in about ten tests in test_capacity.py, which couples them to the ORM access pattern rather than to behaviour.
F174 · informational · smell · backend/availability/tests/test_capacity.py – The 'a day that is not a Monday is refused' test is duplicated in TestAWeek, TestTheWholeWeek and TestSeveralWeeks in test_capacity.py and could be a single parametrized test.
F175 · informational · smell · backend/availability/tests/test_absences.py – The helper illness_count in test_absences.py duplicates kind_count(user, UnavailablePeriod.Kind.ILLNESS) and adds no meaning.
F176 · informational · smell · backend/availability/tests/test_fixed_sessions_api.py – In test_fixed_sessions_api.py, the assertion 'created | {"id": None} == {...}' masks the id to None to compare the rest, which is unclear to a reader because the id is only checked elsewhere.
F177 · warning · smell · backend/availability/tests/test_models.py:148 – The database-constraint test asserts only that the message contains the substring "availability_", so it would still pass if a different or wrong constraint rejected the row, which weakens the check it is meant to make.
F178 · informational · smell · backend/availability/tests/test_models.py – The test name `test_minutes_default_to_none` contradicts its assertion, which expects `minutes` to default to 0.
F179 · informational · smell · backend/availability/tests/test_limitations_api.py:114 – The assertion `created | {"id": None} == {...}` overwrites the id before comparing, which hides the real response shape and makes the test harder to read; the id is checked separately elsewhere.
F180 · informational · smell · backend/availability/tests/test_limitations_api.py – The bulk creation of MAX_LIMITATIONS entries is copied into three tests (deleting, changing and the limit test), so a change to the fixture setup would have to be made in several places.
F181 · informational · smell · backend/availability/tests/test_limitations_api.py – `test_deleting_one_makes_room` does not assert the status of its DELETE request, so a failed deletion only shows up indirectly in the later create assertion.
F182 · informational · smell · backend/availability/tests/test_periods_api.py:225 – The status parametrization lists the case (-10, -1, "past") twice, so the same case runs twice without adding coverage.
F183 · warning · smell · backend/availability/tests/test_periods_api.py:131 – The read-back assertion sets the id to None on both sides of the comparison, so the returned id is never checked despite the test name.
F184 · informational · security · backend/availability/tests/test_periods_api.py:160 – The test locks in storing raw markup such as <script> in the note, so protection against stored XSS depends entirely on every client escaping this text.
F185 · informational · smell · backend/availability/tests/test_periods_api.py:202 – The period setup loops and UnavailablePeriod bulk_create blocks are repeated across several tests instead of sharing one helper.
F186 · warning · smell · backend/availability/tests/test_preferences.py:26 – The ordering test passes whether the rule is alphabetical or goal-before-supplementary, so the ordering rule it names is not actually pinned down.
F187 · informational · smell · backend/availability/tests/test_preferences.py:12 – The alice and bob fixtures duplicate the user setup from the periods tests and bypass the shared make_user helper.
F188 · warning · smell · backend/availability/tests/test_settings_api.py – Tests named 'kept in the order of the list' and 'the choice can be changed' assert alphabetically sorted sports, so the names contradict what they check and the ordering behaviour is unclear.
F189 · informational · smell · backend/availability/tests/test_settings_api.py – The same full settings dict (EMPTY-style expectation with INTENSITY, DAY_OPTIONS, SHARING, WISHES and PREFERENCES spread in) is repeated in about ten tests, so any new field requires editing every copy; a shared helper would remove the duplication.
F190 · informational · smell · backend/availability/tests/test_settings_api.py – The test named 'a day without minutes still has them' asserts only that weekdays are zero and capacity is zero, never checking that double_days survive, so the name misdescribes the assertion.
F191 · informational · smell · backend/availability/tests/test_settings_api.py – The null-body test calls the private helper api._csrf_token() and builds the request by hand with api.client.generic, duplicating request construction that the AuthApi.call helper already provides and coupling the test to AuthApi internals.
F192 · warning · smell · backend/chat/actions.py – `_mark_sick` only changes the one chosen week, but the illness is noted as an absence for every sick day, so a sick period that runs into the next week leaves that week's workouts in place with no return easing.
F193 · warning · smell · backend/chat/actions.py – The comment on `MIN_MINUTES` says a shorter workout is a removed one, but no code removes a workout for being too short; `_simple` and `_reduce` clamp to `MIN_MINUTES` instead.
F194 · warning · smell · backend/chat/services.py – `_store` saves the draft, the season draft and the absence before the `transaction.atomic()` block that creates the messages, so a failed message insert leaves those changes stored while the athlete gets an error, contrary to the docstring's promise.
F195 · warning · smell · backend/chat/actions.py – `read_actions` does not enforce the prompt rule that no other action may name the days of a `mark_sick` action, so a `move_workout` into the sick days is silently removed, depending on action order.
F196 · warning · smell · backend/chat/actions.py – `_read_one` is about 85 lines and mixes field checks, per-tool validation and object construction across eight `match` cases, which makes it hard to read and test.
F197 · informational · security · backend/chat/actions.py – Keys the coach wrote are copied into `Problem` paths (`f"{path}.{name}"`), and `repair_message` sends those paths back to the coach, which contradicts the docstring rule that nothing the coach wrote is repeated.
F198 · informational · smell · backend/chat/actions.py – The `actions[{index}].id` error in `apply` uses the position within the filtered action tuple, not the position in the coach's list, so the repair message can point to the wrong action.
F199 · informational · smell · backend/chat/actions.py – `_simple` drops exercises when the sport is swapped for the same sport but keeps them for a minutes-only change, while the notes are kept in both cases; the conditional expression is hard to follow and does not match its docstring.
F200 · informational · smell · backend/chat/actions.py – Six `# type: ignore[arg-type]` comments hide that `workout.lineage` may be None and that `Slot`/`Sport` receive unchecked values; a typed helper or an explicit check would remove the need.
F201 · informational · smell · backend/chat/actions.py – The integer range check is repeated in `_minutes`, `_replan_days`, `_sick_days` and `_fever`, and the date parsing is repeated in `_day`, `_start` and `prompt._week`.
F202 · informational · smell · backend/chat/prompt.py – The control-character check is duplicated in `clean_text` and `_reply_problems` with different allowed characters (`\t` is allowed only in one of them), so the two rules can drift apart.
F203 · informational · smell · backend/chat/services.py – `_understand` returns a six-element tuple and `_store` takes nine positional parameters, which makes call sites hard to read and easy to get wrong.
F204 · informational · security · backend/chat/migrations/0001_initial.py:30 – The plan foreign key does not check that the referenced weekly plan belongs to the same owner as the chat message, so the view or serializer must verify plan ownership server-side or a user could attach another athlete's plan.
F205 · informational · security · backend/chat/migrations/0002_chatmessage_season_plan.py:16 – The season_plan foreign key added in this migration has the same missing owner check, so the view or serializer must confirm the referenced season plan belongs to the requesting user.
F206 · informational · smell · backend/chat/migrations/0001_initial.py:35 – The text field allows 5000 characters while the chat_user_text_length constraint limits user messages to 2000, so the two length limits disagree and the field definition is misleading for user input.
F207 · informational · security · backend/chat/tests/test_api.py:26 – The test module hard-codes a key-shaped string with the sk-ant- prefix, which breaks the project rule against secrets in test data and can trip secret scanners even though the value is fake.
F208 · warning · smell · backend/chat/tests/test_api.py:30 – The autouse _clock fixture is copied verbatim from test_api.py into test_briefing.py, so the same monkeypatch of goal_services._utc_now is duplicated instead of living in a shared conftest.
F209 · warning · smell · backend/chat/tests/test_briefing.py:21 – The identical autouse _clock fixture is duplicated here from test_api.py, so changes to the clock patch must be made in two places.
F210 · warning · smell · backend/chat/tests/test_briefing.py:118 – The 7-day and 28-day DailyWellness seeding loop is duplicated between test_the_wellness_reaches_the_chat_briefing and test_the_wellness_stays_isolated_per_user, differing only in owner.
F211 · informational · smell · backend/chat/tests/test_prompt.py – The assertion `"" in problems_of(...)` only checks that some problem exists under an empty path key, so it would pass for any rejection reason.
F212 · informational · smell · backend/chat/tests/test_actions.py – The test_mark_sick_requires_known_symptoms test wraps an assertion in a conditional, so for some parameters the non-echo check is silently skipped.
F213 · informational · smell · backend/chat/tests/test_actions.py – The problems_of helper is re-implemented as a manual dict comprehension over caught.value.problems in several tests, duplicating the existing helper's logic.
F214 · informational · smell · backend/chat/tests/test_prompt.py – The test source contains a literal U+202E bidi override character that is invisible in review, which should be written as an escape sequence such as \u202e for clarity.
F215 · informational · security · backend/chat/tests/test_services.py:55 – The test API key constant uses the real `sk-ant-` prefix format, which may trigger secret scanners; it should use an obviously fake placeholder.
F216 · informational · security · backend/chat/tests/test_services.py:56 – The Intervals.icu test key is a hard-coded credential-like string; a clearly fake placeholder would avoid secret-scanner hits and copy-paste risk.
F217 · informational · smell · backend/chat/tests/test_services.py – The test `test_changes_only_the_first_week_when_week_is_omitted` name says it changes the first week, but it asserts that no draft is made and the coach is asked to name the week.
F218 · informational · smell · backend/chat/tests/test_services.py – `briefing_sent` parses the prompt by splitting on `\n\n` and taking index 1, which couples the tests to the exact prompt layout and breaks silently if the format changes.
F219 · informational · smell · backend/chat/tests/test_services.py – The next-week workout lookup (`make_plan`, filter by plan, `.first()`, `assert is not None`) is repeated in many tests and should be a helper.
F220 · informational · smell · backend/chat/tests/test_services.py – Creating an `AIProviderConfiguration` with the same fields is duplicated across the `athlete` fixture, `TestWithoutAPlan` and `TestIllness`; a shared fixture would remove the copies.
F221 · informational · smell · backend/chat/tests/test_services.py – `test_nothing_is_confirmed_or_pushed` uses unscoped `WorkoutExport.objects.count()` while the rest of the file uses `.for_user(...)`, so it would not catch cross-user leakage if another user were added to the test.
F222 · informational · smell · backend/chat/tests/test_services.py – The parametrized `season_answer` is typed as `object`, which hides that only strings or provider exceptions are valid for `provide`.
F223 · warning · security · backend/coach/answers.py:41 – json.loads parses out-of-range numbers such as 1e400 to inf without any refusal, so the documented refusal of Infinity is bypassed and an infinite value can reach the caller.
F224 · warning · smell · backend/coach/pricing.py:88 – The count check and the insert in save_price are not locked, so concurrent requests can exceed MAX_MODEL_PRICES, and two concurrent creations of the same model raise an unhandled IntegrityError (a 500) instead of being retried as in services._save.
F225 · warning · smell · backend/coach/services.py:303 – _finish writes the status of whichever configuration exists when the call ends, so a call started with an old key can mark a reconfigured provider as connected or invalid.
F226 · informational · smell · backend/coach/answers.py:52 – The unparenthesized form `except ValueError, RecursionError:` is a SyntaxError before Python 3.14, which would break importing this module on older interpreters and is unclear to most readers.
F227 · informational · smell · backend/coach/serializers.py:111 – provider_state decrypts the stored key on every GET only to test whether one exists, which contradicts the services module docstring saying the key is decrypted only where a call needs it.
F228 · informational · security · backend/coach/serializers.py:82 – provider_state returns the operator's full AI_ALLOWED_BASE_URLS list, which may name internal hosts, to every authenticated user.
F229 · informational · security · backend/coach/throttles.py:6 – The check throttle keeps its counters in the process cache, so the limit applies per worker process rather than per user across the deployment.
F230 · informational · smell · backend/coach/models.py:51 – The same RegexValidator(MODEL_PATTERN, ...) expression is repeated for each model field, so the validator should be defined once and reused.
F231 · informational · smell · backend/coach/pricing.py:42 – The _now() helper is duplicated in pricing.py and services.py, so the time source is defined in two places.
F232 · informational · smell · backend/coach/services.py:101 – save_configuration and _save repeat the same eight-parameter signature, and _save combines key handling, change detection and validation in one long function.
F233 · warning · security · backend/coach/migrations/0001_initial.py:26 – The base_url field is an unvalidated free-text CharField (max 200), so any server-side request built from it can be pointed at arbitrary or internal hosts (SSRF); scheme and host validation is not visible in the provided files.
F234 · warning · security · backend/coach/providers/transport.py:59 – A header value with an embedded newline makes http.client raise a ValueError that includes the raw API key, which is not caught by post_json and contradicts the documented rule that no exception carries a header.
F235 · informational · smell · backend/coach/providers/openai_compatible.py:97 – The _count helper is duplicated verbatim in anthropic.py and openai_compatible.py and should live in one shared place such as transport.py or base.py.
F236 · informational · smell · backend/coach/providers/transport.py:67 – The unparenthesized 'except OSError, http.client.HTTPException:' is only valid on Python 3.14+ and fails to import on earlier versions, while the rest of the package targets Python 3.10+; the parenthesized form is portable.
F237 · informational · security · backend/coach/tests/test_costs_api.py – The test data in test_costs_api.py repeats a key-shaped literal (sk-ant-test-...) instead of reusing the KEY constant from test_anthropic.py, which conflicts with the rule against secret-like values in test data even though the value is fake.
F238 · informational · security · backend/coach/tests/test_endpoints.py – test_normal_form pins acceptance of plain http:// for non-loopback hosts such as http://llm.internal, so an operator-configured provider key sent via x-api-key could travel unencrypted.
F239 · informational · smell · backend/coach/tests/test_answers.py – The test name test_json_that_is_broken_says_where_in_numbers_only claims a position is reported, but it only checks the message prefix and suffix, so the name is misleading and the claim is untested.
F240 · informational · smell · backend/coach/tests/test_answers.py – test_nesting_of_any_depth_is_read_or_refused_never_a_crash has no assertion on the success path, so it passes silently whenever the read succeeds and does not check that the result is valid.
F241 · informational · smell · backend/coach/tests/test_models.py:91 – Test name `test_the_defaults_are_untested_and_never_called` promises that the configuration is never called, but the test only checks the default status and timestamps.
F242 · informational · smell · backend/coach/tests/test_models.py – Test name `test_the_text_names_neither_the_model_nor_a_provider_text` does not match its assertions, which check that the purpose 'check' appears in the text.
F243 · informational · smell · backend/coach/tests/test_openai_compatible.py – Test `test_the_address_of_the_fake_is_taken_from_the_list_not_from_the_request` only asserts that the request path starts with '/v1/' and never checks that the address comes from the allow-list, so its name overstates what is tested.
F244 · warning · smell · backend/coach/tests/test_provider_api.py – The test named test_the_messages_are_fixed_texts only checks the set of PROBLEMS keys and never verifies the message texts, so its name promises more than it tests.
F245 · warning · smell · backend/coach/tests/test_provider_api.py – The raw SQL 'UPDATE ... SET api_key = enc:v1:garbage' corruption step is copy-pasted into six tests, so a change to the storage layout must be made in six places.
F246 · informational · smell · backend/coach/tests/test_provider_api.py – The datetime import is repeated inside three test methods instead of once at module level.
F247 · informational · smell · backend/coach/tests/test_provider_api.py – The name test_with_an_empty_list_no_address_is_allowed reads as permitting an address but the test asserts a refusal, and it checks only the status code, not the reason.
F248 · informational · smell · backend/coach/tests/test_provider_api.py – The name test_the_ai_checks_do_not_use_up_the_counter_of_the_intervals_connection does not match its assertion, which checks that the Intervals check endpoint returns 404 rather than 429.
F249 · warning · smell · backend/coach/tests/test_services.py:408 – The return annotation `-> TestJsonOutput.Recorder` on `use` is evaluated inside the class body before `TestJsonOutput` is bound, so the module raises NameError on import under Python 3.13 and earlier unless annotations are deferred.
F250 · informational · smell · backend/coach/tests/test_services.py:615 – `pytest.raises(Exception)` accepts any exception type, so this test would still pass if a call failed with an unrelated error instead of the expected provider error.
F251 · informational · smell · backend/coach/tests/test_services.py:307 – The `save` helper with the same default data dict is duplicated in `TestTheSeasonModelInTheSetup` and `TestTheWeekAndChatModelsInTheSetup`, and a third similar copy exists in `TestSavingTheConfiguration`.
F252 · informational · security · backend/coach/tests/test_services.py:27 – The fixture key `KEY` uses the realistic `sk-ant-` token format, which secret scanners and push protection may flag; an obviously fake placeholder would avoid this.
F253 · informational · security · backend/coach/tests/test_services.py:74 – Raw SQL is built with f-strings from the table name, which is not exploitable here because the name comes from `_meta` and the id is parameterized, but the pattern is copied into `stored_key` and the UPDATE test and could spread.
F254 · warning · security · backend/config/settings.py:33 – The comment at backend/config/settings.py:32 says BACKUP_ENCRYPTION_KEY must differ from ENCRYPTION_KEY, but nothing enforces it, so identical keys would defeat the separation between database and backups.
F255 · warning · security · backend/config/settings.py:149 – X-Forwarded-Proto is trusted by default outside debug mode, so an instance reachable without the proxy lets clients spoof the request scheme and the absolute URLs built from it.
F256 · warning · security · backend/config/settings.py:29 – ENCRYPTION_KEY consisting only of commas or whitespace produces an empty ENCRYPTION_KEYS list that is not rejected at startup, unlike the other settings that are validated.
F257 · warning · security · backend/config/settings_test.py:9 – The test settings hard-code a database password literal in the DATABASE_URL default.
F258 · informational · security · backend/config/settings_test.py:7 – The test settings commit a fixed Fernet encryption key literal, which is harmless only while it is never used outside tests.
F259 · informational · security · backend/config/settings.py:170 – INVITATION_TTL_DAYS has no range check unlike its neighbouring settings, so zero or negative values expire invitations immediately and very large values make them effectively permanent.
F260 · informational · smell · backend/config/settings.py:14 – settings.py imports the application module coach.endpoints, coupling the settings module to app code and to import order.
F261 · warning · security · backend/core/backup.py:79 – create_backup and restore_backup pass a full copy of os.environ to pg_dump and pg_restore, so ENCRYPTION_KEY and BACKUP_ENCRYPTION_KEY, if set as environment variables, reach child processes that do not need them.
F262 · warning · security · backend/core/backup.py:58 – The duplicate-key check compares key strings, but the base64 decoder ignores the low two bits of a key's last character, so a --key-file key that differs from an instance key only in that character passes the check while decoding to the same key bytes.
F263 · warning · smell · backend/core/backup.py:175 – _check_backup converts only file errors, so a file that is not a backup raises BackupCryptoError instead of the documented BackupError, and the same leak occurs at lines 57, 119 and 218.
F264 · warning · smell · backend/core/backup.py:266 – The protect path is kept by unresolved Path equality, so a differently spelled path to the protected backup is not kept and can be deleted despite the docstring guarantee.
F265 · informational · smell · backend/core/backup.py:194 – The restore docstring says existing objects are dropped, but --clean only removes objects that exist in the dump and the emptiness check only looks at public tables, so other objects remain.
F266 · informational · smell · backend/core/backup.py:210 – The Popen, stderr capture and exit-code error handling is duplicated between create_backup and restore_backup, and the connection parameters are duplicated between _pg_command and database_is_empty.
F267 · informational · security · backend/core/backup.py:47 – The key file is read without checking its permissions, so a world-readable file holding the backup key is accepted silently.
F268 · informational · smell · backend/core/backup.py:132 – os.replace silently overwrites an existing backup with the same second-resolution filename, so two runs within one second lose the first backup.
F269 · warning · security · backend/core/management/commands/restore_db.py:23 – The restore command takes the full database URL, including the password, as a command-line argument, so the credential can leak through process listings and shell history; the help text even shows a URL with an embedded password as the example.
F270 · warning · security · backend/core/management/commands/run_backups.py:41 – BACKUP_INTERVAL_HOURS is used unvalidated in time.sleep, so a value of 0 or a negative number turns the loop into a continuous pg_dump run that writes backups and prunes repeatedly.
F271 · informational · smell · backend/core/management/commands/restore_db.py:23 – The URL validation branches in restore_db (empty URL, unparseable URL, missing NAME) have no tests in the submitted files.
F272 · warning · smell · backend/core/tests/test_encryption.py:181 – The test uses a bare `pytest.raises(Exception, ...)`, so any unrelated exception that matches the message pattern would make it pass; it should expect the specific error type.
F273 · informational · smell · backend/core/tests/test_backup_crypto.py – The `# type: ignore[arg-type]` on the short-read stream test is not justified, which the project's rule against unexplained suppressions asks for.
F274 · informational · smell · backend/core/tests/test_backup_service.py:44 – The `stub` fixture writes the database password (via PGPASSWORD) to `record.txt` in tmp_path with default file permissions, leaving a credential in a readable temp file.
F275 · informational · smell · backend/core/tests/test_backup_service.py – The local variable `old` is assigned the output directory `out`, which is a misleading name in `test_backup_db_creates_and_prunes_and_prints_only_a_summary`.
F276 · informational · smell · backend/core/tests/test_backup_restore_e2e.py – `test_encrypted_backup_restores_into_empty_database` is a long function that covers setup, backup, wrong-key, restore, ciphertext and second-restore checks, which makes failures harder to localise.
F277 · informational · security · backend/core/tests/test_backup_restore_e2e.py:65 – `_compose_wrapper` interpolates the docker and compose paths into a double-quoted `sh` script, so a path containing `"`, `$` or a backtick would break or alter the generated command.
F278 · warning · smell · backend/core/tests/test_restore_command.py:42 – The `stub` fixture is named after the fake pg_restore script but returns the `record.txt` path, so assertions such as `assert not stub.exists()` read as if the script itself were checked.
F279 · warning · smell · backend/core/tests/test_restore_command.py – Several tests assert on positional argv slices (`lines[1].split()[-8:]`, `options = lines[1].split()`), which couples them to argument order and breaks on harmless reordering of pg_restore flags.
F280 · informational · security · backend/core/tests/test_restore_command.py – `_key_file` writes the backup key to disk with `write_text` and default file permissions, whereas the code under test expects restricted key-file handling, so the test helper does not model the expected 0600 mode.
F281 · informational · security · backend/core/tests/test_restore_command.py – The database URL test embeds a password literal (`s3cret%40pw`); it is a dummy value, but credential-shaped literals in test code are easy to copy into real config.
F282 · informational · smell · backend/core/tests/test_restore_command.py – The `_key_file(tmp_path, key)` plus `run(...)` boilerplate is repeated in about a dozen tests and could be a single fixture or helper.
F283 · informational · smell · backend/core/tests/test_run_backups.py – The `failing` fake command is defined twice in this file, once in `test_once_failure_raises` and again in `test_loop_survives_a_failed_round`, so a shared fixture would remove the duplication.
F284 · warning · security · backend/core/tests/sample/views.py:10 – NoteSerializer exposes `owner` as a writable field over any User, so clients can assign notes to other users unless OwnedModelViewSet forces the owner server-side, which cannot be verified from these files.
F285 · informational · security · backend/core/tests/sample/views.py:25 – UnscopedViewSet exposes every User object through its queryset, which would leak all accounts if this URL module were ever included outside the tests.
F286 · informational · security · backend/core/tests/sample/migrations/0002_credential.py:15 – The Credential model in this migration has no owner or user foreign key, unlike Note in 0001_initial.py, so per-user access to stored secrets must be enforced entirely in views or services that are not part of this review.
F287 · warning · security · backend/dashboard/views.py:19 – DashboardView declares no permission_classes and relies on a project default noted only in a comment, and the assert that narrows request.user is stripped under python -O, so authorization depends on settings the view does not show.
F288 · warning · smell · backend/dashboard/summary.py:69 – _confirmed_workouts has no order_by, so the next-week fallback in _next_workout (after[0]) picks an arbitrary workout unless PlannedWorkout's Meta ordering sorts it by day.
F289 · informational · smell · backend/dashboard/summary.py:127 – The summary.py docstring says the query count does not depend on the data, but _close_week returns before calling week_summary on Sundays when there is feedback-free work, so the count does vary.
F290 · informational · smell · backend/dashboard/overview.py:148 – _minutes repeats the half-up rounding rule that its docstring says season.done uses instead of reusing it, so the two rules can drift apart.
F291 · warning · smell · backend/dashboard/tests/test_overview.py:185 – The comments in test_stop_after_eight_weeks are off by one: 2026-09-14 is eight weeks before Monday 2026-11-09, not nine, and 2026-09-21 is seven weeks back, not eight.
F292 · informational · smell · backend/dashboard/tests/test_api.py:24 – The autouse _clock fixture that patches goal_services._utc_now is copied verbatim into test_api.py, test_overview.py and test_summary.py, so a change to the clock patch has to be made in three places.
F293 · warning · security · backend/goals/serializers.py:137 – The 30-goal limit is checked with a separate count before the insert, so concurrent creates can each pass the check and exceed MAX_GOALS.
F294 · informational · smell · backend/goals/serializers.py:22 – The WRITABLE comment says target times are the server's, but target_time_seconds is in WRITABLE and client-writable.
F295 · informational · security · backend/goals/migrations/0001_initial.py:38 – The goals_title_not_empty constraint only rejects the empty string, so whitespace-only titles such as " " pass the database check.
F296 · informational · security · backend/goals/migrations/0001_initial.py:38 – No constraint ties metric and target_value to kind or discipline, so race and general goals can carry a threshold metric, and ftp or threshold_pace can be paired with any discipline.
F297 · informational · smell · backend/goals/tests/test_assessing.py:21 – The autouse `_clock` fixture and the `alice`/`bob` fixtures duplicate the clock patching and user setup in `test_goals_api.py` (`_fixed_clock`, `alice`, `bob`); shared fixtures belong in `conftest.py`.
F298 · informational · smell · backend/goals/tests/test_goals_api.py – The helper `best()` and the helper `run_form()` in `test_goals_api.py` both create the same 10 km best time with different defaults, so the setup logic is duplicated.
F299 · informational · smell · backend/goals/tests/test_goals_api.py – `test_deleting_one_makes_room` silences a type error with `# type: ignore[union-attr]` where other tests in the file use an explicit `assert ... is not None`, which hides a possible `None` without a reason.
F300 · informational · smell · backend/goals/tests/test_goals_api.py – `test_a_body_that_is_no_json_is_a_400` calls the private helper `api._csrf_token()`, which couples the test to the internals of `AuthApi`.
F301 · informational · smell · backend/goals/tests/test_goals_api.py – `test_the_time_of_the_last_change_moves` compares timestamps as strings after manual `replace`/slicing instead of parsing them, so it depends on the exact serialized format and can give misleading results.
F302 · informational · smell · backend/goals/tests/test_docs.py – `test_the_pages_that_link_to_it_find_it` only checks that the substring `goals.md` occurs in the other pages, so it does not verify a real link, and its `exists()` assertion repeats what the module-level read already guarantees.
F303 · informational · smell · backend/goals/tests/test_realism.py:334 – The test reads realism.py with open(...).read() without closing the file, and checks the module by scanning its source text for 'django' and 'objects' with a 'no django' string replacement, which is brittle.
F304 · informational · smell · backend/goals/tests/test_realism.py:343 – The '# type: ignore[misc]' on the frozen-dataclass assignment has no comment explaining why it is needed.
F305 · warning · smell · backend/goals/tests/test_services.py:43 – The comment says the profile checks the timezone name when it is saved, but the test calls profile.save() with invalid names and expects it to succeed, so the validation only runs in clean()/full_clean() and invalid names can be stored.
F306 · informational · smell · backend/goals/tests/test_services.py:17 – The alice and bob fixtures and the User creation are duplicated across test_models.py and test_services.py and should live in a shared conftest.py.
F307 · informational · smell · backend/goals/tests/test_models.py – test_updated_at_moves_when_the_goal_is_saved_again relies on time.sleep(0.01) to order timestamps, which can be flaky on coarse-resolution clocks.
F308 · warning · smell · backend/integrations/services.py:78 – check() marks the connection invalid from a key it read before a concurrent connect() replaced it, so a freshly stored valid key can be flagged as invalid.
F309 · warning · smell · backend/integrations/intervals.py:358 – Retry-After waits of up to 60 seconds per attempt, with up to three retries, run synchronously inside the connect and check requests and can hold a web worker for minutes.
F310 · informational · security · backend/integrations/views.py:24 – Authorization relies on a global default permission class and an assert in _user that python -O strips, so the views should declare permission_classes = [IsAuthenticated] explicitly.
F311 · informational · security · backend/integrations/intervals.py:196 – The base URL check accepts http://, so a misconfigured setting would send the Basic-auth API key in cleartext.
F312 · informational · security · backend/integrations/intervals.py:348 – The timeout applies per socket operation, so a server that trickles its answer can keep the request busy far longer than the 10-second limit.
F313 · informational · smell · backend/integrations/intervals.py:354 – The HTTPError response is never closed on the raise paths, so its socket stays open until garbage collection.
F314 · informational · smell · backend/integrations/services.py:61 – The AssertionError after the retry loop is unreachable because the loop already raises on its last attempt.
F315 · informational · smell · backend/integrations/intervals.py:304 – The assert on the stored response is redundant with the preceding check and disappears under python -O, so it only narrows types.
F316 · informational · smell · backend/integrations/services.py:84 – check() and with_client() duplicate the connection lookup and the mark-invalid handling for DecryptionError and InvalidKeyError.
F317 · informational · smell · backend/integrations/intervals.py:248 – get_activities lacks the oldest-after-newest check that get_wellness has, so an inverted range is sent to the API instead of failing locally.
F318 · informational · smell · backend/integrations/tests/test_connection_api.py:38 – The helper `athlete()` only configures the fake Intervals server's response; its name suggests it creates an athlete, so a name like `answer_with_athlete` would be clearer.
F319 · warning · smell · backend/integrations/tests/test_intervals.py – The upsert-event secret-leak test wraps each call in try/except IntervalsError without pytest.raises, so it passes silently if a status stops raising, and it never checks that an error occurred.
F320 · warning · smell · backend/integrations/tests/test_intervals.py – TestTheKeyStaysSecret.test_neither_the_key_nor_a_value_shows_up_in_errors_or_logs and test_no_error_shows_the_key use try/except IntervalsError instead of pytest.raises, so the error-text assertions are skipped when no exception is raised.
F321 · informational · smell · backend/integrations/tests/test_intervals.py – The Basic-auth header is rebuilt inline with base64.b64encode(f"API_KEY:{KEY}") in about a dozen tests, which should be one helper.
F322 · informational · smell · backend/integrations/tests/test_intervals.py – The refusal, busy-service, closed-port and unexpected-status tests are copied almost verbatim across the athlete, sport-settings, upsert, delete and wellness test classes, which should be one parametrized suite.
F323 · informational · smell · backend/integrations/tests/test_intervals.py – The test name test_test_settings_use_zero_retry_delays is misleading because it checks the default retry delays used in test settings, not a test-only behaviour.
F324 · informational · security · backend/integrations/tests/test_intervals.py – A Fernet encryption key literal is hard-coded in the test module's subprocess environment, which should be generated at runtime as test_services.py does.
F325 · warning · smell · backend/jobs/runner.py:155 – for_each_user logs failed weekly-job attempts without week_start, so those failures never count toward MAX_FAILED_TRIES and the retry cap is bypassed.
F326 · warning · smell · backend/jobs/schedule.py:70 – run_round computes the user's Monday and due jobs outside its try block, so an exception there aborts the round for all later users, contrary to the docstring promise that the round goes on.
F327 · warning · smell · backend/jobs/runner.py:79 – The broad except Exception handlers in run_review and run_draft record only a code and never log the exception, so unexpected errors are invisible to operators.
F328 · warning · smell · backend/jobs/services.py:45 – record() never sets started_at or finished_at, so both default to the logging time, although the model defines them as the ends of the attempt and _sync_is_due depends on started_at.
F329 · warning · smell · backend/jobs/views.py:36 – Two concurrent first PATCH requests both see no settings row and both INSERT, so the unique owner constraint raises an IntegrityError and returns a 500, and the check relies on the private _state attribute.
F330 · informational · security · backend/jobs/views.py:15 – Authorization relies on the global default permission class and on an assert that python -O strips, since the views declare no permission_classes of their own.
F331 · informational · smell · backend/jobs/runner.py:63 – A review skipped because a comment already exists is logged as Code.ALREADY_PLANNED, a code whose name describes plans, which makes the job log misleading.
F332 · informational · smell · backend/jobs/runner.py:9 – The docstring promises nothing is paid twice, but the exists() check and the coach call are not atomic, so concurrent rounds can call the coach twice.
F333 · informational · smell · backend/jobs/schedule.py:82 – The next-week and Monday arithmetic is repeated in run_draft, due() and the error path of run_round, so the week written to the log can drift from the week that was actually checked.
F334 · informational · smell · backend/jobs/services.py:55 – The runs_of function is not used by any of the audited files.
F335 · informational · smell · backend/jobs/models.py:100 – The JobRun docstring says counts can never hold text, but the JSONField and record() enforce only type hints, not values.
F336 · informational · smell · backend/jobs/schedule.py:46 – The audited set contains no tests for due(), run_round or the runner outcome rules, which carry the retry and settlement logic.
F337 · informational · smell · backend/jobs/runner.py:52 – run_review and run_draft repeat the same chain of except clauses that each build a record call, which makes the outcome mapping hard to keep consistent.
F338 · warning · smell · backend/jobs/management/commands/run_scheduler.py:42 – With `--now` and without `--once`, `fixed` is never updated, so every loop round evaluates due jobs at the same instant instead of advancing the clock.
F339 · informational · smell · backend/jobs/management/commands/sync_activities.py:28 – The `--email` existence check is copy-pasted into several commands and should be shared in one helper.
F340 · informational · smell · backend/jobs/management/commands/draft_next_week.py:38 – The Monday-of-the-week calculation is duplicated here and in review_weeks.py, so it should be a shared helper.
F341 · informational · smell · backend/jobs/management/commands/draft_next_week.py:33 – The docstring says no personal data is ever printed, but the CommandError on this line echoes the raw `--email` value back to the console.
F342 · warning · smell · backend/jobs/migrations/0001_initial.py:24 – The jobs_run_week_is_a_monday constraint only checks week_start when it is non-null, so week_review and week_draft rows can be saved with week_start NULL, which the field's blank=True/null=True allows.
F343 · informational · smell · backend/jobs/migrations/0001_initial.py:23 – The job names 'sync', 'week_review' and 'week_draft' are hard-coded in the JobRun choices, the JobRun check constraint and as JobSettings boolean columns, so adding a job means changing the schema in several places.
F344 · informational · smell · backend/jobs/migrations/0001_initial.py:26 – No constraint ensures finished_at is not earlier than started_at, and both timestamps default to timezone.now, so inconsistent run durations can be stored.
F345 · informational · security · backend/jobs/tests/test_commands.py – Test fixtures hard-code an `sk-ant-` shaped API key literal (KEY), which violates the project rule against secrets in test data and can trigger secret scanners.
F346 · warning · smell · backend/jobs/tests/test_commands.py – The helpers `answer` and `answer_wellness` are defined but never called in this module.
F347 · warning · smell · backend/jobs/tests/test_commands.py – The helpers `connect`, `entry`, `wellness_entry`, `athlete`, `provide`, `ride`, `good_plan`, the `fake` fixture and the Monday constants are copied across test_commands.py, test_runner_weekly.py and test_runner_sync.py instead of living in the shared conftest.
F348 · informational · smell · backend/jobs/tests/conftest.py – The `make_user` docstring promises a verified address, but `create_user` does not verify anything, so the comment is misleading.
F349 · warning · smell · backend/jobs/tests/test_runner_sync.py – `test_the_log_holds_only_fixed_words` only asserts `run.code in Code.values` and never checks that the provider's secret text is absent from the stored code or counts, so the test name overclaims what it verifies.
F350 · informational · smell · backend/jobs/tests/test_runner_sync.py – The final `json.dumps` equality in `test_an_unreadable_answer_is_a_failure_with_a_fixed_code` repeats earlier assertions and does not check the log for provider text, although the comment claims it does.
F351 · warning · smell · backend/jobs/tests/test_runner_weekly.py – `TestTheReview` does not use the `no_push_and_no_confirm` fixture, so the review job's guarantee that it never confirms or pushes is untested.
F352 · informational · smell · backend/jobs/tests/test_runner_weekly.py – The comment on `assert scripted.calls` says the coach was the only thing asked, but the assertion only checks that at least one call happened.
F353 · warning · smell · backend/jobs/tests/test_docs.py – `test_the_page_says_the_log_holds_numbers_and_fixed_words_only` uses an `or` between two phrases, so the check passes if either phrase appears and weakens the assertion.
F354 · warning · smell · backend/jobs/tests/test_docs.py – `FLAT_DOC.index("sync")` and similar calls match substrings such as "synced" anywhere in the page, so the job-order test can pass or fail for the wrong reason.
F355 · informational · smell · backend/jobs/tests/test_docs.py – The variable `readme` holds a regex match object for the Configuration section, not the README text, which makes the name misleading.
F356 · informational · smell · backend/jobs/tests/test_schedule.py:95 – The `settings: object` parameter of `test_the_sync_is_due_after_the_configured_hours` is never used and has a misleading type; drop it or type it as the pytest-django fixture.
F357 · informational · smell · backend/jobs/tests/test_schedule.py:53 – The `log` helper gives SKIPPED runs `Code.UNEXPECTED`, which misstates the outcome, so tests that record skips carry a wrong error code.
F358 · informational · smell · backend/jobs/tests/test_schedule.py:102 – The test deletes the SKIPPED run it just recorded before asserting, so the sequence of events and what the final assertion proves are hard to follow.
F359 · informational · smell · backend/jobs/tests/test_schedule.py:155 – The job-to-week mapping is duplicated: it appears in the parametrize table and again in the inline `NEXT_MONDAY if ... else THIS_MONDAY` conditional, which could be a single parametrized value.
F360 · informational · smell · backend/jobs/tests/test_schedule.py:27 – Fixtures and helpers are imported from the sibling module `.test_commands` rather than shared through `conftest.py`, which couples this test module to another test file's internals.
F361 · warning · smell · backend/planning/briefing.py:13 – The module docstring says the only free text in the briefing is the goal text, the limitations text, and the season plan's reason and detail, but the athlete's weekly note (athlete_note) is also free text sent to the coach and is not listed.
F362 · informational · security · backend/planning/briefing.py – The athlete's weekly note and goal notes reach the LLM as free text, and the only protection against prompt injection is the data framing in the prompt, which is not among the audited files.
F363 · informational · smell · backend/planning/load.py:35 – _zone_rate indexes the rate tables with zone - 1 without a range check, so zone 0 silently takes the top rate and an out-of-range zone raises IndexError unless the schema already rules those out.
F364 · informational · smell · backend/planning/load.py:82 – The week_load docstring says it totals user-scoped activities of the local week, but the function accepts any iterable of activities and does no scoping, so that guarantee depends on every caller.
F365 · informational · smell · backend/planning/generation.py:19 – The name coach is bound to the coach.services module in generation.py, so coach.call and coach.NotConfiguredError read as if they refer to the coach itself.
F366 · informational · smell · backend/planning/context.py – The sport-to-threshold-group mapping ('ride' and 'run') is written as literals in usable_zone_systems and again as _THRESHOLD_SPORT in briefing.py, so the two can drift apart.
F367 · warning · security · backend/planning/models.py:215 – PlannedWorkout.save() refuses changes once the plan is not a draft, but PlannedWorkout.delete(), queryset update() and bulk_create() bypass save(), so a confirmed plan's workouts can still be altered or removed.
F368 · warning · security · backend/planning/models.py:27 – WeeklyPlan has no save() guard, so a confirmed plan's reason, rationale, note or status can be changed directly, contradicting the class docstring that a confirmed plan is never changed.
F369 · warning · security · backend/planning/models.py:212 – PlannedWorkout.save() never calls clean(), so the owner-matches-plan and day-within-week checks run only when callers invoke full_clean(), and a caller that skips it can attach a workout to another user's plan.
F370 · informational · security · backend/planning/prompt.py – _read_json forwards str(error) from AnswerFormatError into the problem list, although the module promises that no answer text is repeated, and coach/answers.py is not provided to confirm that the message never echoes the answer.
F371 · informational · smell · backend/planning/push.py:122 – The assert comparing the lengths of rows and workouts is redundant with the strict zip that follows and is skipped under python -O.
F372 · informational · smell · backend/planning/push.py:186 – _succeed and _fail duplicate the same update_or_create call and differ only in status, error code and event id, so the export-row write logic is repeated.
F373 · informational · smell · backend/planning/rules.py – The planned-minutes sum over workouts within the week is repeated in check_week_capacity, check_progression, check_minimum_minutes and check_season_minutes instead of using one helper such as _workouts_by_day.
F374 · informational · smell · backend/planning/rules.py – The docstring of check_limitations says it names the newest limitation, but the code takes the first match in context.limitations and this module never orders them.
F375 · informational · smell · backend/planning/rules.py – check_long_days uses assert to enforce a runtime invariant, which is skipped when Python runs with -O.
F376 · informational · smell · backend/planning/rules.py – The threshold and VO2max goal check is written out separately in intensity_of, easy_minutes and _fits_key_session, so a change to the hard-goal rule must be made in several places.
F377 · informational · smell · backend/planning/rules.py – _label maps ZoneSystem values through a hand-written dict keyed by strings, which raises KeyError when a new zone system is added to the enum without updating it.
F378 · warning · security · backend/planning/views.py – ConfirmView.get_throttles applies PlanPushThrottle only when push is exactly True, but ConfirmBody's BooleanField also accepts values such as "true", 1 or form data, so those requests push to Intervals.icu without the throttle.
F379 · warning · security · backend/planning/views.py – ConfirmView and GenerateView read request.data without the RecursionError guard that CheckView and ReviseView use, so a deeply nested JSON body produces an unhandled 500 error.
F380 · warning · security · backend/planning/schema.py – _Reader._object echoes unknown keys that match the name pattern into Problem paths, which contradicts the module's stated guarantee that no input text appears in messages and lets model output reach the 422 response.
F381 · warning · security · backend/planning/schema.py – _FORBIDDEN omits the bidi marks U+200E, U+200F and U+061C, which are category Cf and are not rejected by _forbidden, so titles and notes can still reorder text on screen despite the comment saying such controls are refused.
F382 · informational · smell · backend/planning/schema.py – The _workout method is about 75 lines and combines field reading, zone handling, nested list parsing and a long chain of None checks, which makes it hard to follow.
F383 · informational · smell · backend/planning/schema.py – The local variable counted in _exercise is True when the reps/seconds choice is invalid, so its name says the opposite of what it holds.
F384 · informational · smell · backend/planning/views.py – CheckView and ReviseView repeat the same mapping of PlanFormatError to a 422 response with the same problem list.
F385 · informational · smell · backend/planning/views.py – The _monday helper and its _WEEK regex duplicate the date validation already in schema._DATE and _day.
F386 · warning · security · backend/planning/migrations/0001_initial.py:81 – The `planning_not_its_own_parent` check only blocks a row from being its own parent, so a longer cycle (A→B→A) is not prevented by the database and code that walks the `revisions` chain could loop forever.
F387 · informational · smell · backend/planning/migrations/0004_plannedworkout_lineage.py:5 – The `# type: ignore[no-untyped-def]` on `own_id` suppresses type checking without a justification; the function should get proper type annotations instead.
F388 · informational · smell · backend/planning/tests/test_context.py:112 – The test name `test_it_accepts_a_one_shot_iterable_with_the_match_last` does not describe what is checked, which is that a one-shot iterable works and the result does not depend on input order.
F389 · informational · smell · backend/planning/tests/test_context.py:45 – The `alice` and `bob` fixtures create users directly without the verified EmailAddress that `make_user` in conftest.py sets up, so the test users differ from the helper the suite already provides.
F390 · informational · smell · backend/planning/tests/test_context.py – The best-times test reads the real clock with `datetime.now(UTC)` while the rest of the file pins the plan to the fixed date `MONDAY = 2027-07-19`, which makes the test's notion of "recent" depend on the day it runs.
F391 · informational · smell · backend/planning/tests/scripted.py:17 – `Scripted.complete` types `messages` as `Any` even though `calls` records it as `list[Message]`, which weakens the typing of the test double.
F392 · warning · smell · backend/planning/tests/test_docs.py – `rows()` silently drops any table row whose first cell is in a hardcoded set such as "Status", "Key" or "Level", so a documented row with such a name escapes the comparison and a test can pass wrongly.
F393 · informational · smell · backend/planning/tests/test_docs.py – `integer_constants` types its parameter as `object` and silences the attribute error with `# type: ignore[attr-defined]` instead of typing it as `ModuleType`.
F394 · informational · smell · backend/planning/tests/test_docs.py – `test_every_check_of_the_rules_is_covered_by_the_table` hardcodes the counts 30 and 36, which must be updated by hand whenever a rule is added.
F395 · informational · smell · backend/planning/tests/test_docs.py – The availability page files are read again and again in several tests and classes, and class attributes read files at import time, which duplicates logic and adds collection-time I/O.
F396 · informational · smell · backend/planning/tests/test_docs.py – `TestTheApi.in_the_code` selects routes with the substring test `"planning" in str(pattern.pattern)`, which is fragile and could match unrelated routes.
F397 · informational · smell · backend/planning/tests/test_editing.py – `test_a_segment_with_an_out_of_range_zone_is_refused` takes the `alice` fixture but never uses it.
F398 · informational · smell · backend/planning/tests/test_editing.py – `test_an_older_version_is_restored_before_it_is_changed` branches on its parameter with if/else, so the two cases are harder to read and a failure does not show which case ran.
F399 · informational · smell · backend/planning/tests/test_editing.py – The parametrized offset 3 in `test_a_week_that_cannot_be_planned` gives Thursday 2027-07-15, which is not a week start, so the case does not match the test name and its reason is unexplained.
F400 · informational · smell · backend/planning/tests/test_editing.py – `test_a_plan_for_another_week` is duplicated in two classes, and `test_a_plan_that_is_no_plan_raises_the_format_error` duplicates `test_something_that_is_no_plan`.
F401 · warning · security · backend/planning/tests/test_generation.py:47 – The test module hard-codes an Anthropic-style API key string, which violates the project rule against secrets in test data even though the value is fake.
F402 · warning · smell · backend/planning/tests/test_generation.py – The test named test_a_single_minute_is_enough_to_ask only asserts len(scripted.calls) >= 1, so it does not verify that a one-minute week is actually asked for.
F403 · informational · smell · backend/planning/tests/test_generation.py – Two tests have garbled names ("loses_a_readable_plan_not") that contradict their assertions, which check that the readable plan is kept.
F404 · informational · smell · backend/planning/tests/test_export.py – The note-validation assertions in test_notes_never_become_steps_or_repeats repeat the step and repeat checks already written for exercise names, so the same rules are duplicated in two places.
F405 · informational · smell · backend/planning/tests/test_export.py – test_the_type_follows_the_sport checks the completeness of the EVENT_TYPE mapping inside a parametrized test, so the same check runs once per sport.
F406 · informational · smell · backend/planning/tests/test_load.py – The PlanContext constructor is called with unlabeled positional arguments (60, 60, frozenset(), ()), which makes the capacity test hard to read and check.
F407 · warning · security · backend/planning/tests/test_models.py – The ownership tests call full_clean and never check that objects.create or save refuses a workout or export whose plan or workout belongs to another user, so a cross-tenant write may pass when validation is skipped.
F408 · warning · smell · backend/planning/tests/test_prompt.py – test_every_key_it_names_is_a_key_of_the_briefing compares the prompt against a hardcoded key set rather than the briefing schema, so renamed or removed briefing keys would not fail the test.
F409 · informational · smell · backend/planning/tests/test_prompt.py – test_a_deeply_nested_answer_is_refused_not_crashed_on is named as a refusal but only asserts that a 'week_start' problem appears, so it would not detect a change in how the nesting error is reported.
F410 · informational · smell · backend/planning/tests/test_models.py – test_the_zone_counts_are_the_documented_ones repeats the ZONE_COUNT check already made in test_the_zone_counts_are_those_of_the_zone_models, so the same expectation is asserted twice in two places.
F411 · informational · smell · backend/planning/tests/test_models.py – The PlannedWorkout construction with owner, plan=make_plan(alice) and workout_fields is repeated in about twenty places, and the refused and rejected_by_database helpers are not used consistently, which makes the tests harder to change.
F412 · informational · security · backend/planning/tests/test_push.py:39 – The test fixture hard-codes an API-key-shaped literal as KEY; it is fake, but a credential-looking value in the repository invites mistakes, so generate it or keep it clearly marked as a dummy.
F413 · warning · smell · backend/planning/tests/test_push.py:193 – The test name says the other workouts stay, but it asserts that all four old events are removed (removed=4) and three are re-created, so the name misdescribes the behaviour.
F414 · informational · smell · backend/planning/tests/test_push.py:362 – The `# type: ignore[arg-type]` suppression hides a type mismatch in the test instead of fixing it, and the project rules require such suppressions to be justified.
F415 · informational · smell · backend/planning/tests/test_push.py:138 – The parametrized test branches on its own `decided` argument with several `if` statements, so the setup logic is harder to read than separate cases would be.
F416 · warning · smell · backend/planning/tests/test_rules_capacity.py – The purity test only inspects `ast.ImportFrom` nodes, so a module that runs `import django` or `import django.db` would pass it.
F417 · informational · smell · backend/planning/tests/test_rules_capacity.py – The test named as order-independent only checks that two identical calls return the same findings, so its name overstates what it verifies.
F418 · informational · smell · backend/planning/tests/test_rules_capacity.py – The module defines its own `workout(offset, minutes, **fields)` helper and `MONDAY`, while sibling test modules use a `workout(day, offset, minutes)` helper with a different signature, which invites confusion when copying tests between them.
F419 · informational · smell · backend/planning/tests/test_rules_capacity.py – The same no-leak check for coach-written title and notes is repeated in several classes with near-identical bodies instead of one parametrized test.
F420 · warning · security · backend/planning/tests/test_schema.py – The test source contains literal bidirectional control characters (for example "a‮b" and "a⁦b" in test_schema.py), which can make code look different from how it runs during review, and the file's own comment says such characters should be written as escapes.
F421 · informational · smell · backend/planning/tests/test_schema.py – The title and rationale test lists contain "a b" more than once, so the entries are indistinguishable on screen and the duplicate likely hides a non-ASCII whitespace variant that the test is meant to cover.
F422 · warning · smell · backend/planning/tests/test_rules_season.py – test_every_sport_that_is_missing_is_named_once_in_the_order_of_the_season extracts the sport name by splitting the message text on " of " and spaces, so any wording change breaks the test even when the behaviour is correct.
F423 · informational · smell · backend/planning/tests/test_schema.py – test_a_system_must_be_one_of_the_known_texts only checks that the path appears in the problem list and never verifies the message, so a wrong or missing explanation would still pass.
F424 · informational · smell · backend/planning/tests/test_schema.py – test_the_module_needs_no_django builds its import set with a convoluted comprehension that substitutes a fake ast.alias, which is hard to read and misses relative imports such as `from . import x`.
F425 · informational · smell · backend/planning/tests/test_rules_season.py – Test helpers are duplicated across the file (workout, plan, with_workout, with_segment, with_exercise), and some test names repeat across classes, such as test_workouts_outside_the_week_do_not_count and test_without_a_season_week_nothing_is_checked.
F426 · informational · smell · backend/planning/tests/test_services.py – The test name `test_nothing_is_stored_when_the_workouts_cannot_be_(` is truncated and unclear, ending in an unfinished word and an open parenthesis.
F427 · informational · smell · backend/planning/tests/test_validation.py – The `workout()` and `good_week()` helpers are duplicated almost verbatim between test_services.py and test_validation.py, so a change to the sample week must be made in two places.
F428 · informational · smell · backend/planning/tests/test_services.py – The `prepared()` helper in test_services.py duplicates the threshold and weekday setup that test_targets.py performs through `make_user` and `hold`, so the user fixtures are defined in parallel instead of shared.
F429 · informational · smell · backend/planning/tests/test_services.py – The parametrized status-to-timestamp logic (`stamp = NOW if status in {...}`) is copied into both the confirm and discard state tests instead of being shared.
F430 · warning · smell · backend/reviews/serializers.py – The mapping from Figures to a dict is copied field by field in briefing.py (_figures) and serializers.py (_figures), so a new field on the Figures dataclass in comparison.py must be added in three places or the outputs drift apart.
F431 · warning · smell · backend/reviews/services.py – correct() turns every IntegrityError into ActivityLinkedElsewhere, so a deleted activity (foreign key violation) or any other constraint failure is reported to the user as the activity belonging to another workout.
F432 · informational · security · backend/reviews/briefing.py – The briefing docstring promises no free text, but unplanned sessions send activity.sport unchecked and the comparison.py comment assumes sports are stored choices; if sync can store arbitrary sport strings, that text reaches the model unfiltered.
F433 · informational · security · backend/reviews/throttles.py – The comment rate limit counters are kept in the process cache, so if that cache is process-local the limit applies per worker process rather than per user, letting a script exceed it across workers.
F434 · informational · security · backend/reviews/prompt.py – extract_comment passes str(error) from AnswerFormatError into a Problem, which can be sent back to the coach and logged, although the docstring says nothing of the answer is ever repeated; this depends on the message text in coach.answers, which is not shown.
F435 · informational · smell · backend/reviews/models.py – The status vocabulary is repeated as literals and sets in several places (matching.Status and CHOOSABLE, WorkoutReview.Status choices, the CheckConstraint list, and NEEDS_AN_ACTIVITY as strings in services.py), so a change to the statuses must be made in each.
F436 · warning · security · backend/reviews/views.py:47 – No view declares permission_classes and _user() relies on an assert plus the global DRF default; if the default changes, anonymous requests reach the services, and python -O strips the assert entirely.
F437 · informational · smell · backend/reviews/views.py:95 – The 'if monday is None' to 404 NOT_REVIEWABLE block is repeated in four handlers and the WeekNotReviewable mapping is repeated in four more, so a single change would need to touch every view.
F438 · informational · smell · backend/reviews/views.py:55 – parse_week accepts any calendar date, but the result is named 'monday' and passed to the services unchanged, so a non-Monday value is not rejected here and the name and docstring disagree with the behaviour.
F439 · informational · security · backend/reviews/views.py:157 – FeedbackView forwards **form.validated_data straight into save_feedback, so any field later added to FeedbackSerializer reaches the service as a keyword argument without an explicit whitelist.
F440 · informational · smell · backend/reviews/views.py:170 – CommentView runs a synchronous provider call that the docstring says can take a minute or two inside the request cycle, which ties up a worker and has no timeout visible in this file.
F441 · informational · security · backend/reviews/views.py:185 – The CommentNotUsable branch returns the provider's problem paths and messages verbatim to the client, which may expose validator or model output internals.
F442 · warning · security · backend/reviews/migrations/0001_initial.py:44 – The schema does not enforce that the linked workout (planning.PlannedWorkout) and activity belong to the same owner as the review, so any view that accepts these FKs from client input without an ownership check can link another user's records.
F443 · informational · smell · backend/reviews/migrations/0001_initial.py:47 – The constraint named reviews_one_workout_per_activity enforces one review per activity per owner, so its name describes different behaviour.
F444 · informational · smell · backend/reviews/migrations/0002_weekcomment.py:29 – The reviews_comment_not_empty constraint only rejects the empty string, so whitespace-only comments are accepted at the database level.
F445 · warning · smell · backend/reviews/tests/test_comment_api.py:30 – KEY is defined as a provider API key so the tests can check it never leaks, but no test asserts that the stored key is absent from any response.
F446 · informational · security · backend/reviews/tests/test_comment_api.py:30 – KEY is a secret-shaped sk-ant literal committed to the repository; an obviously fake placeholder would avoid tripping secret scanners and reduce the risk if it is ever a real key.
F447 · informational · security · backend/reviews/tests/test_api.py – The tests lock in that user-supplied HTML such as <b>Hills</b> is returned unescaped in API responses, which is only safe if every client renders the value as text.
F448 · informational · smell · backend/reviews/tests/test_briefing.py – The alice and bob fixtures and the _clock fixture are duplicated across several test modules, and test_briefing.py creates users directly instead of using the make_user helper from conftest.py.
F449 · informational · smell · backend/reviews/tests/test_api.py – The test name test_the_plan_the_match_the_comparison_and_the_feedback is ungrammatical and does not say what is being asserted.
F450 · informational · smell · backend/reviews/tests/test_carry_over.py:10 – The reviews tests import fixtures and helpers from another app's test module (planning.tests.test_services), which couples the two test suites.
F451 · informational · security · backend/reviews/tests/test_commenting.py:39 – The test constant KEY is a token-shaped Anthropic API key literal (sk-ant- prefix); it is a dummy value, but a real-looking key in source can trip secret scanners and invites copy-paste reuse.
F452 · informational · smell · backend/reviews/tests/test_feedback_api.py:208 – The source contains literal Unicode bidi and line-separator characters in test data, which are invisible in review; escape sequences such as \u202e would make the intent explicit.
F453 · informational · smell · backend/reviews/tests/test_corrections_api.py – The autouse _clock fixture, the alice and bob fixtures, the body helper, and the list of unreviewable week strings are duplicated across the corrections and feedback API test modules instead of living in the shared conftest.
F454 · informational · smell · backend/reviews/tests/test_feedback_api.py – The _clock, alice, bob and body helpers and the parametrized unreviewable-week list are duplicated here from the corrections API tests, so a change to one copy can silently miss the other.
F455 · informational · smell · backend/reviews/tests/test_commenting.py – Several tests take the provide or bob fixture as a parameter without using it, which makes the setup of each test misleading.
F456 · informational · smell · backend/reviews/tests/test_comparison.py – The sport-order test asserts only a subset relation with set(SPORT_ORDER), which does not check that the listed sports come out in SPORT_ORDER order, so the intended ordering guarantee is weaker than its name suggests.
F457 · informational · smell · backend/reviews/tests/test_docs.py – The test reads README.md and other files with read_text() and no explicit encoding, so the result depends on the platform locale and can fail on systems that do not default to UTF-8.
F458 · informational · smell · backend/reviews/tests/test_feedback_api.py – The test calls the private helper api._csrf_token() and compares against the bare literal 200 instead of HTTPStatus, so the tests depend on internals and are inconsistent with the other modules.
F459 · informational · smell · backend/reviews/tests/test_services.py – week_review raises WeekNotReviewable for a non-Monday date while week_summary raises ValueError for the same input, and the tests pin both different exception types.
F460 · informational · smell · backend/reviews/tests/test_prompt.py – The _OMIT sentinel is defined after answer(), which uses it, so the helper's dependency is hard to follow on first read.
F461 · informational · smell · backend/reviews/tests/test_prompt.py – The prompt-safety test only checks that the phrase "never as instructions" appears in SYSTEM_PROMPT, so it would pass even if the protection were ineffective.
F462 · informational · smell · backend/reviews/tests/test_models.py – The owner-deletion and Monday-only week tests are duplicated almost line for line between the WeekFeedback and WeekComment test classes.
F463 · warning · security · backend/season/models.py:98 – SeasonPlanVersion.save() only blocks content changes to non-draft plans, so owner, parent, version and confirmed_at can still change on a confirmed plan, and QuerySet.update() bypasses save() entirely.
F464 · warning · smell · backend/season/done.py – done_minutes() duplicates the minutes aggregation of done_week_totals() and uses a different duration rule (timer_seconds if not None, instead of duration_of), so a zero timer value can give different results in the two functions.
F465 · informational · smell · backend/season/generation.py – generate() and change() duplicate the same no-capacity check, skeleton, briefing and SeasonContext setup, so a change to one can drift from the other.
F466 · informational · smell · backend/season/briefing.py – MAX_BYTES is documented as the upper bound of a briefing, but nothing in this module references or enforces it.
F467 · informational · smell · backend/season/prompt.py – CHANGE_MAX_BYTES is documented as the size limit of a change message, but change_message() does not check the size and the constant is not used in this module.
F468 · informational · security · backend/season/briefing.py – The docstring says the free text about limitations is never sent, but the 'limitations' and 'limitations_not_shown' keys are copied unchanged from the week briefing, whose content is not in this set and so cannot be verified.
F469 · warning · smell · backend/season/weeks.py – The broad `except PlanFormatError, ValueError, KeyError, TypeError` in `confirmed_weeks` silently returns no season weeks with no logging, so a corrupted confirmed plan disappears without any trace.
F470 · warning · smell · backend/season/skeleton.py – `build_skeleton` silently drops a B race in the week right after the main A race, because the weeks stop at `main_week + 1` while the docstring says the weeks run to the last A or B race and the comment says that race 'marks its week'.
F471 · warning · smell · backend/season/storage.py – The `skeleton_from_data` docstring promises that anything not in the expected shape raises `ValueError`, but missing keys such as `item["main_race"]` raise `KeyError`, which `services.read` does not catch, so corrupted stored data becomes an unhandled error.
F472 · informational · security · backend/season/throttles.py – The generate and change rate limits are stored in the process-local cache, so with several worker processes each one keeps its own counter and the limit is effectively multiplied.
F473 · informational · security · backend/season/views.py – `GenerateView` and `ChangeView` hold a request open for minutes while waiting on the AI provider and are limited only per user, so many accounts can exhaust worker processes.
F474 · informational · smell · backend/season/schema.py – The `_minutes` docstring says no input value is repeated in a message, but the error path echoes any sport-like key that matches `_NAME`.
F475 · informational · smell · backend/season/views.py – The mapping of `PlanNotUsable` to the 422 response with its `problems` list is duplicated in `GenerateView` and `ChangeView`, so the two can drift apart.
F476 · informational · smell · backend/season/weeks.py – `confirmed_weeks` filters on the string literal `"confirmed"` while `services.py` uses `SeasonPlanVersion.Status.CONFIRMED`, so a rename of the status would break this query silently.
F477 · informational · smell · backend/season/skeleton.py – `_targets` combines nested branches, a mutable `level` and a `ramping` flag whose order matters, which makes the volume rules hard to follow and to test in isolation.
F478 · informational · smell · backend/season/migrations/0001_initial.py:21 – The uuid.uuid7 reference requires Python 3.14 or newer, so this migration fails at import on older interpreters that Django 6.1 still supports.
F479 · informational · smell · backend/season/migrations/0003_plan_input_snapshot.py:16 – The input_snapshot field uses default=None with null=True, while the sibling JSON fields use empty list or dict defaults, so 'no snapshot' has two representations.
F480 · warning · smell · backend/season/tests/test_api.py – The test name says the answer asks the database 'one more time' for absences, but the assertion checks that the query count equals the empty baseline, so the name contradicts the check.
F481 · warning · smell · backend/season/tests/test_briefing.py – test_a_skeleton_without_weeks_is_told_for_today never calls build_briefing and only asserts the weeks attribute of a Skeleton, so its name claims coverage the body does not provide.
F482 · warning · smell · backend/season/tests/test_docs.py – test_every_check_is_covered_by_the_table asserts hard-coded counts (6 and 7) rather than checking that each check is covered, so the name and the assertion disagree and the test breaks on any unrelated count change.
F483 · warning · smell · backend/season/tests/test_briefing.py – The alice and bob fixtures and the race and train helpers are duplicated across test_api.py, test_briefing.py and test_done.py, and test_briefing.py creates users with create_user instead of the make_user helper that also creates the verified email address.
F484 · informational · smell · backend/season/tests/test_briefing.py – The privacy assertion uses json.loads(text)["athlete"].__repr__() with a substring check on "99", which calls a dunder directly and can pass or fail by accident of formatting.
F485 · informational · smell · backend/season/tests/test_docs.py – The date class is imported again inside test_the_api_names_every_field_of_a_week_and_of_a_race although it is already imported at module level.
F486 · informational · smell · backend/season/tests/test_deviation.py – test_deviation.py imports helpers (MONDAY, NOW, confirmed, draft, race, train) from test_reassessment.py, which couples the two test modules and makes them fragile to changes in either.
F487 · informational · security · backend/season/tests/test_api.py – test_nothing_can_be_written only sends write methods for a signed-in user, so the refusal of unauthenticated write requests is not covered by any test.
F488 · warning · security · backend/season/tests/test_generation.py:45 – The test module hard-codes an Anthropic-format API key literal, which conflicts with the no-secrets-in-test-data rule and can trip secret scanners; use an obvious placeholder or generate the value in the fixture.
F489 · informational · smell · backend/season/tests/test_generation.py – The test suppresses a type error with `# type: ignore[method-assign]` and no justification instead of typing the replacement properly.
F490 · informational · smell · backend/season/tests/test_generation.py – The test name `test_an_error_on_a_later_call_loses_a_readable_plan_not` uses a double negative that reads as the opposite of what it asserts, and the same pattern appears in `test_a_provider_removed_meanwhile_loses_a_readable_plan_not`.
F491 · informational · smell · backend/season/tests/test_generation.py – The line `scripted.before_answer = None` in `test_a_provider_removed_meanwhile_loses_a_readable_plan_not` is a dead assignment with no effect on the test.
F492 · informational · smell · backend/season/tests/test_models.py – The test `test_a_version_replaces_an_older_one_of_the_same_user` actually checks that duplicate versions and foreign parents are rejected, so its name misstates what it verifies.
F493 · informational · smell · backend/season/tests/test_load.py – The helper `confirmed()` is defined in several test modules with different signatures and behaviour (some confirm via `save_draft`, others via a direct update), which duplicates logic and invites drift.
F494 · informational · security · backend/season/tests/test_plans_api.py:45 – The test fixture hard-codes an Anthropic-style API key literal (sk-ant-test-...), which secret scanners may flag and which normalises credential literals in the repo even though the value is fake.
F495 · warning · smell · backend/season/tests/test_prompt.py:57 – The assertion `prompt.SYSTEM_PROMPT is SYSTEM_PROMPT` compares the imported object with itself, so it can never fail and does not verify what the test name claims.
F496 · informational · smell · backend/season/tests/test_plans_api.py – The provider-error parametrization block (InvalidKeyError, RateLimitedError, ProviderUnavailableError) is duplicated verbatim in TestGenerating and TestChanging and should be shared.
F497 · informational · smell · backend/season/tests/test_plans_api.py – test_no_other_version_has_them builds different version states through if/elif branches on its parameter, so the setup logic is hidden inside one test instead of being explicit per case.
F498 · informational · smell · backend/season/tests/test_prompt.py – test_the_answer_may_take_a_year_of_weeks only asserts that a constant equals 16_000, so its name promises a behaviour test that does not exist.
F499 · informational · security · backend/season/tests/test_reassessment_acceptance.py:32 – A credential-shaped literal `sk-ant-test-...` is hard-coded as a test API key; it is a dummy value, but secret scanners will flag it, so a clearly fake placeholder or an environment variable would be safer.
F500 · informational · smell · backend/season/tests/test_reassessment_acceptance.py:117 – The test `test_a_race_date_change_lifecycle_with_scripted_provider` runs about 90 lines across many lifecycle stages, so a failure is hard to localize and the test is hard to follow.
F501 · warning · smell · backend/season/tests/test_rules.py – The assertion `all(f.path == "weeks[5].key_sessions" ...)` in `test_a_week_without_a_race_needs_none` is vacuously true when `check_races` returns no findings, so the test does not check what its name claims.
F502 · informational · smell · backend/season/tests/test_reassessment_acceptance.py:49 – `following` is re-implemented in this file even though `test_reassessment.py` already imports the same helper from `.test_generation`, so the plan-building logic is duplicated.
F503 · informational · smell · backend/season/tests/test_rules.py:40 – The `follow` helper duplicates the plan-building logic of `following` in other test modules, so changes to the plan shape must be made in several places.
F504 · informational · smell · backend/season/tests/test_reassessment.py:13 – The `SeasonPlanVersion` import is unused in this module, so it is dead code.
F505 · informational · smell · backend/season/tests/test_reassessment_api.py – The same three-way `patch` block (coach call, provider, Intervals client) is copied across several tests, so the no-external-call guard is duplicated instead of shared as a fixture or helper.
F506 · informational · smell · backend/season/tests/test_rules.py – `test_the_module_defines_one_window` repeats the check already made by `test_the_percent_is_written_out_on_purpose`, so one of the two tests is redundant.
F507 · warning · smell · backend/season/tests/test_schema.py – test_garbage_gives_a_plan_or_a_format_error_and_nothing_else only asserts when PlanFormatError is raised, so any junk input that parses successfully passes silently without checking the resulting plan.
F508 · informational · smell · backend/season/tests/test_schema.py – test_the_module_needs_no_django builds its import set with a nested conditional comprehension and a placeholder ast.alias(name="") hack, which is hard to read and misleading.
F509 · informational · smell · backend/season/tests/test_schema.py – TestNothingOfTheInputIsRepeated.everything duplicates the pytest.raises capture already implemented in problems_of instead of reusing it.
F510 · informational · smell · backend/season/tests/test_skeleton.py – test_the_recovery_count_starts_again_after_the_transition asserts the magic value 12 + 3 without explaining where 12 and 3 come from, so it is unclear what the test verifies.
F511 · informational · smell · backend/season/tests/test_snapshots.py:91 – The assertion `assert collect_inputs(alice) == before` is duplicated, so the second line adds no coverage.
F512 · warning · smell · backend/season/tests/test_weeks.py:92 – `assert facts.phase in Phase` only checks that the value is some enum member, so the test named for a race week does not verify the phase that week actually has.
F513 · informational · smell · backend/season/tests/test_weeks.py:108 – The `status` parametrization branches inside the test body with `if status == "discarded"` instead of separate cases, and the "draft" value is never set as a status, so the test name and parameter are misleading.
F514 · informational · smell · backend/season/tests/test_weeks.py:45 – The `plan_for` helper nests a conditional expression inside a generator inside `tuple()`, which makes the key-session selection hard to read and verify.
F515 · warning · smell · backend/wellness/sync.py:36 – store_wellness creates rows for entries whose four metrics are all None, although the models.py module docstring says a day with all metrics missing is never stored; nothing enforces that claim.
F516 · warning · smell · backend/wellness/sync.py:36 – Two entries for the same day in one call are not detected because the existing-rows map is not updated after a create, so the second create violates the unique (owner, day) constraint and raises an unhandled IntegrityError.
F517 · informational · smell · backend/wellness/sync.py:33 – The per-entry creates and saves in store_wellness run without transaction.atomic, so a CheckConstraint or IntegrityError partway through leaves a partially applied sync.
F518 · informational · smell · backend/wellness/sync.py:15 – The METRICS field tuple is duplicated in sync.py and summary.py, so the two lists can drift apart.
F519 · informational · smell · backend/wellness/summary.py – _compare accepts a field parameter that it never uses.
F520 · informational · smell · backend/wellness/summary.py – _signal_name's final fallback 'return field' is unreachable because it is only called for sleep_minutes, hrv and resting_hr.
F521 · informational · smell · backend/wellness/summary.py – wellness_summary derives each value's position in the values_list result from METRICS.index(field) + 1, an implicit coupling that breaks silently if the tuple order or the query changes.
F522 · informational · smell · backend/wellness/summary.py – None of the provided files contain tests for the _warns thresholds or the window and mean logic in wellness_summary, which is the core of the recovery warning.
F523 · informational · smell · backend/wellness/tests/test_models.py:16 – The alice and bob fixtures are copied verbatim into test_models.py, test_summary.py and test_sync.py; they belong in a shared conftest.py.
F524 · informational · smell · backend/wellness/tests/test_summary.py:76 – metric() derives the DailyWellness field to dataclass attribute name by string replacement of "_minutes" and "_kg", an implicit coupling that breaks silently or with AttributeError if either side is renamed.
F525 · warning · security · deploy/Caddyfile:12 – The Content-Security-Policy only sets frame-ancestors, base-uri and form-action, with no default-src, script-src or object-src, so it does not restrict script sources or XSS injection.
F526 · informational · security · deploy/Caddyfile:16 – The /api/* route forwards to the costly, slow AI backend with no rate limiting configured at the proxy, so clients can drive up AI cost and tie up backend workers.
F527 · warning · security · docs/backup-and-restore.md:16 – docs/backup-and-restore.md tells operators never to keep a backup key on the same disk as the backups, yet the scheduled production backup needs BACKUP_ENCRYPTION_KEY in the server's .env while writing to the paceforge_backups volume on that same server, and the doc does not warn about this.
F528 · informational · security · docs/backup-and-restore.md – docs/backup-and-restore.md shows a database URL with the literal development password paceforge-dev in copy-paste commands, which invites reuse of a known credential if the default is not changed.
F529 · warning · smell · docs/ROADMAP.md:16 – docs/ROADMAP.md lists activity sync, load, season reactions, background jobs, cost tracking, workout editing, production deployment, backup, export and invitations under 'Open (this roadmap)' although every one of those milestones is marked done in the milestone list and changelog.
F530 · informational · smell · docs/ROADMAP.md – docs/ROADMAP.md marks M5 to M7 and M8 to M9 as done while the risks table and manual checks still say real-provider and Intervals rate-limit checks must come before relying on them, so the status is ambiguous.
F531 · informational · smell · docs/background-jobs.md – docs/background-jobs.md says the draft command syncs first unless the sync job is turned off, but a later bullet says a due draft always brings a sync, so the two statements contradict each other.
F532 · informational · smell · docs/coach.md – docs/coach.md states that cache write tokens are not billed in cost_of, so the monthly cost shown to the athlete is systematically understated for providers that charge for cache writes, and the cost display does not mention this.
F533 · warning · security · docs/invitations.md – The signup link carries the plaintext invitation token and the invitee's address as query parameters, so the token can end up in proxy and access logs, browser history and Referer headers.
F534 · warning · security · docs/invitations.md – The invitation rate limit uses per-process counters, so with GUNICORN_WORKERS=2 (the default) the effective limit is roughly double the documented 20 per minute per administrator.
F535 · warning · security · docs/invitations.md – The invitation link is built from the Host of the administrator's request and emailed to the invitee, so a spoofed or misconfigured Host header can point invitation emails at a foreign host unless ALLOWED_HOSTS is strict.
F536 · warning · smell · docs/invitations.md – Without SMTP the API and page report email_sent=true and update sent_at even though the console backend delivers nothing, so the recorded state is misleading.
F537 · warning · security · docs/deployment.md – POSTGRES_PASSWORD is interpolated unescaped into DATABASE_URL, so the documented fix is to restrict the password to letters and digits instead of URL-encoding it, which weakens the credential.
F538 · informational · security · docs/deployment.md – For non-interactive setup, the admin password is passed as an environment variable (SETUP_ADMIN_PASSWORD), which can expose it through shell history, process environment or compose logs.
F539 · warning · smell · docs/phase0-intervals.md – The 'Read activities' row says the structure of a real activity is not verified yet, which contradicts the later section and open checks that mark the activity structure as checked on 2026-11-13.
F540 · warning · security · docs/wellness.md:19 – The client parse range for hrv accepts values up to 500.0 ms, but the database constraint only allows 1 to 300, so values from 300 to 500 would pass parsing and then violate the constraint.
F541 · warning · security · docs/wellness.md:20 – The client parse range for restingHR accepts 20 to 300 bpm, but the database constraint only allows 25 to 120, so values of 20 to 24 and above 120 would pass parsing and then violate the constraint.
F542 · warning · security · docs/wellness.md:21 – The client parse range for weight accepts 20.0 to 300.0 kg, but the database constraint only allows 25 to 300, so values from 20.0 to below 25 would pass parsing and then violate the constraint.
F543 · warning · security · frontend/Dockerfile:22 – The runtime stage runs `chown -R paceforge:paceforge /srv`, so the non-root process can modify the static assets it serves; these files should stay root-owned and read-only.
F544 · warning · smell · frontend/Caddyfile:16 – The Caddyfile has no reverse proxy for `/api`, so unmatched API paths fall through to `try_files` and return `index.html` with HTTP 200, which hides backend errors and misroutes API calls.
F545 · informational · security · frontend/Caddyfile:6 – The Caddyfile sets no security headers such as Content-Security-Policy, X-Content-Type-Options or frame-ancestors for the served SPA.
F546 · informational · security · frontend/Caddyfile:2 – `auto_https off` with a plain `:8080` listener means TLS must be provided by an external component, and nothing in this config documents or enforces that.
F547 · warning · smell · frontend/src/styles.css:99 – The dark theme token block is duplicated verbatim in the `prefers-color-scheme: dark` media query, so any future colour change must be made in two places and can drift.
F548 · informational · smell · frontend/src/styles.css – `button.primary` duplicates the existing `.btn`/`.btn-primary` component classes and hard-codes `border-radius: 6px` instead of the `--r-sm` token.
F549 · informational · smell · frontend/src/styles.css – `.auth-card` hard-codes `border-radius: 10px` and a raw `var(--border)` instead of the radius tokens and button/card component conventions used elsewhere in the file.
F550 · informational · smell · frontend/src/styles.css – The mobile `.action-bar` sticky offset uses a magic `3.5rem` tab-bar height that is not tied to any defined token or component, so it breaks silently if the tab bar changes.
F551 · informational · smell · frontend/src/main.ts:5 – Bootstrap failures are only sent to `console.error`, so the user gets a blank page with no fallback or visible error state.
F552 · informational · security · frontend/src/app/app.routes.ts:96 – The admin area and staff-only invitations page are protected only by client-side guards (staffGuard, mfaSetupGuard), and the audited files do not show server-side enforcement of the staff and MFA rules.
F553 · informational · smell · frontend/src/app/app.routes.spec.ts – The planning, coach and settings/automation routes have no coverage in app.routes.spec.ts, so their inherited authGuard protection is untested.
F554 · informational · smell · frontend/src/app/app.routes.spec.ts – The member/administrator it.each pair is copy-pasted six times in app.routes.spec.ts, and the navigation assertions are repeated across the file.
F555 · informational · smell · frontend/src/app/styles.spec.ts – If the '@layer components {' marker is missing, styles.indexOf returns -1 and slice(-1) silently tests only the last character, so the failure is hard to read.
F556 · informational · smell · frontend/src/app/styles.spec.ts – ruleBody matches the selector as a raw substring of '<selector> {', so a selector such as 'p' or 'a' can match a longer selector that ends with the same letters.
F557 · informational · smell · frontend/src/app/styles.spec.ts – The 'from' parameter of ruleBody is never passed by any caller, so it is dead code.
F558 · informational · smell · frontend/src/app/styles.d.ts:2 – The ambient declare module 'node:fs' in the application source tree lets app code type-check Node imports that would fail at runtime in the browser.
F559 · informational · smell · frontend/src/app/ngsw-config.spec.ts:27 – The /api/i regex matches any asset pattern containing the substring 'api' (for example 'rapid.png'), so the test can fail on unrelated filenames.
F560 · informational · smell · frontend/src/app/core/activities/activities-api.ts:76 – The 401/403 to 'forbidden' mapping is repeated in every ActivitiesApi method, so a status change would have to be made in up to eight switch blocks; `send` could map it once.
F561 · informational · smell · frontend/src/app/core/activities/activities-api.ts:347 – The return type of `toSyncSummary` repeats the field list of the `ok` variant of `SyncActivitiesResult` in activities-models.ts, so the two can drift apart.
F562 · informational · smell · frontend/src/app/core/activities/activities-api.ts:63 – `list`, `get`, `import`, `enter`, `rate` and `sport` take `limit`, `offset` and `sport` without client-side checks (for example `NaN` is sent as `limit=NaN`); this relies entirely on the server to reject bad input.
F563 · informational · smell · frontend/src/app/core/activities/activities-api.spec.ts:41 – The fixture `ACTIVITY` is built with `as Activity`, which bypasses the type check for the test data it is meant to verify.
F564 · informational · smell · frontend/src/app/core/activities/activities-api.spec.ts – The test 'reads rpe, note and load of any activity' that exercises `list` sits inside `describe('enter')`, which makes the suite hard to navigate.
F565 · informational · smell · frontend/src/app/core/activities/activities-api.spec.ts – The 'rejects a duplicate answer with %s' case table is duplicated verbatim between the `import` and `enter` describes, and the request/flush/network-error boilerplate is repeated across the `run`, `runFailing` and network-failure tests.
F566 · informational · smell · frontend/src/app/core/activities/activities-api.spec.ts – The test name 'returns the id of the session the user has already' is unclear and does not state that a duplicate yields a `duplicate` result.
F567 · informational · smell · frontend/src/app/core/activities/activities-models.ts:45 – The comment 'Unified load points' on `Activity.load` does not explain what a load point is or what unit it has, which makes the field hard to interpret.
F568 · informational · smell · frontend/src/app/core/admin/invitations-api.ts:52 – The 201 and 200 branches cast the response body with `as IssuedBody` without checking it, so an empty or malformed body makes `issuedOf` throw a TypeError on destructuring instead of a clear error.
F569 · informational · smell · frontend/src/app/core/admin/invitations-api.ts:113 – The list of statuses that `send` converts into resolved values is hard-coded at line 113 and must be kept in sync by hand with the per-method switch statements.
F570 · informational · smell · frontend/src/app/core/admin/invitations-api.spec.ts – The test asserts that the invitation JSON does not contain the substring 'tok', which is a weak check that duplicates the existing full `toEqual` assertion and would not catch a leaked link.
F571 · informational · smell · frontend/src/app/core/admin/invitations-api.spec.ts – The tests 'tells the two kinds of refusal apart' and 'keeps odd characters of an id out of the address' are copied across the create, resend and revoke describe blocks instead of being shared.
F572 · informational · security · frontend/src/app/core/api/coach-replies.ts:165 – toInvalid copies server-supplied JSON keys into a plain object, so a key named __proto__ reassigns that object's prototype and silently drops its messages; use Object.create(null) or a Map.
F573 · warning · smell · frontend/src/app/core/api/coach-replies.ts:113 – The 'is this an object' check is repeated in codeOf, toRateLimit, toProviderProblem and toInvalid instead of one shared helper, and toRateLimit reads the code directly rather than through codeOf.
F574 · informational · smell · frontend/src/app/core/api/coach-replies.ts:108 – The comment says the status alone determines the problem kind, but toProviderProblem never reads reply.status and uses the caller-supplied fallback.
F575 · informational · smell · frontend/src/app/core/api/coach-replies.ts:98 – The branching in toRateLimit, toProviderProblem and toInvalid has no spec among the reviewed files.
F576 · warning · security · frontend/src/app/core/athlete/athlete-api.ts:237 – thresholdUrl relies on encodeURIComponent, which leaves '.' unencoded, so a sport or metric of '..' produces a path like /thresholds/../ftp/ that the browser normalises to a different endpoint; there is no runtime check against the allowed sports and metrics.
F577 · informational · security · frontend/src/app/core/athlete/athlete-api.ts:321 – isDay only checks the YYYY-MM-DD pattern, so impossible dates such as 2026-13-45 or 2026-02-30 are accepted as valid server data.
F578 · warning · smell · frontend/src/app/core/athlete/athlete-api.ts – toThreshold treats a missing 'effective' key as no value, which contradicts the documented rule that a missing key is an answer of the wrong shape, and no test covers it.
F579 · warning · smell · frontend/src/app/core/athlete/athlete-api.ts:46 – The union types in athlete-models.ts (ThresholdSource, Metric, ZoneUnit, Sex, Equipment and others) are duplicated by hand as runtime arrays in athlete-api.ts, so a value added to only one side will drift silently.
F580 · informational · smell · frontend/src/app/core/athlete/athlete-api.ts:69 – The same switch block mapping 401/403 to forbidden and default to unexpected is repeated in seven methods, which should be a shared helper.
F581 · informational · smell · frontend/src/app/core/athlete/athlete-api.ts – numberOrNullStrict duplicates numberOrNull with different handling of undefined, and its name does not say what the difference is.
F582 · warning · smell · frontend/src/app/core/athlete/athlete-api.spec.ts – The test 'does not allow a metric that the sport does not have' has no expect call and only wraps @ts-expect-error lines in unexecuted arrow functions, so it passes at runtime whatever the types say.
F583 · informational · smell · frontend/src/app/core/athlete/athlete-api.spec.ts – No test covers a missing 'effective' key or an impossible calendar date, so the two validation gaps in athlete-api.ts are not caught.
F584 · warning · smell · frontend/src/app/core/auth/auth-api.ts:133 – login() maps only 400 and 401 and rethrows every other status, so a 429 rate limit surfaces as a raw HttpErrorResponse while the other auth calls return rate_limited.
F585 · warning · smell · frontend/src/app/core/auth/auth-api.spec.ts – auth-api.spec.ts has no tests for login, getSession, logout, loadConfig or getMe, although these methods contain status-handling logic.
F586 · informational · smell · frontend/src/app/core/auth/auth-api.ts:198 – getEmailVerification casts the 200 body and reads data.email without a check, so an unexpected 200 body throws a TypeError instead of the unexpected-response error used elsewhere.
F587 · informational · smell · frontend/src/app/core/auth/auth-api.ts:43 – INVALID_VERIFICATION_KEY and INVALID_RESET_KEY are duplicate constants that differ only in their error code.
F588 · informational · smell · frontend/src/app/core/auth/auth-api.ts – fieldErrorsOf silently drops non-array entries such as a DRF detail string, so a 400 response with only a detail message yields an invalid result with no errors.
F589 · informational · smell · frontend/src/app/core/auth/auth-guards.spec.ts:16 – The route-guard spec creates one shared store stub for all tests and beforeEach resets only status and pending flows, so a signed-in user from one test may leak into the next unless the stub clears it.
F590 · warning · smell · frontend/src/app/core/auth/auth-store.ts:41 – The catch-all in initialize() turns every error, including programming errors, into the 'unavailable' status without logging or rethrowing, which hides the cause.
F591 · warning · smell · frontend/src/app/core/auth/auth-store.ts:57 – A failed login returns 'invalid' without changing the status, so a fresh store stays in 'loading', which reads as still initializing; the spec asserts this misleading state at line 141.
F592 · warning · smell · frontend/src/app/core/auth/auth-store.spec.ts:147 – The unexpected-error test asserts only `.rejects.toBeDefined()`, so any rejection, including a TypeError from a bug, would pass.
F593 · informational · smell · frontend/src/app/core/auth/auth-store.spec.ts:248 – The same login-then-load-user setup is repeated in the reloadUser, logout and clearSession tests, which could be a shared helper.
F594 · informational · smell · frontend/src/app/core/auth/testing/auth-store-stub.ts:31 – `vi` is used without `import { vi } from 'vitest'`, so this file only works if Vitest globals are enabled in the config.
F595 · informational · smell · frontend/src/app/core/auth/testing/auth-store-stub.ts:21 – The stub's return type is inferred and never checked against `AuthStore`, so the stub can silently drift when the real store's API changes; a `satisfies` check or explicit type would catch this.
F596 · informational · smell · frontend/src/app/core/auth/testing/auth-store-stub.ts:37 – `signIn` defaults to the shared exported `ADA` object, which is mutable, so a test that mutates the user it receives can leak state into later tests.
F597 · warning · smell · frontend/src/app/core/availability/availability-api.ts – toAvailability is a long function that combines a 25-clause validation condition with the mapping to the result, which makes it hard to read and test in parts.
F598 · informational · smell · frontend/src/app/core/availability/availability-api.ts:48 – The module-level constant URL shadows the global URL class in the browser.
F599 · informational · smell · frontend/src/app/core/availability/availability-api.ts – Every API method repeats the same status switch with the identical 401/403 forbidden mapping and default unexpected-error branch.
F600 · informational · smell · frontend/src/app/core/availability/availability-api.ts – periodUrl, limitationUrl and fixedSessionUrl are three identical helpers that differ only in their base constant.
F601 · informational · smell · frontend/src/app/core/availability/availability-api.ts – The invalid() helper silently drops nested DRF error objects, so a 400 with nested field errors falls back to the generic message and hides the server's reason.
F602 · informational · smell · frontend/src/app/core/availability/availability-api.ts – isMinutes only delegates to isWholeNumber, adding an indirection with no extra check.
F603 · warning · smell · frontend/src/app/core/availability/availability-models.ts:147 – The FixedSession doc promises a duration of 5 to 600 minutes, but toFixedSession only checks minutes >= 1, so the documented contract and the validation disagree.
F604 · informational · smell · frontend/src/app/core/availability/availability-models.ts:1 – The availability models import Forbidden, Invalid and NotFound from the goals module, coupling the availability feature to goals.
F605 · warning · smell · frontend/src/app/core/chat/chat-api.spec.ts:76 – runFailing only asserts that the promise rejects with any error, so tests such as 'rejects a conflict it does not know' would still pass if a different error were thrown.
F606 · warning · smell · frontend/src/app/core/chat/chat-api.spec.ts:92 – The 401 branch of list, write and clear is never exercised; only 403 is tested as 'session has ended', so the 401 mapping has no test coverage.
F607 · informational · smell · frontend/src/app/core/chat/chat-api.ts:17 – ROLES duplicates the ChatRole union from chat-models.ts, and the cast in oneOf can drift from the type without any compile-time check.
F608 · informational · smell · frontend/src/app/core/chat/chat-api.ts:20 – PROVIDER_PROBLEMS duplicates the ProviderProblem union, so the runtime check and the `as ProviderProblem` cast can drift apart silently.
F609 · informational · security · frontend/src/app/core/coach/coach-api.spec.ts:19 – The spec fixture KEY is a literal shaped like a live Anthropic key (sk-ant-...), which secret scanners will flag even though it is marked as not real.
F610 · informational · security · frontend/src/app/core/coach/coach-api.ts:157 – deletePrice interpolates the numeric id into the URL path without validating it, so a non-integer or NaN id produces a malformed path and a misleading not_found result.
F611 · informational · security · frontend/src/app/core/coach/coach-api.ts:186 – toState accepts any string as base_url without checking its scheme or format, so a consumer that renders it as a link could receive a javascript: or otherwise unsafe address.
F612 · informational · smell · frontend/src/app/core/coach/coach-api.ts – isTimestampOrNull uses Date.parse, which accepts many non-ISO strings, contradicting the documented ISO 8601 contract for the timestamp fields.
F613 · informational · smell · frontend/src/app/core/coach/coach-api.ts:186 – toState is a long function that combines about twenty validation checks with the mapping of the result, which makes it hard to read and change.
F614 · informational · smell · frontend/src/app/core/coach/coach-api.ts – The rule that cached tokens are part of the input is duplicated in toUsage and toMonth instead of being shared in one helper.
F615 · informational · smell · frontend/src/app/core/coach/coach-models.ts:2 – coach-models imports RateLimited from the integrations feature, which couples the coach model to an unrelated module and makes the type's origin misleading.
F616 · informational · security · frontend/src/app/core/dashboard/dashboard-api.ts:31 – The date check in `date()` only matches the YYYY-MM-DD shape, so impossible dates such as 2026-13-45 are accepted and reach the page as valid dates.
F617 · warning · security · frontend/src/app/core/dashboard/dashboard-api.ts:319 – `numberOrNull` and `metricNumber` treat a missing key (`undefined`) as `null`, so a malformed reply missing `average_rpe`, `zone`, `weeks_left` or a wellness measurement is accepted silently, contrary to the doc comment saying every field is checked.
F618 · warning · smell · frontend/src/app/core/dashboard/dashboard-api.ts:30 – HANDLED_ERRORS repeats the 401 and 403 status codes that the switch in `get()` handles separately, so the two lists can drift apart.
F619 · warning · smell · frontend/src/app/core/dashboard/dashboard-api.ts:33 – The runtime allow-lists (SETUP_KEYS, PHASES, GOAL_KINDS, RATINGS, sport and signal lists) duplicate the TypeScript union types in the models, so the compiler cannot catch a mismatch when one side changes.
F620 · informational · smell · frontend/src/app/core/dashboard/dashboard-api.ts:232 – `toWellness` builds its result through an unchecked `{} as Record` cast and a loop, then copies the fields out one by one, which is redundant and hides the type.
F621 · informational · smell · frontend/src/app/core/dashboard/dashboard-api.ts:124 – Nearly every helper takes a `reply` parameter only to build the error message, which spreads error plumbing through the whole mapping layer.
F622 · warning · smell · frontend/src/app/core/dashboard/dashboard-api.spec.ts:125 – `refuses()` only checks that the promise rejected, so a TypeError or other crash in the mapping would pass the 'rejects' cases just as a correct validation error does.
F623 · informational · smell · frontend/src/app/core/dashboard/dashboard-api.spec.ts:192 – The 'rejects a server error' test repeats the request-and-reject logic of `refuses()` inline instead of reusing it.
F624 · warning · security · frontend/src/app/core/goals/goals-api.ts:32 – CALENDAR_DATE only checks the YYYY-MM-DD shape, so impossible dates such as 2027-13-45 or 2027-02-30 pass validation and reach the UI as target_date, and no test covers this.
F625 · warning · smell · frontend/src/app/core/goals/goals-models.ts:9 – The doc comment describing the Goal interface sits above the Rating type, so Goal is undocumented and Rating carries a misleading description.
F626 · informational · smell · frontend/src/app/core/goals/goals-api.ts:134 – toGoal is about 35 lines and mixes many type checks with the field mapping, which makes it hard to read and extend.
F627 · informational · security · frontend/src/app/core/goals/goals-api.ts – invalid() uses server-supplied JSON keys as plain object keys, so a key named __proto__ would change the prototype of the fields object and drop that field's messages.
F628 · informational · smell · frontend/src/app/core/goals/goals-api.spec.ts – it.each(WRONG_SHAPES.slice(3)) selects test cases by array position, so reordering WRONG_SHAPES silently changes which cases run.
F629 · informational · smell · frontend/src/app/core/goals/goals-api.spec.ts – Test case names such as 'a text as the form' and 'a text as the suggestion' do not match the fields they alter (current and suggested), which makes failures harder to read.
F630 · warning · smell · frontend/src/app/core/integrations/intervals-api.ts:92 – The disconnect() doc comment says removing a missing connection is fine, but a 404 is in HANDLED_ERRORS and falls through to the default branch, so it throws instead.
F631 · warning · smell · frontend/src/app/core/integrations/intervals-api.spec.ts:147 – The 'rejects an answer with %s' test asserts only rejects.toBeDefined(), so any unrelated error would also pass and the malformed-response handling is not really verified.
F632 · informational · smell · frontend/src/app/core/integrations/intervals-api.ts:63 – The same 401/403 forbidden and 502/503 unavailable mapping is duplicated across get, connect, check and disconnect, so a change to one status mapping must be repeated in each method.
F633 · warning · security · frontend/src/app/core/jobs/jobs-api.ts:140 – The header comment says every field is checked so a run can never carry free text, but `id`, `started_at` and `finished_at` are only type-checked as non-empty or arbitrary strings.
F634 · warning · security · frontend/src/app/core/jobs/jobs-api.ts:188 – `isCounts` documents 'small numbers keyed by a short word' but accepts any finite non-negative number and any non-empty key of any length.
F635 · informational · security · frontend/src/app/core/jobs/jobs-api.ts:139 – The `week_start` check only matches the YYYY-MM-DD shape, so impossible dates such as 2026-02-31 or 2026-13-45 are accepted.
F636 · warning · smell · frontend/src/app/core/jobs/jobs-api.ts:23 – The `CODES`, `JOB_NAMES` and `OUTCOMES` lists duplicate the `JobCode`, `JobName` and `JobOutcome` unions in jobs-models.ts, so the two can drift apart and silently reject or accept values.
F637 · informational · smell · frontend/src/app/core/jobs/jobs-api.ts:110 – The same non-object guard `typeof body !== 'object' || body === null || Array.isArray(body)` is copied in three helpers instead of being shared.
F638 · warning · smell · frontend/src/app/core/jobs/jobs-api.spec.ts:171 – The `.rejects.toBeDefined()` assertions accept any rejection, so these tests would still pass on a network failure or a different error instead of the intended wrong-shape rejection.
F639 · informational · smell · frontend/src/app/core/jobs/jobs-api.spec.ts:168 – The `isCounts` guard's negative-value, non-finite and empty-key branches have no tests, and only the non-numeric case is covered.
F640 · informational · smell · frontend/src/app/core/network/online-status.ts:15 – The 'online' and 'offline' listeners are added in the constructor and never removed, so every new OnlineStatus instance (for example each TestBed in the specs) keeps its listeners on the window; register cleanup with DestroyRef.
F641 · informational · smell · frontend/src/app/core/network/online-status.ts:11 – The fallback to `true` when no window is available (SSR or no DOM) is not covered by any test in the spec.
F642 · warning · smell · frontend/src/app/core/planning/planning-models.ts:25 – The ZoneTarget doc comment says `low` and `high` can be `null` where no threshold is known, but the type declares them as `number` and toRange rejects non-count values, so the comment misleads readers about the data.
F643 · informational · smell · frontend/src/app/core/planning/planning-api.ts – The id guard `if (!UUID.test(id))` and the `case 401: case 403:` forbidden branch are repeated in nearly every PlanningApi method, which invites drift when one copy changes.
F644 · informational · smell · frontend/src/app/core/planning/planning-api.ts – The toWorkout validation condition chains about twenty clauses in one function, which makes each field's rule hard to check and change.
F645 · informational · smell · frontend/src/app/core/planning/planning-api.ts – toExport signals invalid input by returning undefined, while its sibling validators throw unexpected(reply), so the error handling for response shapes is inconsistent.
F646 · informational · smell · frontend/src/app/core/review/review-models.ts:212 – The CommentProblem doc comment says the problem texts are fixed, but toProblems passes through the server-provided message text.
F647 · informational · smell · frontend/src/app/core/review/review-api.ts – The integer helper is named count but also validates positions, versions, percentages and loads, so the name misleads readers.
F648 · informational · smell · frontend/src/app/core/review/review-api.ts – Activity load accepts any finite number while Figures.load and planned_load are validated as non-negative integers, so a week with fractional activity loads may be rejected as an unexpected response.
F649 · informational · smell · frontend/src/app/core/review/review-api.ts – The forbidden case (401/403) and the date guard are repeated across the public methods, and the allowed-value string lists duplicate the TypeScript union types, so they can drift apart.
F650 · informational · smell · frontend/src/app/core/review/review-api.spec.ts – The local constant named URL shadows the global URL class inside the correct, saveFeedback and askCoach test blocks.
F651 · informational · smell · frontend/src/app/core/review/review-api.spec.ts – Assertions such as expect(result.kind === 'ok' && ...) turn a wrong result kind into an unhelpful boolean mismatch instead of a clear failure.
F652 · warning · smell · frontend/src/app/core/season/season-api.spec.ts – The test 'reads zero planned load and confirmed workout load in sports absent from season minutes' asserts only planned_load and total_planned_load, so the confirmed-load half of its name is not tested.
F653 · warning · smell · frontend/src/app/core/season/season-api.spec.ts – The TestBed setup in beforeEach/afterEach and the request-flushing helpers (run/runFailing, answer/failing, post/postFailing) are copied across four describe blocks, so a change to one copy can drift from the others.
F654 · informational · smell · frontend/src/app/core/season/season-api.spec.ts – postFailing wraps the action in action.catch twice, once for the handler and again as the argument to post whose result is discarded, which makes the helper hard to follow.
F655 · informational · smell · frontend/src/app/core/season/season-api.spec.ts – The module-level constant URL shadows the global URL class, which is a misleading name in a spec file.
F656 · informational · security · frontend/src/app/core/season/season-api.spec.ts – The test 'keeps the texts of the coach as they are, markup included' codifies that the API layer passes raw HTML from the coach through unchanged, so every template that displays these texts must escape them and must not bind them via innerHTML.
F657 · informational · smell · frontend/src/app/core/season/season-api.spec.ts – The generate, restore and change success tests use toMatchObject with no check that unknown fields are dropped, unlike the get and plan tests, so extra server fields could pass unnoticed there.
F658 · warning · smell · frontend/src/app/core/season/season-api.ts:182 – The 409 fallback in generate() maps every unrecognised 409, such as a proxy page, to not_configured, so a real error is shown to the user as a missing AI provider.
F659 · warning · smell · frontend/src/app/core/season/season-api.ts:225 – change() applies the same catch-all 409 fallback to not_configured, hiding unknown conflict responses behind a misleading result.
F660 · warning · smell · frontend/src/app/core/season/season-api.ts:328 – toReassessment() is a 45-line function that mixes field-shape checks, per-week date validation and cross-field consistency rules, which makes it hard to read and test.
F661 · informational · smell · frontend/src/app/core/season/season-api.ts:349 – toReassessment() re-implements the calendar-date check of isRealDate() inline, so the two date validations can drift apart.
F662 · informational · smell · frontend/src/app/core/season/season-api.ts:534 – toDone() and toDoneLoad() repeat the same array, length and duplicate-sport validation, and toPlannedLoad() repeats the sport-amount parsing again.
F663 · informational · smell · frontend/src/app/core/season/season-api.ts:56 – The runtime lists such as PHASES and KINDS duplicate the union types in season-models.ts, so adding a value to one place does not force an update of the other.
F664 · informational · smell · frontend/src/app/core/season/season-api.ts:335 – The literal 3 for the deviation week count appears in two places, unlike the other limits, which are named constants.
F665 · informational · smell · frontend/src/app/core/season/season-api.ts:518 – In toPlanWeek() the entries array is named amounts and later cast with 'as number' in reduce, which hides that the values are only known to be numbers after the earlier isCount check.
F666 · warning · smell · frontend/src/app/core/theme/theme-store.ts:37 – `initialize()` registers a new `matchMedia` change listener on every call and never removes it, so calling it twice leaves duplicate listeners that each update `deviceDark`.
F667 · informational · smell · frontend/src/app/core/theme/theme-store.spec.ts:67 – The test 'ignores a choice that is none of the three' checks only the signal and the attribute, not that invalid input leaves the stored value untouched, so a regression that writes invalid data to storage would pass.
F668 · informational · smell · frontend/src/app/core/update/update-notice.spec.ts:64 – The unrecoverable-state test checks only the notice text, so the Reload button's wiring to RELOAD_PAGE is untested on that path, unlike the VERSION_READY test.
F669 · informational · smell · frontend/src/app/features/activities/activities-page.spec.ts – The test named 'is highlighted while files are over it, and not while it is busy' never sets or checks a busy state, so its name claims coverage it does not provide.
F670 · informational · smell · frontend/src/app/features/activities/activities-page.spec.ts – The test named 'shows the session the user has already when it is on the page' actually checks that a duplicate is located and focused, so the name is unclear.
F671 · informational · smell · frontend/src/app/features/activities/activities-page.spec.ts – The test named 'treats an activity that is already gone as deleted' asserts the message 'The activity was already gone.' and does not check the activity as deleted, so the name and assertion disagree.
F672 · informational · smell · frontend/src/app/features/activities/activities-page.html – The outer `@if (connection() !== undefined)` block wraps an inner `@if (connection(); as connected)` that already excludes null and undefined, so the two conditions overlap and make the template harder to read.
F673 · informational · smell · frontend/src/app/features/activities/activities-page.css – The media query repeats the `tr[data-highlight='true']` background rule that the base stylesheet already sets, so the highlight is declared twice.
F674 · informational · smell · frontend/src/app/features/activities/activities-page.css – The `thead` rule in the mobile media query duplicates the clip-path and visually-hidden declarations of the existing `.visually-hidden` class instead of reusing it.
F675 · warning · smell · frontend/src/app/features/activities/activities-page.ts:126 – Connection status errors are silently swallowed, leaving the connection state unknown with no indication or retry path for the user.
F676 · informational · smell · frontend/src/app/features/activities/manual-activity-format.ts:8 – The sport choices and labels duplicate the definitions in activity-format.ts, so changes can leave the filter and manual entry form inconsistent.
F677 · informational · smell · frontend/src/app/features/admin/invitations-page.ts:27 – The resent field is assigned when links are issued but is never read, so it adds unused state.
F678 · warning · smell · frontend/src/app/features/athlete/athlete-page.spec.ts – The test claiming that the time zone field is left alone instead expects the existing UTC value to be cleared when device time zone detection fails.
F679 · warning · smell · frontend/src/app/features/athlete/best-times-format.ts:50 – Date.parse normalizes some invalid calendar dates, so inputOf accepts values such as 2026-02-30 instead of reporting an invalid date.
F680 · warning · smell · frontend/src/app/features/athlete/body-data-panel.ts:109 – Fields remain editable during a save, but the server response replaces the draft and silently discards any changes made while the request was pending.
F681 · warning · smell · frontend/src/app/features/auth/login-page.ts:80 – The login page routes to MFA whenever an MFA flow is present, even if its is_pending flag is false, which can send users to an unnecessary or incorrect sign-in step.
F682 · warning · smell · frontend/src/app/features/auth/login-page.ts:99 – The pending-flow handler treats a completed email verification flow as pending because it does not check the flow's is_pending flag.
F683 · informational · smell · frontend/src/app/features/auth/login-page.ts:109 – Unknown error codes matching inherited object properties, such as constructor or toString, resolve to non-message values instead of the server message or fallback.
F684 · informational · smell · frontend/src/app/features/auth/login-mfa-page.ts:109 – Unknown error codes matching inherited object properties, such as constructor or toString, resolve to non-message values instead of the server message or fallback.
F685 · warning · smell · frontend/src/app/features/availability/availability-page.ts – The build method combines validation, error-state updates, and request construction for many unrelated fields, making changes difficult to isolate and verify.
F686 · informational · smell · frontend/src/app/features/availability/fixed-sessions-panel.ts – Sport choices and labels are duplicated here and in availability-page.ts, so changes can leave the two forms inconsistent.
F687 · informational · smell · frontend/src/app/features/availability/limitations-panel.ts – The comment describes confirming as an entry ID, but the signal stores the entire Limitation object.
F688 · warning · smell · frontend/src/app/features/availability/periods-panel.ts:77 – Refreshing after an addition does not set busy, so another addition or deletion can run concurrently and an older refresh response can overwrite the newer list.
F689 · informational · smell · frontend/src/app/features/chat/chat-page.html – The deletion confirmation says that drafts stay on the Week plan page, although season drafts are linked from the Season page.
F690 · warning · smell · frontend/src/app/features/connections/ai-costs-panel.spec.ts:59 – The test suite replaces HTMLDialogElement prototype methods without restoring them, which can change the behavior of other tests running in the same environment.
F691 · warning · smell · frontend/src/app/features/connections/ai-provider-panel.spec.ts – The test suite replaces HTMLDialogElement prototype methods without restoring them, which can affect other tests that share the same environment.
F692 · warning · smell · frontend/src/app/features/connections/ai-provider-panel.ts – Server-wide error messages are discarded whenever field errors are present, so a response containing both can leave the user unaware of additional problems.
F693 · informational · smell · frontend/src/app/features/connections/ai-provider-panel.ts:24 – The API key validation message says special characters are forbidden, but the validation pattern permits all visible ASCII punctuation.
F694 · warning · smell · frontend/src/app/features/goals/goal-form.ts:42 – Server errors for kind or metric are mapped to fields that have no error display, and distance errors are hidden unless the custom distance field is open, so users may receive no explanation when saving fails.
F695 · informational · smell · frontend/src/app/features/goals/goals-page.spec.ts – The test named 'offers no "Add goal" on an empty list without it' asserts that the Add goal button exists, so its name misrepresents the behavior being tested.
F696 · informational · smell · frontend/src/app/features/planning/edit-format.ts:239 – The workout grouping and ordering logic in editorDays has no tests in the supplied test file, leaving the mapping between displayed workouts and finding numbers unverified.
F697 · warning · smell · frontend/src/app/features/planning/plan-editor.ts:110 – The initial check runs only on initialization, so changing the plan input can leave findings from the previous plan displayed or allow its pending check to overwrite the new plan's state.
F698 · warning · smell · frontend/src/app/features/planning/planning-page.ts – The show method clears the shared work state when called from restore or decision handling, allowing another action to start while the original operation is still refreshing data.
F699 · warning · smell · frontend/src/app/features/planning/workout-form.ts:106 – Field errors remain visible when the form receives a different workout because the errors signal is not reset with the other form state.
F700 · informational · smell · frontend/src/app/features/review/review-page.spec.ts – The coach comment test claims to cover a week without a plan but only sets up a week with a plan, leaving that case untested.
F701 · informational · smell · frontend/src/app/features/review/week-feedback-form.ts:149 – The firstMessages helper duplicates the implementation in session-rating.ts, so changes to error handling must be kept in sync.
F702 · warning · smell · frontend/src/app/features/season/season-chart.spec.ts – The test claiming to verify labels every fourth week slices its input to two weeks, so it cannot detect an incorrect labeling interval.
F703 · warning · smell · frontend/src/app/features/season/season-chart.ts:104 – The hour-axis step falls back to 100 for all larger values, so sufficiently large inputs produce more than the documented maximum of six steps.
F704 · warning · smell · frontend/src/app/features/season/season-page.ts – Calling show() from change(), restore(), or decided() clears the shared work state before the enclosing operation finishes refreshing, allowing another action to start while the first is still running.
F705 · warning · smell · frontend/src/app/features/season/season-page.ts – When show() is called with announce set to false, a failed reload is silently ignored, leaving the potentially stale plan displayed without reporting the failure.
F706 · warning · smell · frontend/src/app/features/security/delete-account-panel.ts:109 – The catch block reports a generic retry message if navigation fails after the account has already been deleted, misleading the user about the outcome.
F707 · warning · smell · frontend/src/app/features/security/data-export-panel.spec.ts:22 – The tests replace global URL methods without restoring them, which can affect other tests running in the same environment.
F708 · warning · smell · frontend/src/app/features/security/delete-account-panel.spec.ts:14 – The tests replace global dialog methods without restoring them, which can affect other tests running in the same environment.
F709 · warning · smell · frontend/src/app/layout/shell.css:219 – If the screen widens to 40rem while the More dialog is open, CSS hides the dialog without closing it, potentially leaving the rest of the page inert with no visible way to dismiss the modal.
F710 · informational · smell · frontend/src/app/layout/shell.css:1 – The comment says the sidebar stacks above the page below 40rem, but the sidebar is hidden at that width.
F711 · warning · smell · frontend/src/app/shared/confirm-dialog.spec.ts:9 – The test suite replaces HTMLDialogElement prototype methods without restoring them, so later tests in the same environment can observe the mocks.
F712 · warning · smell · frontend/src/app/shared/confirm-dialog.ts:59 – The backdrop handler also closes the dialog when a user clicks its own padding, because those clicks have the dialog as their target too.
F713 · warning · smell · frontend/src/app/shared/season-change-notice.ts:116 – The catch block treats programming errors as a temporary availability failure and suppresses their details, making defects difficult to diagnose.
F714 · warning · smell · frontend/src/app/testing/dom.ts:26 – The settle helper claims to render the result but never calls fixture.detectChanges(), so waiting for stability does not reliably update the view.

## Milestones

### M1 [x] Audit: PostgreSQL credentials across development, CI and production

- **Goal:** Give every service a reliable database connection without embedding a reusable password in the repository.
- **Includes:** F1 (development password fallback), F2 (production URL interpolation), F4 (repeated connection construction), F257 (test password fallback), F528 (backup examples), F537 (deployment password restrictions).
- **Done when:** Backend, scheduler and backup connect with a generated password containing URL-reserved characters. A fresh checkout can run the PostgreSQL tests using documented local credentials without a `.env` file. README and deployment examples cover existing volumes as well as new installations.
- **Depends on:** -
- **Size:** M, ~5 commits

### M2 [ ] Audit: CI trust and test credentials

- **Goal:** Make CI verify its package source and keep reusable or live-looking keys out of workflows and test fixtures.
- **Includes:** F5 (CI encryption key), F6 (CI Django key), F8 (PostgreSQL signing key), F401 (weekly generation fixture), F488 (season generation fixture), F207, F215, F252, F345, F446, F494, F499, F609 (related provider fixtures).
- **Done when:** CI generates fresh keys of the required formats and verifies the expected signing fingerprint before trusting the repository, or uses an already trusted PostgreSQL client source. The listed suites pass with generated encryption keys or clearly synthetic provider markers and still detect leaked marker values.
- **Depends on:** M1
- **Size:** M, ~4 commits

### M3 [ ] Audit: Public proxy and static frontend

- **Goal:** Make the public proxy responsible for trusted scheme information, browser security headers and API routing.
- **Includes:** F255 (forwarded scheme trust), F525 (content security policy), F543 (writable frontend assets), F544 (API requests receiving the SPA).
- **Done when:** Direct requests cannot set the trusted scheme, and HTTPS through production Caddy works. The shipped Angular app boots under a policy restricting script and object sources. The runtime user cannot modify `/srv`. Smoke tests cover a deep SPA link, a missing API route through the proxy and an API request directly to the static server.
- **Depends on:** -
- **Size:** M, ~5 commits

### M4 [ ] Audit: Backup keys, subprocesses and restore credentials

- **Goal:** Keep backup credentials separate from instance keys and expose PostgreSQL credentials only where the tools need them.
- **Includes:** F254 (backup key separation), F256 (empty instance key ring), F261 (child process environment), F262 (equivalent key encodings), F269 (restore credentials in arguments), F270 (backup interval), F527 (same-host key custody).
- **Done when:** Startup and key-file tests reject empty instance key rings and backup keys matching any decoded rotation key. Invalid intervals fail before the first dump. Stub tools verify the child environment and argument list. A restore succeeds using protected credential input, and the backup guide explains what an off-host copy and separately held key protect.
- **Depends on:** M1
- **Size:** L, ~7 commits

### M5 [ ] Audit: Administrator bootstrap and invitation delivery

- **Goal:** Make administrator creation race-safe and invitation delivery bounded, private and accurately reported.
- **Includes:** F22 (bootstrap race), F13 (recipient throttling), F534 (cross-worker admin throttling), F533 (token and email in URLs), F535 (request-derived host), F536 (console delivery status).
- **Done when:** Two simultaneous bootstrap commands create one administrator. Create and resend share atomic limits per administrator and normalized recipient across workers. New links use the configured public origin, keep invitation data out of HTTP request URLs and referrers, and clear it from displayed browser history after capture. Signup, existing-link transition, real mail acceptance, console output and mail failure each have an explicit tested outcome.
- **Depends on:** M3
- **Size:** L, ~7 commits

### M6 [ ] Audit: Authenticated views, owner assignment and account exports

- **Goal:** Make authentication, ownership and export disclosure explicit at the affected API boundaries.
- **Includes:** F27 (integration export fields), F284 (sample serializer owner), F287 (dashboard authentication), F436 (review authentication), F17, F310, F330 (account, integration and job permissions).
- **Done when:** Anonymous requests are refused by the affected views independently of the global default. Two-user tests verify server-assigned ownership on create and update, including the existing `OwnedModelViewSet` override. Integration exports use an explicit field list and pass structural tests for the expected metadata and absence of credentials.
- **Depends on:** -
- **Size:** M, ~5 commits

### M7 [ ] Audit: AI provider transport and JSON decoding

- **Goal:** Restrict outbound calls to operator-approved destinations and keep transport errors and non-finite numbers out of provider results.
- **Includes:** F233 (stored endpoint validation), F243 (allowlist test), F234 (header errors exposing keys), F223 (numeric overflow), F239 (JSON error positions).
- **Done when:** Configuration writes and the existing call-time allowlist agree. A stale or directly stored unapproved URL causes zero outbound calls, while an approved self-hosted endpoint works. Invalid headers produce fixed errors without credential text. Nested overflowing numbers are refused, finite numbers parse, and malformed JSON reports a numeric position.
- **Depends on:** -
- **Size:** M, ~5 commits

### M8 [ ] Audit: Planning requests and model-written diagnostics

- **Goal:** Apply the same push limit to equivalent confirmations and return safe, predictable errors for malformed plan data.
- **Includes:** F378 (push throttle), F379 (nested request bodies), F380 (unknown keys in errors), F381 (bidirectional marks), F420 (invisible test characters), F197, F214 (chat repair paths and fixtures).
- **Done when:** Every accepted representation of a push consumes the push limit before any external call. Generate and confirm return a handled client error for excessive nesting. Validation and repair paths contain only trusted field names and indexes. Escaped fixtures exercise the prohibited Unicode marks in titles and notes.
- **Depends on:** M7
- **Size:** M, ~5 commits

### M9 [ ] Audit: Weekly plan ownership and immutable revisions

- **Goal:** Enforce weekly plan ownership, revision ancestry and confirmed-history rules at the persistence boundary.
- **Includes:** F367 (workout write bypasses), F368 (confirmed weekly plan edits), F369 (workout owner and date), F386 (revision cycles), F407 (direct-write ownership coverage).
- **Done when:** PostgreSQL tests cover ordinary saves, bulk inserts, queryset updates and deletes, foreign-owner workouts and exports, out-of-week workouts, and multi-row ancestry cycles. New migrations check existing rows before enforcement. Confirmation, supersession, restore-as-draft and account deletion still pass through their normal services.
- **Depends on:** M6
- **Size:** L, ~7 commits

### M10 [ ] Audit: Season history and ownership of linked reviews and messages

- **Goal:** Protect confirmed season versions and ensure linked reviews and chat messages belong to the same athlete as their referenced records.
- **Includes:** F463 (season version mutation), F442 (review foreign keys), F431 (misclassified integrity failures), F204, F205 (weekly and season chat links).
- **Done when:** Direct and bulk writes cannot change protected season metadata or attach another athlete’s workout, activity or plan. New migrations account for existing links. Correction tests distinguish an already-linked activity, a deleted activity and an unrelated database failure. Legitimate supersession and account deletion succeed.
- **Depends on:** M9
- **Size:** L, ~6 commits

### M11 [ ] Audit: Strava archive work limits and import errors

- **Goal:** Bound the total work of a bulk import and give each failed recording an accurate, safe outcome.
- **Includes:** F47 (repeated archive processing), F46 (overlong recording names), F50 (parser text in API errors), F97 (missing archive diagnosis).
- **Done when:** Instrumented imports demonstrate bounded decompressed bytes and parse calls for repeated members and large sets of distinct members. Overlong references count as unreadable and never create manual activities. Missing archives and malformed ZIPs have distinct command errors. Upload responses contain fixed messages.
- **Depends on:** -
- **Size:** M, ~5 commits

### M12 [-] Audit: Activity summary and series parsers

- **Goal:** Apply consistent timestamp, sample and session checks when reading activity summaries and time series.
- **Includes:** F60 (GPX UTC overflow), F61 (TCX timestamp arithmetic), F62 (invalid samples), F63 (merged sessions), F64 (broad FIT exception handling), F65 (duplicated FIT reader).
- **Done when:** Boundary timestamps produce a handled file outcome. Sample readers follow the existing finite-value and plausibility rules. Summary and series readers both reject unsupported multi-session files and share FIT read limits. Tests distinguish a damaged file from an unexpected implementation error.
- **Depends on:** -
- **Size:** L, ~6 commits

### M13 [-] Audit: Atomic absence merging and per-athlete limits

- **Goal:** Keep absence ranges and per-athlete creation limits correct when multiple requests arrive together.
- **Includes:** F151 (reversed ranges), F152 (concurrent absence writes), F153 (bridging periods), F161 (availability collection limits), F293 (goal limit).
- **Done when:** Reversed dates fail before merging. A bridging report merges all connected periods of the same kind and preserves other kinds and owners. PostgreSQL concurrency tests cover simultaneous extensions, creation at the last free slot for each collection, and extension of an existing period at capacity.
- **Depends on:** -
- **Size:** M, ~5 commits

### M14 [-] Audit: Availability settings transactions and intensity limits

- **Goal:** Validate each availability update against the state it will actually change and enforce the same intensity ordering in storage.
- **Includes:** F159 (stale settings), F160 (non-field validation errors), F162 (oversized PATCH handler), F163 (field persistence drift), F168 (progression constraint), F172 (misleading boundary test).
- **Done when:** Concurrent PATCH tests preserve valid budget and minimum combinations. All accepted settings fields survive read-back, and both field and non-field failures return 400. A new constraint enforces the existing strict `warning < error` rule with explicit and inherited limits. Tests show why an error limit of 100 is refused and exercise the lowest valid pair.
- **Depends on:** M13
- **Size:** L, ~6 commits

### M15 [-] Audit: Athlete profile writes and threshold integrity

- **Goal:** Make first profile updates and threshold validation consistent across the API, model and database.
- **Includes:** F123 (non-finite and excessive stored thresholds), F116 (first PATCH race), F114 (positive finite checks), F121 (concurrent heart-rate changes), F305 (time zone validation and fallback).
- **Done when:** Concurrent first patches retain valid changes on one profile. A new migration checks existing values and enforces metric-specific bounds, including rejection of PostgreSQL NaN. Concurrent heart-rate updates preserve the ordering rule. Tests distinguish normal time zone validation from the UTC fallback for invalid legacy data.
- **Depends on:** -
- **Size:** L, ~6 commits

### M16 [-] Audit: Wellness import ranges and idempotency

- **Goal:** Make Intervals.icu wellness parsing and daily storage agree on exactly which measurements can be saved.
- **Includes:** F540 (HRV bounds), F541 (resting heart rate bounds), F542 (weight bounds), F515 (empty days), F516 (duplicate dates), F517 (partial batch writes).
- **Done when:** Fake Intervals responses exercise both ends of the database ranges and values just outside them. Valid sibling measurements survive. Empty entries create no row. Duplicate days have a documented deterministic result, replay reports zero changes, and a failed batch rolls back. The wellness guide lists the same limits.
- **Depends on:** -
- **Size:** M, ~5 commits

### M17 [-] Audit: Athlete and goal client input contracts

- **Goal:** Validate threshold routes, nullable response fields and real calendar dates before using them in athlete and goal screens.
- **Includes:** F576 (threshold path segments), F578 (missing effective value), F579 (runtime and TypeScript vocabularies), F582 (metric compatibility test), F624 (goal dates), F625 (goal model documentation), F679 (best-time input dates).
- **Done when:** Invalid sport and metric combinations issue zero HTTP requests and fail the applicable type checks. Missing `effective` is rejected while explicit `null` succeeds. Goal responses and best-time forms agree on leap days and impossible dates. Runtime choices and their types share one definition.
- **Depends on:** -
- **Size:** M, ~5 commits

### M18 [-] Audit: Dashboard response validation

- **Goal:** Detect incomplete dashboard responses before they can appear as missing athlete measurements.
- **Includes:** F617 (missing numeric fields), F618 (duplicated HTTP status handling), F619 (duplicated vocabularies), F622 (weak rejection assertions), F616 (calendar dates).
- **Done when:** Removing each required nullable field produces the expected response-shape error, while explicit `null` and valid zero values render correctly. Date tests include impossible days. Status handling and allowed-value types each have one definition, with tests for recognized and unknown values.
- **Depends on:** M17
- **Size:** M, ~4 commits

### M19 [-] Audit: Job history response validation

- **Goal:** Ensure the automation screen accepts only job identifiers, times, outcomes and counts that the backend can legitimately emit.
- **Includes:** F633 (IDs and timestamps), F634 (count keys and values), F635 (week dates), F636 (job vocabulary), F638 (rejection assertions), F639 (count boundary tests).
- **Done when:** Representative backend records pass, including valid empty counts. Tests reject invalid UUIDs, timestamps, week dates, count names, fractions, non-finite values and out-of-contract counts with the expected error. Runtime vocabularies supply the corresponding TypeScript types.
- **Depends on:** M17
- **Size:** M, ~4 commits

### M20 [-] Audit: Account deletion and historical MFA compatibility

- **Goal:** Keep account deletion predictable and preserve the encryption contract used to replay the historical MFA migration.
- **Includes:** F14 (deletion error dispatch), F24 (historical encryption imports), F34 (owned-model discovery), F35 (account test setup), F41 (runtime annotation), F42 (hidden invitation creation).
- **Done when:** An unmapped deletion error returns a defined 4xx response. Deletion tests discover concrete owned models through Django’s app registry and verify another account survives. Migration replay tests pin the version-one encryption behavior through stable compatibility entry points while leaving applied migrations intact. MFA tests collect on the supported Python version and make invitation creation explicit.
- **Depends on:** M4, M6, M10
- **Size:** M, ~5 commits

### M21 [-] Audit: Backup failure handling and retention

- **Goal:** Give backup callers consistent errors and preserve the selected backup through pruning.
- **Includes:** F263 (crypto error translation), F264 (protected path identity), F272 (encryption check exception), F278 (restore recorder fixture), F279 (positional command assertions).
- **Done when:** Invalid backup data and keys reach callers through the documented exception types. Pruning preserves the protected file through alternate path spellings. Restore tests identify the invocation record, verify flag meanings independently of order, and check that failed preflight prevents restore from starting.
- **Depends on:** M4
- **Size:** M, ~4 commits

### M22 [-] Audit: Activity creation, duplicate detection and estimate refresh

- **Goal:** Keep estimates current after supported activity writes and make duplicate handling demonstrably owner-scoped.
- **Includes:** F53 (manual estimate refresh), F57 (backfill file queries), F82 (unexercised insert race), F83 (duplicate identity), F91 (foreign duplicate disclosure).
- **Done when:** A qualifying manual entry refreshes the owner’s estimates. Backfill fetches stored files in bounded batches and retains its missing-file counts. The race test reaches the insert conflict and returns the exact winning activity. Two-user service and API tests inspect the duplicate ID that can actually be disclosed.
- **Depends on:** M11, M12, M15
- **Size:** M, ~5 commits

### M23 [-] Audit: Deterministic activity parser and command tests

- **Goal:** Make import safeguards testable independently of CI speed, allocator behavior and unrelated startup failures.
- **Includes:** F71, F72 (compressed-import settings), F95 (startup failure reason), F96 (Strava settings), F103 (TCX exception syntax), F104 (timing assertion), F105 (memory assertions).
- **Done when:** Typed settings fixtures pass mypy. The startup test requires the intended configuration error. TCX tests use explicit exception syntax and verify bounded reads, retained state or enforced limits on large inputs. The focused suite passes without absolute timing or allocator thresholds.
- **Depends on:** M11, M12
- **Size:** M, ~4 commits

### M24 [-] Audit: Athlete facts and threshold reconciliation

- **Goal:** Give profile facts and threshold updates one implementation per rule while preserving source priority and user isolation.
- **Includes:** F111 (best-time priority documentation), F112 (duplicated body and training mapping), F113 (duplicated reconciliation), F127 (ID substring assertions), F128 (threshold substring assertions).
- **Done when:** Profile and briefing tests agree on body and training fields. Sync and estimate refresh share reconciliation while deleting only stale rows of their own source and owner. Priority tests cover manual, best-time, Intervals and estimated values. Privacy tests inspect parsed fields and values.
- **Depends on:** M15, M22
- **Size:** M, ~4 commits

### M25 [-] Audit: Threshold and sync regression tests

- **Goal:** Make every threshold refusal, source ordering and timestamp assertion identify the specific behavior under test.
- **Includes:** F137 (broad sync exception), F139 (implicit sport cases), F143 (wall-clock ordering), F144 (heart-rate ordering cases), F145 (inconsistent user fixtures), F146 (duplicated maximum-heart-rate setup).
- **Done when:** Parameterized cases name the sport, counterpart and expected refusal. Failures assert the specific exception and preserve secret redaction. A controlled clock replaces sleeps. Shared user and activity fixtures cover the historical maximum-heart-rate estimate using the source enum.
- **Depends on:** M24
- **Size:** M, ~4 commits

### M26 [-] Audit: Availability form, period refresh and API contracts

- **Goal:** Keep availability edits, list refreshes and field validation consistent from the Angular form to persisted records.
- **Includes:** F597 (response decoder), F603 (fixed-session duration), F685 (form construction), F688 (stale period refresh), F177 (constraint identity), F183 (read-back ID), F186 (preference ordering), F188 (sports-list ordering).
- **Done when:** Smaller validators cover each settings group and fixed sessions accept 5–600 minutes. An out-of-order response cannot restore a deleted period or hide a new one. Backend tests identify the exact constraint and returned ID, and use examples where alphabetical order differs from priority or submission order.
- **Depends on:** M13, M14
- **Size:** L, ~6 commits

### M27 [-] Audit: Provider configuration and pricing races

- **Goal:** Prevent stale provider calls and concurrent price edits from corrupting the athlete’s current configuration.
- **Includes:** F224 (price count and creation races), F225 (stale completion status), F244 (fixed error text), F245 (corrupt-key setup), F249 (test recorder annotation).
- **Done when:** Concurrent price creates respect the cap and resolve same-model edits without a 500. A call finishing after reconfiguration records its usage while leaving the new connection status intact. Tests assert public error texts, use one corrupt-key fixture and resolve the recorder annotation safely.
- **Depends on:** M7
- **Size:** M, ~5 commits

### M28 [-] Audit: Intervals connection checks and recovery

- **Goal:** Keep connection checks responsive and ensure users see the outcome for their current Intervals.icu credentials.
- **Includes:** F308 (stale invalidation), F309 (synchronous retry waits), F319, F320 (secret-error assertions), F630 (disconnecting an absent connection), F631 (malformed replies), F675 (silent status failure).
- **Done when:** A delayed check cannot invalidate a replacement key. Interactive checks honor a bounded retry budget. Fake-server tests require the expected exceptions and inspect errors and logs for credential markers. Disconnecting an absent connection succeeds, malformed replies get the specified error, and the Activities page offers recovery after a status failure.
- **Depends on:** -
- **Size:** L, ~6 commits

### M29 [-] Audit: Scheduler retry accounting and failure isolation

- **Goal:** Record real attempt times and keep one athlete’s scheduling failure from blocking others or bypassing retry limits.
- **Includes:** F325 (missing retry week), F326 (per-user failure boundary), F327 (unexpected error diagnostics), F328 (attempt times), F329 (first settings PATCH), F338 (frozen loop clock), F342 (weekly run constraint).
- **Done when:** Controlled-clock tests show correct start and finish times, advancing scheduler rounds and a bounded weekly retry count for command and scheduler failures. Later athletes still run after an earlier failure. Diagnostics identify unexpected failures without provider or personal text. Concurrent initial PATCHes succeed. A new migration handles legacy rows before requiring the target Monday for weekly runs.
- **Depends on:** M19, M28
- **Size:** L, ~7 commits

### M30 [-] Audit: Job runner fixtures and side-effect guarantees

- **Goal:** Prove what scheduled syncs and reviews store and which external actions they can take.
- **Includes:** F346 (unused helpers), F347 (duplicated runner fixtures), F349 (job log contents), F351 (review confirmation and push coverage).
- **Done when:** Command and runner tests use shared fakes and dates. Failure tests inspect persisted codes and counts for unexpected text. Weekly review tests fail on any confirmation or push attempt and pass with the scripted coach.
- **Depends on:** M29
- **Size:** S, ~3 commits

### M31 [-] Audit: Atomic chat actions and illness across weeks

- **Goal:** Keep replies, drafts and absences consistent when illness or its return period extends beyond the selected week.
- **Includes:** F192 (cross-week illness), F193 (minimum-duration behavior), F194 (partial chat writes), F195 (conflicting sick-day actions), F196 (action parser structure).
- **Done when:** A Sunday illness case accounts for unavailable and eased-return days on both sides of Monday. The existing one-week editing rule has an explicit follow-up for another affected plan, and the reply identifies any draft still needed. Conflicting actions are refused in either order. Forced message failure rolls back drafts and absences. Per-action tests cover the documented duration floor. Confirmation remains an athlete action.
- **Depends on:** M8, M9, M10, M13
- **Size:** L, ~7 commits

### M32 [-] Audit: Chat briefing and response tests

- **Goal:** Give chat tests stable briefing data and distinguish authentication failures from malformed coach responses.
- **Includes:** F208, F209 (shared clock), F210 (wellness seeding), F573 (reply object checks), F605 (generic rejection), F606 (untested 401 handling).
- **Done when:** API and briefing tests share a scoped clock and owner-aware wellness fixture covering both windows. Reply helpers share object and code checks. List, write and clear tests cover both 401 and 403, and unknown conflicts must raise the intended error.
- **Depends on:** M16, M31
- **Size:** M, ~4 commits

### M33 [-] Audit: Weekly generation, rule and export contracts

- **Goal:** Make week-planning tests verify what the coach receives, what the rules report and what confirmation exports.
- **Includes:** F361 (weekly note disclosure), F402 (one-minute request), F408 (briefing keys), F413 (replacement push behavior), F416 (rule purity), F422 (sport ordering), F642 (zone range documentation).
- **Done when:** The briefing documents its free text, and a scripted call exposes the actual one-minute capacity. Prompt tests derive keys from the briefing contract. Rule tests catch both Python import forms and verify sport order without splitting English messages. Push tests assert removal and recreation counts. The client’s zone documentation matches the serialized representation.
- **Depends on:** M8, M9, M24
- **Size:** M, ~5 commits

### M34 [-] Audit: Review, dashboard and season totals

- **Goal:** Make review figures, completed minutes and next-workout selection consistent across athlete-facing summaries.
- **Includes:** F288 (next-workout ordering), F291 (eight-week chart boundary), F430 (duplicated figures mapping), F445 (comment response redaction), F464 (duration aggregation).
- **Done when:** Out-of-order inserts demonstrate the existing day, position and ID ordering for next week’s workout. Chart tests identify the first included and first excluded weeks. Briefing and API share the figures mapping. Both season totals agree for missing and zero timers, and comment response tests inspect success and failure bodies for the fixture credential.
- **Depends on:** M6, M10
- **Size:** M, ~5 commits

### M35 [-] Audit: Season race coverage and stored-plan recovery

- **Goal:** Preserve races at the season boundary and make malformed historical season data diagnosable.
- **Includes:** F469 (silent corrupt-plan fallback), F470 (B race after the main race), F471 (missing skeleton keys), F480 (absence query test), F481 (empty-skeleton briefing), F483 (season fixtures), F512 (race-week phase).
- **Done when:** A B race immediately after the main A race appears in its week with the expected phase. Malformed stored skeletons produce a defined service outcome and a diagnostic without athlete text. Tests call the actual briefing builder for an empty skeleton, assert query growth against the baseline and use shared verified-user, race and training fixtures.
- **Depends on:** M10, M34
- **Size:** L, ~6 commits

### M36 [-] Audit: Season prompt, rules and schema tests

- **Goal:** Make season contract tests fail when a prompt, race rule, documented check or parsed plan is wrong.
- **Includes:** F495 (prompt self-comparison), F501 (vacuous race assertion), F507 (unchecked successful parse), F482 (hard-coded rule counts).
- **Done when:** Distinct athlete inputs exercise the fixed system prompt. Race-free and missing-race-session cases assert exact findings. Every successful parse in the malformed-input suite satisfies the plan contract. Documentation tests compare rule identifiers and levels with the implemented checks.
- **Depends on:** M35
- **Size:** M, ~4 commits

### M37 [-] Audit: Sign-in, pending flows and account deletion outcomes

- **Goal:** Make authentication state and page messages reflect what actually happened to the session or account.
- **Includes:** F584 (login throttling), F585 (auth API coverage), F590 (hidden initialization defects), F591 (loading after refusal), F592 (generic rejection), F681, F682 (pending MFA and verification), F706 (navigation after deletion).
- **Done when:** Tests cover login, session, logout, config and current-user responses. Rate limiting has a typed result and visible feedback. Invalid login leaves a settled state. Only pending flows trigger MFA or verification. Expected outages are distinguishable from programming errors. Navigation failure after successful deletion still reports that the account was deleted.
- **Depends on:** M5, M20
- **Size:** L, ~6 commits

### M38 [-] Audit: Profile, provider and goal form feedback

- **Goal:** Preserve athlete edits during saves and show every actionable validation error.
- **Includes:** F678 (device time zone failure), F680 (edits during body-data save), F692 (provider-wide errors), F694 (hidden goal field errors).
- **Done when:** Failed time zone detection preserves the existing value. A delayed save cannot discard later edits. Provider forms display global and field errors together. Goal kind, metric and distance errors are visible for every relevant form layout, including when custom distance is collapsed.
- **Depends on:** M15, M17, M27
- **Size:** M, ~4 commits

### M39 [-] Audit: Season client conflicts and reassessment decoding

- **Goal:** Give season generation and change requests accurate conflict messages and validate reassessment data consistently.
- **Includes:** F658, F659 (unknown 409 responses), F660 (reassessment decoder), F652 (confirmed-load coverage), F653 (duplicated HTTP test setup).
- **Done when:** Both endpoints map recognized conflict codes explicitly and reject unknown codes or proxy bodies with the expected error. Reassessment tests cover field shape, real dates and cross-week consistency independently. Shared request fixtures verify both planned and confirmed load for a sport absent from season minutes.
- **Depends on:** M17, M35
- **Size:** M, ~5 commits

### M40 [-] Audit: Weekly plan editor state

- **Goal:** Keep validation findings, field errors and busy state attached to the plan or workout currently displayed.
- **Includes:** F697 (stale plan checks), F698 (busy state during refresh), F699 (stale workout errors).
- **Done when:** Changing the input plan starts a fresh check and ignores late results for the old plan. Restore and decision actions stay busy through their final refresh. Switching workouts resets field errors. Component tests control response order for each transition.
- **Depends on:** M33
- **Size:** S, ~3 commits

### M41 [-] Audit: Season page refresh, notices and chart scale

- **Goal:** Keep season actions exclusive through refresh and make charts and failure notices accurate.
- **Includes:** F704 (busy state cleared early), F705 (hidden reload failure), F713 (suppressed notice defects), F702 (fourth-week label coverage), F703 (unbounded axis steps).
- **Done when:** Delayed refreshes keep change, restore and decision controls locked until completion. Failed reloads identify stale data, and unexpected notice errors remain diagnosable. Chart tests span multiple fourth-week labels and verify at most six axis steps across small and large inputs.
- **Depends on:** M39
- **Size:** M, ~5 commits

### M42 [-] Audit: Theme lifecycle and accessible dialogs

- **Goal:** Keep theme changes and modal navigation predictable across repeated initialization and viewport changes.
- **Includes:** F547 (duplicated dark tokens), F666 (theme listener lifecycle), F709 (hidden open More dialog), F712 (padding treated as backdrop).
- **Done when:** Explicit and system dark modes use one token definition. Reinitialization installs one active media listener and teardown removes it. Widening the viewport closes the mobile modal and restores usable focus. Dialog tests distinguish backdrop, padding, content and Escape.
- **Depends on:** -
- **Size:** M, ~4 commits

### M43 [-] Audit: Frontend test isolation and rendering

- **Goal:** Make component tests independent of suite order and ensure their shared rendering helper updates the DOM.
- **Includes:** F690, F691 (connection dialog mocks), F707 (global URL mocks), F708, F711 (security and shared dialog mocks), F714 (settling and change detection).
- **Done when:** The affected suites restore original global methods and property descriptors after each test. A focused regression proves that settling renders an asynchronous state change. Connection, security and dialog suites pass individually and together.
- **Depends on:** M37, M42
- **Size:** S, ~3 commits

### M44 [-] Audit: Roadmap status and documentation checks

- **Goal:** Make project status, integration evidence and operator instructions agree with the behavior delivered by the repository.
- **Includes:** F529 (completed features listed as open), F530 (manual checks versus delivery status), F539 (Intervals evidence), F531 (sync-before-draft wording), F353 (job log promises), F354 (job ordering assertions), F392 (skipped documentation rows).
- **Done when:** The roadmap distinguishes delivered work, open audit milestones and outstanding manual verification. The Intervals guide records what was observed and what still needs checking. README and job docs agree on sync-before-draft behavior. Tests require both log guarantees, inspect job order in the intended section and distinguish table headers from data rows by structure.
- **Depends on:** M29, M30, M33, M36
- **Size:** M, ~4 commits

## Suggestions

- Add a read-only deployment check that reports proxy trust, database connectivity and backup readiness without printing configuration values, so operators can verify an installation before accepting signups.
- Add a restore rehearsal against a disposable database, so operators can verify that an off-host backup and its separately held key work together.
- Add an import summary with per-reason counts and retry guidance, so athletes can understand partially successful Strava imports without exposing recording contents.
- Show which dates and draft versions an illness report affects, so an athlete can review the remaining changes before confirming either week.
- Add a last-successful-sync indicator for activities and wellness, so athletes can distinguish an uneventful training week from stale data.

## Definition of done

- Builds, tests green, lint clean
- Every included finding is fixed, or explained as a false positive in the commit message
- Fixes add or extend tests where the finding was about untested or unsafe logic

## Changelog

- 2026-11-20: audit planned
- 2026-11-20: M1 done: discrete `POSTGRES_*` settings, no hardcoded database passwords, docs for existing and new volumes
