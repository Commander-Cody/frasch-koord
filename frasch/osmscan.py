"""Id-filtered passes over an OSM extract.

The dev machine has no memory for a location cache of a whole extract (let
alone for pyosmium to build every area of it), so whatever needs geometry
reads it in three passes that each keep only the objects asked for: the
relations, then their and the referenced ways, then all of those ways'
nodes.  names/locate.py and names/build_dialect_areas.py both do."""
from __future__ import annotations

import osmium


def rings_of(relation) -> dict:
    """`{"outer": [way ids], "inner": [way ids]}` of an OSM relation; a
    member way without the `inner` role counts as outer."""
    rings = {"outer": [], "inner": []}
    for m in relation.members:
        if m.type == "w":
            rings["inner" if m.role == "inner" else "outer"].append(m.ref)
    return rings


def relations(pbf, ids) -> dict:
    """-> {id: {"rings": rings_of(...), "label": node id or None,
               "tags": {...}}}; `label` is the first `label` or
    `admin_centre` member node."""
    out = {}
    for r in _filtered(pbf, osmium.osm.RELATION, ids):
        label = next((m.ref for m in r.members
                      if m.type == "n" and m.role in ("label", "admin_centre")), None)
        out[r.id] = {"rings": rings_of(r), "label": label, "tags": dict(r.tags)}
    return out


def ways(pbf, ids) -> dict:
    """-> {id: {"nodes": [node ids], "tags": {...}}} for the ways with nodes."""
    return {w.id: {"nodes": [n.ref for n in w.nodes], "tags": dict(w.tags)}
            for w in _filtered(pbf, osmium.osm.WAY, ids) if len(w.nodes)}


def nodes(pbf, ids) -> dict:
    """-> {id: {"loc": (lon, lat), "tags": {...}}} for the nodes with a valid
    location."""
    return {n.id: {"loc": (n.location.lon, n.location.lat), "tags": dict(n.tags)}
            for n in _filtered(pbf, osmium.osm.NODE, ids) if n.location.valid()}


def _filtered(pbf, entity, ids):
    if not ids:
        return iter(())
    return osmium.FileProcessor(str(pbf), entity).with_filter(osmium.filter.IdFilter(ids))
