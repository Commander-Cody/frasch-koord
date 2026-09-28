"""A row's location hint (`hint` in places.csv: "on Sylt", "Karrharde"),
resolved to a circle the matching object has to lie in.

A hint names a place itself: it is looked up in the same name index as the
rows (frasch.nameindex), and the most plausible place of that name wins --
the nearest to North Frisia, islands and villages first.  The historic
Harden and a few spellings OSM does not know have fixed circles.
"""
from __future__ import annotations

from frasch.candidates import ISLAND_PLACES
from frasch.geo import NF_CENTRE, haversine
from frasch.nameindex import NameIndex, norm

HINT_KM = 8.0           # a village-sized hint
HINT_KM_ISLAND = 10.0   # a Hallig / small island
HINT_KM_LARGE = 25.0    # Sylt, Foehr, Eiderstedt, a Harde ...

# Fallback centroids for hints that OSM does not carry as an object
# (the historic Harden) or that are spelled differently in the sheet.
HINT_FALLBACK = {
    "karrharde": (9.02, 54.80, 15.0),
    "boekingharde": (8.85, 54.77, 15.0),
    "wiedingharde": (8.72, 54.88, 12.0),
    "beltringharde": (8.93, 54.58, 12.0),
    "boekingharde osterdeich": (8.85, 54.77, 15.0),
    "nordmarsch": (8.56, 54.63, 6.0),
    "butweel": (8.60, 54.63, 6.0),
    "luett moor": (8.83, 54.55, 6.0),
    "uthlande": (8.60, 54.65, 40.0),
    "dreiharde eck": (8.87, 54.80, 10.0),
    "st peter": (8.640, 54.306, 10.0),
    "sankt peter": (8.640, 54.306, 10.0),
}
# big enough that "X lies on Y" only narrows things down to ~25 km
LARGE_HINTS = {"sylt", "foehr", "amrum", "eiderstedt", "pellworm", "nordstrand",
               "nordfriesland", "dithmarschen", "angeln"}


class HintResolver:
    def __init__(self, index: NameIndex):
        self.index = index
        self.cache = {}

    def resolve(self, hint: str):
        """-> (lon, lat, radius_km) or None"""
        key = norm(hint)
        if not key:
            return None
        if key not in self.cache:
            self.cache[key] = HINT_FALLBACK.get(key) or self._lookup(hint, key)
        return self.cache[key]

    def _lookup(self, hint, key):
        places = [rec for rec, _rank in self.index.lookup(hint)
                  if rec["lon"] is not None and _is_a_place(rec["tags"])]
        if not places:
            return None
        best = max(places, key=_plausibility)
        return best["lon"], best["lat"], _radius(key, best["tags"])


def _is_a_place(tags) -> bool:
    return bool(tags.get("place") or tags.get("natural")
                or tags.get("boundary") == "administrative")


def _plausibility(rec) -> float:
    """Nearer to North Frisia is better; an island or a village better
    still.  Of equals, the first record wins."""
    tags = rec["tags"]
    score = -(haversine(rec["lon"], rec["lat"], *NF_CENTRE) or 999)
    if tags.get("place") in ISLAND_PLACES or tags.get("natural") == "peninsula":
        score += 40
    if tags.get("place") in ("village", "town", "city", "hamlet"):
        score += 30
    return score


def _radius(key, tags) -> float:
    if key in LARGE_HINTS:
        return HINT_KM_LARGE
    if (tags.get("place") in ISLAND_PLACES or tags.get("place") == "region"
            or tags.get("natural") in ("island", "islet", "peninsula")):
        return HINT_KM_ISLAND
    return HINT_KM
