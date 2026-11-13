from .fit import parse_fit
from .tcx import parse_tcx
from .types import ActivityFileError, InvalidFileError, ParsedActivity, UnsupportedFileError

__all__ = [
    "ActivityFileError",
    "InvalidFileError",
    "ParsedActivity",
    "UnsupportedFileError",
    "parse_activity_file",
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
