"""Id-filtered passes over an OSM extract.

Whatever needs the geometry of a few objects reads it in three passes that
each keep only the objects asked for: the relations, then their and the
referenced ways, then all of those ways' nodes (`read_geometry`).  That
takes neither a location cache for the whole extract nor pyosmium building
every area of it.  frasch.locate and frasch.build_dialect_areas both read
it so, over several extracts with `across`.  Besides those: the relations
by their tags (`relations_where`), the objects that carry a tag (`tagged`),
and the extract's header and the stamp made of it, without a pass at all."""

from __future__ import annotations

import os
from collections.abc import Callable, Collection, Iterable, Mapping
from typing import NamedTuple, TypedDict

import osmium
import osmium.osm
from osmium.osm.types import OSMEntity

from frasch.geo import LonLat
from frasch.paths import StrPath
from frasch.provenance import ExtractStamp
from frasch.refs import OsmRef, ids_of


class Rings(TypedDict):
    """The member ways of a relation by role: way ids."""

    outer: list[int]
    inner: list[int]


class Relation(TypedDict):
    rings: Rings
    member_ways: list[int]  # every member way, whatever its role, in member order
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
    """-> {id: {"rings": rings_of(...), "member_ways": [way ids],
               "label": node id or None, "tags": {...}}}; `label` is the
    first `label` or `admin_centre` member node."""
    return {
        r.id: _relation(r)
        for r in _filtered(pbf, osmium.osm.RELATION, ids)
        if isinstance(r, osmium.osm.Relation)
    }


def relations_where(
    pbf: StrPath, wanted: Callable[[osmium.osm.TagList], bool]
) -> dict[int, Relation]:
    """The relations whose tags `wanted` picks, as `relations` gives them --
    a pass over every relation of the extract, for the ones nobody has an
    id of."""
    return {
        r.id: _relation(r)
        for r in osmium.FileProcessor(str(pbf), osmium.osm.RELATION)
        if isinstance(r, osmium.osm.Relation) and wanted(r.tags)
    }


def _relation(r: osmium.osm.Relation) -> Relation:
    label = next(
        (m.ref for m in r.members if m.type == "n" and m.role in ("label", "admin_centre")),
        None,
    )
    return {
        "rings": rings_of(r),
        "member_ways": [m.ref for m in r.members if m.type == "w"],
        "label": label,
        "tags": dict(r.tags),
    }


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


class Geometry(NamedTuple):
    """What one extract holds of the objects asked for and of what they are
    made of, each by its id."""

    relations: dict[int, Relation]
    ways: dict[int, Way]
    nodes: dict[int, Node]


def read_geometry(
    pbf: StrPath, refs: Collection[OsmRef], extra_relations: Mapping[int, Relation] | None = None
) -> Geometry:
    """The objects `refs` of one extract with everything their geometry
    takes, in three passes: the relations, then the referenced ways and the
    relations' member ways, then the referenced nodes, the relations' label
    nodes and all of those ways' nodes.  `extra_relations`, read before
    (`relations_where`), ride along in the way and node passes."""
    found = relations(pbf, ids_of(refs, "r")) | dict(extra_relations or {})
    member_ids = {w for r in found.values() for w in r["rings"]["outer"] + r["rings"]["inner"]}
    made_of = ways(pbf, ids_of(refs, "w") | member_ids)
    node_ids = ids_of(refs, "n") | {n for w in made_of.values() for n in w["nodes"]}
    node_ids |= {r["label"] for r in found.values() if r["label"] is not None}
    return Geometry(found, made_of, nodes(pbf, node_ids))


def across[T](
    pbfs: Iterable[StrPath],
    refs: Collection[OsmRef],
    read: Callable[[StrPath, set[OsmRef]], Mapping[OsmRef, T]],
) -> dict[OsmRef, T]:
    """What `read` finds of `refs` in several extracts: each is asked only
    for the references no earlier one held."""
    found: dict[OsmRef, T] = {}
    for pbf in pbfs:
        found.update(read(pbf, {ref for ref in refs if ref not in found}))
    return found


def tagged(pbf: StrPath, key: str) -> dict[OsmRef, str]:
    """-> {('n', id): value} for every node, way and relation whose tag
    `key` has a value -- one pass, but only the tagged objects are kept."""
    scan = osmium.FileProcessor(str(pbf)).with_filter(osmium.filter.KeyFilter(key))
    return {
        (o.type_str(), o.id): o.tags[key]
        for o in scan
        if isinstance(o, (osmium.osm.Node, osmium.osm.Way, osmium.osm.Relation)) and o.tags.get(key)
    }


def header(pbf: StrPath) -> osmium.io.Header:
    """The extract's header (its bounds, its replication timestamp)."""
    reader = osmium.io.Reader(str(pbf))
    try:
        return reader.header()
    finally:
        reader.close()


def extract_stamp(pbf: StrPath) -> ExtractStamp:
    """An extract as a stamp records it (frasch.provenance): its file name
    and the replication timestamp of its header, `""` when it has none."""
    timestamp = header(pbf).get("osmosis_replication_timestamp") or ""
    return {"file": os.path.basename(pbf), "replication_timestamp": timestamp}


def extract_stamps(pbfs: Iterable[StrPath]) -> list[ExtractStamp]:
    return [extract_stamp(pbf) for pbf in pbfs]


def _filtered(
    pbf: StrPath, entity: osmium.osm.osm_entity_bits, ids: Collection[int]
) -> Iterable[OSMEntity]:
    if not ids:
        return iter(())
    return osmium.FileProcessor(str(pbf), entity).with_filter(osmium.filter.IdFilter(ids))
