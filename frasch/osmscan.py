"""Id-filtered passes over an OSM extract.

The dev machine has no memory for a location cache of a whole extract (let
alone for pyosmium to build every area of it), so whatever needs geometry
reads it in three passes that each keep only the objects asked for: the
relations, then their and the referenced ways, then all of those ways'
nodes.  names/locate.py and names/build_dialect_areas.py both do.  And the
extract's header, without a pass at all."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import TypedDict

import osmium
import osmium.osm
from osmium.osm.types import OSMEntity

from frasch.geo import LonLat
from frasch.paths import StrPath


class Rings(TypedDict):
    """The member ways of a relation by role: way ids."""

    outer: list[int]
    inner: list[int]


class Relation(TypedDict):
    rings: Rings
    label: int | None
    tags: dict[str, str]


class Way(TypedDict):
    nodes: list[int]
    tags: dict[str, str]


class Node(TypedDict):
    loc: LonLat
    tags: dict[str, str]


def rings_of(relation: osmium.osm.Relation) -> Rings:
    """`{"outer": [way ids], "inner": [way ids]}` of an OSM relation; a
    member way without the `inner` role counts as outer."""
    rings: Rings = {"outer": [], "inner": []}
    for m in relation.members:
        if m.type == "w":
            rings["inner" if m.role == "inner" else "outer"].append(m.ref)
    return rings


def relations(pbf: StrPath, ids: Collection[int]) -> dict[int, Relation]:
    """-> {id: {"rings": rings_of(...), "label": node id or None,
               "tags": {...}}}; `label` is the first `label` or
    `admin_centre` member node."""
    out: dict[int, Relation] = {}
    for r in _filtered(pbf, osmium.osm.RELATION, ids):
        if not isinstance(r, osmium.osm.Relation):
            continue
        label = next(
            (m.ref for m in r.members if m.type == "n" and m.role in ("label", "admin_centre")),
            None,
        )
        out[r.id] = {"rings": rings_of(r), "label": label, "tags": dict(r.tags)}
    return out


def ways(pbf: StrPath, ids: Collection[int]) -> dict[int, Way]:
    """-> {id: {"nodes": [node ids], "tags": {...}}} for the ways with nodes."""
    return {
        w.id: {"nodes": [n.ref for n in w.nodes], "tags": dict(w.tags)}
        for w in _filtered(pbf, osmium.osm.WAY, ids)
        if isinstance(w, osmium.osm.Way) and len(w.nodes)
    }


def nodes(pbf: StrPath, ids: Collection[int]) -> dict[int, Node]:
    """-> {id: {"loc": (lon, lat), "tags": {...}}} for the nodes with a valid
    location."""
    return {
        n.id: {"loc": (n.location.lon, n.location.lat), "tags": dict(n.tags)}
        for n in _filtered(pbf, osmium.osm.NODE, ids)
        if isinstance(n, osmium.osm.Node) and n.location.valid()
    }


def header(pbf: StrPath) -> osmium.io.Header:
    """The extract's header (its bounds, its replication timestamp)."""
    reader = osmium.io.Reader(str(pbf))
    try:
        return reader.header()
    finally:
        reader.close()


def _filtered(
    pbf: StrPath, entity: osmium.osm.osm_entity_bits, ids: Collection[int]
) -> Iterable[OSMEntity]:
    if not ids:
        return iter(())
    return osmium.FileProcessor(str(pbf), entity).with_filter(osmium.filter.IdFilter(ids))
