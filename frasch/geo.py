"""Where North Frisia is, and how far apart two points are -- one box for
the matcher, the candidate scan and the curation view, so that "in North
Frisia" means the same everywhere."""
from __future__ import annotations

import math

# lon_min, lat_min, lon_max, lat_max: North Frisia including Helgoland, with
# the Danish islands just across the border (Röm)
NF_BBOX = (7.8, 54.15, 9.55, 55.12)
NF_CENTRE = (8.9, 54.7)                 # lon, lat

EARTH_RADIUS_KM = 6371.0


def in_north_frisia(lon, lat) -> bool:
    """Whether a point lies in NF_BBOX; False for an unknown position."""
    return (lon is not None and lat is not None
            and NF_BBOX[0] <= lon <= NF_BBOX[2] and NF_BBOX[1] <= lat <= NF_BBOX[3])


def haversine(lon1, lat1, lon2, lat2) -> float | None:
    """The great-circle distance in km, None when a position is unknown."""
    if None in (lon1, lat1, lon2, lat2):
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
