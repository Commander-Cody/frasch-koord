#!/usr/bin/env python3
"""Export the rows of names/places.csv that are on the map as the client-side
search index used by web/ (web/public/data/names.json).

Every dialect name of a place is searchable, not only the one the map
currently labels with: somebody who knows a Hallig as *Hansweerf* must find it
while the map shows Mooring.

Where a place is, and so which dialect is the *local* one there, comes from
names/osm_objects.json (names/locate.py) and names/dialect_areas.geojson --
the same files, read through the same `locate.dialect_at`, as the injector
uses for the tiles, so a search result and the map label agree.  An entry
lies where the first object of its row's `osm` cell lies.  A row for a place
OSM does not have (`osm` = `local/<slug>`) takes its position from the
curation row with the same reference (names/curation.csv).  The Low Saxon
name (`name_nds`) is the object's OSM `name:nds`: the name list has no Low
Saxon column, but the map labels with it before German, and the card and
search results have to agree with it.

A row with an OSM reference the objects file does not know stops the export
-- it is on the map, and would be missing from search.  Re-run
`just objects` after giving a row a new reference.  Rows keyed by a Wikidata
QID alone (the countries) have no position and are left out.

The output records what it was built from (`built_from`, see
names/provenance.py); the tiles carry the same stamp, and the frontend warns
when the two differ.

An entry's `id` is its row's `id` -- the same string the injector writes into
the tiles as `frasch:ref`, which is how a click on a map label finds the entry
it belongs to (web/src/names.ts).  Its `osm` is the row's `osm` cell, for the
card's link to OpenStreetMap and for the share links and tiles from before the
row ids, which name a place by its first OSM reference (or its QID).

Usage: names/export_search_index.py [--names names/places.csv]
                                    [--dialects names/dialects.csv]
                                    [--areas names/dialect_areas.geojson]
                                    [--objects names/osm_objects.json]
                                    [--curation names/curation.csv]
                                    [--out web/public/data/names.json]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import placelist  # noqa: E402
import dialects  # noqa: E402
import locate  # noqa: E402
import provenance  # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "web", "public", "data", "names.json")


def entry_object(row, objects, local_points, where):
    """Where a row's entry lies: the object of the first reference in its
    `osm` cell, or the curation position of its local reference.  None for
    a row keyed by its QID alone; a KeyError for a reference nobody located."""
    slug = placelist.local_ref(row["osm"])
    if slug:
        if slug not in local_points:
            raise SystemExit(f"{where}: local/{slug} has no row with lat/lon "
                             f"in the curation file")
        lon, lat = local_points[slug]
        return {"lon": lon, "lat": lat}
    refs = placelist.parse_osm(row["osm"], where)
    if not refs:
        return None
    return objects.by_ref[refs[0]]


def entry(row, obj, areas, reg) -> dict:
    """The search-index entry of one row whose object is `obj`."""
    area_tag = locate.dialect_at(obj, areas)
    names = {}
    for d in reg:
        name = dialects.dialect_name(row, d["tag"], area_tag, reg)
        if name:
            names[d["tag"]] = name
    out = {
        "id": row["id"],
        "names": names,
        "name_de": placelist.primary(row["de"]),
        "lon": round(float(obj["lon"]), 5),
        "lat": round(float(obj["lat"]), 5),
        "kind": row["kind"],
    }
    optional = {
        "local": dialects.local_name(row, area_tag, reg),
        "dialect": area_tag,
        "variety": dialects.variety(row),
        "name_nds": obj.get("name_nds"),
        "name_da": placelist.primary(row["da"]),
        "osm": row["osm"],
        "wikidata": row["wikidata"],
    }
    return out | {k: v for k, v in optional.items() if v}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--dialects", default=dialects.DEFAULT_PATH)
    ap.add_argument("--areas", default=dialects.DEFAULT_AREAS)
    ap.add_argument("--objects", default=locate.DEFAULT_OUT)
    ap.add_argument("--curation", default=placelist.CURATION_PATH,
                    help="positions of the local references (places OSM does not have)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    reg = dialects.read(a.dialects)
    if not os.path.exists(a.areas):
        raise SystemExit(f"{a.areas} not found -- build it with `just areas`")
    areas = dialects.AreaIndex.from_geojson(a.areas)
    objects = locate.read_objects(a.objects)
    local_points = placelist.local_points(a.curation)
    rows, _ = placelist.read(a.names)

    out, unlocated, qid_only = [], [], 0
    for r in rows:
        if not placelist.on_map(r):
            continue
        where = f"{a.names}:{r['_line']}"
        try:
            obj = entry_object(r, objects, local_points, where)
        except KeyError as missing:
            unlocated.append(f"  {r['id']} (line {r['_line']}): "
                             f"{placelist.format_osm([missing.args[0]])}")
            continue
        if obj is None:
            qid_only += int(bool(r["wikidata"]))
            continue
        out.append(entry(r, obj, areas, reg))
    if unlocated:
        raise SystemExit(f"{len(unlocated)} row(s) on the map have an object that "
                         f"{a.objects} does not know -- run `just objects` "
                         f"(names/locate.py) to locate them:\n" + "\n".join(unlocated))

    stamp = provenance.stamp(a.names, a.dialects, a.curation, a.areas, a.objects)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    placelist.atomic_write(a.out, json.dumps({"built_from": stamp, "places": out},
                                             ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"wrote {len(out)} entries to {a.out} ({os.path.getsize(a.out)/1e3:.0f} kB); "
          f"{sum(1 for e in out if 'dialect' in e)} in a dialect area, "
          f"{sum(1 for e in out if 'local' in e)} with a local name, "
          f"{sum(1 for e in out if 'name_nds' in e)} with a Low Saxon one; "
          f"left out {qid_only} keyed by Wikidata alone (no position)")


if __name__ == "__main__":
    main()
