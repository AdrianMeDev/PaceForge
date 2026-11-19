# Production deployment

This guide takes a fresh Linux VPS from zero to a running PaceForge instance over HTTPS using
`compose.prod.yaml`, with automatic TLS certificates from Caddy, mandatory administrator two-factor
authentication, and a repeatable update workflow.

## Architecture

`compose.prod.yaml` runs five services on an internal Docker network:

| Service     | Role                                                                          |
| ----------- | ----------------------------------------------------------------------------- |
| `caddy`     | Public reverse proxy on ports 80 and 443; gets and renews HTTPS certificates. |
| `frontend`  | Static Angular build served by Caddy on internal port 8080.                   |
| `backend`   | Django + Gunicorn on internal port 8000; runs deploy checks and migrations.   |
| `scheduler` | Runs `python manage.py run_scheduler` after `backend` is healthy.             |
| `db`        | PostgreSQL 17.11 with persistent volume `pgdata`.                             |

Only `caddy` publishes host ports (`80`, `443`, `443/udp`). Everything else stays on the internal
network.

## Prerequisites

- A Linux server with **Docker** and **Docker Compose** (`docker compose` v2).
- A **public DNS name** (for example `pace.example.com`) with an A or AAAA record pointing to the
  server's public IP address.
- **Ports 80 and 443** (TCP and UDP) open in your firewall and cloud security group. Caddy needs
  port 80 for ACME certificate checks and HTTP-to-HTTPS redirects.
- Optional: **SMTP credentials** for sending invitation and password-reset emails. If `SMTP_HOST` is
  left empty, PaceForge writes emails to the `backend` container log instead of sending them.

## 1. Configure `.env` and generate keys

Clone the repository onto the server and copy the production environment template:

```sh
cp .env.prod.example .env
```

Never commit `.env`. Edit `.env` and fill in every empty value:

1. **Domain:** set `APP_DOMAIN` to your public host name without scheme, port or path (for example
   `APP_DOMAIN=pace.example.com`). Caddy uses this for the TLS certificate, and Django uses it for
   `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` (`https://<APP_DOMAIN>`).
2. **Django secret key (`DJANGO_SECRET_KEY`):** generate a random signing key:

   ```sh
   python3 -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

3. **Instance encryption key (`ENCRYPTION_KEY`):** generate a Fernet key used to encrypt
   Intervals.icu API keys, AI provider keys and two-factor authentication secrets in the database:

   ```sh
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   If `cryptography` is not installed on the host, build the backend image first and run the command
   inside it:

   ```sh
   docker compose -f compose.prod.yaml build backend
   docker compose -f compose.prod.yaml run --rm --no-deps backend \
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   **Store `ENCRYPTION_KEY` separately from database backups** (for example in a password manager).
   A database backup without `ENCRYPTION_KEY` cannot decrypt stored secrets, and anyone holding both
   can read them. To rotate keys later, put the new key first and keep the old key after a comma:
   `ENCRYPTION_KEY=<new>,<old>`.

4. **Database password (`POSTGRES_PASSWORD`):** choose a strong password using **letters and digits
   only**. It is embedded directly into `DATABASE_URL` inside `compose.prod.yaml`, and PostgreSQL
   refuses to start if it is empty.
5. **Email (`SMTP_*` and `DEFAULT_FROM_EMAIL`):** set `DEFAULT_FROM_EMAIL` and your SMTP server
   details, or leave `SMTP_HOST` empty to log emails to the `backend` container output.
6. **AI endpoints (`AI_ALLOWED_BASE_URLS`):** optionally list comma-separated base URLs for
   OpenAI-compatible AI providers (for example `https://api.openai.com/v1`). Leave empty to allow
   Anthropic only.

## 2. Start the stack with automatic HTTPS

Build the images and start all services in the background:

```sh
docker compose -f compose.prod.yaml up -d --build
```

On startup:

- `db` starts PostgreSQL and waits until `pg_isready` succeeds.
- `backend` runs `python manage.py check --deploy`, applies database migrations (when
  `AUTO_MIGRATE=true`), and starts Gunicorn.
- `scheduler` starts once `backend` passes its health check.
- `caddy` obtains a TLS certificate for `APP_DOMAIN` and starts serving `https://<APP_DOMAIN>`.

Check that every service is running and healthy:

```sh
docker compose -f compose.prod.yaml ps
```

## 3. First setup (no database edits)

Create the first administrator account with `setup_admin`:

```sh
docker compose -f compose.prod.yaml exec backend python manage.py setup_admin --email you@example.com
```

The command prompts for a password and refuses to run once an administrator exists. For
non-interactive scripts, pass `SETUP_ADMIN_EMAIL` and `SETUP_ADMIN_PASSWORD` as environment
variables instead.

Then complete the initial sign-in in your browser:

1. Open `https://<APP_DOMAIN>` and sign in with the administrator email and password.
2. **Enable two-factor authentication:** administrators must enable MFA before using the app or the
   admin API, so your first sign-in lands on **Security** (`/settings/security`). Scan the QR code
   with an authenticator app, enter the 6-digit code, confirm your password, and save the recovery
   codes.
3. **Invite users:** open **Invitations** in the navigation, enter a user's email address, and press
   **Create invitation**. Copy the one-time link and send it to them. Invitations expire after
   `INVITATION_TTL_DAYS` days (default `7`).

## Registration modes

Control who can create an account with `REGISTRATION_MODE` in `.env`:

- `invite_only` (default): only people with an active invitation link can register.
- `closed`: nobody can register, even with an existing invitation link. Set this once all intended
  athletes have created their accounts.

After changing `REGISTRATION_MODE` in `.env`, recreate `backend` and `scheduler` so they load the
new setting:

```sh
docker compose -f compose.prod.yaml up -d backend scheduler
```

## Scheduler control, upload limits and timeouts

- **Scheduler:** `scheduler` runs continuously in `compose.prod.yaml` and checks for due jobs every
  `JOBS_INTERVAL_MINUTES` minutes (default `15`). Activity syncs run every `JOBS_SYNC_HOURS` hours
  (default `6`), and Sunday reviews and drafts start at `JOBS_SUNDAY_HOUR` (default `18`) in each
  athlete's profile time zone. Stop or start the scheduler independently without affecting the web
  app:

  ```sh
  docker compose -f compose.prod.yaml stop scheduler
  docker compose -f compose.prod.yaml start scheduler
  ```

  See [Background jobs](background-jobs.md) for all job commands and settings.

- **Upload limits:** `ACTIVITY_UPLOAD_MAX_BYTES` defaults to `26214400` (25 MB) in Django.
  `deploy/Caddyfile` sets `max_size 32MB` on `/api/*` to leave room for multipart form overhead. If
  you raise `ACTIVITY_UPLOAD_MAX_BYTES`, update `max_size` in `deploy/Caddyfile` and reload Caddy.
- **Timeouts:** AI plan generation can take up to two minutes (60 seconds per provider call plus one
  repair round). `GUNICORN_TIMEOUT` defaults to `240` seconds in `.env.prod.example`, and
  `deploy/Caddyfile` sets `response_header_timeout 240s` on the `backend` proxy to match.
  `GUNICORN_WORKERS` defaults to `2`.

## Updating and migrating

Always back up the database before updating.

### 1. Back up the database

Create a compressed `pg_dump` backup from the running `db` container:

```sh
docker compose -f compose.prod.yaml exec -T db \
  pg_dump -U "${POSTGRES_USER:-paceforge}" -Fc "${POSTGRES_DB:-paceforge}" \
  > "paceforge-$(date +%F-%H%M).dump"
```

Keep `ENCRYPTION_KEY` backed up separately from the `.dump` file.

### 2. Pull and rebuild images

Pull the latest code and rebuild the `backend` and `frontend` images:

```sh
git pull
docker compose -f compose.prod.yaml build
```

(If you use pre-built images via `BACKEND_IMAGE` and `FRONTEND_IMAGE`, run
`docker compose -f compose.prod.yaml pull` instead.)

### 3. Migrate and restart

- **Automatic migrations (`AUTO_MIGRATE=true`, default):** `backend/entrypoint.sh` runs
  `python manage.py check --deploy` and `python manage.py migrate --noinput` before starting
  Gunicorn. Because `scheduler` waits for `backend` to be healthy, migrations finish before the
  scheduler starts:

  ```sh
  docker compose -f compose.prod.yaml up -d
  ```

- **Manual migrations (`AUTO_MIGRATE=false`):** set `AUTO_MIGRATE=false` in `.env` if you prefer to
  run migrations explicitly before starting the updated containers:

  ```sh
  docker compose -f compose.prod.yaml run --rm backend python manage.py migrate
  docker compose -f compose.prod.yaml up -d
  ```

### 4. Verify health

Check container health and test the public health endpoint:

```sh
docker compose -f compose.prod.yaml ps
curl -fsS "https://$APP_DOMAIN/api/health/"
```

The backend returns `{"status": "ok"}`.
