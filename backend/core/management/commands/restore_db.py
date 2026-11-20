from pathlib import Path
from typing import Any

import environ
from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.backup import BackupError, load_backup_keys, restore_backup
from core.backup_crypto import BackupCryptoError


class Command(BaseCommand):
    help = (
        "Restore an encrypted backup file into a database with pg_restore. The backup is "
        "decrypted while it is read and never stored as plaintext. A database that already "
        "has tables is refused unless --allow-non-empty is given."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("backup_file", type=Path)
        parser.add_argument(
            "--database-url",
            default=None,
            help="Target database without a password, for example "
            "postgres://user@host:5432/name. Give the password with --password-file. "
            "Default: DATABASE_URL.",
        )
        parser.add_argument(
            "--password-file",
            type=Path,
            default=None,
            help="File with the password of the --database-url target. Needs --database-url.",
        )
        parser.add_argument(
            "--key-file",
            type=Path,
            default=None,
            help="File with the backup key(s). Default: BACKUP_ENCRYPTION_KEY.",
        )
        parser.add_argument(
            "--allow-non-empty",
            action="store_true",
            help="Restore into a database that has tables and replace the objects in it.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        database = None
        database_url: str | None = options["database_url"]
        password_file: Path | None = options["password_file"]
        if password_file is not None and database_url is None:
            raise CommandError("--password-file needs --database-url.")
        if database_url is not None:
            if not database_url.strip():
                raise CommandError("--database-url must not be empty.")
            try:
                database = environ.Env.db_url_config(database_url)
            except Exception:
                # Do not echo the URL: it holds the password.
                raise CommandError("--database-url is not a valid database URL.") from None
            if not database.get("NAME"):
                raise CommandError("--database-url must name a database.")
            if database.get("PASSWORD"):
                # Arguments show up in process listings and shell history.
                raise CommandError(
                    "--database-url must not contain a password. Use --password-file instead."
                )
            if password_file is not None:
                database["PASSWORD"] = self._read_password(password_file)
        try:
            keys = load_backup_keys(options["key_file"])
            restore_backup(
                options["backup_file"],
                keys,
                database,
                allow_non_empty=options["allow_non_empty"],
            )
        except (BackupError, BackupCryptoError, OSError) as error:
            raise CommandError(str(error)) from None

        self.stdout.write(self.style.SUCCESS(f"Restored {options['backup_file'].name}."))

    @staticmethod
    def _read_password(path: Path) -> str:
        # Never echo the content: it is the password.
        try:
            password = path.read_text(encoding="utf-8")
        except OSError, UnicodeError:
            raise CommandError("The password file cannot be read.") from None
        password = password.removesuffix("\n").removesuffix("\r")
        if not password:
            raise CommandError("The password file is empty.")
        return password
