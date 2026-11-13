"""What a parser returns and the errors it raises. Nothing here knows about Django."""

from dataclasses import dataclass
from datetime import datetime

# Normalised sports; the values match ``Activity.Sport``.
RUNNING = "running"
CYCLING = "cycling"
SWIMMING = "swimming"
STRENGTH = "strength"
OTHER = "other"

# The values of ``Activity.Source``.
FIT_FILE = "fit_file"
TCX_FILE = "tcx_file"

# A lap list longer than this is not a lap list of one activity; refusing it also bounds the
# size of what is stored.
MAX_LAPS = 5000


class ActivityFileError(Exception):
    """A file cannot be imported. The message is a fixed text for the user and never contains
    anything from the file itself."""


class UnsupportedFileError(ActivityFileError):
    """A valid file that this import does not handle (not an activity, several sessions, …)."""


class InvalidFileError(ActivityFileError):
    """A file that is damaged, incomplete or not what it claims to be."""


@dataclass(frozen=True)
class ParsedLap:
    start_time: datetime | None = None
    elapsed_seconds: float | None = None
    distance_m: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None


@dataclass(frozen=True)
class ParsedActivity:
    """The summary of one activity. ``None`` means the file does not say; nothing is estimated."""

    source: str
    sport: str
    source_sport: str
    start_time: datetime
    elapsed_seconds: float | None = None
    timer_seconds: float | None = None
    distance_m: float | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_power_w: int | None = None
    total_ascent_m: int | None = None
    calories: int | None = None
    manufacturer: str = ""
    laps: tuple[ParsedLap, ...] = ()
