#!/usr/bin/env python3
"""names/dialect_areas.csv + OSM extract(s) -> names/dialect_areas.geojson.

Which dialect is spoken where is a question about *areas*, not about single
places: a Warft on Hallig Hooge is Halligfriesisch even when the name list
says nothing about it, and the name of a place whose own column is empty is
still the name of the dialect around it.  `dialect_areas.csv` answers it the
only way that stays maintainable: by naming the OSM municipalities (and, where
a municipality is the wrong unit, the island polygons) that belong to each
dialect.  This script turns those references into geometry.

    build_dialect_areas.py <in.osm.pbf> [<in.osm.pbf> ...]
                           [--areas names/dialect_areas.csv]
                           [--out names/dialect_areas.geojson]

The result is **committed**: it is a handful of kilobytes, the injector and
the search exporter need it on every build, and a planet build must not have
to re-extract boundaries.  Re-run it when dialect_areas.csv changes or when a
municipality boundary in OSM has moved -- with a Schleswig-Holstein extract
(`tiles/data/schleswig-holstein-latest.osm.pbf`), which covers every Frisian
area there is.

How it stays within a few hundred MB of RAM: instead of letting pyosmium build
every area of the file (which needs a location cache for the whole extract),
it walks the file three times with an id filter -- the wanted relations, then
their member ways, then those ways' nodes.  Rings are assembled here; the
polygons of one dialect are unioned, simplified (0.0005 deg, ~50 m -- these
are label-lookup areas, not a cadastre) and written as one Feature per
dialect with coordinates rounded to 5 decimals.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time

import osmium

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dialects  # noqa: E402
import placelist  # noqa: E402

DEFAULT_AREAS = os.path.join(HERE, "dialect_areas.csv")
DEFAULT_OUT = dialects.DEFAULT_AREAS
SIMPLIFY_DEG = 0.0005            # ~50 m
ROUND = 5


def read_areas(path, reg):
    """-> ({(type, id): dialect_tag}, {(type, id): label}) in file order."""
    if not os.path.exists(path):
        raise SystemExit(f"dialect area list not found: {path}")
    known = set(dialects.tags(reg))
    by_ref, labels = {}, {}
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for col in ("dialect", "osm"):
            if col not in (reader.fieldnames or []):
                raise SystemExit(f"{path}: missing column {col!r}")
        for n, row in enumerate(reader, start=2):
            tag = (row.get("dialect") or "").strip()
            if not tag and not (row.get("osm") or "").strip():
                continue                                  # blank spacer line
            if tag not in known:
                raise SystemExit(f"{path}:{n}: unknown dialect {tag!r} "
                                 f"(not in names/dialects.csv)")
            refs = placelist.parse_osm(row.get("osm"), f"{path}:{n}")
            if not refs:
                raise SystemExit(f"{path}:{n}: no OSM reference")
            for ref in refs:
                if ref in by_ref and by_ref[ref] != tag:
                    raise SystemExit(f"{path}:{n}: {placelist.format_osm([ref])} "
                                     f"is already {by_ref[ref]}")
                by_ref[ref] = tag
                labels[ref] = (row.get("name") or "").strip()
    return by_ref, labels


# ------------------------------------------------------------- reading ----
def read_relations(path, ids):
    """-> {rel_id: {'outer': [way ids], 'inner': [way ids]}} for the wanted
    relations that are in this file."""
    out = {}
    if not ids:
        return out
    fp = osmium.FileProcessor(path, osmium.osm.RELATION) \
               .with_filter(osmium.filter.IdFilter(ids))
    for r in fp:
        rings = {"outer": [], "inner": []}
        for m in r.members:
            if m.type != "w":
                continue                       # label / admin_centre nodes
            rings["inner" if m.role == "inner" else "outer"].append(m.ref)
        out[r.id] = rings
    return out


def read_ways(path, ids):
    """-> {way_id: [node ids]}."""
    out = {}
    if not ids:
        return out
    fp = osmium.FileProcessor(path, osmium.osm.WAY) \
               .with_filter(osmium.filter.IdFilter(ids))
    for w in fp:
        out[w.id] = [n.ref for n in w.nodes]
    return out


def read_nodes(path, ids):
    """-> {node_id: (lon, lat)}."""
    out = {}
    if not ids:
        return out
    fp = osmium.FileProcessor(path, osmium.osm.NODE) \
               .with_filter(osmium.filter.IdFilter(ids))
    for n in fp:
        out[n.id] = (n.location.lon, n.location.lat)
    return out


# ------------------------------------------------------------ assembly ----
def assemble_rings(ways):
    """Join way node-lists end to end into closed rings.
    -> (rings, unclosed) as lists of node ids."""
    segments = [list(w) for w in ways if len(w) >= 2]
    rings, unclosed = [], []
    while segments:
        cur = segments.pop(0)
        joined = True
        while cur[0] != cur[-1] and joined:
            joined = False
            for i, seg in enumerate(segments):
                if seg[0] == cur[-1]:
                    cur += seg[1:]
                elif seg[-1] == cur[-1]:
                    cur += seg[-2::-1]
                elif seg[-1] == cur[0]:
                    cur = seg[:-1] + cur
                elif seg[0] == cur[0]:
                    cur = seg[:0:-1] + cur
                else:
                    continue
                segments.pop(i)
                joined = True
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
        else:
            unclosed.append(cur)
    return rings, unclosed


def polygons_for(ref, rel, ways, nodes, problems):
    """The shapely polygon(s) of one referenced object."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    def ring_coords(ring):
        try:
            return [nodes[n] for n in ring]
        except KeyError:
            return None

    def build(way_ids, what):
        rings, unclosed = assemble_rings([ways[w] for w in way_ids if w in ways])
        missing = [w for w in way_ids if w not in ways]
        if missing:
            problems.append(f"{placelist.format_osm([ref])}: {len(missing)} "
                            f"{what} way(s) not in the file")
        if unclosed:
            problems.append(f"{placelist.format_osm([ref])}: {len(unclosed)} "
                            f"unclosed {what} ring(s) -- skipped")
        out = []
        for ring in rings:
            coords = ring_coords(ring)
            if coords is None:
                problems.append(f"{placelist.format_osm([ref])}: a {what} ring "
                                f"has nodes that are not in the file -- skipped")
                continue
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            out.append(poly)
        return out

    if ref[0] == "w":
        if ref[1] not in ways:
            return []
        return build([ref[1]], "outer")
    rings = rel.get(ref[1])
    if rings is None:
        return []
    outer = build(rings["outer"], "outer")
    inner = build(rings["inner"], "inner")
    if not outer:
        return []
    geom = unary_union(outer)
    if inner:
        geom = geom.difference(unary_union(inner))
    return [geom]


def km2(geom):
    """Rough area in km² (equirectangular around the geometry's centre) --
    for the report only."""
    lat = geom.centroid.y
    return geom.area * (111.32 ** 2) * math.cos(math.radians(lat))


def round_geojson(obj, nd=ROUND):
    if isinstance(obj, (list, tuple)):
        return [round_geojson(o, nd) for o in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pbf", nargs="+", help="OSM extract(s) holding the areas")
    ap.add_argument("--areas", default=DEFAULT_AREAS)
    ap.add_argument("--registry", default=dialects.DEFAULT_PATH)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--simplify", type=float, default=SIMPLIFY_DEG,
                    help=f"tolerance in degrees (default {SIMPLIFY_DEG})")
    a = ap.parse_args(argv)
    try:
        from shapely.geometry import mapping
        from shapely.ops import unary_union
    except ImportError:
        raise SystemExit("shapely is needed (.venv/bin/pip install shapely)")

    reg = dialects.read(a.registry)
    by_ref, labels = read_areas(a.areas, reg)
    print(f"area list : {a.areas} -> {len(by_ref)} OSM objects, "
          f"{len(set(by_ref.values()))} dialects")

    geoms = {}          # ref -> [shapely geometry]
    problems = []
    for path in a.pbf:
        t0 = time.time()
        want = {ref for ref in by_ref if ref not in geoms}
        rel_ids = {i for t, i in want if t == "r"}
        way_ids = {i for t, i in want if t == "w"}
        rel = read_relations(path, rel_ids)
        member_ids = {w for r in rel.values() for w in r["outer"] + r["inner"]}
        ways = read_ways(path, way_ids | member_ids)
        node_ids = {n for w in ways.values() for n in w}
        nodes = read_nodes(path, node_ids)
        print(f"{os.path.basename(path)}: {len(rel)}/{len(rel_ids)} relations, "
              f"{len(ways):,} ways, {len(nodes):,} nodes ({time.time()-t0:.0f}s)")
        for ref in sorted(want):
            polys = polygons_for(ref, rel, ways, nodes, problems)
            if polys:
                geoms[ref] = polys

    missing = [ref for ref in by_ref if ref not in geoms]
    features, total = [], 0
    for d in reg:
        refs = [r for r in by_ref if by_ref[r] == d["tag"] and r in geoms]
        if not refs:
            continue
        geom = unary_union([p for ref in refs for p in geoms[ref]])
        geom = geom.simplify(a.simplify, preserve_topology=True)
        if not geom.is_valid:
            geom = geom.buffer(0)
        n_poly = len(getattr(geom, "geoms", [geom]))
        n_pts = len(json.dumps(mapping(geom)).split(","))
        total += n_poly
        print(f"  {d['tag']:<15} {len(refs):>2} object(s) -> {n_poly:>2} polygon(s), "
              f"{km2(geom):8.1f} km², valid={geom.is_valid}, ~{n_pts} coords")
        features.append({
            "type": "Feature",
            "properties": {"dialect": d["tag"], "label": d["label"]},
            "geometry": round_geojson(mapping(geom)),
        })
    if not features:
        raise SystemExit("no geometry found -- is the extract the right region?")

    for p in problems:
        print(f"  ! {p}")
    if missing:
        print(f"\n{len(missing)} object(s) not found in the extract(s):")
        for ref in sorted(missing):
            print(f"  {placelist.format_osm([ref])}  {labels.get(ref) or '?'} "
                  f"({by_ref[ref]})")

    fc = {"type": "FeatureCollection",
          "properties": {"source": os.path.basename(a.areas),
                         "simplify_deg": a.simplify},
          "features": features}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"\nwrote {a.out} ({len(features)} features, {total} polygons, "
          f"{os.path.getsize(a.out)/1e3:.0f} kB)")
    idx = dialects.AreaIndex.from_geojson(a.out)
    print(f"reads back as {len(idx)} polygon(s): {idx.summary()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
