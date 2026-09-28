"""A tiny OSM extract written with pyosmium, for the tests that read one."""
from __future__ import annotations

import osmium


def write_extract(path, nodes=None, ways=None, relations=None, timestamp=None):
    """Write an extract to `path` in node/way/relation order, ids ascending.

    nodes      {id: ((lon, lat), {tags})}
    ways       {id: ([node ids], {tags})}
    relations  {id: ([(type letter, ref, role)], {tags})}
    timestamp  the header's `osmosis_replication_timestamp`, if any
    """
    header = osmium.io.Header()
    if timestamp:
        header.set("osmosis_replication_timestamp", timestamp)
    Node, Way, Relation = (osmium.osm.mutable.Node, osmium.osm.mutable.Way,
                           osmium.osm.mutable.Relation)
    w = osmium.SimpleWriter(str(path), overwrite=True, header=header)
    try:
        for i, (loc, tags) in sorted((nodes or {}).items()):
            w.add_node(Node(id=i, version=1, visible=True, location=loc, tags=tags))
        for i, (refs, tags) in sorted((ways or {}).items()):
            w.add_way(Way(id=i, version=1, visible=True, nodes=refs, tags=tags))
        for i, (members, tags) in sorted((relations or {}).items()):
            w.add_relation(Relation(id=i, version=1, visible=True, members=members,
                                    tags=tags))
    finally:
        w.close()
    return path


def ring(first_id, *corners):
    """Nodes {id: ((lon, lat), {})} and the closed way's node list for a ring
    through `corners`, ids counting up from `first_id`."""
    nodes = {first_id + n: (c, {}) for n, c in enumerate(corners)}
    ids = list(nodes)
    return nodes, ids + ids[:1]
