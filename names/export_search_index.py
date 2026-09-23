#!/usr/bin/env python3
"""Export the rows of names/places.csv that are on the map as the client-side
search index used by web/ (web/public/data/names.json), and the dialect
registry the frontend compiles in (web/src/generated/dialects.json).

Every dialect name of a place is searchable, not only the one the map
currently labels with: somebody who knows a Hallig as *Hansweerf* must find it
while the map shows Mooring.  Which dialect is the *local* one at a place
comes from names/dialect_areas.geojson, the same file the injector uses, so
search results and tile labels agree.

Coordinates come from names/work/matches.csv, which names/match.py writes --
run match.py first (it also looks up the position of rows a human filled in).
The Low Saxon name (`name_nds`) comes from there too: the name list has no Low
Saxon column, but the map labels with OSM's `name:nds` before German, and the
card and search results have to agree with it.
A row for a place OSM does not have (`osm` = `local/<slug>`) takes its position
from the curation row with the same reference (names/curation.csv), and that
reference is the entry's id.

An entry's `id` is `placelist.entry_id` -- the same string the injector writes
into the tiles as `frasch:ref`, which is how a click on a map label finds the
entry it belongs to (web/src/names.ts).

Usage: names/export_search_index.py [--names names/places.csv]
                                    [--dialects names/dialects.csv]
                                    [--areas names/dialect_areas.geojson]
                                    [--matches names/work/matches.csv]
                                    [--curation names/curation.csv]
                                    [--out web/public/data/names.json]
                                    [--registry-out web/src/generated/dialects.json]
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import placelist  # noqa: E402
import dialects  # noqa: E402

REGISTRY_FIELDS = ["tag", "column", "label", "status", "view"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--dialects", default=dialects.DEFAULT_PATH)
    ap.add_argument("--areas", default=dialects.DEFAULT_AREAS)
    ap.add_argument("--matches", default=os.path.join(HERE, "work", "matches.csv"))
    ap.add_argument("--curation", default=placelist.CURATION_PATH,
                    help="positions of the local references (places OSM does not have)")
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "public", "data", "names.json"))
    ap.add_argument("--registry-out",
                    default=os.path.join(ROOT, "web", "src", "generated", "dialects.json"))
    a = ap.parse_args()
    if not os.path.exists(a.matches):
        raise SystemExit(f"{a.matches} not found -- run names/match.py first")
    reg = dialects.read(a.dialects)
    areas = None
    if os.path.exists(a.areas):
        areas = dialects.AreaIndex.from_geojson(a.areas)
    else:
        print(f"note: {a.areas} absent -- no `dialect` in the index "
              f"(build it with names/build_dialect_areas.py)")
    # matches.csv is keyed by physical line, which shifts as soon as a row is
    # added to or deleted from places.csv.  Coordinates are therefore looked
    # up by OSM reference first; the line is only trusted when the row it
    # points at is still the same place (`de`).
    by_osm, by_line, nds_by_osm = {}, {}, {}
    with open(a.matches, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if "name_nds" not in (reader.fieldnames or []):
            print(f"note: {os.path.relpath(a.matches, ROOT)} has no name_nds column "
                  f"-- re-run names/match.py to export Low Saxon names")
        for m in reader:
            if m["osm"] and m.get("name_nds"):
                nds_by_osm[m["osm"]] = m["name_nds"]
            pos = (m["lon"], m["lat"])
            if not (pos[0] and pos[1]):
                continue
            if m["osm"]:
                by_osm[m["osm"]] = pos
            by_line[int(m["line"])] = (pos, m["de"])
    local_points = placelist.local_points(a.curation)
    rows, _ = placelist.read(a.names)
    out, skipped, unnamed, seen, stale = [], 0, 0, set(), 0
    n_area = 0
    for r in rows:
        if r["status"] == "skip" or r["kind"] == "not_a_place":
            continue
        if not placelist.any_name(r):
            unnamed += 1
            continue
        if not (r["osm"] or r["wikidata"]):
            continue
        lon, lat = "", ""
        slug = placelist.local_ref(r["osm"])
        if slug:
            if slug not in local_points:
                raise SystemExit(f"{a.names}:{r['_line']}: local/{slug} has no row "
                                 f"with lat/lon in {a.curation}")
            lon, lat = local_points[slug]
        elif r["osm"] in by_osm:
            lon, lat = by_osm[r["osm"]]
        else:
            cached = by_line.get(r["_line"])
            if cached and cached[1] == r["de"]:
                lon, lat = cached[0]
            elif cached:
                stale += 1
        if lon == "" or lat == "":
            skipped += 1
            continue
        area_tag = areas.lookup(float(lon), float(lat)) if areas else None
        if area_tag:
            n_area += 1
        ident = placelist.entry_id(r)
        # several rows may point at the same object (two spellings, two
        # sheet sections); keep both searchable with a unique id
        if ident in seen:
            ident = f"{ident}#{r['_line']}"
        seen.add(ident)
        names = {}
        for d in reg:
            name = dialects.dialect_name(r, d["tag"], area_tag, reg)
            if name:
                names[d["tag"]] = name
        entry = {
            "id": ident,
            "names": names,
            "name_de": placelist.primary(r["de"]),
            "lon": round(float(lon), 5),
            "lat": round(float(lat), 5),
            "kind": r["kind"],
        }
        local = dialects.local_name(r, area_tag, reg)
        if local:
            entry["local"] = local
        if area_tag:
            entry["dialect"] = area_tag
        variety = dialects.variety(r)
        if variety:
            entry["variety"] = variety
        name_nds = nds_by_osm.get(r["osm"])
        if name_nds:
            entry["name_nds"] = name_nds
        name_da = placelist.primary(r["da"])
        if name_da:
            entry["name_da"] = name_da
        if r["wikidata"]:
            entry["wikidata"] = r["wikidata"]
        out.append(entry)

    for path, data in ((a.out, out),
                       (a.registry_out, [{k: d[k] for k in REGISTRY_FIELDS} for d in reg])):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
    print(f"wrote {len(out)} entries to {a.out} ({os.path.getsize(a.out)/1e3:.0f} kB); "
          f"{n_area} in a dialect area, "
          f"{sum(1 for e in out if 'local' in e)} with a local name, "
          f"{sum(1 for e in out if 'name_nds' in e)} with a Low Saxon one; "
          f"skipped {skipped} without coordinates, {unnamed} without a Frisian name")
    if stale:
        print(f"note: {stale} row(s) have moved to another line since "
              f"{os.path.relpath(a.matches, ROOT)} was written and lost their "
              f"position -- re-run names/match.py")
    print(f"wrote {len(reg)} dialects to {a.registry_out}")


if __name__ == "__main__":
    main()
