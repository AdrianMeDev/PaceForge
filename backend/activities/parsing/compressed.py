"""Compressed activity files: Strava keeps most files of an export as ``.fit.gz`` or ``.tcx.gz``.

A file is recognised as compressed by its first two bytes, never by its name. It is unpacked in
memory and never past a limit, so that a small file that unpacks to gigabytes (a "bomb") stops
at the limit and is refused.
"""

import zlib

from .types import ActivityFileError, UnsupportedFileError

_GZIP = b"\x1f\x8b"
_GZIP_WINDOW = 16 + zlib.MAX_WBITS


class UnpackedTooLargeError(ActivityFileError):
    """The file unpacks to more than the limit; only the limit was ever held in memory."""


def is_compressed(data: bytes) -> bool:
    return data.startswith(_GZIP)


def unpack(data: bytes, limit: int) -> bytes:
    """``data`` as it is if it is no gzip file, else what it unpacks to (one member; whatever
    follows it is ignored).

    Raises ``UnpackedTooLargeError`` if the result would be larger than ``limit`` bytes and
    ``UnsupportedFileError`` if the gzip data is broken. Nothing of the data is in a message.
    """
    if not is_compressed(data):
        return data
    unpacker = zlib.decompressobj(_GZIP_WINDOW)
    try:
        # one byte more than the limit is enough to know that it is too much
        unpacked = unpacker.decompress(data, limit + 1)
        if len(unpacked) <= limit and not unpacker.eof:
            unpacked += unpacker.flush()
    except zlib.error:
        raise UnsupportedFileError("The file is neither a FIT nor a TCX file.") from None
    if len(unpacked) > limit:
        raise UnpackedTooLargeError("The file is too large.")
    if not unpacker.eof:
        # cut off in the middle: what was read is not a file
        raise UnsupportedFileError("The file is neither a FIT nor a TCX file.")
    return unpacked
