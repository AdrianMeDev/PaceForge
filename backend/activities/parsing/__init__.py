import re

from ..efforts import Sample
from .compressed import UnpackedTooLargeError, is_compressed, unpack
from .fit import parse_fit
from .gpx import gpx_series, parse_gpx
from .series import fit_series, tcx_series
from .tcx import parse_tcx
from .types import ActivityFileError, InvalidFileError, ParsedActivity, UnsupportedFileError

__all__ = [
    "ActivityFileError",
    "InvalidFileError",
    "UnpackedTooLargeError",
    "is_compressed",
    "unpack",
    "ParsedActivity",
    "UnsupportedFileError",
    "parse_activity_file",
    "parse_series",
    "parse_fit",
    "parse_gpx",
    "parse_tcx",
]

# What may precede the first "<" of an XML document: a byte order mark and white space.
_GPX_ROOT = re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?gpx[\s>/]")
_ROOT_LOOKAHEAD = 4096
_XML_PREFIXES = (b"<", b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b" ", b"\t", b"\r", b"\n")


def parse_activity_file(data: bytes) -> ParsedActivity:
    """Parse a FIT or TCX file. The format is decided by the content, never by the file name.

    Raises ``UnsupportedFileError`` or ``InvalidFileError`` (both ``ActivityFileError``).
    """
    if len(data) >= 12 and data[8:12] == b".FIT":
        return parse_fit(data)
    if data.startswith(_XML_PREFIXES):
        return parse_gpx(data) if _is_gpx(data) else parse_tcx(data)
    raise UnsupportedFileError("The file is neither a FIT, a TCX nor a GPX file.")


def _is_gpx(data: bytes) -> bool:
    """The document element is ``gpx`` (looked at in the first bytes only: the reader checks it
    again, and a TCX file is told by its own root)."""
    return _GPX_ROOT.search(data[:_ROOT_LOOKAHEAD]) is not None


def parse_series(data: bytes) -> list[Sample]:
    """The time series of a FIT or TCX file, decided by the content like ``parse_activity_file``."""
    if len(data) >= 12 and data[8:12] == b".FIT":
        return fit_series(data)
    if data.startswith(_XML_PREFIXES):
        return gpx_series(data) if _is_gpx(data) else tcx_series(data)
    raise UnsupportedFileError("The file is neither a FIT, a TCX nor a GPX file.")
