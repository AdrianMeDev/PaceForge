"""Encrypts the TOTP secrets and recovery-code seeds that earlier versions stored in clear text.

Values that already carry the encryption marker are left alone, so running it twice changes
nothing. Reversing decrypts them again. Both directions need ``ENCRYPTION_KEY``.
"""

from collections.abc import Callable
from typing import Any

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

from core.encryption import PREFIX, decrypt, encrypt

# The fields of an authenticator's data that hold secrets. "migrated_codes" is a list of codes.
SECRET_FIELDS = {"totp": ("secret",), "recovery_codes": ("seed", "migrated_codes")}


def _convert(data: dict[str, Any], fields: tuple[str, ...], applies: Callable[[str], bool],
             convert: Callable[[str], str]) -> bool:
    changed = False
    for field in fields:
        value = data.get(field)
        if isinstance(value, str):
            new: Any = convert(value) if applies(value) else value
        elif isinstance(value, list):
            new = [convert(v) if isinstance(v, str) and applies(v) else v for v in value]
        else:
            continue
        if new != value:
            data[field] = new
            changed = True
    return changed


def _run(apps: Apps, applies: Callable[[str], bool], convert: Callable[[str], str]) -> None:
    Authenticator = apps.get_model("mfa", "Authenticator")
    for authenticator in Authenticator.objects.filter(type__in=SECRET_FIELDS).iterator():
        fields = SECRET_FIELDS[authenticator.type]
        if _convert(authenticator.data, fields, applies, convert):
            authenticator.save(update_fields=["data"])


def encrypt_secrets(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    _run(apps, lambda value: not value.startswith(PREFIX), encrypt)


def decrypt_secrets(apps: Apps, schema_editor: BaseDatabaseSchemaEditor | None) -> None:
    _run(apps, lambda value: value.startswith(PREFIX), decrypt)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_userinvitation"),
        ("mfa", "0003_authenticator_type_uniq"),
    ]

    operations = [migrations.RunPython(encrypt_secrets, decrypt_secrets)]
