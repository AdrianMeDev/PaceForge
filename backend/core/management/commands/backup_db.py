from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from core.backup import BackupError, create_backup, load_backup_keys, prune_backups
from core.backup_crypto import BackupCryptoError


class Command(BaseCommand):
    help = (
        "Dump the database with pg_dump into an encrypted backup file and remove expired "
        "backups. The dump is encrypted while it is written and never stored as plaintext."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--output-dir", type=Path, default=None, help="Default: BACKUP_DIR.")
        parser.add_argument(
            "--key-file",
            type=Path,
            default=None,
            help="File with the backup key(s). Default: BACKUP_ENCRYPTION_KEY.",
        )
        parser.add_argument(
            "--keep-daily", type=int, default=None, help="Default: BACKUP_KEEP_DAILY."
        )
        parser.add_argument(
            "--keep-weekly", type=int, default=None, help="Default: BACKUP_KEEP_WEEKLY."
        )
        parser.add_argument(
            "--no-prune", action="store_true", help="Do not remove expired backups."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        output_dir: Path = options["output_dir"] or settings.BACKUP_DIR
        keep_daily: int = (
            settings.BACKUP_KEEP_DAILY if options["keep_daily"] is None else options["keep_daily"]
        )
        keep_weekly: int = (
            settings.BACKUP_KEEP_WEEKLY
            if options["keep_weekly"] is None
            else options["keep_weekly"]
        )
        if keep_daily < 1 or keep_weekly < 0:
            raise CommandError("--keep-daily must be at least 1 and --keep-weekly at least 0.")

        try:
            keys = load_backup_keys(options["key_file"])
            path = create_backup(output_dir, keys)
            # Only a successful dump may remove older backups.
            pruned = (
                0
                if options["no_prune"]
                else prune_backups(output_dir, keep_daily, keep_weekly, protect=path)
            )
        except (BackupError, BackupCryptoError, OSError) as error:
            raise CommandError(str(error)) from None

        self.stdout.write(
            self.style.SUCCESS(f"{path.name}  {path.stat().st_size} bytes  pruned {pruned}")
        )
