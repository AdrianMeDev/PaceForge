"""A GPX document for the tests: a run of ``count`` points, one every ``step`` seconds, going
north from a place near Berlin, at ``speed`` metres per second."""

import math
from datetime import UTC, datetime, timedelta

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)
LATITUDE = 52.5
LONGITUDE = 13.4
METRES_PER_DEGREE = 111_195.0


def point(
    index: int,
    *,
    start: datetime,
    step: int,
    speed: float,
    heart_rate: int | None,
    with_time: bool = True,
) -> str:
    latitude = LATITUDE + index * step * speed / METRES_PER_DEGREE
    time = (
        f"<time>{(start + timedelta(seconds=index * step)).strftime('%Y-%m-%dT%H:%M:%SZ')}</time>"
    )
    extension = (
        f"<extensions><gpxtpx:TrackPointExtension><gpxtpx:hr>{heart_rate}</gpxtpx:hr>"
        "</gpxtpx:TrackPointExtension></extensions>"
        if heart_rate is not None
        else ""
    )
    return (
        f'<trkpt lat="{latitude:.7f}" lon="{LONGITUDE}"><ele>40</ele>'
        f"{time if with_time else ''}{extension}</trkpt>"
    )


def gpx_document(
    *,
    count: int = 61,
    step: int = 10,
    speed: float = 3.0,
    start: datetime = START,
    heart_rate: int | None = 150,
    track_type: str | None = "running",
    creator: str | None = "Test App",
    prolog: str = '<?xml version="1.0" encoding="UTF-8"?>',
    segments: int = 1,
    with_time: bool = True,
    inside: str = "",
) -> bytes:
    """A typical GPX document: 61 points ten seconds apart (ten minutes) at 3 m/s: about 1800 m."""
    creator_attr = "" if creator is None else f' creator="{creator}"'
    kind = "" if track_type is None else f"<type>{track_type}</type>"
    per_segment = math.ceil(count / segments)
    body = ""
    index = 0
    for _ in range(segments):
        points = []
        for _ in range(per_segment):
            if index >= count:
                break
            points.append(
                point(
                    index,
                    start=start,
                    step=step,
                    speed=speed,
                    heart_rate=heart_rate,
                    with_time=with_time,
                )
            )
            index += 1
        body += f"<trkseg>{''.join(points)}</trkseg>"
    document = (
        f'{prolog}<gpx version="1.1"{creator_attr} xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">'
        f"<metadata><time>{start.strftime('%Y-%m-%dT%H:%M:%SZ')}</time></metadata>"
        f"{inside}<trk><name>Morning run</name>{kind}{body}</trk></gpx>"
    )
    return document.encode()
