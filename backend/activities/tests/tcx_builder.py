"""Builds TCX documents for tests, so no real (and personal) file has to be committed."""

from datetime import UTC, datetime, timedelta
from typing import Any

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)

# Lap 1: 10 min, lap 2: 20 min right after it, lap 3: 5 min after a 30 s pause. Totals: 35 min
# of lap time, 7 km, 350 kcal, the last moment 07:05:30, that is 2130 s after the start.
DEFAULT_LAPS: list[dict[str, Any]] = [
    {"start": START, "seconds": 600, "distance": 2000, "calories": 100, "avg_hr": 140, "max_hr": 150, "avg_watts": 200},  # noqa: E501
    {"start": START + timedelta(seconds=600), "seconds": 1200, "distance": 4000, "calories": 200, "avg_hr": 150, "max_hr": 170, "avg_watts": 250},  # noqa: E501
    {"start": START + timedelta(seconds=1830), "seconds": 300, "distance": 1000, "calories": 50, "avg_hr": 130, "max_hr": 140, "avg_watts": 180},  # noqa: E501
]  # fmt: skip

_HEAD = (
    '<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2" '
    'xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _optional(tag: str, value: Any, wrapper: str | None = None) -> str:
    if value is None:
        return ""
    inner = f"<Value>{value}</Value>" if wrapper else str(value)
    return f"<{wrapper or tag}>{inner}</{wrapper or tag}>"


def lap_xml(lap: dict[str, Any], *, points: int = 3) -> str:
    start: datetime = lap["start"]
    seconds = lap.get("seconds")
    trackpoints = ""
    for i in range(points):
        moment = start + timedelta(seconds=(seconds or 0) * i / max(points - 1, 1))
        trackpoints += (
            f"<Trackpoint><Time>{stamp(moment)}</Time>"
            "<Position><LatitudeDegrees>12.345678</LatitudeDegrees>"
            "<LongitudeDegrees>23.456789</LongitudeDegrees></Position>"
            "<AltitudeMeters>101.5</AltitudeMeters><DistanceMeters>999999.0</DistanceMeters>"
            "<HeartRateBpm><Value>111</Value></HeartRateBpm>"
            "<Extensions><ns3:TPX><ns3:Speed>3.1</ns3:Speed><ns3:Watts>9999</ns3:Watts></ns3:TPX>"
            "</Extensions></Trackpoint>"
        )
    watts = lap.get("avg_watts")
    extensions = (
        f"<Extensions><ns3:LX><ns3:AvgWatts>{watts}</ns3:AvgWatts></ns3:LX></Extensions>"
        if watts is not None
        else ""
    )
    return (
        f'<Lap StartTime="{stamp(start)}">'
        + _optional("TotalTimeSeconds", seconds)
        + _optional("DistanceMeters", lap.get("distance"))
        + _optional("Calories", lap.get("calories"))
        + _optional("AverageHeartRateBpm", lap.get("avg_hr"), wrapper="AverageHeartRateBpm")
        + _optional("MaximumHeartRateBpm", lap.get("max_hr"), wrapper="MaximumHeartRateBpm")
        + "<Intensity>Active</Intensity><TriggerMethod>Manual</TriggerMethod>"
        + f"<Track>{trackpoints}</Track>"
        + extensions
        + "</Lap>"
    )


def tcx_document(
    *,
    sport: str | None = "Running",
    laps: list[dict[str, Any]] | None = None,
    creator: str | None = "Test Watch",
    activity_id: datetime | str | None = START,
    points: int = 3,
    prolog: str = '<?xml version="1.0" encoding="UTF-8"?>',
    before_root: str = "",
    inside: str = "",
    activities: int = 1,
) -> bytes:
    """A typical TCX document; ``laps`` replaces the default laps (keys left out or ``None`` leave
    the element out)."""
    chosen = DEFAULT_LAPS if laps is None else laps
    ident = (
        ""
        if activity_id is None
        else f"<Id>{activity_id if isinstance(activity_id, str) else stamp(activity_id)}</Id>"
    )
    sport_attr = "" if sport is None else f' Sport="{sport}"'
    device = (
        f'<Creator xsi:type="Device_t"><Name>{creator}</Name></Creator>'
        if creator is not None
        else ""
    )
    body = "".join(
        f"<Activity{sport_attr}>{ident}{''.join(lap_xml(lap, points=points) for lap in chosen)}"
        f"{device}</Activity>"
        for _ in range(activities)
    )
    document = f"{prolog}{before_root}{_HEAD}{inside}<Activities>{body}</Activities>"
    return (document + "</TrainingCenterDatabase>").encode()


def big_document(trackpoints: int) -> bytes:
    """A single long lap with ``trackpoints`` trackpoints, for size and memory checks."""
    lap = {
        "start": START,
        "seconds": trackpoints,
        "distance": trackpoints * 3,
        "avg_hr": 150,
        "max_hr": 170,
    }
    return tcx_document(laps=[lap], points=trackpoints)


def trackpoint_document(
    points: list[tuple[float, float | None, int | None, int | None]], *, sport: str = "Running"
) -> bytes:
    """One lap with the given trackpoints: (seconds after the start, distance in metres, heart
    rate, watts); ``None`` leaves the element out."""
    rows = ""
    for seconds, distance, heart_rate, watts in points:
        rows += f"<Trackpoint><Time>{stamp(START + timedelta(seconds=seconds))}</Time>"
        if distance is not None:
            rows += f"<DistanceMeters>{distance}</DistanceMeters>"
        if heart_rate is not None:
            rows += f"<HeartRateBpm><Value>{heart_rate}</Value></HeartRateBpm>"
        if watts is not None:
            rows += f"<Extensions><ns3:TPX><ns3:Watts>{watts}</ns3:Watts></ns3:TPX></Extensions>"
        rows += "</Trackpoint>"
    lap = (
        f'<Lap StartTime="{stamp(START)}"><TotalTimeSeconds>60</TotalTimeSeconds>'
        f"<Track>{rows}</Track></Lap>"
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>{_HEAD}<Activities>'
        f'<Activity Sport="{sport}"><Id>{stamp(START)}</Id>{lap}</Activity>'
        "</Activities></TrainingCenterDatabase>"
    ).encode()
