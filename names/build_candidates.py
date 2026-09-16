#!/usr/bin/env python3
"""One pyosmium pass per OSM extract, collecting every named object that could
be a place / water / landscape / Warft / Koog / road / country.

Output: names/work/candidates.jsonl  (one JSON object per line)
  {"src","t","id","lon","lat","cls","tags":{...}}

Tag filter (object must carry a name-ish tag AND one of):
  place=*, natural=<water-ish/island-ish>, water=*, waterway=*, landuse=*,
  boundary=administrative|political|historic|maritime|land_area|place|
           protected_area,
  man_made=*, historic=*, amenity=harbour, harbour=*, leisure=marina,
  admin_level=*, wikidata=*, wikipedia=*,
  highway=*  -- only inside the North Frisia bbox (lon 8.2-9.5, lat 54.2-55.1)

Why these: a reconnaissance pass over Schleswig-Holstein showed that
  * Warften are mostly place=isolated_dwelling / place=hamlet nodes, plus
    landuse=residential|farmyard ways, place=locality and man_made=embankment;
  * Koge are place=hamlet / place=locality / place=polder nodes, sometimes only
    a highway or a waterway carries the name;
  * Halligen are place=island|islet ways (with natural=coastline) plus an
    admin boundary relation; some are only place=isolated_dwelling nodes;
  * historic Harden are essentially absent (only the modern Amter Arensharde
    and Hohner Harde exist as admin_level=7 relations);
  * big waters (Nordsee, Wattenmeer) are place=sea relations whose `name` is a
    multilingual slash-list -- only name:de is usable.

Run:  .venv/bin/python names/build_candidates.py tiles/data/*.osm.pbf
"""
from __future__ import annotations

import argparse
import array
import bisect
import collections
import json
import os
import sys
import time

import osmium

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "work", "candidates.jsonl")

NF_BBOX = (8.2, 54.2, 9.5, 55.1)          # lon_min, lat_min, lon_max, lat_max

NATURAL_KEEP = {
    "water", "bay", "strait", "wetland", "sand", "shoal", "beach", "island",
    "islet", "archipelago", "peninsula", "cape", "reef", "mud", "dune",
    "spring", "glacier", "isthmus", "hill", "ridge",
}
BOUNDARY_KEEP = {
    "administrative", "political", "historic", "maritime", "land_area",
    "place", "protected_area",
}
NAME_KEYS_EXTRA = ("alt_name", "old_name", "official_name", "loc_name",
                   "short_name", "int_name", "nat_name", "reg_name")
CLASS_KEYS = ("place", "natural", "water", "waterway", "landuse", "boundary",
              "man_made", "historic", "harbour", "leisure", "amenity",
              "highway", "admin_level", "type", "tourism", "building")
EXTRA_KEYS = ("wikidata", "wikipedia", "population", "ref")


def name_tags(tags: dict) -> dict:
    out = {}
    for k, v in tags.items():
        if k == "name" or k.startswith("name:") or k in NAME_KEYS_EXTRA:
            out[k] = v
    return out


def classify(tags: dict):
    """Return a sorted list of tag classes the object belongs to, or None."""
    cls = []
    if "place" in tags:
        cls.append("place=" + tags["place"])
    if tags.get("natural") in NATURAL_KEEP:
        cls.append("natural=" + tags["natural"])
    if "water" in tags:
        cls.append("water=" + tags["water"])
    if "waterway" in tags:
        cls.append("waterway=" + tags["waterway"])
    if "landuse" in tags:
        cls.append("landuse=" + tags["landuse"])
    if tags.get("boundary") in BOUNDARY_KEEP:
        cls.append("boundary=" + tags["boundary"])
    if "man_made" in tags:
        cls.append("man_made=" + tags["man_made"])
    if "historic" in tags:
        cls.append("historic=" + tags["historic"])
    if "harbour" in tags or tags.get("amenity") == "harbour":
        cls.append("harbour")
    if tags.get("leisure") == "marina":
        cls.append("marina")
    if "admin_level" in tags:
        cls.append("admin_level=" + tags["admin_level"])
    if "wikidata" in tags:
        cls.append("wikidata")
    elif "wikipedia" in tags:
        cls.append("wikipedia")
    return cls or None


def in_bbox(lon, lat, b=NF_BBOX):
    return lon is not None and b[0] <= lon <= b[2] and b[1] <= lat <= b[3]


class WayCentroids:
    """Compact way_id -> centroid store (ways arrive in ascending id order)."""

    def __init__(self):
        self.ids = array.array("q")
        self.lon = array.array("f")
        self.lat = array.array("f")
        self._sorted = True

    def add(self, wid, lon, lat):
        if self.ids and wid < self.ids[-1]:
            self._sorted = False
        self.ids.append(wid)
        self.lon.append(lon)
        self.lat.append(lat)

    def get(self, wid):
        if not self._sorted:
            return None
        i = bisect.bisect_left(self.ids, wid)
        if i < len(self.ids) and self.ids[i] == wid:
            return self.lon[i], self.lat[i]
        return None


def first_location(w):
    """Cheapest usable position of a way: its first resolvable node."""
    nodes = w.nodes
    for i in (0, len(nodes) // 2, -1):
        try:
            loc = nodes[i].location
        except (osmium.InvalidLocationError, IndexError):
            continue
        if loc.valid():
            return loc.lon, loc.lat
    return None


def way_centroid(w, sample=12):
    """Average of up to `sample` evenly spaced node locations (approximate)."""
    nodes = w.nodes
    ln = len(nodes)
    if not ln:
        return None
    step = max(1, ln // sample)
    n = 0
    sx = sy = 0.0
    for i in range(0, ln, step):
        try:
            loc = nodes[i].location
        except osmium.InvalidLocationError:
            continue
        if not loc.valid():
            continue
        sx += loc.lon
        sy += loc.lat
        n += 1
    if not n:
        return None
    return sx / n, sy / n


def has_name(tags) -> bool:
    """Cheap-first test for any name-ish tag (works on the C++ TagList)."""
    for k in ("name", "alt_name", "old_name", "official_name"):
        if k in tags:
            return True
    for k in tags:
        if k.k.startswith("name:"):
            return True
    return False


def process(pbf: str, src: str, out, counts, idx="flex_mem"):
    ways = WayCentroids()
    t0 = time.time()
    n_seen = 0
    fp = osmium.FileProcessor(pbf).with_locations(idx)
    for o in fp:
        n_seen += 1
        typ = o.type_str()          # 'n' | 'w' | 'r'
        otags = o.tags

        if typ == "w":
            # every way gets a cheap position so that relation centroids can be
            # averaged from their member ways further down the file
            c = first_location(o)
            if c:
                ways.add(o.id, c[0], c[1])
            if not otags or not has_name(otags):
                continue
            lon, lat = (way_centroid(o) or c or (None, None))
        elif typ == "n":
            if not otags or not has_name(otags):
                continue
            loc = o.location
            lon, lat = (loc.lon, loc.lat) if loc.valid() else (None, None)
        else:                        # relation
            if not otags or not has_name(otags):
                continue
            lon = lat = None
            sx = sy = 0.0
            n = 0
            for m in o.members:
                if m.type == "w":
                    cc = ways.get(m.ref)
                    if cc:
                        sx += cc[0]
                        sy += cc[1]
                        n += 1
            if n:
                lon, lat = sx / n, sy / n

        tags = dict(otags)
        cls = classify(tags) or []
        # named roads: only inside the North Frisia bbox
        if "highway" in tags and in_bbox(lon, lat):
            cls.append("highway=" + tags["highway"])
        if not cls:
            continue

        names = name_tags(tags)
        if not names:
            continue
        keep = {k: tags[k] for k in CLASS_KEYS + EXTRA_KEYS if k in tags}
        keep.update(names)
        rec = {"src": src, "t": typ, "id": o.id,
               "lon": round(lon, 6) if lon is not None else None,
               "lat": round(lat, 6) if lat is not None else None,
               "cls": cls, "tags": keep}
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for cl in cls:
            counts[cl.split("=")[0]] += 1
        counts["_total"] += 1
        counts["_total_" + typ] += 1
    print(f"  {src}: {n_seen:,} objects scanned, "
          f"{len(ways.ids):,} way centroids cached, {time.time()-t0:.0f}s",
          file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pbf", nargs="+", help="OSM extracts to scan")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--index", default="flex_mem",
                    help="pyosmium node-location index (default flex_mem)")
    args = ap.parse_args(argv)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    counts = collections.Counter()
    t0 = time.time()
    with open(args.out, "w", encoding="utf-8") as fh:
        for p in args.pbf:
            src = os.path.basename(p).split("-latest")[0].split(".")[0]
            print(f"scanning {p} ...", file=sys.stderr)
            process(p, src, fh, counts, args.index)

    print(f"\nwrote {counts['_total']:,} candidates to {args.out} "
          f"in {time.time()-t0:.0f}s")
    print(f"  nodes {counts['_total_n']:,}  ways {counts['_total_w']:,}  "
          f"relations {counts['_total_r']:,}")
    print("counts by tag class (an object can count in several):")
    for k, v in sorted(counts.items()):
        if not k.startswith("_"):
            print(f"  {v:8,d}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
