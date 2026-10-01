"""A tiny OSM extract written with pyosmium, for the tests that read one."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import osmium

from frasch.geo import LonLat

Tags = Mapping[str, str]
Nodes = Mapping[int, tuple[LonLat, Tags]]
Ways = Mapping[int, tuple[Sequence[int], Tags]]
# a member is (type letter, ref, role)
Relations = Mapping[int, tuple[Sequence[tuple[str, int, str]], Tags]]
# `ring`'s nodes, a dict so tests can add to them
RingNodes = dict[int, tuple[LonLat, dict[str, str]]]


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
