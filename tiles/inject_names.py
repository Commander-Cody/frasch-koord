#!/usr/bin/env python3
"""Copy an OSM PBF and add North Frisian name / curation tags to it.

    inject_names.py <in.osm.pbf> <out.osm.pbf>
                    [--names ../names/places.csv] [--dialect frr-x-mooring]
                    [--curation ../names/curation.csv] [--dry-run]

Two independent inputs are merged into the extract:

`names/places.csv` (the name list) -- every row that has a label in the
dialect's column (`mooring`, falling back to `older`) and is not `skip`
tags the object(s) in its `osm` column with `name:<dialect>` = the label and
`frasch:kind` = the row's `kind` (island, hallig, sand, settlement, koog, ...).
Rows with a `wikidata` QID additionally tag every object whose `wikidata` tag
equals that QID; for the countries, which have no `osm`, that is the only key.

`names/curation.csv` (per-feature map tuning) -- for every listed object the
`set_tags` (`k=v` pairs separated by `;`) are applied *verbatim*, after the
name list, so they may override `frasch:kind` or `place`; `minzoom` / `maxzoom`
become the tags `frasch:minzoom` / `frasch:maxzoom`.  Curation applies to any object in the file, whether the
name list mentions it or not (a place with no Frisian name can still need a
`place=island` fix or a minimum zoom).  A row with `polygon_km2` does not
change its node but adds a *synthetic* closed way to the file: a square of
that area centred on the node, carrying the node's `name`/`name:*` tags plus
the row's `set_tags` / zooms.  That is how a landform without an OSM polygon
(Nordstrand, a former island that is now a peninsula) gets a label at a chosen
point from the zoom OpenMapTiles gives polygons of that size, instead of the
z12 it gives `place=island` nodes.

Objects are matched by id (or QID) only -- no name matching happens here, so the
hand-reviewed decisions in the CSVs are the single source of truth.  All other
tags are preserved (`o.replace(tags=...)`), as are all objects neither file
mentions.

`frasch:kind` / `frasch:minzoom` / `frasch:maxzoom` reach the tiles because
tiles/build.sh passes them to Planetiler via `--extra_name_tags`; tag values must therefore be
strings.

Used by tiles/build.sh before Planetiler runs.
"""
from __future__ import annotations

import argparse
import collections
import csv
import os
import sys
import time

import osmium

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "names")))
import placelist  # noqa: E402

DEFAULT_NAMES = placelist.DEFAULT_PATH
DEFAULT_CURATION = os.path.normpath(os.path.join(HERE, "..", "names", "curation.csv"))
KIND_KEY = "frasch:kind"
MINZOOM_KEY = "frasch:minzoom"
MAXZOOM_KEY = "frasch:maxzoom"


def load_names(path, dialect, name_column=None):
    """-> (by_id, by_qid, n_rows_used, name_column, conflicts)

    by_id maps ('w', 12) -> (name, kind); by_qid maps 'Q42' -> (name, kind)."""
    by_id, by_qid = {}, {}
    conflicts = []
    used = 0
    rows, fields = placelist.read(path)
    col = name_column or _name_column_for(fields, dialect)
    for row in rows:
        if row["status"] == "skip" or row["kind"] == "not_a_place":
            continue
        # the label; names in the `other` column (Sölring, Halunder, ...)
        # are never published as Mooring -- they wait for their own column
        name = placelist.label(row, col)
        if not name:
            continue
        kind = row["kind"]
        refs = placelist.parse_osm(row["osm"], f"{path}:{row['_line']}")
        if refs:
            # a river or dyke is split into many OSM ways and all of them
            # need the label
            for key in refs:
                prev = by_id.get(key)
                if prev is not None and prev[0] != name:
                    conflicts.append((key, prev[0], name, row["_line"]))
                    continue          # first row in file order wins
                by_id[key] = (name, kind)
            used += 1
        elif row["wikidata"]:
            used += 1
        # Every row with a Wikidata QID also tags the other OSM objects that
        # carry that QID (e.g. the offshore place=sea node of the North Sea,
        # the place node next to a matched boundary relation).  Only rows
        # without any OSM id depend on this; for the others it is a bonus.
        qid = row["wikidata"]
        if qid and qid not in by_qid:
            by_qid[qid] = (name, kind)
    return by_id, by_qid, used, col, conflicts


def _name_column_for(fieldnames, dialect):
    """`frr-x-mooring` -> column `mooring` (later dialects analogous)."""
    cand = dialect.split("-x-")[-1] if "-x-" in dialect else ""
    if cand in fieldnames:
        return cand
    raise SystemExit(f"no name column for dialect {dialect!r} in {fieldnames} "
                     f"(use --name-column)")


def parse_set_tags(spec):
    """`place=island;frasch:kind=island` -> {'place': 'island', ...}."""
    tags = {}
    for pair in (spec or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise SystemExit(f"curation: set_tags entry {pair!r} is not k=v")
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            raise SystemExit(f"curation: set_tags entry {pair!r} has an empty key")
        tags[k] = v
    return tags


def load_curation(path, required=False):
    """-> ({('r', 1420555): {'tags': {...}, 'label': 'Nordstrand'}},
        {('n', 85929111): {'km2': 50.0, 'tags': {...}, 'label': '...'}})

    `set_tags` are applied verbatim, `minzoom` / `maxzoom` become
    `frasch:minzoom` / `frasch:maxzoom`.  Every object in the file may be
    curated, whether the name list knows it or not.  Rows with `polygon_km2`
    go into the second dict: they describe a synthetic polygon to add around
    that node (see the module docstring) and leave the node itself alone."""
    by_id, synthetic = {}, {}
    if not os.path.exists(path):
        if required:
            raise SystemExit(f"curation file not found: {path}")
        print(f"curation  : {path} (absent -- nothing curated)")
        return by_id, synthetic
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if "osm" not in (reader.fieldnames or []):
            raise SystemExit(f"{path}: needs an `osm` column (node/ID, way/ID, "
                             f"relation/ID; several separated by `;`)")
        for n, row in enumerate(reader, start=2):
            refs = placelist.parse_osm(row.get("osm"), f"{path}:{n}")
            if not refs:
                continue                      # blank spacer line
            tags = parse_set_tags(row.get("set_tags"))
            for col, tag in (("minzoom", MINZOOM_KEY), ("maxzoom", MAXZOOM_KEY)):
                z = (row.get(col) or "").strip()
                if z:
                    if not z.lstrip("-").isdigit():
                        raise SystemExit(f"{path}:{n}: {col} {z!r} is not an integer")
                    tags[tag] = str(int(z))   # tag values must be strings
            label = (row.get("name") or "").strip()
            km2 = (row.get("polygon_km2") or "").strip()
            if km2:
                try:
                    km2 = float(km2)
                    assert km2 > 0
                except (ValueError, AssertionError):
                    raise SystemExit(f"{path}:{n}: polygon_km2 {km2!r} is not a positive number")
                if len(refs) != 1 or refs[0][0] != "n":
                    raise SystemExit(f"{path}:{n}: polygon_km2 needs exactly one node in `osm`")
                if refs[0] in synthetic:
                    raise SystemExit(f"{path}:{n}: second polygon_km2 row for {refs[0][1]}")
                synthetic[refs[0]] = {"km2": km2, "tags": tags, "label": label}
                continue
            if not tags:
                continue                      # a row with nothing to apply yet
            for key in refs:
                by_id.setdefault(key, {"tags": {}, "label": label})
                by_id[key]["tags"].update(tags)
    return by_id, synthetic


def square_around(lon, lat, km2):
    """Corners of a square of `km2` km² centred on (lon, lat), as (lon, lat).

    Its interior point -- where Planetiler puts a polygon label -- is the
    centre, i.e. the node."""
    import math
    half_km = math.sqrt(km2) / 2
    dlat = half_km / 111.32
    dlon = half_km / (111.32 * math.cos(math.radians(lat)))
    return [(lon - dlon, lat - dlat), (lon + dlon, lat - dlat),
            (lon + dlon, lat + dlat), (lon - dlon, lat + dlat)]


def expand_waterway_relations(path, by_id):
    """Rivers are usually matched to their `type=waterway` relation, but the
    OpenMapTiles waterway layer is built from the member WAYS.  Read only the
    relations of the file and return {('w', id): (name, kind, relation_name)}
    for the members of matched waterway relations; the main pass applies the
    name to a member way only if the way carries the same OSM name (side
    arms like "Alte Eider" keep their own name)."""
    wanted = {k: v for k, v in by_id.items() if k[0] == "r"}
    members = {}
    if not wanted:
        return members

    class Rels(osmium.SimpleHandler):
        def relation(self, r):
            hit = wanted.get(("r", r.id))
            if hit is None:
                return
            if r.tags.get("type") != "waterway" and "waterway" not in r.tags:
                return
            rel_name = r.tags.get("name", "")
            for m in r.members:
                if m.type == "w":
                    members.setdefault(("w", m.ref), (hit[0], hit[1], rel_name))

    reader = osmium.io.Reader(path, osmium.osm.RELATION)
    osmium.apply(reader, Rels())
    reader.close()
    return members


class Injector:
    def __init__(self, writer, by_id, by_qid, key, curation=None, dry_run=False,
                 members=None, synthetic=None):
        self.members = members or {}
        # synthetic polygons: collected while the nodes stream past, written as
        # new nodes before the first way and as new ways before the first
        # relation, so the file stays in node/way/relation order with ascending
        # ids (Planetiler and osmium both expect that)
        self.synthetic = synthetic or {}
        self.pending = []           # [{'key', 'label', 'lon', 'lat', 'km2', 'tags'}]
        self.max_id = {"n": 0, "w": 0, "r": 0}
        self.flushed = {"n": False, "w": False}
        self.created = []           # (way id, node ids, label, km2) for the report
        self.member_hits = 0
        self.w = writer
        self.by_id = by_id
        self.by_qid = by_qid
        self.key = key
        self.curation = curation or {}
        self.dry_run = dry_run
        self.hits = collections.Counter()
        self.seen_keys = set()
        self.qid_hits = collections.Counter()
        self.cur_hits = collections.Counter()
        self.seen_cur = set()
        self.n_objects = 0

    def flush(self, t):
        """Write the synthetic nodes (t='w': before the first way) or ways
        (t='r': before the first relation)."""
        if t == "w" and not self.flushed["n"]:
            self.flushed["n"] = True
            for p in self.pending:
                ids = []
                for lon, lat in square_around(p["lon"], p["lat"], p["km2"]):
                    self.max_id["n"] += 1
                    ids.append(self.max_id["n"])
                    if not self.dry_run:
                        self.w.add_node(osmium.osm.mutable.Node(
                            id=ids[-1], version=1, visible=True, location=(lon, lat)))
                p["node_ids"] = ids
        elif t == "r" and not self.flushed["w"]:
            self.flush("w")
            self.flushed["w"] = True
            for p in self.pending:
                self.max_id["w"] += 1
                if not self.dry_run:
                    self.w.add_way(osmium.osm.mutable.Way(
                        id=self.max_id["w"], version=1, visible=True,
                        nodes=p["node_ids"] + p["node_ids"][:1], tags=p["tags"]))
                self.created.append((self.max_id["w"], p["node_ids"], p["label"], p["km2"]))

    def finish(self):
        """For files that end before any way / relation."""
        self.flush("w")
        self.flush("r")

    def handle(self, o, t):
        """`t` is the OSM type letter (n/w/r), not a name-list kind."""
        self.n_objects += 1
        key = (t, o.id)
        self.max_id[t] = max(self.max_id[t], o.id)
        if t != "n":
            self.flush(t)
        synth = self.synthetic.get(key) if t == "n" else None
        hit = self.by_id.get(key)
        if hit is not None:
            self.seen_keys.add(key)
        if hit is None and self.members:
            mem = self.members.get(key)
            if mem is not None:
                name, kind, rel_name = mem
                own = o.tags.get("name")
                if own and (own == rel_name or o.tags.get("name:de") == rel_name):
                    hit = (name, kind)
                    self.member_hits += 1
        if hit is None and self.by_qid:
            qid = o.tags.get("wikidata")
            if qid and qid in self.by_qid:
                hit = self.by_qid[qid]
                self.qid_hits[qid] += 1
        cur = self.curation.get(key)
        if cur is not None:
            self.seen_cur.add(key)
            self.cur_hits[t] += 1
        if hit is None and cur is None and synth is None:
            if not self.dry_run:
                self.w.add(o)
            return
        if hit is not None:
            self.hits[t] += 1
        tags = dict(o.tags)
        if hit is not None:
            name, kind = hit
            tags[self.key] = name
            if kind:
                tags[KIND_KEY] = kind
        if cur is not None:
            # curation runs last and wins: it may override frasch:kind or place
            tags.update(cur["tags"])
        if synth is not None:
            # the polygon inherits the node's (curated) names, then the row's tags
            ptags = {k: v for k, v in tags.items() if k == "name" or k.startswith("name:")}
            ptags.update(synth["tags"])
            self.pending.append({"key": key, "label": synth["label"], "km2": synth["km2"],
                                 "lon": o.location.lon, "lat": o.location.lat, "tags": ptags})
        if self.dry_run:
            return
        self.w.add(o.replace(tags=tags))


def run(inp, out, names_csv, dialect, dry_run=False, name_column=None,
        curation_csv=None, curation_required=False):
    key = "name:" + dialect
    by_id, by_qid, used, col, conflicts = load_names(names_csv, dialect, name_column)
    print(f"name list : {names_csv}")
    print(f"column    : {col}  ->  tags {key} + {KIND_KEY}")
    print(f"usable    : {used} rows -> {len(by_id)} OSM ids + "
          f"{len(by_qid)} wikidata QIDs")
    for ckey, prev, new, line in conflicts:
        print(f"  ! {placelist.format_osm([ckey])} claimed twice: keeping {prev!r}, "
              f"ignoring {new!r} (places.csv line {line})")

    curation, synthetic = load_curation(curation_csv, curation_required) if curation_csv else ({}, {})
    if curation:
        print(f"curation  : {curation_csv} -> {len(curation)} OSM ids "
              f"({sum(1 for c in curation.values() if MINZOOM_KEY in c['tags'])} with "
              f"{MINZOOM_KEY}, "
              f"{sum(1 for c in curation.values() if MAXZOOM_KEY in c['tags'])} with "
              f"{MAXZOOM_KEY})")
    if synthetic:
        print(f"synthetic : {len(synthetic)} polygon(s) to add around nodes")

    writer = None
    if not dry_run:
        # copy the input header so the extract bounds survive (Planetiler uses
        # them; without bounds it renders low-zoom tiles for the whole world)
        writer = osmium.SimpleWriter(out, overwrite=True, header=osmium.io.Reader(inp).header())
    members = expand_waterway_relations(inp, by_id)
    if members:
        print(f"waterways : {len(members)} member ways of matched waterway relations")
    inj = Injector(writer, by_id, by_qid, key, curation, dry_run, members, synthetic)

    t0 = time.time()
    for o in osmium.FileProcessor(inp):
        inj.handle(o, o.type_str())
    inj.finish()
    if writer is not None:
        writer.close()

    missing = sorted(set(by_id) - inj.seen_keys)
    total = sum(inj.hits.values())
    print(f"\nscanned {inj.n_objects:,} objects in {time.time()-t0:.0f}s")
    print(f"tagged  {total} objects with {key}: "
          f"{inj.hits['n']} nodes, {inj.hits['w']} ways, {inj.hits['r']} relations"
          + (f" (of these {sum(inj.qid_hits.values())} matched by wikidata: "
             f"{len(inj.qid_hits)} of {len(by_qid)} QIDs present)" if by_qid else "")
          + (f"; {inj.member_hits} same-named member ways of waterway relations" if members else ""))
    if missing:
        print(f"\n{len(missing)} rows reference ids that are not in {os.path.basename(inp)}:")
        for t, i in missing:
            print(f"  {t}/{i}  {by_id[(t, i)][0]}")
    if by_qid:
        nf = [q for q in by_qid if not inj.qid_hits[q]]
        if nf:
            print(f"\n{len(nf)} wikidata QIDs not present in the file: "
                  + ", ".join(f"{q} ({by_qid[q][0]})" for q in sorted(nf)))

    if curation:
        cur_total = sum(inj.cur_hits.values())
        print(f"\ncurated {cur_total} objects: {inj.cur_hits['n']} nodes, "
              f"{inj.cur_hits['w']} ways, {inj.cur_hits['r']} relations")
        for k in sorted(inj.seen_cur):
            print(f"  {k[0]}/{k[1]}  {curation[k]['label'] or '?'}: "
                  + ", ".join(f"{a}={b}" for a, b in sorted(curation[k]["tags"].items())))
        cur_missing = sorted(set(curation) - inj.seen_cur)
        if cur_missing:
            print(f"\n{len(cur_missing)} curation rows reference ids that are not in "
                  f"{os.path.basename(inp)}:")
            for t, i in cur_missing:
                print(f"  {t}/{i}  {curation[(t, i)]['label'] or '?'}")
    if synthetic:
        print(f"\nadded {len(inj.created)} synthetic polygon(s):")
        for wid, nids, label, km2 in inj.created:
            print(f"  way/{wid} (nodes {nids[0]}..{nids[-1]})  {label or '?'}: {km2:g} km²")
        synth_missing = sorted(set(synthetic) - {p['key'] for p in inj.pending})
        for t, i in synth_missing:
            print(f"  ! {t}/{i} {synthetic[(t, i)]['label'] or '?'}: node not in "
                  f"{os.path.basename(inp)}, no polygon added")
    if dry_run:
        print("\n(dry run -- nothing written)")
    else:
        print(f"\nwrote {out} ({os.path.getsize(out)/1e6:.1f} MB)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("infile")
    ap.add_argument("outfile")
    ap.add_argument("--names", default=DEFAULT_NAMES)
    ap.add_argument("--curation", default=DEFAULT_CURATION,
                    help="per-feature map tuning (set_tags / minzoom / maxzoom / polygon_km2); "
                         "default names/curation.csv, skipped when absent")
    ap.add_argument("--no-curation", action="store_true",
                    help="ignore the curation file entirely")
    ap.add_argument("--dialect", default="frr-x-mooring")
    ap.add_argument("--name-column", default=None,
                    help="override the CSV column (default derived from --dialect)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be tagged, write nothing")
    a = ap.parse_args(argv)
    if not a.dry_run and os.path.abspath(a.infile) == os.path.abspath(a.outfile):
        raise SystemExit("refusing to overwrite the input file")
    return run(a.infile, a.outfile, a.names, a.dialect, a.dry_run, a.name_column,
               curation_csv=None if a.no_curation else a.curation,
               curation_required=a.curation != DEFAULT_CURATION)


if __name__ == "__main__":
    sys.exit(main())
