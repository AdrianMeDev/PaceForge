# Data export and account deletion

Every signed-in user can download a copy of their own data and delete their account. Both are on
the **Security** page (`/settings/security`), in the cards **Your data** and **Delete account**
below the two-factor card. Administrators have them too. This guide describes what the export
holds, what deletion removes and what it leaves alone, and the API behind both.

## Download your data

Open **Security** and use the download in the **Your data** card. The browser saves a file named
`paceforge-export-YYYY-MM-DD.json`; the date is the day on the server.

API: `GET /api/me/export/`. It answers with `application/json` as an attachment and with
`Cache-Control: no-store`. Anonymous requests get `403`.

### What the file holds

The file is UTF-8 JSON with indented lines. Dates and times are ISO 8601 text, and decimal numbers
(such as prices) are text, so no precision is lost.

| Key | Content |
| --- | --- |
| `version` | Format version (`1`). It goes up when a section changes in a way a reader has to know about. |
| `exported_at` | When the export was made. |
| `account` | Email address, display name and the date you joined. |
| `profile` | `athlete` (time zone, data about you, ...), `thresholds` and `best_times`. |
| `availability` | `settings`, `weekdays`, `sport_preferences`, `fixed_sessions`, `unavailable_periods` and `limitations`. |
| `goals` | Your goals. |
| `activities` | Activity summaries (sport, times, distance, heart rate, power, load, ...). |
| `wellness` | Daily sleep, HRV, resting heart rate and weight. |
| `plans.season` | Season plan versions. |
| `plans.weeks` | Week plan versions, each with its `workouts`. |
| `reviews` | `workouts` (your ratings), `week_feedback` and `week_comments`. |
| `chat` | Messages with the coach. |
| `coach` | `provider` (the setup without the key; `has_api_key` says whether a key is stored), `usage` (call counts and tokens, no prompts or answers) and `prices`. |
| `integrations` | Status of your Intervals.icu connection, without the key. |
| `automation` | `settings` (which background jobs are on) and `runs` (their log). |

### What the file leaves out

- Your password and your sign-in sessions.
- Two-factor secrets and recovery codes.
- Your Intervals.icu API key and your AI provider key.
- The uploaded activity files (FIT, TCX, GPX). This includes the GPS tracks. The summaries of the
  activities are in the file.
- Internal technical fields: file hashes, provider activity ids and stored best efforts.
- Data of other users. The file contains only what belongs to the account that asked for it.

## Delete your account

Deletion is permanent. Nothing can be recovered from PaceForge afterwards (see
[Backups](#backups) for the copies that still exist).

### What you confirm

| Check | What is needed | Error if it fails |
| --- | --- | --- |
| Email | The email address of the account, typed again. Upper and lower case and spaces at the ends do not matter. | `confirmation`: "The email does not match this account." |
| Password | Your current password. | `password`: "The password is wrong." |
| Authenticator code | Only when two-factor authentication is on: a current code from your app, or an unused recovery code. Spaces are ignored. A recovery code is used up. | `mfa_code`: "A code from your authenticator app is required." or "The code is not valid." |
| Last administrator | The account must not be the last active administrator. | `409` with `"code": "last_admin"` |

The checks run in this order. If one fails, nothing is deleted.

On the **Security** page, type the email address, enter the password (and the code, if asked), press
the delete button and confirm in the dialog. On success PaceForge signs you out and opens the sign-in
page with a notice.

API: `POST /api/me/delete/` with a JSON body such as
`{"confirmation": "you@example.com", "password": "...", "mfa_code": "123456"}`. The request needs
the CSRF token like every other `POST`. `mfa_code` can be left out when two-factor authentication is
off.

| Status | Meaning |
| --- | --- |
| `204` | The account and its data are deleted, and the session has ended. |
| `400` | One or more fields are wrong. The body names the field, for example `{"password": ["The password is wrong."]}`. |
| `403` | You are not signed in. |
| `409` | `{"detail": ..., "code": "last_admin"}`: the last active administrator cannot be deleted. |
| `429` | Too many requests (see [Limits](#limits)). |

### What is deleted

- Everything the account owns: profile, thresholds, best times, goals, training time, activities
  with their files, wellness, season and week plans, reviews, chat, the AI provider setup with its
  key, usage records and prices, the Intervals.icu connection with its key, automation settings and
  runs, email addresses and the two-factor setup.
- Invitations that the account used, and invitations sent to its email address. Invitations the
  account created for other people stay, but they no longer name a sender.
- Every active session of the account, including the one you deleted from.

### What is not touched

- **Intervals.icu:** PaceForge sends nothing to Intervals.icu. Your activities, wellness data and
  settings stay there, and the API key still works. Revoke the key in Intervals.icu if it should stop
  working. PaceForge cannot do this for you.
- **AI providers:** PaceForge sends nothing to them either. Delete the key at your provider if it
  should stop working.
- **Other users:** their data, their sessions and their invitations are not changed.

### Last administrator

An active administrator cannot delete their account while they are the only active administrator.
The check happens inside the deletion and locks the active administrators, so two administrators
cannot delete themselves at the same moment and leave none behind. Make sure another active
administrator exists before you delete your own account.

## Backups

Deleting an account does not change backups that were made before. Such a backup still holds the
account's data until the backup retention removes it (see [Backup and restore](backup-and-restore.md)).
Restoring an older backup brings the account back with its data, so delete it again after a restore
if it should stay deleted.

## Limits

- Exporting and deleting are each limited to 5 requests per minute per user. The limits do not share
  a counter with the Intervals.icu or AI limits.
- Exceeding a limit answers `429`. Wait a minute and try again.

## For developers

- `backend/accounts/services/export.py`: `build_user_export` builds the file. Every model is read
  through `for_user()`. A new field is exported by default; a new secret must be an encrypted field
  or be listed as excluded.
- `backend/accounts/services/deletion.py`: `delete_account` checks the request and deletes the user.
  The rest is removed by the cascade of the user row.
- `backend/accounts/views.py`: the two endpoints and their error mapping.
- `frontend/src/app/features/security/`: the **Your data** and **Delete account** cards.
