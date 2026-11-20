# Security policy

## Supported versions

PaceForge has no releases yet. Only the latest commit on `main` gets security fixes.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately through
**Security → Report a vulnerability** on the GitHub repository page. Include the affected file or
endpoint, the steps to reproduce it and the impact you expect.

You get an answer within a week. Once a fix is on `main`, the report is published as a security
advisory, with credit if you want it.

## Known findings

[`docs/AUDIT.md`](docs/AUDIT.md) lists the findings of a code audit and the milestones that fix
them. Milestones marked `[x]` are done; the others are still open. You do not need to report a
finding that is already listed there.

## Running your own instance

- Generate your own `DJANGO_SECRET_KEY`, `ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY` and database
  password. Never reuse the values from `.github/workflows/ci.yml`, `backend/config/settings_test.py`
  or the tests; they are public.
- Read [Instance key](README.md#instance-key) and [docs/deployment.md](docs/deployment.md) before
  you expose an instance to the internet.
