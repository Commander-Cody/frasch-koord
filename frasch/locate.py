#!/usr/bin/env python3
"""Where the objects of the name list are: OSM extract(s) -> names/osm_objects.json.

The map labels and the search index must agree on where a place is and
therefore on which dialect is spoken there (`frasch:dialect`, `frasch:local`).
They used to work that out separately -- the injector from the extract it
tags, the search export from the matcher's cache of vertex averages, days
apart -- and disagreed on Sylt, Amrum, Stiardebel and more (#24).  Now it is
worked out once, here, and both read the result:

    locate.py <in.osm.pbf> [<in.osm.pbf> ...]
              [--names names/places.csv] [--out names/osm_objects.json]

For every OSM reference in the `osm` column of a row that is on the map, the
file records

  lon, lat     where the object is: a node's own location; for a way or
               relation that closes into a polygon, a point *inside* that
               polygon (shapely's `representative_point`) -- an island is not
               where its coastline starts, and a vertex average can lie in the
               sea; for anything else, the relation's `label` / `admin_centre`
               member, else the first vertex
  outline      the second point for the dialect lookup, see `dialect_at`
  admin_level  of an administrative boundary (see `object_facts`)
  name_nds     OSM's Low Saxon name (see `object_facts`)

and, as `built_from`, the extracts it was read from (names/provenance.py).

The file is **committed**, like names/dialect_areas.geojson: it is small, and
the search index can then be rebuilt -- and checked in CI -- without an
extract.  Re-run it (`just objects`) when a row gets a new `osm` reference;
the search export and the injector stop on a reference it does not know.
"""
from __future__ import annotations

import argparse
import json
import os
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import NamedTuple, NotRequired, Protocol, TypedDict

from frasch import cli, files, osmgeom, osmscan, paths, placelist, provenance
from frasch.errors import PipelineError
from frasch.geo import LonLat
from frasch.osmscan import Rings
from frasch.paths import StrPath
from frasch.placelist import OsmRef, Row

DEFAULT_OUT = paths.OBJECTS
ROUND = 6


class Facts(TypedDict, total=False):
    """See `object_facts`."""
    admin_level: int
    name_nds: str


class Point(TypedDict):
    lon: float
    lat: float
    outline: NotRequired[list[float]]


class LocatedObject(Point, Facts):
    """One object of the objects file: where it is (`lon`, `lat`, and for
    an area the `outline` point too) and its `object_facts`."""


def mapped_refs(rows: Iterable[Row]) -> set[OsmRef]:
    """The OSM references (not the local ones) of the rows on the map."""
    return {ref for row in rows if placelist.on_map(row)
            for ref in placelist.osm_refs(row["osm"])}


def locate(pbfs: Iterable[StrPath], refs: Collection[OsmRef]) -> dict[OsmRef, LocatedObject]:
    """-> {ref: object} for the references found in the extract(s); an
    object found in an earlier extract is not looked up again."""
    found: dict[OsmRef, LocatedObject] = {}
    for pbf in pbfs:
        todo = {ref for ref in refs if ref not in found}
        if todo:
            found.update(locate_in(str(pbf), todo))
    return found


def locate_in(pbf: StrPath, refs: Collection[OsmRef]) -> dict[OsmRef, LocatedObject]:
    """One extract: three id-filtered passes (the relations, their and the
    referenced ways, all their nodes) -- never a location cache for the
    whole file, which the dev machine has no memory for."""
    relations = osmscan.relations(pbf, {i for t, i in refs if t == "r"})
    way_ids = {i for t, i in refs if t == "w"}
    for rel in relations.values():
        way_ids |= set(rel["rings"]["outer"]) | set(rel["rings"]["inner"])
    ways = osmscan.ways(pbf, way_ids)
    node_ids = {i for t, i in refs if t == "n"}
    node_ids |= {r["label"] for r in relations.values() if r["label"] is not None}
    for way in ways.values():
        node_ids |= set(way["nodes"])
    nodes = osmscan.nodes(pbf, node_ids)
    locs = {i: n["loc"] for i, n in nodes.items()}
    rel_rings = {i: r["rings"] for i, r in relations.items()}
    way_nodes = {i: way["nodes"] for i, way in ways.items()}
    found: dict[OsmRef, LocatedObject] = {}
    for ref in refs:
        t, i = ref
        scanned: osmscan.Node | osmscan.Relation | osmscan.Way | None
        obj: Point | None = None
        if t == "n":
            scanned = nodes.get(i)
            obj = _node_object(scanned)
        elif t == "r":
            scanned = relations.get(i)
            if scanned is not None:
                obj = _area_object(ref, scanned["label"], rel_rings, way_nodes, locs)
        else:
            scanned = ways.get(i)
            if scanned is not None:
                obj = _area_object(ref, None, rel_rings, way_nodes, locs)
        if obj is not None and scanned is not None:
            found[ref] = {**obj, **object_facts(scanned["tags"])}
    return found


def object_facts(tags: Mapping[str, str]) -> Facts:
    """What else the search index needs to know about an object:

    admin_level  of an administrative boundary -- one above municipality level
                 (a Kreis, an Amt) spans several dialects, see `dialect_at`
    name_nds     its Low Saxon name: the name list has no Low Saxon column,
                 but the map labels with OSM's `name:nds` before German, and
                 the place card must name the place as its label does"""
    facts: Facts = {}
    level = tags.get("admin_level", "")
    if tags.get("boundary") == "administrative" and level.isdigit():
        facts["admin_level"] = int(level)
    if tags.get("name:nds"):
        facts["name_nds"] = tags["name:nds"]
    return facts


def _node_object(node: osmscan.Node | None) -> Point | None:
    if node is None:
        return None
    lon, lat = node["loc"]
    return {"lon": lon, "lat": lat}


def _area_object(ref: OsmRef, label: int | None,
                 rel_rings: Mapping[int, Rings], way_nodes: Mapping[int, Sequence[int]],
                 locs: Mapping[int, LonLat]) -> Point | None:
    """A way or relation: inside its polygon if it closes into one, else at
    its outline point; the outline point is kept for the dialect lookup.
    `label`: a relation's label node (osmscan.relations)."""
    outline = _outline_point(ref, label, rel_rings, way_nodes, locs)
    inside = _inside_point(ref, rel_rings, way_nodes, locs)
    point = inside or outline
    if point is None:
        return None
    obj: Point = {"lon": point[0], "lat": point[1]}
    if inside and outline:
        obj["outline"] = list(outline)
    return obj


def _inside_point(ref: OsmRef, rel_rings: Mapping[int, Rings],
                  way_nodes: Mapping[int, Sequence[int]],
                  locs: Mapping[int, LonLat]) -> LonLat | None:
    """A point inside the object's own polygon, or None when it does not
    close.  Ring assembly is frasch.osmgeom's, so a place and the areas it
    is compared against are read out of OSM the same way."""
    for geom in osmgeom.polygons_for(ref, rel_rings, way_nodes, locs, []):
        if geom.is_empty:
            continue
        try:
            p = geom.representative_point()
        except Exception:          # a ring OSM leaves in a state shapely
            continue               # cannot make a point of
        return p.x, p.y
    return None


def _outline_point(ref: OsmRef, label: int | None,
                   rel_rings: Mapping[int, Rings], way_nodes: Mapping[int, Sequence[int]],
                   locs: Mapping[int, LonLat]) -> LonLat | None:
    """The relation's `label` / `admin_centre` member node, else the first
    vertex of its first outer way the extract holds (of a way: its own first
    vertex).  An extract holds a sea or a large area only in part: the North
    Sea's label node lies offshore, outside every extract but a planet."""
    t, i = ref
    if label is not None and label in locs:
        return locs[label]
    first = way_nodes.get(i) if t == "w" else next(
        (way_nodes[w] for w in rel_rings[i]["outer"] if w in way_nodes), None)
    return locs.get(first[0]) if first else None


# -------------------------------------------------------------- dialects ----
# OSM's admin_level of a German municipality; anything lower is a Kreis or an
# Amt, which spans several dialects
MUNICIPALITY_LEVEL = 8


class DialectLookup(Protocol):
    """The dialect areas, as `dialect_at` asks them (frasch.dialects)."""

    def lookup(self, lon: float, lat: float) -> str | None: ...


def dialect_at(obj: LocatedObject, areas: DialectLookup | None) -> str | None:
    """The dialect spoken where an object of the objects file lies, or None:
    the area around its point, else the area around its outline point.

    The two points miss in opposite directions: an island's coastline runs
    outside the municipality boundaries the areas are cut from (Amrum), while
    an area may cover only part of an island (the Langeneß municipality holds
    only the south-west third of Oland), so the point inside the island falls
    outside it and a vertex still lands in it.  The first point that is in an
    area at all wins, so nothing that had a dialect can lose it.

    An administrative area above municipality level gets none: Kreis
    Nordfriesland would otherwise be "Nordergoesharde" because its interior
    point happens to lie there."""
    if areas is None or obj.get("admin_level", MUNICIPALITY_LEVEL) < MUNICIPALITY_LEVEL:
        return None
    points = [(obj["lon"], obj["lat"])]
    if "outline" in obj:
        points.append((obj["outline"][0], obj["outline"][1]))
    for lon, lat in points:
        tag = areas.lookup(lon, lat)
        if tag:
            return tag
    return None


class Objects(NamedTuple):
    """The objects file, read back: `by_ref` maps ('w', 12) to its object."""
    by_ref: dict[OsmRef, LocatedObject]
    built_from: provenance.BuiltFrom


def read_objects(path: str = DEFAULT_OUT) -> Objects:
    if not os.path.exists(path):
        raise PipelineError(f"{path} not found -- build it with `just objects` "
                         f"(names/locate.py)")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    by_ref = {placelist.osm_refs(ref)[0]: obj for ref, obj in data["objects"].items()}
    return Objects(by_ref, data["built_from"])


def objects_json(objects: Objects) -> str:
    """The file's text: one object per line, in reference order, so a re-run
    on a moved object is a one-line diff."""
    lines = [f"{json.dumps(placelist.format_osm([ref]))}:{_compact(_rounded(obj))}"
             for ref, obj in sorted(objects.by_ref.items(), key=_ref_order)]
    return (f'{{"built_from":{_compact(objects.built_from)},\n"objects":{{\n'
            + ",\n".join(lines) + "\n}}\n")


def _compact(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _ref_order(item: tuple[OsmRef, LocatedObject]) -> tuple[int, int]:
    (t, i), _ = item
    return "nwr".index(t), i


def _rounded(obj: LocatedObject) -> dict[str, object]:
    return {k: (round(v, ROUND) if isinstance(v, float)
                else [round(x, ROUND) for x in v] if isinstance(v, list) else v)
            for k, v in obj.items()}


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pbf", nargs="+", help="OSM extract(s) holding the objects")
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    rows, _ = placelist.read(a.names)
    refs = mapped_refs(rows)
    objects = Objects(locate(a.pbf, refs),
                      {"extracts": [provenance.extract_stamp(p) for p in a.pbf]})
    files.atomic_write(a.out, objects_json(objects))
    print(f"wrote {a.out}: {len(objects.by_ref)} of {len(refs)} objects located")
    missing = sorted(refs - set(objects.by_ref), key=lambda ref: ("nwr".index(ref[0]), ref[1]))
    if missing:
        # the search export and the injector stop on these; fix the rows
        print(f"{len(missing)} not in {', '.join(map(os.path.basename, a.pbf))}: "
              + ", ".join(placelist.format_osm([ref]) for ref in missing))
    return 0

