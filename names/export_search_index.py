#!/usr/bin/env python3
"""Export the rows of names/places.csv that are on the map as the client-side
search index used by web/ (web/public/data/names.json).

Coordinates come from names/work/matches.csv, which names/match.py writes --
run match.py first (it also looks up the position of rows a human filled in).

Usage: names/export_search_index.py [--names names/places.csv]
                                    [--matches names/work/matches.csv]
                                    [--out web/public/data/names.json]
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--matches", default=os.path.join(HERE, "work", "matches.csv"))
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "public", "data", "names.json"))
    a = ap.parse_args()
    if not os.path.exists(a.matches):
        raise SystemExit(f"{a.matches} not found -- run names/match.py first")
    with open(a.matches, encoding="utf-8", newline="") as fh:
        coords = {int(m["line"]): (m["lon"], m["lat"]) for m in csv.DictReader(fh)}
    rows, _ = placelist.read(a.names)
    out, skipped, seen = [], 0, set()
    for r in rows:
        name = placelist.label(r)
        if not name or r["status"] == "skip" or r["kind"] == "not_a_place":
            continue
        if not (r["osm"] or r["wikidata"]):
            continue
        lon, lat = coords.get(r["_line"], ("", ""))
        if not (lon and lat):
            skipped += 1
            continue
        refs = placelist.parse_osm(r["osm"])
        ident = placelist.format_osm(refs[:1]) if refs else r["wikidata"]
        # several rows may point at the same object (Mooring + older
        # spelling); keep both searchable with a unique id
        if ident in seen:
            ident = f"{ident}#{r['_line']}"
        seen.add(ident)
        out.append({
            "id": ident,
            "name": name,
            "name_de": placelist.primary(r["de"]),
            "lon": round(float(lon), 5),
            "lat": round(float(lat), 5),
            "kind": r["kind"],
        })
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {len(out)} entries to {a.out} ({os.path.getsize(a.out)/1e3:.0f} kB); "
          f"skipped {skipped} without coordinates")


if __name__ == "__main__":
    main()
