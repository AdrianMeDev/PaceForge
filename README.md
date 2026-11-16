# PaceForge

A self-hostable, AI-assisted endurance coach for running, cycling, swimming and strength training.
The long-term goal is described in `PROJECT_PLAN.md`; this repository is in early development.

**What works today:** accounts for a multi-user instance, invitation-only registration with an
admin page for invitations, email verification, sign-in and sign-out with server-side sessions,
password reset, two-factor authentication (authenticator app plus recovery codes, mandatory for
administrators), a personal Intervals.icu connection with an API key (stored encrypted), importing
activities from FIT and TCX files, an athlete profile with your time zone, your thresholds (typed in,
read from Intervals.icu or estimated from your activities) and the training zones that follow from
them, goals (races, threshold targets and general goals, with priorities A, B and C), your training time
(minutes per weekday, a weekly budget, injuries and limitations, vacation and illness), your own AI provider
([Anthropic or an OpenAI-compatible endpoint](#ai-coach-bring-your-own-key), key stored encrypted,
with a connection check and a usage overview), the model and the plausibility checks for a
training week ([format and rules](docs/weekly-plan.md)), a **Week plan** page on which your own
AI coach drafts a training week that you read, change by hand, confirm or discard ([Week plan](#week-plan)), a
**Season** page with the phases and the volume of every week up to your race
([Season](#season)), a **Week review** page that shows how a week went against the confirmed plan, on which you rate your
sessions, say how the week felt and ask your coach about it ([Week review](#week-review)), and the
data-isolation foundation the training features will build on.
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
3. Optionally give a **model for the season plan**, in the field of that name (same rules as the
   model name; leave it empty to use the normal one). The season is
   the biggest thing the coach is asked, so a stronger model may be worth it there; left empty,
   the normal model does it. It is the same provider and the same key, and only the season plan
   uses it.
4. Change anything later by saving again. Any change of provider, model, season model, address or
   key sets the status back to **Not checked yet**; saving the very same setup again changes nothing. The check
   always uses the **saved** setup (the page says when you have unsaved changes).
5. **Remove** deletes the setup and the stored key after a question. PaceForge cannot revoke the key
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
the model that was used (the season model for the season plan, else the normal one), purpose, how it ended (success, key refused, rate limited, unavailable, unexpected), the
tokens the provider counted (if it said), how many of the input tokens came from the provider's
prompt cache and how many were written to it, and the time. **Never** the prompt, the answer or an
error text. The page shows the sum of the last 30 days: calls (failed ones included), input and
output tokens and, when there are any, the cached ones. A request that was refused before it was sent (the address is no longer allowed) is not
counted. Costs and budgets are not calculated yet. The records stay when you remove the setup.

**Prompt caching.** The system prompt of the coach (the rules and the format, the same for every
athlete) and the first message of a conversation (the briefing about you) are marked for
**Anthropic's prompt cache**, for the default of **five minutes**. A repair round, which starts with
the same bytes, and the next draft within five minutes read them from the cache for a tenth of the
price of reading them again; writing to the cache costs a quarter more once. The cache is the one
of **your own key and organization**: nothing of it is shared with other users of this server. It
only works above a minimum length that depends on the model (512 to 4096 tokens), so a short
prompt is simply not cached, and a first answer that needs no repair has paid the small extra for
nothing. The connection check sends no system prompt and caches nothing. **OpenAI** and compatible
servers cache a long prefix on their own; the request is not changed, and where the provider says
how much it read, that is counted. The Connections page shows both numbers, which is how you see
whether it works; nothing about it can change what the coach answers.

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
   large*. The list below shows date, sport, duration, distance, average heart rate, RPE, load and
   source, newest first, 20 per page.
3. **Enter a session** by hand for what no watch recorded (strength training, a session that only
   Strava has): sport, day, the time it started, the duration in minutes, and optionally the
   distance, how hard it felt and a note. See [Sessions entered by hand](#sessions-entered-by-hand).
4. **Delete** (with a confirmation) removes the activity and the file that was stored with it, if
   it has one.

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
- **Duplicates are refused:** the same file, or the same session from another source, answers
  *Already imported* (see [the same session twice](#the-same-session-twice)). Each user has their
  own activities; another user may import the same file.
- **Limits:** 25 MB per file (`ACTIVITY_UPLOAD_MAX_BYTES`, see [Configuration](#configuration)),
  30 imports or entries by hand per minute per user (they share one counter), files with several sessions (multisport) are refused. Behind a
  reverse proxy, allow request bodies at least that large (for nginx `client_max_body_size`); the
  proxy would otherwise answer before PaceForge can.
- **Damaged or hostile files** are refused with a message and store nothing: FIT checksums are
  verified, TCX documents with a `DOCTYPE` or entities are refused, and the number of records,
  laps and nested elements is capped.

### Sessions entered by hand

The form on the Activities page stores a session without a file. It is meant for what a watch did
not record, and for the sessions that only Strava has (Intervals.icu cannot hand those out).

- **What you give:** the sport, the **day** and **the time it started** (on the clock of your time
  zone from the [profile](#athlete-profile); without one, UTC), the duration in whole minutes (1 to
  1440), optionally the distance in kilometres (up to 1000), **how hard it felt** on a scale from 1
  to 10 (RPE, the rating of perceived exertion) and a note of up to 500 characters. A session in
  the future, or before the year 2000, is refused. Apart from the rating and the note (see [Week
  review](#week-review)) there is no editing: delete the session and enter it again.
- **The coach counts it** like an imported activity: its duration is part of the minutes of the last
  four weeks that the plan builds on. Nothing is estimated beyond that: no heart rate, no power, no
  best efforts, so it does not change your estimated thresholds.
- **The load** of a session is the duration in minutes times the RPE, rounded, shown as *AU*
  (arbitrary units; a 45 minute session at 7 is 315 AU). It is an estimate from how it felt and
  **not the training stress score (TSS)** of a power meter or a platform: the two are on different
  scales and are never added up. A session without a rating has no load, and neither does one
  without a duration. (Imported files carry no rating at first; you can rate any activity afterwards
  on the [Week review](#week-review) page.)

#### The same session twice

One session can arrive more than once: as the file from the watch, in another format, entered by
hand. Two activities of yours count as the same session if they have the **same sport** and either
start at exactly the same moment, or start **within 10 minutes** of each other and their durations
differ by **at most 10 %** of the longer one (where a duration is missing on one side, the start
alone decides). The second one is refused with *Already imported* (a file) or *You already have
this session* (the form), and the page offers to show the first. This is a guess: two real, short
sessions of one sport that start minutes apart and are about equally long would be taken for one.
If that happens to you, change the start of one of the two by more than 10 minutes. The tolerances
are two constants in `backend/activities/duplicates.py`.

## Athlete profile

The **Profile** page (`/settings/profile`, also in the navigation) holds what PaceForge needs to
know about you as an athlete: your time zone, some data about you and your training, your
thresholds and the training zones that follow from them. Cycling has FTP, lactate threshold heart rate (LTHR) and maximum heart rate; running has
threshold pace, LTHR and maximum heart rate. Swimming and strength training have none yet.

**Where a value comes from, and which one counts.** Every threshold shows its source: **You**,
**Best time** (the running threshold pace only, see below), **Intervals.icu** or **Estimated**. If
there are several, the first one in that order counts and the others are listed as "Also known". A value you type in therefore always counts, until you press
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

6. **About you.** A panel below the time zone for data that helps the coach size your training. All
   of it is optional and an empty field removes what was saved:
   - **Year of birth** (1900 to ten years ago), **sex** (female, male or other), **weight** (25 to
     300 kg, one decimal) and **resting heart rate** (25 to 120 bpm).
   - **Years of training** in running, cycling, swimming and strength (0 to 80 whole years each).
   - **Strength training experience** (beginner or advanced) and the **equipment** you have (gym,
     bodyweight only, dumbbells; none ticked: not said).

   These go to your AI coach with every plan request, as numbers and fixed words and without any
   text of yours, and the panel names the provider. **The year of birth is not sent**, only the age
   worked out from it for the week to plan (it can be one year too high before your birthday). The
   coach uses it to size the load; no rule checks it. **Save** sends the whole panel at once, the
   page checks the ranges first and a message from the server appears at its field.

7. **Best times and VDOT.** Below the running thresholds you can enter your best time over 5 km,
   10 km, the half marathon and the marathon, with the day of the race (one per distance; a new one
   replaces the old one). The time is `19:57` or `1:35:00`; the day is not in the future and not
   before 1900, and a time that no runner has (a VDOT below 20 or above 90) is refused as a typo.
   - **VDOT** is the "effective VO2max" of Jack Daniels and Jimmy Gilbert, worked out from the
     distance and the time. The **threshold pace** is the speed at 88 percent of it (VDOT 50 gives
     about 4:15 per km), rounded to whole seconds like every threshold.
   - **Which time counts:** only races of the **last 365 days**, the **newest** first, on the same
     day the higher VDOT. Older times stay in the list, marked "too old to count", and give
     nothing. With a time that counts, the running threshold pace comes from it **after a pace you
     typed in and before Intervals.icu and the estimate**, so the pace zones follow your race form.
     Removing the time, or the year running out, brings the next source back; nothing else is
     deleted.
   - **It is a model.** A short race can give a pace that many runners cannot hold for an hour; the
     zones stay a starting point, and a pace you type in always wins.
   - **The coach** is told your best times (distance, time, day, VDOT, whether the race is recent
     and whether it counts) and the VDOT that counts, as numbers and fixed words.

Thresholds and the data about you are personal: every user sees and changes only their own,
administrators included, and no answer contains another user's values.

The API is `GET` and `PATCH` on `/api/athlete/`. The best times are `PUT` (`seconds` and `date`, `YYYY-MM-DD`) and `DELETE` on
`/api/athlete/best-times/<distance>/` (`5k`, `10k`, `half_marathon`, `marathon`); the answer has
`best_times` for every distance and `vdot`. `PATCH` takes any of `timezone`, `birth_year`,
`sex`, `weight_kg`, `resting_hr`, `training_years` (an object with any of `running`, `cycling`,
`swimming`, `strength`), `strength_experience` and `strength_equipment`; a field that is left out
stays as it is, `null` clears one, and at least one has to be there. Nothing is saved unless every
field is usable. The thresholds are `PUT` and `DELETE` on `/api/athlete/thresholds/<sport>/<metric>/`
and `POST /api/athlete/sync/` reads Intervals.icu.

## Goals

The **Goals** page (`/goals`, also in the navigation) is where you say what you are training for.
Each user has their own goals; another user, an administrator included, never sees them.

**Kinds.** Every goal has a title (up to 100 characters), optional notes (up to 1000), a priority
and a status. The kind is chosen when the goal is added and cannot be changed afterwards.

- **Race:** a discipline (running, cycling, swimming or triathlon) and the date are required. A
  distance (the form offers the usual ones for running and triathlon, any other in km, up to
  1000 km) and a target time (`3:45:00`, from 1 minute to 100 hours) are optional.
- **Threshold:** raise your FTP (watts, cycling) or your threshold pace (minutes and seconds per
  kilometre, running) to a target value. The date is optional. The value is compared with your
  current value to say how realistic it is (see below).
- **General:** a title and notes, optionally a date ("Build endurance"). Nothing else.

**Priority.** Every goal is **A** (main goal), **B** (secondary goal, the default) or **C**
(preparation race). A card shows its priority as a badge. At most one **active** goal is the main
goal (A); any number are B or C. Making another goal the main goal is refused with "You already
have a main goal. Change it first.": press **Make secondary** on the current one first. A goal
that is achieved or dropped no longer counts as the main goal for this rule. **C is for races
only**: the form offers it only for a race, and the server refuses it for a threshold or general
goal ("Only a race can be a preparation race."). A preparation race is a race on the way to the
main goal. The coach is told which goals are C, and is asked to plan the race day as a hard
session without a taper and to keep the day before easy; no rule checks that. **Make main goal**
also works on a C race. In the API the priorities are `main`, `secondary` and `preparation`.

**Status.** A goal is **active**, **achieved** or **dropped**. **Mark achieved**, **Drop** and
**Reactivate** change it; nothing is deleted by that. **Delete** removes the goal for good, after a
question. An active race cannot lie in the past: adding one, changing its date or reactivating it
with a past date is refused, while a past race that stays as it is (its title changes, say) is left
alone. Mark it achieved or dropped instead.

**Order and days to go.** Active goals come first, then achieved, then dropped; within each, A
first, then B, then C, then by date (goals without a date last), then by when they were added. Next to
a date the page says how far away it is ("in 12 days", "tomorrow", "today", "3 days ago"). Which
day it is **today** depends on the time zone in your [profile](#athlete-profile); without one (or
with one this server does not know) the page uses UTC, so around midnight the count can be a day
off until you set it.

**How realistic is it?** Every active goal with a target gets a badge: **realistic**, **ambitious**
or **unrealistic**, with a sentence, the numbers behind it and a target that can be reached by the
date. A running race is judged through VDOT (the form of your best time that counts, which grows by
0.2 VDOT a week up to 5), a threshold goal against your current FTP or threshold pace (0.5 % a
week up to 15 %). A race with fewer weeks left than its distance asks for (4 for 5 km, 6 for 10 km,
10 for a half marathon, 16 for a marathon) gets a warning. **Edit** a goal and **Use it** puts the
suggested time or value into the field; nothing is saved until you save, and **your own target
stays yours**: it is a hint and never changes anything. Cycling, swimming and triathlon races, and
goals without a target, a date or a form to start from, say why they cannot be judged. Your coach
is told the judgement in the briefing of the week and of the season. The rules, every number and
what is not judged are in [`docs/goals.md`](docs/goals.md).

**Limits.** At most 30 goals per user (finished ones included), so delete old ones when it is full.
Titles and notes are shown as plain text, never as markup.

Not there yet: training phases.

## Training time

The **Training time** page (`/availability`, also in the navigation) tells PaceForge how much time
you can train. It does not plan anything itself; the [Week plan](#week-plan) checks its sessions
against it. Everything here is personal: every user sees and changes only their own, an
administrator included.

**Per weekday.** Seven fields, Monday first. Enter minutes (`90`) or hours and minutes (`1:30`,
the minutes always with two digits and below 60); at most 24:00 (1440 minutes) per day. A field you
leave empty counts as **no time**, and so does a user who has entered nothing: PaceForge never
assumes that you are free. While you type, the page adds the days up ("Together: 7:30 per week").

**Parts of the day and two sessions.** Under the weekdays, a table with a row for each of them:
tick the parts of the day you can train in (**Morning**, **Afternoon**, **Evening**; at least one
per day, the page says which day has none) and whether **Two sessions** are fine on that day. Until
you say otherwise every day has all three parts open and allows two sessions, so nothing changes for
you before you untick something. Your coach is told, and the checks of every plan hold to it: a
session with a time of day only in a part you left open, a second session only on a day that allows
two, never a third, never two hard sessions on one day, and where a day has two running, cycling or
swimming sessions with a time of day each the harder one comes first (a warning). A session without
a time of day is not held to the parts of the day. Unticking a part or a day does not move sessions
of drafts you already have: they show an error until you change them (see **Changing a plan by
hand**).

**Your week.** Four optional wishes, each with "No wish" or an empty field as the default:
**Days a week you want to train on, at most** (1 to 7), **Least you want to train in a week** (in
the form of the budget, `5:00`; it cannot be above your weekly budget, and the page says so), and
the **Day of your long run** and the **Day of your long ride**. Your coach is told all four, and
the checks of every plan **warn** (they never block a plan): more days with a workout than you
wanted, fewer minutes than your least (as far as your days and budget allow it at all: a week that
offers 200 minutes is not blamed for not reaching 300), and the longest run or ride of the week on
another day than the one you chose (when the longest are tied, one on your day is enough; nothing
is said when the week has no run or ride, or when your long day is a day of absence or has no
time).

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
headed, not where it starts. It is **your word and your responsibility**: 120 % of a normal week
(the warning limit of the level "normal", see **Intensity**) is a big first week after a long
break, so enter what you really want to build up to. An operator who
wants more care can lower `TYPICAL_VOLUME_PERCENT` in `backend/planning/rules.py` (100 counts the
whole week, 70 would count 70 % of it).

**Sports and stretching.** Tick the sports you want in your plan: **Running**, **Cycling**,
**Swimming** and **Strength / gym** (at least one; if you never chose, all four count). Your coach
plans only those, and the checks refuse a workout in any other sport. **Add stretching to sessions**
lets the coach add a few minutes of stretching to a session: it is never a session of its own, it
uses up none of your minutes and it does not count as a training day. Off is the default.

**What each sport is for.** Above the sport boxes, a table with a row per sport: a **Role**
(**Goal sport**, **Secondary sport** or **Supplementary**, or no role) and how many sessions a week
you want of it, the **least** and the **most** (whole numbers from 0 to 14; either may stay empty).
The coach is told and uses the roles to decide what to plan first and what to cut first when time
is short; nothing checks a role. A week with fewer sessions of a sport than your least, or more
than your most, gets a **warning** on the [Week plan](#week-plan) page (a sport you said nothing
about is never looked at). Below the table, **What strength training is for** (**Legs**,
**Core**, **Upper body**, **Full body**, or not said). A strength session that trains the legs
gets a **warning** on the day before your longest run of the week or before a hard run. A session
**with exercises** trains the legs if one of its exercises is for the legs or the whole body,
whatever the focus; a session **without** exercises (an older plan, or one that was changed) does
if the focus is **Legs** or **Full body**.

**Intensity.** How hard your plans may be: **Relaxed**, **Normal** (the default) or **Intensive**.
The level sets the limits that the checks of every plan use, and the coach is told them:

| Level | Hard days a week, at most | Warning above | Error above | Easy share, at least |
| --- | --- | --- | --- | --- |
| Relaxed | 1 | 115 % | 130 % | 85 % |
| Normal | 2 | 120 % | 140 % | 80 % |
| Intensive | 3 | 130 % | 150 % | 75 % |

A day is hard if it has a workout with the goal threshold or VO2max or in zone 4 or above, on any
sport. The two percentages are the planned minutes of a week against your usual week: the average
of your last four weeks, or **A normal week** if that is more. Above the warning limit the plan gets
a warning, above the error limit an error, and a plan with an error cannot be confirmed. The easy
share counts the minutes of running, cycling and swimming (not strength) that are easy (zone 2 or
below, or no zone without a hard goal; intervals count part by part); less than the share is a
warning. The stories behind the levels ask for 5, 8 or 10 % more a
week; a steady rise of that size ends at about 113, 121 or 126 % of the four weeks before, which the
warning limits round. **Intensive** has the limits that applied to everyone before there were
levels.

Under **Your own limits** each of the four can be given a value of its own (hard days 0 to 4,
warning 100 to 200 %, error 100 to 300 %, easy share 50 to 100 %); an empty field keeps the value of
the level, and each field shows that value while it is empty. The warning limit must stay below the
error limit, also when only one of them is your own. A change applies from the next check: to the
next draft, to the checks while you change a plan by hand and when you confirm one, so a draft with
three hard days can be confirmed after switching to **Intensive**. Plans that are already confirmed
are not checked again.

**Before levels existed** every athlete had the limits of **Intensive**. Everyone now starts with
**Normal**, which allows one hard day less and warns from 120 % instead of 130 %: a stored draft
with three hard days shows an error until you pick **Intensive** or give your own number of hard
days.

**Limitations.** Free text of up to 1000 characters ("no running on consecutive days"). It is kept
and shown as plain text, never as markup, and nothing interprets it. **By default it is not sent
to the coach:** it is free text about your body. Tick **Send this text to my AI coach** to change
that. The page then says where it goes (your provider and model), and only the **first 150
characters** are sent with every plan request; the coach reads them as information about you and
never as instructions. Writing the text does not switch the box on.

**Fixed appointments (the list).** Below the form, a list for sessions that happen every week at a
fixed time, such as a running club on Tuesday: choose the **day**, the **sport**, the **minutes**
(5 to 600) and, if you want, the **part of the day**, then **Add**. There is no text field, so
there is no name to give. Your AI coach is told every week to plan each one on its day, as the
date, the sport, the minutes and the part of the day, nothing else. A plan without one of them
(no workout of that sport on that day, in that part of the day if you named one) gets the warning
"…has no … workout…" on the [Week plan](#week-plan) page; you can still confirm it. Nothing is said
for a day of vacation or illness or a day without time. The minutes are not checked against the
workout. **Delete** removes an entry after a question; to change one, delete it and add it again
(the API can change it). You can have at most 14 entries. They repeat every week: a session on one
date only belongs to "Not available" (below) or to the wishes for a week.

**Injuries and limitations (the list).** Below the form, a list for what the plan should take care
of: choose **where** (foot, ankle, Achilles tendon, calf, shin, knee, thigh, hip, back, shoulder or
other) and tick the **sports it affects** (none ticked: no particular sport), then **Add**. There
is no text field on an entry. A **current** entry goes to your AI coach with every plan request,
as the body part and the sports, nothing else (the newest 10; the coach is told if there are
more), and the page names the provider it goes to. A session in an affected sport gets the
warning "…your … limitation affects …" on the [Week plan](#week-plan) page: you can still confirm
the plan. **Mark as healed** keeps an entry as a record without sending or checking it any more,
**Current again** brings it back, and **Delete** removes it after a question. You can have at most
50 entries. These entries are sent to your provider as soon as they are current, as decided for
health data: your own instance, your own provider, your own choice of what to enter.

**Save** sends the weekdays, the parts of the day and two sessions, the budget, the normal week,
the sports, the stretching choice, the wishes for a week, the intensity with your own limits, the
limitations text and whether it may go to the coach together (the lists of fixed appointments and of injuries save on their own). The page checks
the limits
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

The API is `GET` and `PATCH` on `/api/availability/` (`weekdays` Monday first, `double_days` and `time_windows` per weekday,
`weekly_budget_minutes`, `min_weekly_minutes`, `training_days`, `long_run_day`, `long_ride_day`,
`typical_weekly_minutes`, `sport_preferences`, `strength_focus`, `sports`, `stretching`,
`limitations`,
`share_limitations_text`,
`intensity_level`, the own limits `max_hard_days`, `progression_warning_percent`,
`progression_error_percent` and `easy_share_percent`, and the read-only `level_limits` of every
level; `null` removes a number) and
`/api/availability/periods/`, `/api/availability/limitations/` and
`/api/availability/fixed-sessions/` (`weekday` 0 for Monday to 6, `sport`, `minutes`, `slot` or
`null`), each with list, create, read, change and delete.

Not there yet: time windows within a day, and different time per sport.

## Season

The **Season** page (`/season`, also in the navigation) shows the skeleton of your season: one row
for every week from this week to the week of your last **A or B race**, with the **phase** of the
week (base, build, specific, taper), the minutes to aim for, the minutes the week offers and the
races. It is the frame that your coach fills with the main plan (see [below](#filling-the-season-with-your-coach)); the [week plan](#week-plan) follows it.

It is **worked out by the code, not by a coach**, every time you open the page, from your goals,
your last four weeks of training (or your normal week, if that is more), your training time and
your intensity level. Nothing is saved, so a change of a goal, of your time or of a vacation shows
the next time you look. The numbers are a starting point, not coaching science.

- **Phases** are counted back from the main race (your A race, else your latest B race): first the
  taper, then the specific phase, the build and the base. A short preparation loses its base first,
  never its taper. The taper takes one, two or three weeks by the distance of the race.
- **Recovery weeks** come every third week with the level **Relaxed** and every fourth with
  **Normal** and **Intensive**, at about two thirds of the week before; never in the taper.
- **Volume** starts at your reference week and adds 5, 8 or 10 percent a week by the level in the
  base and the build; the specific phase holds it. No week aims for more than it offers: a week of
  vacation aims for nothing.
- **More than one race:** a B race before the main race gets a short taper of its own, a B race
  after it gets a rest week and a build of its own, a C race is only marked.
- **Without a race** (or without a date) the page shows a rolling skeleton of twelve weeks of base
  and build, and says what to add. A race more than a year away cuts the skeleton off after 52
  weeks.

### Filling the season with your coach

The skeleton is only the frame. With an [AI provider](#ai-coach-bring-your-own-key) set up your own
coach **fills the weeks**: for every week the minutes of each sport, a focus, up to three key
sessions (a long run, a threshold session, the race …) and a reason. The model that does it is the
**model for the season plan** if you gave one, else your normal model.

- **What the coach is told:** the skeleton, your races (the title cut to 60 characters, as data and
  never as instructions), your sports and their roles, the strength focus, your age (not your birth
  year), your best times and VDOT, your limits and your current limitations (a body part and the
  sports, no text) and your recent training. **Not** your name, e-mail address, the notes of your
  goals, your activities or the free text about your limitations.
- **What is checked:** the plan must have exactly the weeks of the skeleton, in their order. The
  minutes of a week add up to its target, give or take ten percent, and never to more than the
  week offers (a week of vacation has none). Only the sports you ticked, key sessions only in a
  sport that has minutes that week and not longer than those minutes. A week with a race should have
  a key session for it (a warning).
- **Up to three answers:** if the answer cannot be read or breaks a rule, the coach is told what was
  wrong (fixed texts, never its own words) and tries again, three answers at most. The best one is
  kept; a plan with errors is still saved as a draft, so you see what is wrong, but it cannot be
  confirmed. **This costs several times what a week does**, and up to three calls; the limit is 3
  requests a minute.
- **Versions:** every drafting is a new version. A draft can be **confirmed** (it replaces the
  confirmed version, which stays as **superseded**) or **discarded**. A confirmed plan is never
  changed. A plan keeps the skeleton and the sports it was made for, so it stays readable and is
  checked against them when goals, time or the week move on; it is **not updated** by that.
- **Restoring:** a version that was **replaced or discarded** can be brought back with **Make this
  the new draft**. That copies it as the next version, a draft (its reason says "Restored from
  version N"), with the skeleton and the sports it was made for; the old version is not touched
  and the confirmed one stays confirmed until you confirm the copy. It is checked like any draft
  and may have errors if it has any. A draft and the confirmed version cannot be restored. It
  costs nothing: no coach is asked.
- **Changing a version on request:** under a confirmed version or a draft the page has **Ask for a
  change**: you write what should be different ("less cycling in January", at most 500
  characters, plain text) and your coach turns that version into a **new draft**. It keeps the
  weeks, the skeleton and the sports of the version it comes from, is asked like a draft (up to
  three answers, the same checks, the same cost, 3 requests a minute together with drafting) and
  is told your wish as data, never as an instruction about the rules or its task. Your wish is
  stored with the new version and shown with it. Under the draft the page shows **what changed**
  since the version it was made from, week by week: the minutes of each sport, the focus, key
  sessions added or dropped and a rewritten reason, and how many weeks are the same. That is the
  safeguard when the coach changes more than you asked; the old version stays as it is and the
  confirmed one stays confirmed until you confirm the new draft. If the coach gives the season
  back as it was, nothing is stored. A version that was replaced or discarded is restored first.
- **On the page:** under the skeleton note the page shows your versions (the confirmed one, else
  the newest draft, opens on its own) and, for the one that is open, three more columns: the
  **plan** (minutes of each sport and the total), the **focus** and the **key sessions**, with the
  coach's reason under each week and its rationale above. The weeks are those of the skeleton the
  version was made for; the page says so when today's skeleton has other weeks. **Draft the season
  with my coach** (or **Draft a new version**) asks for a draft, and says before that what it
  costs and that it takes a few minutes. A draft is shown with what the checks say, in order of
  the week; **Confirm plan** is disabled while it has errors and says why, **Discard** always
  works. Without an AI provider the page points to the Connections page. The coach's texts are
  shown as text, never as markup.
- **Timeline and chart:** above the table the page draws the season. The **timeline** has a cell
  for every week, coloured and lettered by phase (Ba base, Bu build, Sp specific, Ta taper, Tr
  transition), an R for a recovery week, the letter of every race (A, B, C) and an outline round
  the current week; the full text of a cell (week, phase, races with their titles) is its tooltip.
  The **chart** shows the minutes of every week as a stacked bar, one colour per sport, with hours
  on the axis: the plan of the open version, or, without one, the aim of the skeleton in one
  colour. For the **confirmed** plan and the weeks that have begun a narrower bar beside the plan
  shows what you actually trained, in the same colours, and the table has a **Done** column. Done
  minutes come from your activities: the timer time (else the elapsed time), added up per week
  (Monday to Sunday in your time zone) and sport, activities of no sport of the plan as *Other*;
  the current week counts with what is done so far. Every bar has its numbers as text and the
  table has all of them; the page scrolls sideways on a narrow screen. There is no load measure
  yet, only minutes.
- **The week plan follows the confirmed plan:** a week that lies in the **confirmed** season plan
  (never a draft) is told to the coach with its phase, minutes of each sport, focus, key sessions
  and reason, and the Week plan page shows the same above the versions. See
  [Week plan](#week-plan) for what is checked.
- **Not there yet:** Whether a model fills a whole year well within
  `SEASON_MAX_TOKENS` has not been tried against a real provider.

Every number and the rules are in [`docs/season.md`](docs/season.md). The API is `GET /api/season/`
for the skeleton and, for the filled plans, `GET /api/season/plans/` (the versions),
`POST /api/season/plans/generate/` (draft one), `GET /api/season/plans/<id>/` and
`POST /api/season/plans/<id>/confirm/` and `…/discard/`. Errors have a fixed text and a `code`:
`not_configured`, `no_time`, `not_usable` (with the `problems`), `not_found`, `not_a_draft`,
`not_confirmable` (with the `findings`), and the codes of a provider that did not answer.

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

**The season plan.** If you have a **confirmed** [season plan](#filling-the-season-with-your-coach)
and the week lies in it, the page shows a box above the versions: the phase (and whether it is a
recovery week), the minutes of each sport, the focus, the key sessions and the coach's reason for
the week. The coach is told the same when it drafts the week and plans the week as a part of that
season. It is a **plan and no rule**: the checks only **warn** when the minutes are more than 15
percent away from the season week, when a sport it has minutes for is missing, or when a key
session (tempo, threshold, VO2max, long or strength) has no workout of its own. You can still
confirm the week. Drafts, replaced and discarded season plans are never used, and neither is a
season plan for weeks it does not contain. A season week above what your progression limit allows
can give both that warning and the one about the progression; the limit of your intensity level
is the one that counts.

**Zones as numbers.** Next to a zone the page shows what it means for you today, for example
"Power zone 2 · 138–188 W", worked out from your thresholds (see
[Athlete profile](#athlete-profile)). Without the threshold for a zone the page shows only the zone.

**Two sessions a day.** A day may have two sessions, never three, for example an easy run in the
morning and a ride in the afternoon. A weekday you did not allow two sessions on (see **Training
time**) has one. Each of them has a time of day (**morning**, **afternoon** or
**evening**) shown next to it; no two sessions of a day share one, and a day with several sessions
should name a time for each (the checks say so). The time you have is still given **per day**: the
coach splits it over the day, and knows from the Training time page in which parts of the day you
can train. Stretching
comes as "+ 10 min stretching" under a session, only if you switched it on, and never as a session.

**Strength sessions and their exercises.** The coach lists the exercises of every strength session
in the order you do them: a name of its own ("Goblet squat"), the sets and the repetitions or, for
a hold such as a plank, the seconds, and if it likes the RPE and the rest between sets. Next to the
name every exercise says what it trains (legs, core, upper body, full body) and what it needs (gym,
dumbbells, body weight). The coach chooses them for your **strength focus**, your **experience**
and your **equipment** (see the athlete page: *Bodyweight only*, *Dumbbells*, *Gym*). The checks
**warn** about an exercise that needs a gym or dumbbells which you did not list (a gym provides
dumbbells too; body weight always fits; nothing is said if you listed no equipment), and refuse
exercises on a session that is not strength. They never judge the name. A workout form keeps the
exercises when you change the session and drops them if you make it another sport; there is no way
to change a single exercise by hand yet. Older plans have none.

**Changing a plan by hand.** **Change this plan** (on a draft and on a confirmed plan) opens an
editor in place of the plan. Change a workout (day, time of day, sport, goal, title, duration,
target zone, stretching, notes), **move** it by changing its day and its time of day (there is no
drag and drop), **remove** it or **add** one. After every change the page asks the server to run
the checks, which stores nothing, and shows what they say at the workout they name; while it asks,
no finding is shown. A workout with an interval structure keeps it, and its duration follows it,
unless you tick *Remove the interval structure*. **Save as a new version** stores the plan as a new
**draft** (its reason is "Changed by hand") made from the version you started from, which stays as
it is: a confirmed plan is never changed. A plan with errors can be saved too; it only cannot be
confirmed. **Discard changes** drops everything: nothing is stored before you save. Nothing else on
the page can be started while the editor is open. Like drafting, changing is for the weeks that
can be planned.

**Restoring a version.** A version that was replaced or discarded has **Make this the new draft**.
It is copied as the next version of the week, a draft (its reason is "Restored from version N"),
and checked again with what you can do now, so it may have errors that the old version did not.
Nothing is changed or sent before you confirm it.

**What a change does to the rest.** A workout keeps its identity (its *lineage*) from version to
version when a version is made from another one by changing or restoring it; a workout that the
coach drafted anew has a new one. So when you confirm and [send](#sending-to-intervalsicu) a
changed week, a workout you moved or changed **updates its event** in your calendar, one you
removed is deleted from it and one you added is created. And what you said about a workout in the
[Week review](#week-review) (its activity, none, its status) moves with it to the new version when
that is confirmed.

**After a break.** If the plans look too small, enter **A normal week** on the
[Training time](#training-time) page: the limit for how far a week may rise then follows what you
are used to and not only the last four weeks. If they look too hard or too easy, choose another
**Intensity** there.

**No time.** If the week offers no training time at all (nothing on any day, a weekly budget of 0,
or away the whole week), the page says "You have no training time for this week." with a link to
the Training time page. Nothing is sent to your provider then, so it costs nothing.

The coach is told only a fixed set of facts: the week and today, the minutes you can train on each
day and your absences, your weekly budget, your zone tables, the sports you ticked and whether
stretching is allowed, your active goals (title and notes), the minutes you trained in the last
four weeks, your normal week if you gave one, your current injuries (a body part and the sports it
affects, no text), a summary of last week's confirmed plan and how that week went (see [Week
review](#week-review)). **Not** your name, e-mail address, activities' names or anything of other
users, and the free text about your limitations only if you switched on **Send this text to my AI
coach** (then its first 150 characters). A goal's title and notes (and the limitations text, if you allow it) are free text, and a model can
be influenced by text; whatever it answers still has to pass the strict reading and the checks before it is a draft,
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
page (changing and restoring included) with test doubles for the API; none of it has been tried
against a real provider or in a browser by the developer. Your first real draft is the first real test; please read it critically.

### Sending to Intervals.icu

With [Intervals.icu connected](#connections) a confirmed week can be sent to your calendar. It
never happens by itself: press **Send to Intervals.icu** on a confirmed plan, or tick **Send the
week to Intervals.icu right away** before you confirm. If sending does not work, the plan stays
confirmed and the page says why.

- **What arrives:** one workout in your calendar for each workout of the plan, with its steps, the
  targets in watts, beats per minute or minutes per kilometre (worked out from your thresholds at
  the moment of sending), the time of day as start time (**morning** 07:00, **afternoon** 12:00,
  **evening** 18:00, otherwise all day), strength (with its exercises, one numbered line each, for
  example "1. Goblet squat: 3 sets of 10, RPE 7, rest 1:30") and stretching as text. Intervals.icu passes the
  workouts on to the devices and services you connected there (Zwift, COROS, Garmin …).
- **Sending again** updates the same workouts and never adds them twice. A version made from
  another by [changing or restoring it](#week-plan) updates the events of the workouts it keeps,
  also a moved one, and deletes those of workouts that were taken out. A version that the coach
  drafted anew replaces the workouts of the version before in your calendar.
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

## Week review

The **Week review** page (`/review`, in the navigation) shows how a week went against the plan you
confirmed. It reads the plan and what you did; it never changes the plan. Choose the **week**: the
current week and the four before it can be reviewed (`REVIEW_WEEKS` in
`backend/reviews/services.py`), and the page starts with the latest of them that has a confirmed
plan. A week is a calendar week, Monday to Sunday, on the clock of the time zone of your
[profile](#athlete-profile) (UTC without one), so a session just after midnight belongs to the day
you lived it. A week without a confirmed plan shows what you did and a link to the plan page.

**Which activity belongs to which workout.** PaceForge matches them by itself:

- An activity belongs to the workout of the **same day and the same sport**. Several of one sport on
  a day pair up in order: the workouts by their time of day, the activities by their start.
- A workout on a day that is over and still without an activity takes one that is left over on its
  day, whatever its sport: it was **replaced**.
- An activity belongs to **one workout at most**. What is left over is listed under *Not planned*.

**How a workout went.** Every workout has one status:

| Status       | When                                                                     |
| ------------ | ------------------------------------------------------------------------ |
| **Done**     | an activity of its sport with at least 75 % of the planned minutes       |
| **Partial**  | an activity of its sport with less than that                             |
| **Replaced** | an activity of another sport                                             |
| **Missed**   | no activity, and its day is over                                         |
| **Open**     | no activity, and its day is not over yet (it cannot be chosen by hand)   |

The 75 % is `PARTIAL_BELOW_PERCENT` in `backend/reviews/matching.py`. An activity without a duration
counts as done: a shortfall is not guessed. The page counts the statuses and says how many of the
workouts that are not open are done ("1 of 2 workouts done (50 %)").

**Correct it.** Under *Change what belongs to this workout* you can choose an activity of the week
for the workout, say that **no activity** belongs to it, or leave it to the automatic match, and
set the status by hand. Setting **Done**, **Partial** or **Replaced** needs an activity; **Missed**
frees the workout of its activity, which a later workout of the day can then take. An activity can
be assigned by hand to one workout only; to move it, free it there first. Saving with everything
empty goes back to the automatic match. What you set is kept beside the plan, because a confirmed
plan is never changed; when a changed version of the week is confirmed, your corrections move to
the workouts that are the same training (see [Week plan](#week-plan)).

**Rate a session.** Every activity of the week, planned or not and imported or entered by hand, has
*Rate this session*: how hard it felt (1 to 10, [RPE](#sessions-entered-by-hand)) and a note of up
to 500 characters. You can change or clear it at any time. The load follows the rating (minutes
times RPE, in AU; it is not TSS).

**How the week felt.** Tiredness, motivation and pain, each from 1 to 5, and a note of up to 500
characters. There is one feedback per week; saving replaces it, and saving with nothing in it
removes it.

**Planned and done.** A table per sport and for the week: the planned workouts and minutes, the
activities done and their minutes (every activity of the week counts, planned or not), and the sum
of the loads of the rated sessions, with "(1 of 2 rated)" where not every session is rated. There is
no planned load, because workouts have none yet.

**Ask the coach.** At the bottom of the page, *What your coach says* has the button **Ask the
coach** (**Ask again** once there is a comment). It asks your own
[AI provider](#ai-coach-bring-your-own-key) to look back on the week and brings back a **comment**
of up to 600 characters (`COMMENT_MAX` in `backend/reviews/models.py`) and a **recommendation** for
the next week: *increase the volume a little*, *keep the volume about the same* or *reduce the
volume*. The comment is kept with the week; asking again replaces it, and a try that fails leaves
the old one where it is. Any week of the list can be asked about, also the one that is running (the
coach is then told that the open workouts are not over). A week with no confirmed plan, no activity
and no feedback has nothing to look back on: nothing is sent then, so it costs nothing.

**What the coach is told.** Numbers and fixed words only (`backend/reviews/briefing.py`): for each
workout its day, sport, goal, planned minutes, status, the minutes done and the RPE; the sessions
that were not planned (at most `MAX_UNPLANNED`, the rest is only counted); planned and done per
sport and for the week; the statuses and the share done; and the three scales of the feedback.
**Not** your notes (of a session or of the week), the titles and notes of workouts, names, e-mail
addresses or ids: there is no free text in it at all. The comment is the coach's own text; it is
shown as text, and it is **never sent back** to the coach, not even when it plans the next week.

**The effect on the next week.** When your coach drafts a [week plan](#week-plan), it is told how
the week before went (`previous_week_review`): the workouts by status, the minutes planned and
done, the mean RPE, the three scales and the recommendation of your review of that week, if you
asked for one. That is advice, not a rule: the checks of the plan stay as they are, and nothing is
confirmed without you. The figures are worked out when the plan is drafted, so a correction or a
rating you make later is in the next draft without asking the coach again.

**Cost and limit.** Every request goes to your provider with your key and is **billed to you**: a
comment costs one request, or two if the coach had to correct its answer. They are counted in the
usage overview of the AI coach (the purpose "week review" is stored with each record). Asking is
limited to 5 a minute per user, with a counter of its own. Like drafting, it waits for the provider
inside the request, so the timeouts named under [Week plan](#week-plan) apply.

The API (all of it needs a signed-in user, and what you send replaces what was there; a field that
is not part of a form is refused):

| Request                                            | What it does                                              |
| -------------------------------------------------- | --------------------------------------------------------- |
| `GET /api/reviews/weeks/`                          | the weeks that can be reviewed                            |
| `GET /api/reviews/weeks/<Monday>/`                 | one week: plan, match, activities, comparison, feedback, comment |
| `PUT /api/reviews/weeks/<Monday>/workouts/<id>/`   | `activity`, `no_activity`, `status` of one workout        |
| `PUT /api/reviews/weeks/<Monday>/feedback/`        | `fatigue`, `motivation`, `pain`, `notes` of the week      |
| `POST /api/reviews/weeks/<Monday>/comment/`        | asks the coach to comment on the week (`201`)             |
| `PATCH /api/activities/<id>/`                      | `rpe` and `notes` of an activity (nothing else changes)  |

The two `PUT`s and the `POST` answer with the whole week as the `GET` shows it.

**Not verified yet.** The page is tested with test doubles for the API, the endpoints against a
test database and the comment with a provider that answers from a script; it has not been used in a
browser by the developer, and the comment has not been tried against a real provider. Your first
real comment is the first real test; please read it critically.

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
uv run pytest -n auto   # in parallel, one test database per core; plain `uv run pytest` is serial

# frontend
cd frontend
npm run format:check && npm run lint
npx ng test --no-watch
npx ng build
```

The backend tests create and drop their own `test_*` database next to the development one (with
`-n auto` one per worker, `test_*_gw0`, `test_*_gw1`, …). They hash passwords quickly, not with
Argon2; the tests that check the production hashers set them themselves.

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
- **An import says "The file is neither a FIT, a TCX nor a GPX file".** The file is a zip
  archive, a format of another kind or something else. Unpack it (a `.gz` file is read as it is), or
  export FIT, TCX or GPX instead.
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
