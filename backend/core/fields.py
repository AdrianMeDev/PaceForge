from typing import Any

from django.core.exceptions import FieldError
from django.db import models

from .encryption import decrypt, encrypt


class EncryptedTextField(models.TextField):
    """Text that is stored encrypted with the instance key (see ``core.encryption``).

    The database holds ``enc:v1:`` ciphertext; the model attribute is the plaintext. Use it for
    credentials such as API keys and tokens, and never expose such a field through a serializer.

    - ``None`` stays ``NULL``; the empty string is encrypted like any other text.
    - A value that cannot be decrypted (other key, damaged, never encrypted) raises
      ``DecryptionError`` when the row is loaded; nothing is guessed.
    - The ciphertext is different on every save, so a value cannot be searched: only
      ``isnull`` is allowed as a lookup.
    - Assign plain values. A database expression such as ``Value("x")`` in an ``update()`` would
      bypass the encryption.
    """

    description = "Text stored encrypted with the instance key"

    def from_db_value(self, value: str | None, expression: Any, connection: Any) -> str | None:
        return None if value is None else decrypt(value)

    def get_prep_value(self, value: Any) -> str | None:
        prepared = super().get_prep_value(value)
        return None if prepared is None else encrypt(prepared)

    def get_lookup(self, lookup_name: str) -> Any:
        if lookup_name != "isnull":
            raise FieldError(
                f"EncryptedTextField cannot be searched ('{lookup_name}'): the stored value "
                "is different on every save. Only 'isnull' is supported."
            )
        return super().get_lookup(lookup_name)
