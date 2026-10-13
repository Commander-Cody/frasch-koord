"""An OSM object's polygon, built from what frasch.osmscan read.

pyosmium could assemble the areas itself, but only of the whole extract and
with a location cache for it (see osmscan); so the rings are joined here,
from the member ways and node locations of the objects asked for.  The dialect areas
and a place's point inside its own polygon (frasch.locate) both use this,
so a place and the areas it is compared against are read out of OSM the
same way."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from frasch import refs
from frasch.osmscan import Geometry
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


def polygon_of(ref: OsmRef, geometry: Geometry, problems: list[str]) -> BaseGeometry | None:
    """The shapely polygon of one referenced object, of what `geometry`
    (osmscan.read_geometry) holds of it: a way's own ring, a relation's
    outer rings minus its inner ones.  None when the extract lacks the
    object or no outer ring of it closes.

    problems  gets a message for every member way or node the extract
              lacks, and every ring that does not close"""
    kind, i = ref
    if kind == "w":
        own = _polygons(ref, [i], "outer", geometry, problems) if i in geometry.ways else []
        return own[0] if own else None
    relation = geometry.relations.get(i) if kind == "r" else None
    if relation is None:
        return None
    outer = _polygons(ref, relation["rings"]["outer"], "outer", geometry, problems)
    inner = _polygons(ref, relation["rings"]["inner"], "inner", geometry, problems)
    if not outer:
        return None
    area = unary_union(outer)
    return area.difference(unary_union(inner)) if inner else area


def _polygons(
    ref: OsmRef, way_ids: Iterable[int], what: str, geometry: Geometry, problems: list[str]
) -> list[BaseGeometry]:
    """The valid polygons of the closed rings the ways `way_ids` form."""
    ways, nodes = geometry.ways, geometry.nodes
    where = refs.format([ref])
    missing = [w for w in way_ids if w not in ways]
    if missing:
        problems.append(f"{where}: {len(missing)} {what} way(s) not in the file")
    rings, unclosed = assemble_rings([ways[w]["nodes"] for w in way_ids if w in ways])
    if unclosed:
        problems.append(f"{where}: {len(unclosed)} unclosed {what} ring(s) -- skipped")
    out: list[BaseGeometry] = []
    for ring in rings:
        if any(n not in nodes for n in ring):
            problems.append(f"{where}: a {what} ring has nodes that are not in the file -- skipped")
            continue
        poly = Polygon([nodes[n]["loc"] for n in ring])
        out.append(poly if poly.is_valid else poly.buffer(0))
    return out
