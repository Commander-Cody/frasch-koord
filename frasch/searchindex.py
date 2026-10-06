"""The client-side search index of web/ (web/public/data/names.json): the
rows of names/places.csv that are on the map, built by `build` and written
by `write` (`frasch index` runs the two).

Every dialect name of a place is searchable, not only the one the map
currently labels with: somebody who knows a Hallig as *Hansweerf* must find it
while the map shows Mooring.

Where a place is, and so which dialect is the *local* one there, comes from
names/osm_objects.json (`frasch objects`) and names/dialect_areas.geojson --
the same files, read through the same `objects.dialect_at`, as the injector
uses for the tiles, so a search result and the map label agree.  An entry
lies where the first object of its row's `osm` cell lies.  A row for a place
OSM does not have (`osm` = `local/<slug>`) takes its position from the
curation row with the same reference (names/curation.csv).  The Low Saxon
name (`name_nds`) is the object's OSM `name:nds`: the name list has no Low
Saxon column, but the map labels with it before German, and the card and
search results have to agree with it.  The generic name (`name_osm`) is the
object's OSM `name`, for the same reason: it is the chain's generic step
near its end, and north of the border it is the Danish name, not the list's
German one.  A local reference gets the `name` the injector gives its point.
The local name (`local`) of a row that has none is the object's OSM
`name:frr` inside a dialect area (`dialects.osm_local_name`), as the injector
writes it into `frasch:local` (#81).

A row with an OSM reference the objects file does not know stops the export
-- it is on the map, and would be missing from search.  Re-run
`just objects` after giving a row a new reference.  Rows keyed by a Wikidata
QID alone (the countries) have no position and are left out.

The output records what it was built from (`built_from`, see
frasch.provenance); the tiles carry the same stamp, and the frontend warns
when the two differ.

An entry's `id` is its row's `id` -- the same string the injector writes into
the tiles as `frasch:ref`, which is how a click on a map label finds the entry
it belongs to (web/src/names.ts).  Its `osm` is the row's `osm` cell, for the
card's link to OpenStreetMap and for the share links and tiles from before the
row ids, which name a place by its first OSM reference (or its QID).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import NotRequired, TypedDict

from frasch import (
    cli,
    curationlist,
    dialects,
    files,
    placelist,
    provenance,
    registry,
)
from frasch.errors import PipelineError
from frasch.geo import LonLat
from frasch.objects import LocatedObject, Objects, dialect_at, read_objects
from frasch.paths import Workspace
from frasch.placelist import Row
from frasch.registry import Registry


class SearchEntry(TypedDict):
    """One place of the index (web/src/names.ts reads it); the optional
    fields are left out when empty."""

    id: str
    names: dict[str, str]  # dialect tag -> name
    name_de: str
    lon: float
    lat: float
    kind: str
    local: NotRequired[str]
    dialect: NotRequired[str]
    variety: NotRequired[str]
    name_nds: NotRequired[str]
    name_osm: NotRequired[str]
    name_da: NotRequired[str]
    osm: NotRequired[str]
    wikidata: NotRequired[str]


class SearchIndex(TypedDict):
    built_from: provenance.BuiltFrom
    places: list[SearchEntry]


def entry_object(
    row: Row, objects: Objects, local_points: Mapping[str, LonLat], reg: Registry, where: str
) -> LocatedObject | None:
    """The object a row's entry stands for: the object of the first reference
    in its `osm` cell, or for a local reference the point the injector adds --
    at its curation position, with the name the injector gives it.  None for
    a row keyed by its QID alone; a KeyError for a reference nobody located."""
    slug = placelist.local_ref(row["osm"])
    if slug:
        if slug not in local_points:
            raise PipelineError(
                f"{where}: local/{slug} has no row with lat/lon in the curation file"
            )
        lon, lat = local_points[slug]
        point: LocatedObject = {"lon": lon, "lat": lat}
        if name := placelist.point_name(row, reg):
            point["name"] = name
        return point
    refs = placelist.osm_refs(row["osm"], where)
    if not refs:
        return None
    return objects.by_ref[refs[0]]


def entry(row: Row, obj: LocatedObject, areas: dialects.AreaIndex, reg: Registry) -> SearchEntry:
    """The search-index entry of one row whose object is `obj`."""
    area_tag = dialect_at(obj, areas)
    names: dict[str, str] = {}
    for d in reg:
        name = dialects.dialect_name(row, d["tag"], area_tag, reg)
        if name:
            names[d["tag"]] = name
    out: SearchEntry = {
        "id": row["id"],
        "names": names,
        "name_de": placelist.primary(row["de"]),
        "lon": round(float(obj["lon"]), 5),
        "lat": round(float(obj["lat"]), 5),
        "kind": row["kind"],
    }
    if local := dialects.local_name(row, area_tag, reg) or dialects.osm_local_name(
        obj.get("name_frr"), area_tag
    ):
        out["local"] = local
    if area_tag:
        out["dialect"] = area_tag
    if variety := dialects.variety(row):
        out["variety"] = variety
    if name_nds := obj.get("name_nds"):
        out["name_nds"] = name_nds
    if name_osm := obj.get("name"):
        out["name_osm"] = name_osm
    if name_da := placelist.primary(row["da"]):
        out["name_da"] = name_da
    if row["osm"]:
        out["osm"] = row["osm"]
    if row["wikidata"]:
        out["wikidata"] = row["wikidata"]
    return out


def build(ws: Workspace, reg: Registry) -> SearchIndex:
    """The search index, `{"built_from", "places"}`, from its input files."""
    if not os.path.exists(ws.areas):
        raise PipelineError(f"{ws.areas} not found -- build it with `just areas`")
    areas = dialects.AreaIndex.from_geojson(ws.areas)
    objects = read_objects(ws.objects)
    local_points = curationlist.local_points(ws.curation)
    rows, _ = placelist.read(ws.names, reg)

    places: list[SearchEntry] = []
    unlocated: list[str] = []
    for r in rows:
        if not placelist.on_map(r, reg):
            continue
        try:
            obj = entry_object(r, objects, local_points, reg, f"{ws.names}:{r.line}")
        except KeyError as missing:
            unlocated.append(
                f"  {r['id']} (line {r.line}): {placelist.format_osm([missing.args[0]])}"
            )
            continue
        if obj is not None:
            places.append(entry(r, obj, areas, reg))
    if unlocated:
        raise PipelineError(
            f"{len(unlocated)} row(s) on the map have an object that "
            f"{ws.objects} does not know -- run `just objects` "
            f"to locate them:\n" + "\n".join(unlocated)
        )
    return {"built_from": provenance.stamp(ws), "places": places}


def write(index: SearchIndex, out: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    files.atomic_write(out, json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n")


def run(ws: Workspace, reg: Registry) -> None:
    """Build the search index, write it and say what it holds."""
    index = build(ws, reg)
    write(index, ws.index)
    places = index["places"]
    print(
        f"wrote {len(places)} entries to {ws.index} "
        f"({os.path.getsize(ws.index) / 1e3:.0f} kB); "
        f"{sum(1 for e in places if 'dialect' in e)} in a dialect area, "
        f"{sum(1 for e in places if 'local' in e)} with a local name, "
        f"{sum(1 for e in places if 'name_nds' in e)} with a Low Saxon one; "
        f"rows keyed by Wikidata alone (no position) are left out"
    )


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("index", __doc__)
    cli.add_workspace_options(ap, "names", "dialects", "curation", "areas", "objects", "index")
    ws = cli.workspace(ap.parse_args(argv))
    run(ws, registry.read(ws.dialects))
    return 0
