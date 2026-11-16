from ..efforts import Sample
from .compressed import UnpackedTooLargeError, is_compressed, unpack
from .fit import parse_fit
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
    "parse_tcx",
]

# What may precede the first "<" of an XML document: a byte order mark and white space.
_XML_PREFIXES = (b"<", b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b" ", b"\t", b"\r", b"\n")


def parse_activity_file(data: bytes) -> ParsedActivity:
    """Parse a FIT or TCX file. The format is decided by the content, never by the file name.

    Raises ``UnsupportedFileError`` or ``InvalidFileError`` (both ``ActivityFileError``).
    """
    if len(data) >= 12 and data[8:12] == b".FIT":
        return parse_fit(data)
    if data.startswith(_XML_PREFIXES):
        return parse_tcx(data)
    raise UnsupportedFileError("The file is neither a FIT nor a TCX file.")


def parse_series(data: bytes) -> list[Sample]:
    """The time series of a FIT or TCX file, decided by the content like ``parse_activity_file``."""
    if len(data) >= 12 and data[8:12] == b".FIT":
        return fit_series(data)
    if data.startswith(_XML_PREFIXES):
        return tcx_series(data)
    raise UnsupportedFileError("The file is neither a FIT nor a TCX file.")
