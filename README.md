# PaceForge

A self-hostable, AI-assisted endurance coach for running, cycling, swimming and strength training.
The long-term goal is described in `PROJECT_PLAN.md`; this repository is in early development.

**What works today:** accounts for a multi-user instance, invitation-only registration with an
admin page for invitations, email verification, sign-in and sign-out with server-side sessions,
password reset, two-factor authentication (authenticator app plus recovery codes, mandatory for
administrators), a personal Intervals.icu connection with an API key (stored encrypted), importing
activities from FIT and TCX files, an athlete profile with your time zone, your thresholds (typed in,
read from Intervals.icu or estimated from your activities) and the training zones that follow from
them, goals (races, threshold targets and general goals, with one main goal), your training time
(minutes per weekday, a weekly budget, limitations, vacation and illness), your own AI provider
([Anthropic or an OpenAI-compatible endpoint](#ai-coach-bring-your-own-key), key stored encrypted,
with a connection check and a usage overview), the model and the plausibility checks for a
training week ([format and rules](docs/weekly-plan.md)), a **Week plan** page on which your own
AI coach drafts a training week that you read, confirm or discard ([Week plan](#week-plan)), and
the data-isolation foundation the training features will build on.
**Not there yet:** reading activities from Intervals.icu over that connection (it can only ever
work for activities that do not come from Strava, see [Activities](#activities)), sending
invitations by email (the administrator hands the link on) and more of the coach: it drafts a
week, but you cannot yet change a draft by talking to it, and it has not been tried against a real
provider (see [Week plan](#week-plan)). Before an instance is exposed to the
internet, read [Instance key](#instance-key): secrets in the database are encrypted, and the key
has to be backed up apart from the database.

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

## Connections

Every user connects their own training platform on the **Connections** page
(`/settings/connections`, also in the navigation). Intervals.icu is the first one, with a personal
API key; there is no OAuth, because PaceForge is meant for single athletes who host it themselves
and invite a few others. The findings behind this are in
[`docs/phase0-intervals.md`](docs/phase0-intervals.md).

1. In Intervals.icu open Settings, Developer Settings and copy your API key.
2. In PaceForge open **Connections**, paste the key and press **Connect**. The server checks it with
   Intervals.icu, then stores it encrypted together with your athlete id (`i…`).
3. The page shows the status, the athlete and the time of the last check. **Check connection**
   tests the stored key again; if Intervals.icu no longer accepts it (you created a new key there),
   the status says **Needs attention** and you paste the new one under **Replace the API key**.
4. **Disconnect** deletes the stored key. PaceForge cannot revoke it at Intervals.icu; create a new
   key there if the old one should stop working.

- **The key is write-only.** It is sent once, never shown again (not even in part), not returned
  by any endpoint and not logged. Every user sees and changes only their own connection;
  administrators have no way to read other users' keys.
- **Limits:** saving and checking together are limited to 10 per minute per user.
- **Only your thresholds are read from Intervals.icu so far,** see
  [Athlete profile](#athlete-profile). Reading activities comes next and only works for activities
  that did not come from Strava; for everything else use the [file import](#activities).
- **If the instance key is lost,** the stored keys can no longer be used. The page still opens and
  shows **Needs attention** after a check, and each user pastes their key again.
- `INTERVALS_API_BASE_URL` (see [Configuration](#configuration)) is only for tests and fake servers.
- Your AI provider is set up on the same page, in its own section: see
  [AI coach](#ai-coach-bring-your-own-key).

## AI coach (bring your own key)

The coach that plans your training will use an AI model. PaceForge does not ship one: every user
connects **their own** AI account on the **Connections** page (`/settings/connections`, section
**AI coach**) and pays their provider directly. At the moment you can set the provider up, check
that it works and see what you have used. The only thing that calls it besides the check is the
[Week plan](#week-plan) page.

**Two kinds of provider.**

- **Anthropic** (Claude): you need an API key from the console of your Anthropic account and the
  name of a model, for example `claude-sonnet-5-5`.
- **OpenAI-compatible:** OpenAI itself and everything that copies its chat completions API, such as
  Ollama or llama.cpp for a model on your own hardware. You need the model name (`gpt-4o`,
  `llama3.1:8b` ...) and, for OpenAI, a key; local servers usually need none. The **address** is
  not typed in: it is chosen from the list the operator has allowed (see below), and the choice
  only appears when that list is not empty.

**DeepSeek, OpenRouter and other services with an OpenAI-compatible API.** They work with the
second kind, no extra code needed. The operator allows the address, the user chooses it and enters
the key of their own account there:

| Service    | Address (what the operator lists)  | Notes |
| ---------- | ---------------------------------- | ----- |
| DeepSeek   | `https://api.deepseek.com`         | The form names it "DeepSeek". For a plan PaceForge also asks for JSON output (`response_format`), which is not done for the check or for any other address. |
| OpenRouter | `https://openrouter.ai/api/v1`     | One key for many models; the model name is the one OpenRouter lists (`vendor/model`). PaceForge sends no routing preferences, so which company handles a request is up to your OpenRouter settings. |

Things to know before you allow one of them:

- **Where the prompts go.** For a plan that is what [Week plan](#week-plan) lists: goals (title
  and notes), training load, times and zone tables. DeepSeek is a Chinese company and OpenRouter
  hands requests on to the company behind the model: read their terms and privacy statements
  first, and remember that listing an address lets **every user of the instance** send their
  prompts there.
- **Cost.** You pay the service, at its prices, which change. They are often a fraction of what
  Claude costs per token, but a model that makes more mistakes needs more repairs (a repair is a
  second request), so compare the usage overview, not only the price list.
- **Thinking models.** Their reasoning counts against the 8000-token limit of a plan. If the
  answer is cut off, the draft is asked for once more; with a plan that is too long for the limit
  it ends as "the coach gave no usable plan".
- **Not verified.** The addresses and the form of the request follow the services' public
  documentation and the OpenAI format; this has been tested against local fake servers, not
  against the real services. Check the address and the model name in their documentation.

**Setting it up.**

1. Choose the provider, enter the model name exactly as the provider writes it (letters, digits and
   `. _ : / -`, up to 100 characters) and the key (visible characters without spaces, up to 500;
   the field is a password field and never prefilled). Press **Save**.
2. Press **Check connection**. PaceForge sends one request with the fixed text `Reply with the
   single word: ok` (at most 16 tokens, no system prompt) and **nothing about you or your
   training**, and shows how it went.
3. Change anything later by saving again. Any change of provider, model, address or key sets the
   status back to **Not checked yet**; saving the very same setup again changes nothing. The check
   always uses the **saved** setup (the page says when you have unsaved changes).
4. **Remove** deletes the setup and the stored key after a question. PaceForge cannot revoke the key
   at your provider; delete it there if it should stop working.

**The status** shows what was learned at the last call:

| Status                                             | Meaning                                                          |
| -------------------------------------------------- | ---------------------------------------------------------------- |
| Not checked yet                                    | Nothing was tried since the setup was saved or changed.          |
| Connected                                          | The last call worked.                                            |
| The provider did not accept the key                | The provider answered 401 or 403, or the stored key cannot be decrypted. |
| The provider could not be reached                  | Network error, timeout (60 seconds per step), 408 or a 5xx answer. |

Two outcomes leave the status as it was and only move the time of the last check: **rate limited**
(the page adds how long the provider asked to wait, up to an hour) and an **unexpected answer**
(for example a wrong model name: the key may be fine, and it is no outage). Each outcome has a
fixed text on the page; nothing the provider says is shown or stored.

**The key.**

- It is **write-only**: stored encrypted with the [instance key](#instance-key), sent to the
  provider only in the header of the request, never shown again (not even in part), not returned by
  any endpoint, not in logs and not in error messages. The page tells you only whether a key is
  stored.
- A stored key is kept while you change only the model. It is **never carried to another provider
  or address**: if you switch, you enter a key again (Anthropic needs one; an OpenAI-compatible
  endpoint can do without, and **Remove the stored key** drops it).
- If the instance key is lost, a stored key can no longer be read. It counts as none: the next
  check marks the key as refused (without asking the provider) and you enter the key again.

**What is stored about your calls.** One record per request that reached the provider: provider,
model, purpose, how it ended (success, key refused, rate limited, unavailable, unexpected), the
tokens the provider counted (if it said) and the time. **Never** the prompt, the answer or an error
text. The page shows the sum of the last 30 days: calls (failed ones included), input and output
tokens. A request that was refused before it was sent (the address is no longer allowed) is not
counted. Costs and budgets are not calculated yet. The records stay when you remove the setup.

**Limits.** Checks are limited to 10 per minute per user, with a counter of their own (it does not
use up the Intervals.icu limit). An answer larger than 2 MB is refused. Redirects are not followed,
so the key can never be sent to another address.

**For operators: the allowed addresses.** A user must not be able to point the server at an
arbitrary address, because that would let it query internal systems. So OpenAI-compatible
endpoints can only be chosen from `AI_ALLOWED_BASE_URLS`, a comma-separated list in `.env`. It is
empty by default: no OpenAI-compatible endpoint is offered. Each entry is a base URL (for
OpenAI-style APIs it usually ends in `/v1`) with `http://` or `https://`, a host, an optional port
and path, and **no user name, password, query or fragment**; a bad entry stops Django at startup (the message names the entry,
not its text). Entries are compared in a normal form (lower-case host, no trailing slash) and a
user's choice must match one exactly. The list is checked again at every call: if you take an
address off, it stops working at once, nothing is sent and the user sees that it is no longer
allowed. Examples:

```
# OpenAI, and Ollama or llama.cpp on the machine that runs PaceForge
AI_ALLOWED_BASE_URLS=https://api.openai.com/v1,http://localhost:11434/v1,http://localhost:8080/v1
```

```
# DeepSeek and OpenRouter
AI_ALLOWED_BASE_URLS=https://api.deepseek.com,https://openrouter.ai/api/v1
```

Inside a container `localhost` is the container itself; use the host name of the other service or of
the host. Listing an address means that **every user of the instance** may send their prompts there,
so list only what you trust. `ANTHROPIC_API_BASE_URL` (default `https://api.anthropic.com`) is only
for tests and fake servers.

**Not verified against real providers yet.** The adapters are tested against local fake servers
that speak the two formats; the first real connection is up to you. The OpenAI-compatible adapter
sends `max_tokens`, which local servers and most models accept; a model that insists on another
name for it would answer with an error, shown as an unexpected answer.

## Activities

The **Activities** page (`/activities`, also in the navigation) is where athletes bring their
history in: choose FIT or TCX files from a watch or from an export (Garmin, COROS, Strava, …), one
or several at once. Intervals.icu does not hand out activities that it received from Strava, so for
an athlete whose history lives in Strava the file import is the way in (details in
[`docs/phase0-intervals.md`](docs/phase0-intervals.md)).

1. Get the files. The menus change from time to time; if one of these is gone, look for "export
   original" or "export FIT/TCX" in the same place.
   - **Garmin Connect (web):** open an activity, gear icon, **Export Original** (a zip with the FIT
     file inside: unzip it first) or **Export to TCX**.
   - **COROS Training Hub:** open an activity, the three dots, **Export** (FIT or TCX). **Activity
     List**, **Export Data** sends you a bulk export of FIT or TCX files by email.
   - **Strava:** on an activity's web page, the three dots, **Export Original**. For the whole
     history use Settings, My Account, **Download or Delete Your Account**, **Request Your
     Archive**; it can take hours or days to arrive. The files in its `activities` folder are often
     compressed (`.fit.gz`): unpack them first (`gunzip activities/*.gz`).
2. Open **Activities**, press the file chooser and select the files. Each file is sent on its own
   and gets its own line: *Imported*, *Already imported*, the reason it was refused, or *too
   large*. The list below shows date, sport, duration, distance, average heart rate and source,
   newest first, 20 per page.
3. **Delete** (with a confirmation) removes the activity and the file that was stored with it.

What you should know:

- **The content decides, not the name.** A FIT file named `.txt` imports; a text file named `.fit`
  does not. Compressed files (`.gz`) and zip archives are refused with "The file is neither a FIT
  nor a TCX file": unpack them first.
- **Only what the file reports is stored, nothing is estimated.** Sport (running, cycling,
  swimming, strength, otherwise *other* with the file's own wording), start (UTC, shown in your
  browser's time zone), elapsed and timer time, distance, average and maximum heart rate, average
  power, total ascent, calories, the manufacturer and the laps. What the file does not say stays
  empty and is shown as a dash. That is common: a TCX file has no total ascent, and many files have
  no power. There is no elevation gain computed from the altitude track and no cadence yet.
- **The original file is kept** (gzip-compressed, in the database), so charts and training load can
  be built later without asking you to upload again. **This includes the GPS track**: from it,
  home and workplace can be inferred. The database and its backups therefore hold location data and
  need the same care. The file is never returned by the API, and deleting an activity deletes it.
- **Duplicates are refused:** the same file, or the same run exported in another format (same start
  and sport), answers *Already imported*. Each user has their own activities; another user may
  import the same file.
- **Limits:** 25 MB per file (`ACTIVITY_UPLOAD_MAX_BYTES`, see [Configuration](#configuration)),
  30 imports per minute per user, files with several sessions (multisport) are refused. Behind a
  reverse proxy, allow request bodies at least that large (for nginx `client_max_body_size`); the
  proxy would otherwise answer before PaceForge can.
- **Damaged or hostile files** are refused with a message and store nothing: FIT checksums are
  verified, TCX documents with a `DOCTYPE` or entities are refused, and the number of records,
  laps and nested elements is capped.

## Athlete profile

The **Profile** page (`/settings/profile`, also in the navigation) holds what PaceForge needs to
know about you as an athlete: your time zone, your thresholds and the training zones that follow
from them. Cycling has FTP, lactate threshold heart rate (LTHR) and maximum heart rate; running has
threshold pace, LTHR and maximum heart rate. Swimming and strength training have none yet.

**Where a value comes from, and which one counts.** Every threshold shows its source: **You**,
**Intervals.icu** or **Estimated**. If there are several, the first one in that order counts and
the others are listed as "Also known". A value you type in therefore always counts, until you press
**Use automatic value**, which removes only your own value; nothing else is deleted.

1. **Type a value.** Press **Edit** on a row, enter the number and press **Save** (or Enter). Watts
   and beats are numbers (a comma works as the decimal point), the pace is minutes and seconds per
   kilometre, for example `5:00`. Allowed are FTP 30 to 2000 W, heart rates 30 to 250 bpm and a pace
   from 2:00 to 20:00 per km; values are stored as whole numbers. The lactate threshold heart rate
   cannot be above the maximum heart rate of the same sport (compared with what you typed in or
   Intervals.icu holds; an estimate never stops you from entering the right value).
2. **Read from Intervals.icu.** With a working connection (see [Connections](#connections)) the
   page reads your sport settings when it opens, if that has never happened or was more than 24
   hours ago, and **Update from Intervals.icu** does it on demand. The settings entry that includes
   `Ride` or `VirtualRide` is your cycling, the one with `Run` or `VirtualRun` your running;
   swimming and "Other" are ignored. The pace is stored there in metres per second and converted.
   Values outside the ranges above are skipped, values that Intervals.icu no longer has are
   removed, and what you typed in or what was estimated is never touched. Reading is limited to 10
   per minute together with connecting and checking. If Intervals.icu does not accept the stored
   key, the page says so and the connection shows **Needs attention** on the Connections page.
3. **Estimated values.** Where nothing else is known, PaceForge estimates from the activities you
   imported. An estimate never overrides a value you typed in or one from Intervals.icu, and it is
   recomputed after every import and every deletion (so it is only as fresh as the last one).
   - **Maximum heart rate**, for running and cycling separately, from the highest heart rate of
     each activity. Values outside 30 to 250 bpm are ignored; with at least three usable ones, the
     highest value counts if another activity came within 3 bpm below it. A single peak without a
     partner (a chest strap or wrist sensor glitch) is ignored; two glitches that happen to match
     would be believed.
   - **FTP, threshold pace and LTHR** from the best efforts inside the files, using only
     activities of the **last 90 days**. For cycling: FTP is 95 % of the best 20-minute average
     power, LTHR is 95 % of the average heart rate during that effort. For running: the threshold
     pace is the pace of the best 30-minute effort and the LTHR the average heart rate during it.
     Power from a run never becomes an FTP, and the speed of a ride never a running pace. A window
     counts only if the data covers all of it: a pause of more than 10 seconds ends it, a shorter
     gap of power or heart rate is bridged, nothing is interpolated. A file without power gives
     no FTP; this is common for running and for TCX files. Training rarely contains an all-out
     effort, so these values are **lower bounds**: the page says "At least …", and the value you
     enter yourself or Intervals.icu supplies counts instead as soon as it exists. Values outside
     the ranges above are not stored. The best efforts of an activity are computed when the file
     is imported and stored in the database (not the time series, not the track); the page never
     shows them.
   - **Activities imported earlier** have no best efforts yet. Compute them from the stored files
     with `cd backend && uv run python manage.py backfill_best_efforts` (optionally
     `--email you@example.com` for one account). The command skips what is already computed, so it
     can be run again at any time; it then refreshes the estimates of the accounts it filled and
     prints counts only (computed, no usable series, failed, without a stored file).
4. **Zones.** They are computed from the value that counts and shown per sport. They follow
   published conventions, which athletes and coaches handle differently, so treat them as a
   starting point:
   - **Power**, 7 zones with limits at 55, 75, 90, 105, 120 and 150 percent of FTP (after Andrew
     Coggan).
   - **Heart rate**, 5 zones with limits at 85, 90, 95 and 100 percent of the lactate threshold
     heart rate (after Joe Friel). Without one, five zones with limits at 60, 70, 80 and 90 percent
     of the maximum heart rate.
   - **Running pace**, 5 zones with limits at 129, 114, 106 and 99 percent of the threshold pace
     (after Joe Friel). Pace is time per distance, so the zones run from slow (zone 1, 129 percent
     and slower) to fast (zone 5, faster than 99 percent).

   A zone includes its lower limit and not its upper one; the page shows the last whole value
   ("138–187 W"), so neighbouring zones neither overlap nor leave a gap.
5. **Time zone.** Enter a name from the time zone database, exactly spelled (`Europe/Berlin`), or
   press **Use this device's time zone** and then **Save time zone**. An empty field removes it. It
   is stored for the day-based planning that follows; the activities list still shows times in your
   browser's time zone.

Thresholds are personal data: every user sees and changes only their own, administrators included,
and no answer contains another user's values.

## Goals

The **Goals** page (`/goals`, also in the navigation) is where you say what you are training for.
Each user has their own goals; another user, an administrator included, never sees them.

**Kinds.** Every goal has a title (up to 100 characters), optional notes (up to 1000), a priority
and a status. The kind is chosen when the goal is added and cannot be changed afterwards.

- **Race:** a discipline (running, cycling, swimming or triathlon) and the date are required. A
  distance (the form offers the usual ones for running and triathlon, any other in km, up to
  1000 km) and a target time (`3:45:00`, from 1 minute to 100 hours) are optional.
- **Threshold:** raise your FTP (watts, cycling) or your threshold pace (minutes and seconds per
  kilometre, running) to a target value. The date is optional. The value is only a target: it
  is not compared with your profile yet.
- **General:** a title and notes, optionally a date ("Build endurance"). Nothing else.

**Main goal.** At most one **active** goal is the main goal; the others are secondary. Making
another goal the main goal is refused with "You already have a main goal. Change it first.":
press **Make secondary** on the current one first. A goal that is achieved or dropped no longer
counts as the main goal for this rule.

**Status.** A goal is **active**, **achieved** or **dropped**. **Mark achieved**, **Drop** and
**Reactivate** change it; nothing is deleted by that. **Delete** removes the goal for good, after a
question. An active race cannot lie in the past: adding one, changing its date or reactivating it
with a past date is refused, while a past race that stays as it is (its title changes, say) is left
alone. Mark it achieved or dropped instead.

**Order and days to go.** Active goals come first, then achieved, then dropped; within each, the
main goal first, then by date (goals without a date last), then by when they were added. Next to
a date the page says how far away it is ("in 12 days", "tomorrow", "today", "3 days ago"). Which
day it is **today** depends on the time zone in your [profile](#athlete-profile); without one (or
with one this server does not know) the page uses UTC, so around midnight the count can be a day
off until you set it.

**Limits.** At most 30 goals per user (finished ones included), so delete old ones when it is full.
Titles and notes are shown as plain text, never as markup.

Not there yet: training phases, and goals in the coach's context.

## Training time

The **Training time** page (`/availability`, also in the navigation) tells PaceForge how much time
you can train. It does not plan anything itself; the [Week plan](#week-plan) checks its sessions
against it. Everything here is personal: every user sees and changes only their own, an
administrator included.

**Per weekday.** Seven fields, Monday first. Enter minutes (`90`) or hours and minutes (`1:30`,
the minutes always with two digits and below 60); at most 24:00 (1440 minutes) per day. A field you
leave empty counts as **no time**, and so does a user who has entered nothing: PaceForge never
assumes that you are free. While you type, the page adds the days up ("Together: 7:30 per week").

**Weekly budget.** Optional, up to 168:00 (10080 minutes). It caps what the days add up to: with
7:30 in the fields and a budget of 5:00, a week offers 5:00. A budget below the sum is allowed on
purpose (it is the most you *want* to train) and the page says what it means. Leave the field empty
for no cap. The budget applies to a week, never to a single day.

**A normal week.** Optional, in the same form (`6:00`), up to 168:00. What a normal week of
training is, or was before a break, for you. It adds no time to your days and caps nothing. The
[Week plan](#week-plan) uses it as a reference for how far a week may rise: the rule compares the
planned minutes with what you have done in the last four weeks, and after a break that is a low
yardstick (an average of 108 minutes allows about 140, which is how a coach ends up with sessions of
30 minutes). With a normal week of 6:00 the yardstick is that instead, as long as it is higher than
your recent weeks. The coach is told the number and that it is where a return to training is
headed, not where it starts. It is **your word and your responsibility**: 130 % of a normal week is
a big first week after a long break, so enter what you really want to build up to. An operator who
wants more care can lower `TYPICAL_VOLUME_PERCENT` in `backend/planning/rules.py` (100 counts the
whole week, 70 would count 70 % of it).

**Sports and stretching.** Tick the sports you want in your plan: **Running**, **Cycling**,
**Swimming** and **Strength / gym** (at least one; if you never chose, all four count). Your coach
plans only those, and the checks refuse a workout in any other sport. **Add stretching to sessions**
lets the coach add a few minutes of stretching to a session: it is never a session of its own, it
uses up none of your minutes and it does not count as a training day. Off is the default.

**Limitations.** Free text of up to 1000 characters ("no running on consecutive days"). It is kept
and shown as plain text, never as markup. Nothing interprets it, and it is not sent to the coach
either: it is free text about you, and the only free text the coach sees is the title and notes of
your goals.

**Save** sends the weekdays, the budget, the normal week, the sports, the stretching choice and the
limitations together. The page checks the limits
first and names every problem next to its field; if the server still refuses something, its message
appears in the same place. Nothing is saved until every field is usable.

**Not available.** Below the form, the periods in which you cannot train: **vacation**,
**illness** or **other**, with a first and a last day (both belong to the period), a note of up to
200 characters and at most 366 days. A period of one day needs only the first day; the last day
follows it while it is empty. Periods may overlap, may lie in the past (they stay as a record) and
there can be at most 100 of them. Going-on and coming periods come first, the nearest first; past
ones follow, the latest first, marked **Past**; the one that is going on is marked **Now**. Which
day it is today depends on the time zone in your [profile](#athlete-profile), as with the goals.
**Delete** removes a period after a question. Changing a period is possible through the API but
not yet on the page: delete it and add it again.

**What a day or a week offers.** A day inside any period offers no time; every other day offers the
minutes of its weekday. A week offers its seven days added up, at most the weekly budget. The
functions `minutes_on` and `minutes_in_week` in `backend/availability/capacity.py` answer this for
the planning that will use it; they take calendar days, so which day it is stays the caller's
business.

The API is `GET` and `PATCH` on `/api/availability/` (`weekdays` Monday first,
`weekly_budget_minutes`, `typical_weekly_minutes`, `sports`, `stretching`, `limitations`; `null`
removes a number) and
`/api/availability/periods/` with list, create, read, change and delete.

Not there yet: time windows within a day, and different time per sport.

## Week plan

The **Week plan** page (`/planning`, in the navigation) is where your own AI coach drafts a training
week. It needs an [AI provider](#ai-coach-bring-your-own-key); without one the page says so and
links to the Connections page.

1. Choose the **week**. The current week and the four after it can be planned; the page starts with
   next week.
2. Press **Draft a plan with my coach**. The page waits for the answer, which can take **a minute or
   two**. You can do nothing else on the page meanwhile.
3. Read the **draft**: the workouts by day with their length, their zone (power, heart rate or
   pace) and, for intervals, their parts, and below the title what the **checks** say. An *error*
   (for example a workout on a day you cannot train, or segments that do not add up to the length)
   means the plan cannot be confirmed; a *note* is for you to weigh.
4. **Confirm plan** or **Discard**. Confirming checks the plan again with your data of that moment.
   Drafting again makes a **new version** of the week; all versions stay in the list, and
   confirming a draft replaces the version that was confirmed before.
5. Send the confirmed week to your calendar: see [Sending to Intervals.icu](#sending-to-intervalsicu).

**Zones as numbers.** Next to a zone the page shows what it means for you today, for example
"Power zone 2 · 138–188 W", worked out from your thresholds (see
[Athlete profile](#athlete-profile)). Without the threshold for a zone the page shows only the zone.

**Two sessions a day.** A day may have two sessions, rarely three, for example an easy run in the
morning and a ride in the afternoon. Each of them has a time of day (**morning**, **afternoon** or
**evening**) shown next to it; no two sessions of a day share one, and a day with several sessions
should name a time for each (the checks say so). The time you have is still given **per day**: the
coach splits it over the day, and does not know that you can only train in the evening. Stretching
comes as "+ 10 min stretching" under a session, only if you switched it on, and never as a session.

**After a break.** If the plans look too small, enter **A normal week** on the
[Training time](#training-time) page: the limit for how far a week may rise then follows what you
are used to and not only the last four weeks.

**No time.** If the week offers no training time at all (nothing on any day, a weekly budget of 0,
or away the whole week), the page says "You have no training time for this week." with a link to
the Training time page. Nothing is sent to your provider then, so it costs nothing.

The coach is told only a fixed set of facts: the week and today, the minutes you can train on each
day and your absences, your weekly budget, your zone tables, the sports you ticked and whether
stretching is allowed, your active goals (title and notes), the minutes you trained in the last
four weeks, your normal week if you gave one and a summary of last week's confirmed plan. **Not**
your name, e-mail address, activities' names, the limitations you wrote on the training time page
or anything of other users. A goal's title and notes are free text, and a model can be influenced by
text; whatever it answers still has to pass the strict reading and the checks before it is a draft,
and nothing is confirmed without you. Every request goes to your provider with your key and is
**billed to you**: a draft costs one request, or two if the coach had to correct its answer. They
are counted in the usage overview of the AI coach (calls and tokens of the last 30 days; the
purpose "weekly plan" is stored with each record). Drafting is limited to 5 a minute per user, with
a counter of its own.

The full description, with the format, the rules, the exact limits and the API, is
[Drafting with the coach](docs/weekly-plan.md#drafting-with-the-coach).

**For operators.** Drafting waits for the provider inside the request. A reverse proxy and the
application server need a timeout of at least **150 seconds** for it (see the troubleshooting
entry below).

**Not verified yet.** The drafting is tested with a provider that answers from a script, and the
page with test doubles for the API; neither has been tried against a real provider or in a browser
by the developer. Your first real draft is the first real test; please read it critically.

### Sending to Intervals.icu

With [Intervals.icu connected](#connections) a confirmed week can be sent to your calendar. It
never happens by itself: press **Send to Intervals.icu** on a confirmed plan, or tick **Send the
week to Intervals.icu right away** before you confirm. If sending does not work, the plan stays
confirmed and the page says why.

- **What arrives:** one workout in your calendar for each workout of the plan, with its steps, the
  targets in watts, beats per minute or minutes per kilometre (worked out from your thresholds at
  the moment of sending), the time of day as start time (**morning** 07:00, **afternoon** 12:00,
  **evening** 18:00, otherwise all day), strength and stretching as text. Intervals.icu passes the
  workouts on to the devices and services you connected there (Zwift, COROS, Garmin …).
- **Sending again** updates the same workouts and never adds them twice. A **new version** of the
  week replaces the workouts of the version before in your calendar.
- **PaceForge wins.** If you change a workout in Intervals.icu, the next sending overwrites it,
  and one you deleted there comes back.
- **Each workout has a result** on the page: "In Intervals.icu", "Not sent to Intervals.icu yet" or
  why it was not sent. A workout that fails does not keep the others from arriving; **Send again**
  tries the rest. Sending is limited to 10 a minute per user.
- **The key** you gave PaceForge can write to your whole calendar. Nothing but the workouts of the
  plan is sent, and what Intervals.icu answers is never shown or kept beyond a fixed error code.

The format of the events is described in
[Sending to Intervals.icu](docs/weekly-plan.md#sending-to-intervalsicu).

**Not verified yet.** Sending is tested against a stand-in for Intervals.icu; it has not been tried
against the real calendar by the developer, and neither has the page in a browser. In particular
the description format (pace targets, the strength workout) is written from the documentation, and
cycling workouts are sent as `Ride`: whether a ride reaches Zwift as a workout may depend on
Intervals.icu treating it as `VirtualRide`. Your first real week is the first real test.

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
| `INTERVALS_API_BASE_URL`       | `https://intervals.icu/api/v1`      | Only for tests or a fake server: where the Intervals.icu API is. `http://` or `https://`. |
| `AI_ALLOWED_BASE_URLS`         | empty                               | Comma-separated base URLs of OpenAI-compatible AI endpoints that users may choose, e.g. `https://api.openai.com/v1` or `https://api.deepseek.com`. Empty: none. A bad entry stops Django at startup, see [AI coach](#ai-coach-bring-your-own-key). |
| `ANTHROPIC_API_BASE_URL`       | `https://api.anthropic.com`         | Only for tests or a fake server: where the Anthropic API is. `http://` or `https://`. |
| `ACTIVITY_UPLOAD_MAX_BYTES`    | `26214400` (25 MB)                  | Largest FIT or TCX file accepted for import, in bytes. Must be a positive integer. |
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
- **An import says "The file is neither a FIT nor a TCX file".** The file is compressed (`.gz`),
  a zip archive, a GPX file or something else. Unpack it, or export FIT or TCX instead.
- **Importing a big file fails with "413" or an error page before PaceForge answers.** A reverse
  proxy in front limits the request body; raise its limit to the value of
  `ACTIVITY_UPLOAD_MAX_BYTES` or more.
- **The time zone is refused.** The name must be exactly one of the time zone database, with the
  capitalisation shown there (`Europe/Berlin`, not `europe/berlin` or `CET`). Press **Use this
  device's time zone** to fill the field, or pick one of the suggestions.
- **A threshold heart rate is refused with "Cannot be above the maximum heart rate".** The value
  you typed in, or the one from Intervals.icu, for the maximum heart rate of that sport is lower;
  correct the maximum first.
- **"Update from Intervals.icu" says the stored key was not accepted.** Enter the key again on the
  Connections page (the connection shows **Needs attention** there). "Cannot be reached" and "Too
  many attempts" go away by themselves; nothing was changed.
- **Django refuses to start with `DJANGO_SECRET_KEY`, `DATABASE_URL` or `ENCRYPTION_KEY` missing.** Both are required
  and have no default; check that `.env` is in the repository root, not in `backend/`.
- **The Connections page says "Intervals.icu cannot be reached right now".** The server could not
  get an answer from `intervals.icu` (network, timeout, a busy service). Try again later; nothing
  was saved or changed. "Too many attempts" means more than 10 saves or checks within a minute.
- **Drafting a plan ends with a gateway error (502, 504) after a minute or so.** A reverse proxy or
  the application server gave up waiting for the provider. Drafting can take two minutes (60
  seconds per call, and one repair); raise `proxy_read_timeout` (nginx) and the worker timeout to
  150 seconds or more. A draft may have been stored anyway: look at the versions of the week.
- **An administrator cannot reach the admin pages and keeps landing on the security page.** That is
  the rule that administrators need two-factor authentication; set it up there.
- **Sign-in is refused with "too many failed attempts".** That is the brute-force protection: five
  failed attempts for an address lock it for five minutes. The counters live in the server
  process, so restarting the dev server clears them.
