# Backup and restore

PaceForge can copy its whole database into one encrypted file. This guide covers what a backup
holds, where the two keys live, how backups run and how long they are kept, how to copy them away
from the server, and how to restore one into an empty database.

A backup holds every user's data: accounts, profiles, activities with their GPS tracks, plans,
reviews and chat. Treat backup files like the database itself.

## What is backed up

- **The whole database,** in one `pg_dump` snapshot. It is consistent as of the moment the dump
  starts.
- **The secrets, still encrypted.** The Intervals.icu key, the AI provider keys and the
  two-factor secrets are stored encrypted with `ENCRYPTION_KEY`. The backup keeps them in that
  form. A backup does not reveal them, and restoring it does not give them back without
  `ENCRYPTION_KEY`.
- **Not in a backup:** `.env`, either key, the Docker images, and the TLS certificates in the
  `caddy_data` volume. Caddy gets new certificates on its own.

The file is named after the UTC time it was made, for example
`paceforge-20261120-031500Z.pgdump.enc`.

**How it is encrypted.** `pg_dump` writes into a pipe, and the pipe feeds the encryption, so the
plain dump never touches the disk. The output is AES-256-GCM in chunks, with `BACKUP_ENCRYPTION_KEY`.
Each chunk is checked on restore, and any change, a missing end or a reordered chunk is refused.
The file is written with mode `0600`, and it appears under its final name only when it is complete.

## Two keys, stored apart

PaceForge uses two different keys. They protect different things.

| Key | What it protects | If it is lost |
| --- | --- | --- |
| `ENCRYPTION_KEY` | The secrets stored in the database (Intervals.icu key, AI keys, two-factor secrets) | The stored secrets cannot be read. Users connect again and set up two-factor authentication again. |
| `BACKUP_ENCRYPTION_KEY` | The backup files | No backup file can be opened. |

Rules for both keys:

- **Keep each key in a password manager or another secret store,** in at least two places.
- **Never keep a key next to the backups:** not on the same disk, not in the same bucket, not in
  the same folder, not in the same mail.
- **Never copy a key off-site with a backup.** Off-site copies hold only encrypted backup files.
- **Keep the two keys apart from each other.** The instance refuses to start when a backup key
  equals `ENCRYPTION_KEY` (check `core.E007`).
- **Generate each key once, with its own command.** The command is in
  [docs/deployment.md](deployment.md#1-configure-env-and-generate-keys). Use it for
  `BACKUP_ENCRYPTION_KEY` too, and do not reuse the output for `ENCRYPTION_KEY`.

Whoever holds a backup file and `BACKUP_ENCRYPTION_KEY` can read all the data in it, except the
secrets. Those also need `ENCRYPTION_KEY`. Keep that in mind when you decide where each key goes.

### Rotating `BACKUP_ENCRYPTION_KEY`

`BACKUP_ENCRYPTION_KEY` takes several keys separated by commas. The first one encrypts new
backups. All of them open old backups.

1. Generate a new key.
2. In `.env`, put the new key first and keep the old one after it: `BACKUP_ENCRYPTION_KEY=<new>,<old>`.
3. Recreate the scheduled backup service so it reads the new value:

   ```sh
   docker compose -f compose.prod.yaml --profile backup up -d backup
   ```

4. Make one backup by hand and check that it is written (see [Manual backups](#manual-backups)).
5. Keep the old key for as long as a backup made with it is still kept. When the last one is
   deleted by retention, remove the old key from the list.

### Rotating `ENCRYPTION_KEY`

Follow the rotation steps of the [Instance key](../README.md#instance-key) section in the README:
`ENCRYPTION_KEY=<new>,<old>`. There is
no command yet that re-encrypts old values, so keep the old key in the list. When you restore a
backup, use the `ENCRYPTION_KEY` list that was in use when the backup was made, or a list that
still contains that key.

## Manual backups

Each command runs `pg_dump`, encrypts the result into the backup folder and then deletes backups
that retention no longer keeps. Each prints one line: the file name, its size and how many files
were removed.

**Production.** The `backup` service has the backup volume. It needs the `db` container to run and
`BACKUP_ENCRYPTION_KEY` in `.env`:

```sh
docker compose -f compose.prod.yaml --profile backup run --rm --no-deps backup python manage.py backup_db
```

The files are in the volume `paceforge_backups`, which is mounted at `/backups` in that service.

**Local development.** Install `pg_dump` for PostgreSQL 17 on your machine, for example the package
`postgresql-client-17`. Then, with `db` running and `BACKUP_ENCRYPTION_KEY` in the `.env` file in
the repository root:

```sh
cd backend
uv run python manage.py backup_db
```

Files go to `backups/` in the repository root. That folder is git-ignored.

**Options.** `backup_db` accepts these, and each one overrides a setting for that run:

| Option | Meaning |
| --- | --- |
| `--output-dir <path>` | Folder for the backup (default `BACKUP_DIR`). |
| `--key-file <path>` | Read the key(s) from a file instead of `BACKUP_ENCRYPTION_KEY`. The file holds keys separated by commas or line breaks. Keep it outside the repository and make it readable by you only (`chmod 600`). |
| `--keep-daily <n>` | Days to keep (default `BACKUP_KEEP_DAILY`). |
| `--keep-weekly <n>` | Weeks to keep (default `BACKUP_KEEP_WEEKLY`). |
| `--no-prune` | Do not delete anything. |

## Scheduled backups

The `backup` service in `compose.prod.yaml` runs `run_backups`. It makes a backup when it starts,
then one every `BACKUP_INTERVAL_HOURS` hours (default `24`). It is **off by default**. To turn it on:

1. Set `BACKUP_ENCRYPTION_KEY` in `.env`.
2. Start it, either with `--profile backup` on each command or by adding `COMPOSE_PROFILES=backup`
   to `.env`:

   ```sh
   docker compose -f compose.prod.yaml --profile backup up -d backup
   ```

3. Read the log after the first start. A failed round is written there and the service waits for
   the interval before it tries again.

   ```sh
   docker compose -f compose.prod.yaml --profile backup logs backup
   ```

   A missing key shows as `No backup key found`. Fix the key and recreate the service.

**Local development.** `uv run python manage.py run_backups` runs the loop in the foreground.
`uv run python manage.py run_backups --once` makes one backup and stops, with an error exit code
if it fails.

**What a backup can lose.** Everything written after the last successful backup is not in it. With
the default interval that can be up to a day of data.

## Retention

After each successful backup, PaceForge keeps:

- the newest backup of each of the latest `BACKUP_KEEP_DAILY` UTC days that have a backup, and
- the newest backup of each of the latest `BACKUP_KEEP_WEEKLY` ISO weeks that have a backup.

Every other PaceForge backup in the folder is deleted. With the defaults that is about seven daily
and four weekly files. Other files in the folder are never touched. If a backup fails, nothing is
deleted.

| Variable | Default | Allowed | Meaning |
| --- | --- | --- | --- |
| `BACKUP_INTERVAL_HOURS` | `24` | `1` to `168` | Hours between two scheduled backups. |
| `BACKUP_KEEP_DAILY` | `7` | `1` to `365` | Days to keep, newest backup of each day. |
| `BACKUP_KEEP_WEEKLY` | `4` | `0` to `104` | Weeks to keep, newest backup of each week. `0` keeps no weekly ones. |
| `BACKUP_DIR` | `backups/` in the repository root | any folder | Where backups are written. In `compose.prod.yaml` it is `/backups` in the volume. |

Retention on one disk does not protect against losing that disk. Copy backups off the server too.

## Copying backups off-site

PaceForge does not upload anything. You copy the files yourself, with the tool you trust, for
example `rsync`, `rclone` or your provider's storage client.

1. Copy only the backup files, named `paceforge-*.pgdump.enc`. Skip any `.paceforge-*.tmp` file: it is
   an unfinished backup.

   ```sh
   docker compose -f compose.prod.yaml --profile backup cp backup:/backups/. ./offsite/
   ```

2. Do **not** copy `.env`, the keys, the `caddy_data` volume or anything else from the server.
3. Check, from time to time, that the copy can be restored. See [Restore drills](#restore-drills).

Anyone who gets a backup file learns the data it holds, minus the secrets, which need
`ENCRYPTION_KEY`. Pick storage you trust with that.

## Restoring into an empty database

`restore_db` writes a backup into a database and refuses any database that already has tables in
its `public` schema. The restore runs in one transaction. A wrong key, a damaged file or an error
during the restore leaves the database empty.

**Before you start:**

- You have the backup file.
- You have `BACKUP_ENCRYPTION_KEY`, the key that opens the file. If it was rotated, the list must
  still contain the key that made the backup.
- You have `ENCRYPTION_KEY`, with the same rule. Without it the restored secrets cannot be used.
- The PaceForge version is the same as the one that made the backup, or a newer one. Migrations run
  on start, so newer code can bring an older database up to date. Older code cannot.

`--allow-non-empty` restores over a database that has tables. It drops and replaces the objects
first. Use it only when you know what it will replace, and never as the first thing to try.

### Production (`compose.prod.yaml`)

Use this for a new server, or after you have emptied the database of the current server (step B).

**A. New server, or the database is empty.**

1. Set up `.env` as in [docs/deployment.md](deployment.md#1-configure-env-and-generate-keys). Use the
   **same** `ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY` as before. A new `DJANGO_SECRET_KEY` is
   fine: users sign in again.
2. Start only the database. It creates an empty database:

   ```sh
   docker compose -f compose.prod.yaml up -d db
   ```

3. Restore. The command mounts the backup file from the host into the `backend` container. The
   container runs as user `10001`, so that user must be able to read the file. Changing the owner
   keeps the mode at `0600`:

   ```sh
   sudo chown 10001 paceforge-20261120-031500Z.pgdump.enc
   docker compose -f compose.prod.yaml run --rm --no-deps \
     -v "$PWD/paceforge-20261120-031500Z.pgdump.enc:/restore/backup.pgdump.enc:ro" \
     backend python manage.py restore_db /restore/backup.pgdump.enc
   ```

   On the same server you can use the backup volume instead of a file on the host:
   `-v paceforge_backups:/backups:ro` and the file name `/backups/<name>`.

   A success prints `Restored <name>.`

4. Start everything else. The `backend` container runs `migrate` on start, which does nothing when
   the versions match:

   ```sh
   docker compose -f compose.prod.yaml up -d
   docker compose -f compose.prod.yaml ps
   curl -fsS "https://$APP_DOMAIN/api/health/"
   ```

5. Sign in as an administrator with the old password, and enter a code from your authenticator app
   (or a recovery code). Open **Connections**. The Intervals.icu connection should show your
   athlete after **Check connection**. If it says **Needs attention**, the `ENCRYPTION_KEY` in
   `.env` is not the one that made the backup.

**B. Replace the data of a running server.** This deletes the current database. Make a fresh
backup first if the database still works (see [Manual backups](#manual-backups)).

1. Stop the stack. This removes the containers and keeps the volumes:

   ```sh
   docker compose -f compose.prod.yaml --profile backup down
   ```

2. Delete the database volume. The name is the project name plus `_pgdata`:

   ```sh
   docker volume rm paceforge_pgdata
   ```

3. Continue with steps 2 to 5 of **A**.

### Local development (`compose.dev.yaml`)

Use this to check a backup on your machine. It restores into a second database, so your
development data stays as it is.

1. Start the database:

   ```sh
   docker compose -f compose.dev.yaml up -d db mailpit
   ```

2. Create an empty database. Use your `POSTGRES_USER` for `-U` if you changed it:

   ```sh
   docker compose -f compose.dev.yaml exec db createdb -U paceforge paceforge_restore
   ```

3. Restore. Use your `POSTGRES_PASSWORD` in the URL if you changed it:

   ```sh
   cd backend
   uv run python manage.py restore_db ../backups/paceforge-20261120-031500Z.pgdump.enc \
     --database-url postgres://paceforge:paceforge-dev@localhost:5432/paceforge_restore
   ```

   The command prints `Restored <name>.`. Run it again and it refuses, because the database now has
   tables.

4. Check it. Point the shell at the restored database for one command. Variables set in the shell
   win over `.env`. `migrate` should report no migrations to apply:

   ```sh
   DATABASE_URL=postgres://paceforge:paceforge-dev@localhost:5432/paceforge_restore \
     uv run python manage.py migrate
   ```

5. Drop the scratch database when you are done:

   ```sh
   docker compose -f compose.dev.yaml exec db dropdb -U paceforge paceforge_restore
   ```

## Restore drills

A backup that has never been restored is a guess. Restore one on purpose, at least every three
months, and after each change of key or of PaceForge version.

1. Restore the newest off-site copy into an empty database that is not the live one: a second
   server, or the scratch database above.
2. Check that the command ends with `Restored <name>.`
3. Check that the data is there. Compare the number of users and activities with what you expect,
   and open one recent week plan.
4. Check the secrets. On **Connections**, **Check connection** must work for one user. This proves
   that `ENCRYPTION_KEY` and the backup are a matching pair.
5. Write down the date, the file name and the result. Delete the scratch database or server.

## Troubleshooting

- **`No backup key found`.** Set `BACKUP_ENCRYPTION_KEY` in `.env` (or pass `--key-file`) and
  recreate the `backup` service.
- **`A backup key must differ from ENCRYPTION_KEY`.** The same key is in both variables. Generate a
  new `BACKUP_ENCRYPTION_KEY`. Startup check `core.E007` reports this too.
- **`pg_dump could not be started.`** `pg_dump` is not installed on the machine, or not on the
  `PATH`. Install the PostgreSQL 17 client tools. The production image already has them.
- **`pg_dump failed with exit code …`.** The message after it says why. Usual causes: `db` is not
  running, or the database settings are wrong.
- **`The backup is damaged, incomplete or was encrypted with another key.`** Either the key does not
  match the file, or the file is damaged. Try another backup, and check the key list first.
- **`This is not a PaceForge backup.`** The file is not a PaceForge backup. Check the name you
  picked.
- **`The backup file cannot be read.`** The user that runs the command cannot read the file. In
  production, see the `chown` step above.
- **`The target database is not empty.`** You are restoring into a database that has tables. Use an
  empty database (procedure A), or see `--allow-non-empty` above, with care.
- **`The target database cannot be reached.`** Check `DATABASE_URL` and that `db` runs.
