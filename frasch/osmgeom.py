"""An OSM object's polygon(s), built from what frasch.osmscan read.

pyosmium could assemble the areas itself, but only with a location cache for
the whole extract (see osmscan); so the rings are joined here, from the
member ways and node locations of the objects asked for.  The dialect areas
and a place's point inside its own polygon (frasch.locate) both use this,
so a place and the areas it is compared against are read out of OSM the
same way."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from shapely.geometry.base import BaseGeometry

from frasch import refs
from frasch.geo import LonLat
from frasch.osmscan import Rings
from frasch.refs import OsmRef


def assemble_rings(ways: Iterable[Sequence[int]]) -> tuple[list[list[int]], list[list[int]]]:
    """Join way node-lists end to end into closed rings.
    -> (rings, unclosed) as lists of node ids."""
    segments = [list(w) for w in ways if len(w) >= 2]
    rings: list[list[int]] = []
    unclosed: list[list[int]] = []
    while segments:
        cur = _chain(segments.pop(0), segments)
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
        else:
            unclosed.append(cur)
    return rings, unclosed


def _chain(cur: list[int], segments: list[list[int]]) -> list[int]:
    """`cur` extended by the `segments` that fit onto either end, until it
    closes or nothing fits any more; the used segments are removed."""
    joined = True
    while cur[0] != cur[-1] and joined:
        joined = False
        for i, seg in enumerate(segments):
            if seg[0] == cur[-1]:
                cur = cur + seg[1:]
            elif seg[-1] == cur[-1]:
                cur = cur + seg[-2::-1]
            elif seg[-1] == cur[0]:
                cur = seg[:-1] + cur
            elif seg[0] == cur[0]:
                cur = seg[:0:-1] + cur
            else:
                continue
            segments.pop(i)
            joined = True
            break
    return cur


def polygons_for(
    ref: OsmRef,
    rel: Mapping[int, Rings],
    ways: Mapping[int, Sequence[int]],
    nodes: Mapping[int, LonLat],
    problems: list[str],
) -> list[BaseGeometry]:
    """The shapely polygon(s) of one referenced object: a way's own ring, a
    relation's outer rings minus its inner ones.

    rel       {relation id: {"outer": [way ids], "inner": [way ids]}}
    ways      {way id: [node ids]}
    nodes     {node id: (lon, lat)}
    problems  gets a message for every member way or node the extract
              lacks, and every ring that does not close"""
    from shapely.ops import unary_union

    if ref[0] == "w":
        return _polygons(ref, [ref[1]], "outer", ways, nodes, problems) if ref[1] in ways else []
    rings = rel.get(ref[1])
    if rings is None:
        return []
    outer = _polygons(ref, rings["outer"], "outer", ways, nodes, problems)
    inner = _polygons(ref, rings["inner"], "inner", ways, nodes, problems)
    if not outer:
        return []
    geom = unary_union(outer)
    if inner:
        geom = geom.difference(unary_union(inner))
    return [geom]


def _polygons(
    ref: OsmRef,
    way_ids: Iterable[int],
    what: str,
    ways: Mapping[int, Sequence[int]],
    nodes: Mapping[int, LonLat],
    problems: list[str],
) -> list[BaseGeometry]:
    """The valid polygons of the closed rings the ways `way_ids` form."""
    from shapely.geometry import Polygon

    where = refs.format([ref])
    missing = [w for w in way_ids if w not in ways]
    if missing:
        problems.append(f"{where}: {len(missing)} {what} way(s) not in the file")
    rings, unclosed = assemble_rings([ways[w] for w in way_ids if w in ways])
    if unclosed:
        problems.append(f"{where}: {len(unclosed)} unclosed {what} ring(s) -- skipped")
    out: list[BaseGeometry] = []
    for ring in rings:
        if any(n not in nodes for n in ring):
            problems.append(f"{where}: a {what} ring has nodes that are not in the file -- skipped")
            continue
        poly = Polygon([nodes[n] for n in ring])
        out.append(poly if poly.is_valid else poly.buffer(0))
    return out
