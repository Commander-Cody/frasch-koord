"""Which candidates describe one feature.

OSM maps a place as several objects -- a village as a node, a boundary and
a residential area, a river as dozens of ways and a relation -- and several
places under one name.  The matcher (frasch.match) decides among features,
not objects: `cluster` groups the objects of a name into features, and
`placed` says where a feature lies against a row's location hint and North
Frisia.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict

from frasch import geo, osmtags
from frasch.candidates import Candidate
from frasch.geo import haversine
from frasch.hints import Circle

CLUSTER_KM = 3.0  # objects this close describe the same feature
CORE_MIN_KM = 1.0  # two settlement nodes this close are one village
# Two features of one name are told apart for certain only this far from
# each other -- and a river runs that far.
SEPARATION_KM = 30.0
STRETCH_KM = 5.0  # two pieces of one street or dyke lie this close


class Cluster(TypedDict):
    """Candidates that describe one feature, and their mean position (None
    when no member has a location)."""

    members: list[Candidate]
    lon: float | None
    lat: float | None


class PlacedCluster(Cluster):
    """A cluster and where it lies: against the row's location hint, and
    against North Frisia."""

    hint_ok: bool
    nf_d: float | None
    in_nf: bool


def linear_radius(rec: Candidate) -> float | None:
    """How far apart two pieces of the same linear feature may be, or None."""
    if rec["t"] != "w":
        return None
    t = rec["tags"]
    if t.get("waterway"):
        return SEPARATION_KM  # a river runs for tens of kilometres
    if t.get("highway") or t.get("man_made") in ("dyke", "embankment"):
        return STRETCH_KM
    return None


def is_linear(rec: Candidate) -> bool:
    return linear_radius(rec) is not None


def is_core(rec: Candidate) -> bool:
    """A settlement node -- two of these more than CORE_MIN_KM apart are two
    different villages, however similar their names."""
    return rec["t"] == "n" and rec["tags"].get("place") in osmtags.CORE_PLACES


def same_feature(a: Candidate, b: Candidate) -> bool:
    """Whether two objects of one name describe the same feature.

    Point features do within CLUSTER_KM, a piece of a linear feature (a river
    split into dozens of ways) as far as it reaches; two `core` objects (two
    village nodes with the same name) only as duplicate nodes of one village.
    An object without a location is the same feature as no other.
    """
    d = haversine(a["lon"], a["lat"], b["lon"], b["lat"])
    return d is not None and d <= _reach(a, b)


def _reach(a: Candidate, b: Candidate) -> float:
    """How far apart `a` and `b` may be and still be one feature."""
    if is_core(a) and is_core(b):
        return CORE_MIN_KM
    return max(linear_radius(a) or CLUSTER_KM, linear_radius(b) or CLUSTER_KM)


def cluster(cands: Iterable[Candidate]) -> list[Cluster]:
    """Group candidates that describe the same feature (`same_feature`): each
    joins the first group one of whose members it is the same feature as.
    Records without a location land in their own cluster."""
    groups: list[list[Candidate]] = []
    for c in cands:
        target = next(
            (members for members in groups if any(same_feature(c, m) for m in members)), None
        )
        if target is None:
            groups.append([c])
        else:
            target.append(c)
    return [_centred(members) for members in groups]


def _centred(members: list[Candidate]) -> Cluster:
    """The cluster of `members`, at their mean position."""
    pts = [(m["lon"], m["lat"]) for m in members if m["lon"] is not None and m["lat"] is not None]
    return {
        "members": members,
        "lon": sum(p[0] for p in pts) / len(pts) if pts else None,
        "lat": sum(p[1] for p in pts) / len(pts) if pts else None,
    }


def placed(cl: Cluster, hint_pt: Circle | None) -> PlacedCluster:
    """`cl` with whether it lies at the location hint, and its distance to
    North Frisia."""
    hint_ok = False
    if hint_pt and cl["lon"] is not None:
        hint_d = haversine(cl["lon"], cl["lat"], hint_pt[0], hint_pt[1])
        hint_ok = hint_d is not None and hint_d <= hint_pt[2]
    return {
        **cl,
        "hint_ok": hint_ok,
        "nf_d": geo.from_centre(cl["lon"], cl["lat"]),
        "in_nf": geo.in_north_frisia(cl["lon"], cl["lat"]),
    }
