# PaceForge

A self-hostable, AI-assisted endurance coach for running, cycling, swimming and strength training.
The long-term goal is described in `PROJECT_PLAN.md`; this repository is in early development.

**What works today:** accounts for a multi-user instance, invitation-only registration with an
admin page for invitations, email verification, sign-in and sign-out with server-side sessions,
password reset, two-factor authentication (authenticator app plus recovery codes, mandatory for
administrators), and the data-isolation foundation the training features will build on.
**Not there yet:** sending invitations by email (the administrator hands the link on) and all
coaching features. Before an instance is exposed to the internet, read
[Instance key](#instance-key): secrets in the database are encrypted, and the key has to be backed
up apart from the database.

## Layout

| Path               | What it is                                                              |
| ------------------ | ----------------------------------------------------------------------- |
| `backend/`         | Django 6, Django REST framework, django-allauth (headless), PostgreSQL  |
| `frontend/`        | Angular single-page app (standalone components, signals, zoneless)      |
| `compose.dev.yaml` | Development services only: PostgreSQL and Mailpit (a catch-all mailbox) |
| `.env.example`     | Template for the configuration shared by Django and Docker Compose      |

The browser only ever talks to one origin: during development `ng serve` proxies `/api` to Django
(`frontend/proxy.conf.json`), so there is no CORS setup and the session cookie stays `HttpOnly`.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (it installs the required Python 3.14 itself)
- Node.js `^22.22.3`, `^24.15` or `>=26`, with npm
- Docker with Compose, for PostgreSQL and Mailpit

## First run

All commands start in the repository root unless noted.

**1. Configuration.** Copy the template and set a secret key. Django and Docker Compose both read
this one `.env` file; variables that are already set in your shell win over it.

```sh
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # put the output into DJANGO_SECRET_KEY
(cd backend && uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")   # ENCRYPTION_KEY
```

The second key is the instance key for secrets in the database, see [Instance key](#instance-key).

**2. Database and mailbox.**

```sh
docker compose -f compose.dev.yaml up -d db mailpit
```

PostgreSQL listens on `127.0.0.1:5432`, Mailpit on `127.0.0.1:1025` (SMTP) and
`http://localhost:8025` (web interface).

**3. Backend.**

```sh
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py setup_admin --email you@example.com   # asks for a password
uv run python manage.py runserver                              # http://localhost:8000
```

`setup_admin` creates the first administrator and refuses to run once one exists. For scripts, set
`SETUP_ADMIN_PASSWORD` (and optionally `SETUP_ADMIN_EMAIL`) instead of answering the prompt; the
password is deliberately not accepted as a command-line argument.

**4. Frontend**, in a second terminal.

```sh
cd frontend
npm ci
npm start                                                      # http://localhost:4200
```

Open <http://localhost:4200> and sign in with the administrator. Administrators must turn on
two-factor authentication before they can use anything else, so the first sign-in lands on the
security page: scan the QR code with an authenticator app, enter the code, confirm your password and
save the recovery codes (see [Two-factor authentication](#two-factor-authentication)).

## Manual walkthrough: invitation to working account

Administrators create invitations on the **Invitations** page. Nothing is sent by email: you get a
link and hand it on yourself. The rest is what a new user sees.

1. **Create an invitation.** Sign in as the administrator (with two-factor authentication turned on,
   see above), choose **Invitations** in the navigation, enter `ann@example.com` and press **Create
   invitation**. The link is shown **once**; press **Copy link** and send it to the person. If you
   lose it, revoke the invitation in the list and create a new one. Open the link in a private
   window so you stay signed in as the administrator in the other one.
2. **Sign up.** The email address is prefilled and read-only. Choose a password. The page says a
   confirmation link was sent.
3. **Confirm the address.** Open Mailpit (<http://localhost:8025>), open the message and follow
   the link. The page shows the address; confirming happens only when you press **Confirm email
   address**. Opening the link alone confirms nothing.
4. **Sign in** with the new account, look at the dashboard, then **Sign out**.
5. **Reset the password.** On the sign-in page choose **Forgot your password?**, enter the address,
   open the mail in Mailpit, follow the link and choose a new password. You land on the sign-in
   page with a notice; the old password no longer works.

An invitation is valid for 7 days, works once and is bound to the address it was created for. Using
the link a second time, or after it was revoked, shows "This invitation is invalid, has expired or
was issued for a different email address." The list on the Invitations page shows each invitation as
pending, used, revoked or expired; only pending ones can be revoked.

## Two-factor authentication

Every user can turn on two-factor authentication on the **Security** page (`/settings/security`):
an authenticator app (TOTP) plus ten single-use recovery codes. Signing in then asks for a code after
the password; a recovery code works in the same field.

- **Administrators have to have it.** Until it is on, an administrator is sent to the security page
  and the administration API answers `403` with `"code": "mfa_required"`. Administrators cannot turn
  it off in the interface.
- **The password is asked for again** when turning it on or off, showing recovery codes or
  generating new ones, even right after signing in.
- **Recovery codes:** save them when they are shown. Generating new ones replaces all old ones.
- **The QR code is drawn in the browser.** The authenticator URL contains the secret; it is never
  sent to a third party.
- **Stored encrypted.** The authenticator secrets and the seed of the recovery codes are encrypted
  with the [instance key](#instance-key); a copy of the database alone does not reveal them.
  Without the key they cannot be used, so after losing it every user has to be reset (see below).
  Upgrading from a version that stored them in clear text: `migrate` encrypts what is there, so set
  `ENCRYPTION_KEY` first.
- **Lost authenticator and recovery codes?** There is no self-service way back by design. An
  operator removes the second factor of the account (from `backend/`); the user then signs in with
  the password alone and sets it up again, and an administrator is sent to the security page:

  ```sh
  uv run python manage.py reset_mfa --email you@example.com
  ```

  The command leaves the password and all data alone and does not end existing sessions. If a
  device was stolen, also change the password.

## Instance key

Secrets that the database holds for users are encrypted with a separate instance key
(`ENCRYPTION_KEY`, Fernet: AES with an integrity check), so a copy of the database alone reveals
nothing. Django refuses to start without it, and the system check (`manage.py check`) names a key
that is not valid.

- **Generate it once** (from `backend/`), keep it in the environment or a secret file, never in the
  repository: `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **Back it up apart from the database.** A database backup without the key does not restore the
  encrypted secrets. Whoever holds both can read them.
- **Rotating:** put the new key first and keep the old one after it, separated by a comma
  (`ENCRYPTION_KEY=<new>,<old>`). New values use the first key, old values stay readable. There is
  no command yet that re-encrypts old values, so the old key must stay in the list.
- **Losing it** makes the values encrypted with it unrecoverable. For two-factor authentication,
  [`reset_mfa`](#two-factor-authentication) lets the user set it up again.

## Checks

These are the commands the CI workflow (`.github/workflows/ci.yml`) runs.

```sh
# backend (needs the PostgreSQL service from step 2)
cd backend
uv run ruff format --check . && uv run ruff check .
uv run mypy .
uv run python manage.py makemigrations --check --dry-run
uv run pytest

# frontend
cd frontend
npm run format:check && npm run lint
npx ng test --no-watch
npx ng build
```

The backend tests create and drop their own `test_*` database next to the development one.

## Configuration

Set in `.env` or in the environment. Values without a default are required.

| Variable                       | Default                             | Meaning                                                                           |
| ------------------------------ | ----------------------------------- | --------------------------------------------------------------------------------- |
| `DJANGO_SECRET_KEY`            | –                                   | Signing key. Required, there is deliberately no default.                          |
| `DATABASE_URL`                 | –                                   | e.g. `postgres://paceforge:paceforge-dev@localhost:5432/paceforge`. Required.     |
| `DJANGO_DEBUG`                 | `false`                             | `true` for development. With `false`, cookies are sent only over HTTPS.           |
| `DJANGO_ALLOWED_HOSTS`         | empty                               | Comma-separated host names; must be set when `DJANGO_DEBUG` is `false`.           |
| `DJANGO_CSRF_TRUSTED_ORIGINS`  | empty                               | Comma-separated origins allowed to send state-changing requests.                  |
| `ENCRYPTION_KEY`               | –                                   | Instance key for secrets stored in the database; several keys separated by commas. Required. |
| `REGISTRATION_MODE`            | `invite_only`                       | `closed`, `invite_only` or `open`. Anything else stops Django at startup.         |
| `INVITATION_TTL_DAYS`          | `7`                                 | How long an invitation stays valid.                                               |
| `SMTP_HOST`                    | empty                               | Empty: emails are printed to the Django console. Set: they are sent via SMTP.     |
| `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | `587`, empty, empty, `true` | SMTP settings, used when `SMTP_HOST` is set. |
| `DEFAULT_FROM_EMAIL`           | `PaceForge <noreply@localhost>`     | Sender of all emails.                                                             |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `paceforge`, `paceforge-dev`, `paceforge` | Only read by `compose.dev.yaml`; keep them in line with `DATABASE_URL`. |

## Troubleshooting

- **Signing up answers with an error and the invitation is used up.** `.env.example` points SMTP at
  Mailpit (`localhost:1025`). If Mailpit is not running, sending the confirmation mail fails after
  the account was created. Start it (`docker compose -f compose.dev.yaml up -d mailpit`), or leave
  `SMTP_HOST` empty to read the mails in the Django console. The unconfirmed account can still
  receive a fresh link: signing in with it sends one.
- **`Port 4200 is already in use` / `That port is already in use`.** Another dev server is running.
  Stop it, or start this one elsewhere: `uv run python manage.py runserver 8010` together with
  `npx ng serve --port 4210 --proxy-config <file>` that points `/api` to that port.
- **Django refuses to start with `DJANGO_SECRET_KEY`, `DATABASE_URL` or `ENCRYPTION_KEY` missing.** Both are required
  and have no default; check that `.env` is in the repository root, not in `backend/`.
- **An administrator cannot reach the admin pages and keeps landing on the security page.** That is
  the rule that administrators need two-factor authentication; set it up there.
- **Sign-in is refused with "too many failed attempts".** That is the brute-force protection: five
  failed attempts for an address lock it for five minutes. The counters live in the server
  process, so restarting the dev server clears them.
