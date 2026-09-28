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
from typing import NamedTuple


from frasch import cli, osmgeom, osmscan, files, paths, placelist, provenance
from frasch.errors import PipelineError

DEFAULT_OUT = paths.OBJECTS
ROUND = 6


def mapped_refs(rows) -> set:
    """The OSM references (not the local ones) of the rows on the map."""
    return {ref for row in rows if placelist.on_map(row)
            for ref in placelist.parse_osm(row["osm"])
            if ref[0] != placelist.LOCAL_TYPE}


def locate(pbfs, refs) -> dict:
    """-> {ref: object} for the references found in the extract(s); an
    object found in an earlier extract is not looked up again."""
    found = {}
    for pbf in pbfs:
        todo = {ref for ref in refs if ref not in found}
        if todo:
            found.update(locate_in(str(pbf), todo))
    return found


def locate_in(pbf, refs) -> dict:
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
    found = {}
    for ref in refs:
        t, i = ref
        if t == "n":
            obj = _node_object(nodes.get(i))
        else:
            source = relations.get(i) if t == "r" else ways.get(i)
            obj = _area_object(ref, source, rel_rings, way_nodes, locs)
        if obj is not None:
            tags = (nodes if t == "n" else relations if t == "r" else ways)[i]["tags"]
            found[ref] = obj | object_facts(tags)
    return found


def object_facts(tags) -> dict:
    """What else the search index needs to know about an object:

    admin_level  of an administrative boundary -- one above municipality level
                 (a Kreis, an Amt) spans several dialects, see `dialect_at`
    name_nds     its Low Saxon name: the name list has no Low Saxon column,
                 but the map labels with OSM's `name:nds` before German, and
                 the place card must name the place as its label does"""
    facts = {}
    level = tags.get("admin_level", "")
    if tags.get("boundary") == "administrative" and level.isdigit():
        facts["admin_level"] = int(level)
    if tags.get("name:nds"):
        facts["name_nds"] = tags["name:nds"]
    return facts


def _node_object(node):
    if node is None:
        return None
    lon, lat = node["loc"]
    return {"lon": lon, "lat": lat}


def _area_object(ref, source, rel_rings, way_nodes, locs):
    """A way or relation: inside its polygon if it closes into one, else at
    its outline point; the outline point is kept for the dialect lookup."""
    if source is None:
        return None
    outline = _outline_point(ref, source, rel_rings, way_nodes, locs)
    inside = _inside_point(ref, rel_rings, way_nodes, locs)
    point = inside or outline
    if point is None:
        return None
    obj = {"lon": point[0], "lat": point[1]}
    if inside and outline:
        obj["outline"] = list(outline)
    return obj


def _inside_point(ref, rel_rings, way_nodes, locs):
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


def _outline_point(ref, source, rel_rings, way_nodes, locs):
    """The relation's `label` / `admin_centre` member node, else the first
    vertex of its first outer way the extract holds (of a way: its own first
    vertex).  An extract holds a sea or a large area only in part: the North
    Sea's label node lies offshore, outside every extract but a planet."""
    t, i = ref
    if t == "r" and source["label"] in locs:
        return locs[source["label"]]
    first = way_nodes.get(i) if t == "w" else next(
        (way_nodes[w] for w in rel_rings[i]["outer"] if w in way_nodes), None)
    return locs.get(first[0]) if first else None


# -------------------------------------------------------------- dialects ----
# OSM's admin_level of a German municipality; anything lower is a Kreis or an
# Amt, which spans several dialects
MUNICIPALITY_LEVEL = 8


def dialect_at(obj, areas) -> str | None:
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
    for lon, lat in [(obj["lon"], obj["lat"])] + ([obj["outline"]] if "outline" in obj else []):
        tag = areas.lookup(lon, lat)
        if tag:
            return tag
    return None


class Objects(NamedTuple):
    """The objects file, read back: `by_ref` maps ('w', 12) to its object."""
    by_ref: dict
    built_from: dict


def read_objects(path: str = DEFAULT_OUT) -> Objects:
    if not os.path.exists(path):
        raise PipelineError(f"{path} not found -- build it with `just objects` "
                         f"(names/locate.py)")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    by_ref = {placelist.parse_osm(ref)[0]: obj for ref, obj in data["objects"].items()}
    return Objects(by_ref, data["built_from"])


def objects_json(objects: Objects) -> str:
    """The file's text: one object per line, in reference order, so a re-run
    on a moved object is a one-line diff."""
    lines = [f"{json.dumps(placelist.format_osm([ref]))}:{_compact(_rounded(obj))}"
             for ref, obj in sorted(objects.by_ref.items(), key=_ref_order)]
    return (f'{{"built_from":{_compact(objects.built_from)},\n"objects":{{\n'
            + ",\n".join(lines) + "\n}}\n")


def _compact(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _ref_order(item):
    (t, i), _ = item
    return "nwr".index(t), i


def _rounded(obj):
    return {k: (round(v, ROUND) if isinstance(v, float)
                else [round(x, ROUND) for x in v] if isinstance(v, list) else v)
            for k, v in obj.items()}


@cli.command
def main(argv=None):
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

