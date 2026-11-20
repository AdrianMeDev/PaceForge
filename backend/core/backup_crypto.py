"""Authenticated streaming encryption for database backups.

A backup is encrypted in chunks with AES-256-GCM, so a dump of any size never has to fit into
memory and any change to it is detected. The key lives in ``BACKUP_ENCRYPTION_KEY``, apart from
``ENCRYPTION_KEY``: whoever holds a backup alone learns nothing, and whoever holds the instance
key alone cannot read a backup.

File layout::

    magic "PFBK" + version 1 | chunk size (4 bytes) | nonce prefix (8 bytes) | chunk, chunk, ...

Each chunk is the AES-GCM output (ciphertext and 16-byte tag) of up to ``chunk size`` bytes. The
nonce of a chunk is the nonce prefix plus its sequence number. The associated data holds the
header, the sequence number and a flag for the final chunk, so chunks cannot be reordered,
dropped from the end or followed by extra data. The stream always ends with a final chunk, which
may be empty.

``BACKUP_ENCRYPTION_KEY`` may hold several keys separated by commas: the first one encrypts, all of
them decrypt (key rotation). Error messages never contain key material or file content.
"""

import base64
import os
import re
import struct
from collections.abc import Sequence
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

MAGIC = b"PFBK\x01"
CHUNK_SIZE = 1024 * 1024
NONCE_PREFIX_SIZE = 8
TAG_SIZE = 16
KEY_SIZE = 32
_HEADER = struct.Struct(">I")
HEADER_SIZE = len(MAGIC) + _HEADER.size + NONCE_PREFIX_SIZE
_MAX_CHUNK_SIZE = 64 * 1024 * 1024
_MAX_CHUNKS = 2**32
_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}=")

_DAMAGED = "The backup is damaged, incomplete or was encrypted with another key."


class BackupCryptoError(Exception):
    """A backup cannot be encrypted or decrypted.

    The message never contains key material or data, so it is safe to log.
    """


def parse_backup_keys(raw_keys: Sequence[str]) -> list[bytes]:
    """Decode keys (32 bytes, url-safe base64, like a Fernet key) and name bad ones by position."""
    keys: list[bytes] = []
    for position, raw in enumerate(raw_keys, start=1):
        if not _KEY_PATTERN.fullmatch(raw):
            raise BackupCryptoError(
                f"Key {position} of BACKUP_ENCRYPTION_KEY is not a valid key "
                "(32 bytes, url-safe base64)."
            )
        keys.append(base64.urlsafe_b64decode(raw))
    return keys


def shares_an_instance_key(backup_keys: Sequence[bytes]) -> bool:
    """Whether a decoded backup key equals a decoded ``ENCRYPTION_KEYS`` entry (also an old one).

    Compares bytes, not text: the last character of a key only uses some of its bits, so two
    spellings can decode to the same key. Instance keys that cannot be decoded are skipped
    (``core.E002`` reports them).
    """
    instance_keys: set[bytes] = set()
    for key in settings.ENCRYPTION_KEYS:
        try:
            instance_keys.add(base64.urlsafe_b64decode(key))
        except ValueError:
            continue
    return any(key in instance_keys for key in backup_keys)


def _configured_keys(keys: Sequence[str] | None) -> list[bytes]:
    parsed = parse_backup_keys(settings.BACKUP_ENCRYPTION_KEYS if keys is None else keys)
    if not parsed:
        raise BackupCryptoError("BACKUP_ENCRYPTION_KEY is not configured.")
    return parsed


def _nonce(prefix: bytes, sequence: int) -> bytes:
    return prefix + struct.pack(">I", sequence)


def _aad(header: bytes, sequence: int, final: bool) -> bytes:
    return header + struct.pack(">QB", sequence, 1 if final else 0)


def _read_full(source: BinaryIO, size: int) -> bytes:
    """Read ``size`` bytes, fewer only at the end of the stream."""
    parts: list[bytes] = []
    remaining = size
    while remaining:
        part = source.read(remaining)
        if not part:
            break
        parts.append(part)
        remaining -= len(part)
    return b"".join(parts)


def encrypt_stream(
    source: BinaryIO,
    destination: BinaryIO,
    keys: Sequence[str] | None = None,
    *,
    chunk_size: int = CHUNK_SIZE,
) -> None:
    """Encrypt ``source`` into ``destination`` with the first key."""
    if not 0 < chunk_size <= _MAX_CHUNK_SIZE:
        raise BackupCryptoError("Invalid chunk size.")
    cipher = AESGCM(_configured_keys(keys)[0])
    prefix = os.urandom(NONCE_PREFIX_SIZE)
    header = MAGIC + _HEADER.pack(chunk_size) + prefix
    destination.write(header)
    chunk = _read_full(source, chunk_size)
    sequence = 0
    while True:
        following = _read_full(source, chunk_size) if len(chunk) == chunk_size else b""
        # With a full chunk, one more read tells whether it is the last one.
        final = not following
        if sequence >= _MAX_CHUNKS:
            raise BackupCryptoError("The stream is too large.")
        destination.write(
            cipher.encrypt(_nonce(prefix, sequence), chunk, _aad(header, sequence, final))
        )
        if final:
            return
        chunk = following
        sequence += 1


def _decrypt_first(
    frame: bytes, header: bytes, prefix: bytes, final: bool, keys: list[bytes]
) -> tuple[AESGCM, bytes]:
    aad = _aad(header, 0, final)
    for key in keys:
        cipher = AESGCM(key)
        try:
            return cipher, cipher.decrypt(_nonce(prefix, 0), frame, aad)
        except InvalidTag:
            continue
    raise BackupCryptoError(_DAMAGED)


def decrypt_stream(
    source: BinaryIO, destination: BinaryIO, keys: Sequence[str] | None = None
) -> None:
    """Decrypt ``source`` into ``destination`` with any of the keys.

    Every chunk is verified before it is written, but a damaged end is only found after the start
    was written: on ``BackupCryptoError`` the caller must discard the output.
    """
    parsed = _configured_keys(keys)
    header = _read_full(source, HEADER_SIZE)
    if len(header) != HEADER_SIZE or not header.startswith(MAGIC):
        raise BackupCryptoError("This is not a PaceForge backup.")
    (chunk_size,) = _HEADER.unpack_from(header, len(MAGIC))
    if not 0 < chunk_size <= _MAX_CHUNK_SIZE:
        raise BackupCryptoError(_DAMAGED)
    prefix = header[-NONCE_PREFIX_SIZE:]
    frame_size = chunk_size + TAG_SIZE
    frame = _read_full(source, frame_size)
    cipher: AESGCM | None = None
    sequence = 0
    while True:
        if len(frame) < TAG_SIZE:
            raise BackupCryptoError(_DAMAGED)
        following = _read_full(source, frame_size) if len(frame) == frame_size else b""
        final = not following
        if cipher is None:
            cipher, plain = _decrypt_first(frame, header, prefix, final, parsed)
        else:
            try:
                plain = cipher.decrypt(
                    _nonce(prefix, sequence), frame, _aad(header, sequence, final)
                )
            except InvalidTag:
                raise BackupCryptoError(_DAMAGED) from None
        destination.write(plain)
        if final:
            return
        frame = following
        sequence += 1
        if sequence >= _MAX_CHUNKS:
            raise BackupCryptoError(_DAMAGED)
