"""A tiny OSM extract written and read with pyosmium, and the shapes the
tests lay out in it and in the dialect areas."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import osmium

from frasch.geo import LonLat

Tags = Mapping[str, str]
Nodes = Mapping[int, tuple[LonLat, Tags]]
Ways = Mapping[int, tuple[Sequence[int], Tags]]
# a member is (type letter, ref, role)
Relations = Mapping[int, tuple[Sequence[tuple[str, int, str]], Tags]]
# `ring`'s nodes, a dict so tests can add to them
RingNodes = dict[int, tuple[LonLat, dict[str, str]]]
# a node's (lon, lat), a way's node ids, nothing for a relation
Extra = LonLat | list[int] | None
# (type letter, id, tags, extra)
ExtractObject = tuple[str, int, dict[str, str], Extra]

# A U-shaped island: the mean of its corners (8.5, 54.5375) lies in the bay
# between the two arms, outside the island itself.
U_SHAPE: list[LonLat] = [
    (8.0, 54.0),
    (9.0, 54.0),
    (9.0, 55.0),
    (8.8, 55.0),
    (8.8, 54.2),
    (8.2, 54.2),
    (8.2, 55.0),
    (8.0, 55.0),
]


def write_extract(
    path: Path,
    nodes: Nodes | None = None,
    ways: Ways | None = None,
    relations: Relations | None = None,
    timestamp: str | None = None,
) -> Path:
    """Write an extract to `path` in node/way/relation order, ids ascending.

    nodes      {id: ((lon, lat), {tags})}
    ways       {id: ([node ids], {tags})}
    relations  {id: ([(type letter, ref, role)], {tags})}
    timestamp  the header's `osmosis_replication_timestamp`, if any
    """
    header = osmium.io.Header()
    if timestamp:
        header.set("osmosis_replication_timestamp", timestamp)
    Node, Way, Relation = (
        osmium.osm.mutable.Node,
        osmium.osm.mutable.Way,
        osmium.osm.mutable.Relation,
    )
    w = osmium.SimpleWriter(str(path), overwrite=True, header=header)
    try:
        for i, (loc, tags) in sorted((nodes or {}).items()):
            w.add_node(Node(id=i, version=1, visible=True, location=loc, tags=tags))
        for i, (refs, tags) in sorted((ways or {}).items()):
            w.add_way(Way(id=i, version=1, visible=True, nodes=refs, tags=tags))
        for i, (members, tags) in sorted((relations or {}).items()):
            w.add_relation(Relation(id=i, version=1, visible=True, members=members, tags=tags))
    finally:
        w.close()
    return path


def ring(first_id: int, *corners: LonLat) -> tuple[RingNodes, list[int]]:
    """Nodes {id: ((lon, lat), {})} and the closed way's node list for a ring
    through `corners`, ids counting up from `first_id`."""
    nodes: RingNodes = {first_id + n: (c, {}) for n, c in enumerate(corners)}
    ids = list(nodes)
    return nodes, ids + ids[:1]


def read_extract(path: Path) -> list[ExtractObject]:
    """-> [(type letter, id, tags, extra)] in file order; `extra` is a
    node's (lon, lat) or a way's node ids."""
    out: list[ExtractObject] = []
    for o in osmium.FileProcessor(str(path)):
        extra: Extra = (
            (o.location.lon, o.location.lat)
            if isinstance(o, osmium.osm.Node)
            else [n.ref for n in o.nodes]
            if isinstance(o, osmium.osm.Way)
            else None
        )
        out.append((o.type_str(), o.id, dict(o.tags), extra))
    return out


def box(west: float, south: float, east: float, north: float) -> list[LonLat]:
    """The corners of a rectangle, counter-clockwise from its south-west."""
    return [(west, south), (east, south), (east, north), (west, north)]


def areas_geojson(areas: Iterable[tuple[str, Sequence[LonLat]]]) -> dict[str, Any]:
    """Dialect areas as the area build writes them: a FeatureCollection of
    one polygon per (dialect tag, corners)."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"dialect": tag},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[lon, lat] for lon, lat in [*corners, corners[0]]]],
                },
            }
            for tag, corners in areas
        ],
    }
