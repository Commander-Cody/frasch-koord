"""The client-side search index of web/ (web/public/data/names.json): the
rows of names/places.csv that are on the map, built by `build` and written
by `write` (`frasch build index` runs the two).

Every dialect name of a place is searchable, not only the one the map
currently labels with: somebody who knows a Hallig as *Hansweerf* must find it
while the map shows Mooring.

Which names an entry has is frasch.placenames' rule (`resolve`, written as
an entry by `as_entry`), the one the injector tags the tiles by.  Where a
place is, and so which dialect is the *local* one there, comes from
names/osm_objects.json (`frasch build objects`) and names/dialect_areas.geojson --
the same files as the injector uses for the tiles, so a search result and
the map label agree.  An entry lies where the first object of its row's
`osm` cell lies (`placeobjects.for_row`).  A row for a place OSM does not have
(`osm` = `local/<slug>`) takes its position from the curation row with the
same reference (names/curation.csv).  The Low Saxon
name (`name_nds`) is the object's OSM `name:nds`: the name list has no Low
Saxon column, but the map labels with it before German, and the card and
search results have to agree with it.  The generic name (`name_osm`) is the
object's OSM `name`, for the same reason: it is the chain's generic step
near its end, and north of the border it is the Danish name, not the list's
German one.  A local reference gets the `name` the injector gives its point.
The local name (`local`) of a row that has none is the object's OSM
`name:frr` inside a dialect area, as the injector writes it into
`frasch:local` (#81).

A row whose entry lies at an object the objects file has none for stops the
export -- it is on the map, and would be missing from search
(`placeobjects.require_located` says what helps).  Rows keyed by a Wikidata
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
from collections.abc import Iterable
from typing import TypedDict

from frasch import (
    curationlist,
    dialect_areas,
    files,
    placelist,
    placenames,
    placeobjects,
    provenance,
    refs,
)
from frasch.dialects import Registry
from frasch.errors import PipelineError, rebuild
from frasch.objects import read_objects
from frasch.paths import Workspace
from frasch.placelist import PlaceRow
from frasch.placenames import SearchEntry
from frasch.refs import OsmRef


class SearchIndex(TypedDict):
    """The file as a whole, as names/search-index.schema.json defines it."""

    built_from: provenance.BuiltFrom
    places: list[SearchEntry]


def entry_refs(rows: Iterable[PlaceRow]) -> dict[OsmRef, PlaceRow]:
    """The reference to an OSM object each row's entry lies at, with its row."""
    return {osm[0]: row for row in rows if (osm := refs.osm_only(refs.parse(row["osm"])))}


def build(ws: Workspace, reg: Registry) -> SearchIndex:
    """The search index, `{"built_from", "places"}`, from its input files."""
    if not os.path.exists(ws.areas):
        raise PipelineError(f"{ws.areas} not found -- build it with {rebuild('areas')}")
    areas = dialect_areas.AreaIndex.from_geojson(ws.areas)
    objects = read_objects(ws.objects)
    local_points = curationlist.local_points(ws.curation)
    rows, _ = placelist.read(ws.names, reg)

    on_map = [r for r in rows if placelist.on_map(r, reg)]
    placeobjects.require_located(objects, ws.objects, entry_refs(on_map))
    places: list[SearchEntry] = []
    for r in on_map:
        obj = placeobjects.for_row(objects, r, local_points, reg)
        if obj is not None:
            places.append(placenames.as_entry(placenames.resolve([r], obj, areas, reg), obj, r))
    return {"built_from": provenance.stamp(ws).as_json(), "places": places}


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
