"""Where the objects of the name list are: OSM extract(s) -> names/osm_objects.json.

The map labels and the search index must agree on where a place is and
therefore on which dialect is spoken there (`frasch:dialect`, `frasch:local`).
They used to work that out separately -- the injector from the extract it
tags, the search export from the matcher's cache of vertex averages, days
apart -- and disagreed on Sylt, Amrum, Stiardebel and more (#24).  Now it is
worked out once, here, and both read the result (`frasch build objects`).

What the file records, and why it is committed: frasch.objects.
"""

from __future__ import annotations

import os
from collections.abc import Collection, Iterable, Mapping, Sequence

from shapely.errors import GEOSException

from frasch import files, osmgeom, osmscan, placelist, placeobjects, refs
from frasch.dialects import Registry
from frasch.geo import LonLat
from frasch.objects import Facts, LocatedObject, Objects, Point, objects_json
from frasch.osmscan import Geometry
from frasch.paths import StrPath, Workspace
from frasch.provenance import Stamp
from frasch.refs import OsmRef


def locate(pbfs: Iterable[StrPath], refs: Collection[OsmRef]) -> dict[OsmRef, LocatedObject]:
    """-> {ref: object} for the references found in the extract(s); an
    object found in an earlier extract is not looked up again."""
    return osmscan.across(pbfs, refs, locate_in)


def locate_in(pbf: StrPath, refs: Collection[OsmRef]) -> dict[OsmRef, LocatedObject]:
    """One extract: where each of `refs` it holds is, with the object's
    facts.  Read in id-filtered passes (osmscan.read_geometry)."""
    geometry = osmscan.read_geometry(pbf, refs)
    found: dict[OsmRef, LocatedObject] = {}
    for ref in refs:
        point, tags = _located(ref, geometry)
        if point is not None:
            found[ref] = {**point, **object_facts(tags)}
    return found


def _located(ref: OsmRef, geometry: Geometry) -> tuple[Point | None, Mapping[str, str]]:
    """-> (where the object is, its tags); (None, {}) for one `geometry`
    does not hold or has no position for."""
    kind, i = ref
    if kind == "n":
        node = geometry.nodes.get(i)
        return (None, {}) if node is None else (_node_object(node), node["tags"])
    if kind == "r":
        relation = geometry.relations.get(i)
        if relation is None:
            return None, {}
        return _area_object(ref, relation["label"], geometry), relation["tags"]
    way = geometry.ways.get(i)
    return (None, {}) if way is None else (_area_object(ref, None, geometry), way["tags"])


def object_facts(tags: Mapping[str, str]) -> Facts:
    """What else the search index needs to know about an object:

    admin_level  of an administrative boundary -- one above municipality level
                 (a Kreis, an Amt) spans several dialects, see `dialect_at`
    name_nds     its Low Saxon name: the name list has no Low Saxon column,
                 but the map labels with OSM's `name:nds` before German, and
                 the place card must name the place as its label does
    name         its generic name, for the same reason: the local view labels
                 a place without a local or Low Saxon name with it, and north
                 of the border it is the Danish name, not the list's German
    name_frr     its Frisian name of no stated dialect: inside a dialect area
                 it is the local name of a place the list gives none
                 (frasch.placenames)"""
    facts: Facts = {}
    level = tags.get("admin_level", "")
    if tags.get("boundary") == "administrative" and level.isdigit():
        facts["admin_level"] = int(level)
    if tags.get("name:nds"):
        facts["name_nds"] = tags["name:nds"]
    if tags.get("name"):
        facts["name"] = tags["name"]
    if tags.get("name:frr"):
        facts["name_frr"] = tags["name:frr"]
    return facts


def _node_object(node: osmscan.Node) -> Point:
    lon, lat = node["loc"]
    return {"lon": lon, "lat": lat}


def _area_object(ref: OsmRef, label: int | None, geometry: Geometry) -> Point | None:
    """A way or relation: inside its polygon if it closes into one, else at
    its outline point; the outline point is kept for the dialect lookup.
    `label`: a relation's label node (osmscan.relations)."""
    outline = _outline_point(ref, label, geometry)
    inside = _inside_point(ref, geometry)
    point = inside or outline
    if point is None:
        return None
    obj: Point = {"lon": point[0], "lat": point[1]}
    if inside and outline:
        obj["outline"] = list(outline)
    return obj


def _inside_point(ref: OsmRef, geometry: Geometry) -> LonLat | None:
    """A point inside the object's own polygon, or None when it does not
    close.  Ring assembly is frasch.osmgeom's, so a place and the areas it
    is compared against are read out of OSM the same way."""
    polygon = osmgeom.polygon_of(ref, geometry, [])
    if polygon is None or polygon.is_empty:
        return None
    try:
        p = polygon.representative_point()
    except GEOSException:  # a ring OSM leaves in a state GEOS cannot make a point of
        return None
    return p.x, p.y


def _outline_point(ref: OsmRef, label: int | None, geometry: Geometry) -> LonLat | None:
    """The relation's `label` / `admin_centre` member node, else the first
    vertex of its first outer way the extract holds (of a way: its own first
    vertex).  An extract holds a sea or a large area only in part: the North
    Sea's label node lies offshore, outside every extract but a planet."""
    kind, i = ref
    ways, nodes = geometry.ways, geometry.nodes
    if label is not None and label in nodes:
        return nodes[label]["loc"]
    own = [i] if kind == "w" else geometry.relations[i]["rings"]["outer"]
    first = next((ways[w]["nodes"] for w in own if w in ways), None)
    if first is None or first[0] not in nodes:
        return None
    return nodes[first[0]]["loc"]


def wanted_refs(ws: Workspace, reg: Registry) -> set[OsmRef]:
    """The OSM references of the rows on the map, as the name list has them now."""
    rows = placelist.read(ws.names, reg).rows
    return set(placeobjects.named(rows, reg))


def located(refs: Collection[OsmRef], pbfs: Sequence[StrPath]) -> Objects:
    """The objects `refs` found in the extracts `pbfs`, stamped with them,
    and the references none of them holds."""
    found = locate(pbfs, refs)
    not_found = frozenset(refs) - set(found)
    return Objects(found, Stamp.of({}, osmscan.extract_stamps(pbfs)), not_found)


def run(ws: Workspace, reg: Registry, pbfs: Sequence[StrPath]) -> None:
    """Locate the objects, write the objects file and say what is missing."""
    wanted = wanted_refs(ws, reg)
    objects = located(wanted, pbfs)
    files.atomic_write(ws.objects, objects_json(objects))
    print(f"wrote {ws.objects}: {len(objects.by_ref)} of {len(wanted)} objects located")
    if objects.not_found:
        # the search export and the injector stop on these; fix the rows
        print(
            f"{len(objects.not_found)} not in {', '.join(os.path.basename(p) for p in pbfs)}: "
            + ", ".join(refs.format([ref]) for ref in objects.missing(wanted))
        )
