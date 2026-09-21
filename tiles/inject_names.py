#!/usr/bin/env python3
"""Copy an OSM PBF and add North Frisian name / curation tags to it.

    inject_names.py <in.osm.pbf> <out.osm.pbf>
                    [--names ../names/places.csv] [--dialects ../names/dialects.csv]
                    [--areas ../names/dialect_areas.geojson]
                    [--curation ../names/curation.csv] [--dry-run]

Three independent inputs are merged into the extract:

`names/places.csv` (the name list) -- one row per place, one column per
dialect (the columns come from `names/dialects.csv`, the registry).  Every row
that is not `skip` tags the object(s) in its `osm` column with

    name:<tag>       for every dialect whose name for the row is non-empty
    frasch:kind      the row's kind (island, hallig, sand, settlement, ...)
    frasch:dialect   the dialect spoken where the object lies
    frasch:local     what the people of the place themselves call it
    frasch:variety   the name of that local variety, e.g. `Foortuftinge`
    frasch:ref       the row's reference (`node/240042766`, `local/huelltoft`
                     or, for a row with no `osm`, its QID) -- the id of the
                     row's entry in the search index, so that the frontend can
                     go from a clicked label back to the name-list row

Rows with a `wikidata` QID additionally tag every object whose `wikidata` tag
equals that QID; for the countries, which have no `osm`, that is the only key.

A row whose `osm` is a *local reference* (`local/<slug>`) is a place OSM does
not have (Waasterhias on Amrum, Harden, most Köge).  The same reference keys
a row of `names/curation.csv` that carries its position (`lat` / `lon`) and,
like any curation row, may carry `set_tags` / `minzoom` / `maxzoom` /
`polygon_km2`.  Without `polygon_km2` the injector adds a *new node* at that
position, tagged like any other object plus the `place=` value its `kind`
maps to (POINT_TAGS, overridable by `set_tags`) and a `name` -- OpenMapTiles
drops a nameless place node.  With `polygon_km2` no labelled node is written;
only the synthetic square (see curation below) is, which is how an area-like
place (a Koog) gets a label from the zoom OpenMapTiles gives polygons of that
size.  New node ids continue above the highest one in the extract; like the
synthetic polygon nodes they are written before the first way, i.e. after
every original node.

`names/dialect_areas.geojson` (built from `names/dialect_areas.csv` by
`names/build_dialect_areas.py`) says which dialect is spoken where.  It
answers two questions that a name list cannot: which of the dialect names is
the *local* one at this spot (`frasch:local`, the "local dialect" map view),
and which dialect a place's own `local` column belongs to.  The smallest area
containing the object wins.  Without the file the injector still runs -- it
warns and writes `frasch:local` only for rows with an explicit `local` name.
A node is asked at its own location; a way or relation that closes into a
polygon first at an interior point of *that* polygon and only then at its
outline -- an island's coastline runs outside the municipality boundaries the
areas are cut from, so a coastline vertex answers "no dialect" for the very
island the area was drawn around (see `locate_ways_and_relations`).  What does
not close -- an open way, a relation whose members the extract does not hold --
is asked, as before, at the relation's `label` / `admin_centre` member, else
at its first vertex.  Those positions are collected in three id-filtered
pre-passes over the file (matched relations -> their member ways -> those
ways' nodes), never in a location cache for the whole extract -- the dev
machine does not have the memory for one.  Objects matched only through their
Wikidata QID get no area.

`names/curation.csv` (per-feature map tuning) -- for every listed object the
`set_tags` (`k=v` pairs separated by `;`) are applied *verbatim*, after the
name list, so they may override `frasch:kind` or `place`; `minzoom` /
`maxzoom` become the tags `frasch:minzoom` / `frasch:maxzoom`.  Curation
applies to any object in the file, whether the name list mentions it or not (a
place with no Frisian name can still need a `place=island` fix or a minimum
zoom).  A row keyed by a local reference additionally carries `lat` / `lon`
(required there, forbidden on OSM references) and is what *creates* the
object for that reference, see above.  A row with `polygon_km2` does not change its node but adds a
*synthetic* closed way to the file: a square of that area centred on the node,
carrying the node's `name`/`name:*`/`frasch:dialect`/`frasch:local` tags plus
the row's `set_tags` / zooms.  That is how a landform without an OSM polygon
(Nordstrand, a former island that is now a peninsula) gets a label at a chosen
point from the zoom OpenMapTiles gives polygons of that size, instead of the
z12 it gives `place=island` nodes.

Objects are matched by id (or QID) only -- no name matching happens here, so the
hand-reviewed decisions in the CSVs are the single source of truth.  All other
tags are preserved (`o.replace(tags=...)`), as are all objects neither file
mentions.  When two rows claim the same object, the first row in file order
wins per tag and the rest are reported.

The `frasch:*` tags reach the tiles because tiles/build.sh passes them to
Planetiler via `--extra_name_tags`; tag values must therefore be strings.

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
import dialects  # noqa: E402
import build_dialect_areas  # noqa: E402  (ring assembly, see locate_ways_and_relations)

DEFAULT_NAMES = placelist.DEFAULT_PATH
DEFAULT_DIALECTS = dialects.DEFAULT_PATH
DEFAULT_AREAS = dialects.DEFAULT_AREAS
DEFAULT_CURATION = os.path.normpath(os.path.join(HERE, "..", "names", "curation.csv"))
KIND_KEY = "frasch:kind"
MINZOOM_KEY = "frasch:minzoom"
MAXZOOM_KEY = "frasch:maxzoom"
DIALECT_KEY = "frasch:dialect"
LOCAL_KEY = "frasch:local"
VARIETY_KEY = "frasch:variety"
REF_KEY = "frasch:ref"

# The default `place=` of the node added for a local reference, by the row's
# kind.  Only kinds whose OSM equivalent is unambiguous are listed; any other
# kind needs `place=...` in the curation row's `set_tags` (and a look at
# whether OpenMapTiles keeps that tag: it has no `place=locality` at all, and
# `isolated_dwelling` nodes only from z14 while `hamlet` nodes come at z11 --
# which is why a Warft is a hamlet here, as OSM's own Hallig Warften are).
POINT_TAGS = {
    "settlement": {"place": "hamlet"},
    "warft": {"place": "hamlet"},
    "island": {"place": "island"},
    "hallig": {"place": "island"},
}


# ------------------------------------------------------------ name list ----
def load_names(path, reg):
    """-> (by_id, by_qid, n_rows_used, conflicts)

    by_id maps ('w', 12) -> [row, ...] in file order (a local reference is
    the key ('l', slug)), by_qid 'Q42' -> [row].  The rows are kept whole
    because the tags of an object depend on where it lies (see `name_tags`),
    which is only known while the file streams past."""
    by_id, by_qid = {}, {}
    conflicts = []
    used = 0
    rows, _ = placelist.read(path)
    for row in rows:
        if row["status"] == "skip" or row["kind"] == "not_a_place":
            continue
        if not placelist.any_name(row):
            continue
        refs = placelist.parse_osm(row["osm"], f"{path}:{row['_line']}")
        if refs:
            # a river or dyke is split into many OSM ways and all of them
            # need the label
            for key in refs:
                by_id.setdefault(key, []).append(row)
            used += 1
        elif row["wikidata"]:
            used += 1
        # Every row with a Wikidata QID also tags the other OSM objects that
        # carry that QID (e.g. the offshore place=sea node of the North Sea,
        # the place node next to a matched boundary relation).  Only rows
        # without any OSM id depend on this; for the others it is a bonus.
        qid = row["wikidata"]
        if qid and qid not in by_qid:
            by_qid[qid] = [row]
    for key, claim in by_id.items():
        conflicts += _conflicts(key, claim, reg)
    return by_id, by_qid, used, conflicts


def _conflicts(key, rows, reg):
    """Which names a second row for the same object loses.  Reported, not
    fatal: the first row in file order wins, per tag."""
    out = []
    if len(rows) < 2:
        return out
    for column in dialects.columns(reg) + [dialects.LOCAL_COLUMN]:
        kept, kept_line = "", 0
        for row in rows:
            name = (dialects.dialect_name(row, dialects.tag_of_column(reg, column), None, reg)
                    if column != dialects.LOCAL_COLUMN
                    else placelist.primary(row[column]))
            if not name:
                continue
            if not kept:
                kept, kept_line = name, row["_line"]
            elif name != kept:
                out.append((key, column, kept, kept_line, name, row["_line"]))
    return out


def name_tags(rows, area_tag, reg):
    """The full tag dict for one object: a `name:<tag>` per dialect that has a
    name for it, plus the frasch:* attributes.  `rows` are the name-list rows
    claiming the object, in file order -- the first non-empty value wins."""
    tags = {}
    for d in reg:
        for row in rows:
            name = dialects.dialect_name(row, d["tag"], area_tag, reg)
            if name:
                tags["name:" + d["tag"]] = name
                break
    for row in rows:
        if row["kind"]:
            tags[KIND_KEY] = row["kind"]
            break
    if area_tag:
        tags[DIALECT_KEY] = area_tag
    for row in rows:
        local = dialects.local_name(row, area_tag, reg)
        if local:
            tags[LOCAL_KEY] = local
            break
    for row in rows:
        variety = dialects.variety(row)
        if variety:
            tags[VARIETY_KEY] = variety
            break
    for row in rows:
        ref = placelist.entry_id(row)
        if ref:
            tags[REF_KEY] = ref
            break
    return tags


def point_tags(rows, area_tag, reg, curation_tags, where=""):
    """The tag dict of the node added for a local reference: the `place=` its
    kind defaults to, a `name` (the German one -- the Frisian ones live in
    `name:<tag>` like everywhere else; without it OpenMapTiles would drop the
    node), the name tags, and last the curation row's own tags, which win."""
    row = rows[0]
    tags = dict(POINT_TAGS.get(row["kind"], {}))
    name = (placelist.primary(row["de"]) or placelist.primary(row["da"])
            or placelist.any_name(row))
    if name:
        tags["name"] = name
    tags.update(name_tags(rows, area_tag, reg))
    tags.update(curation_tags)
    if "place" not in tags:
        raise SystemExit(f"{where}: kind {row['kind']!r} (places.csv line "
                         f"{row['_line']}) has no default place= (POINT_TAGS in "
                         f"tiles/inject_names.py) -- give the curation row "
                         f"`place=...` in set_tags")
    return tags


def check_local(by_id, points, reg):
    """Validate every local reference before anything is written: the node
    needs a `place=` (see point_tags), and a square only labels as
    `place=island` -- OpenMapTiles takes hamlets, villages etc. from POINTS
    only, so any other value on a polygon would silently label nothing."""
    for key, p in points.items():
        rows = by_id.get(key)
        if rows is None:
            continue
        tags = point_tags(rows, None, reg, p["tags"], p["where"])
        if p["km2"] is not None and tags["place"] != "island":
            raise SystemExit(f"{p['where']}: polygon_km2 on {placelist.format_osm([key])} "
                             f"needs place=island (got place={tags['place']}; "
                             f"OpenMapTiles labels polygons only as islands) -- "
                             f"put `place=island` in set_tags, keep frasch:kind")


# -------------------------------------------------------------- curation ----
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
        {('n', 85929111): {'km2': 50.0, 'tags': {...}, 'label': '...'}},
        {('l', 'westerheide-amrum'): {'lon': 8.34, 'lat': 54.65, 'km2': None,
                                      'tags': {...}, 'label': '...'}})

    `set_tags` are applied verbatim, `minzoom` / `maxzoom` become
    `frasch:minzoom` / `frasch:maxzoom`.  Every object in the file may be
    curated, whether the name list knows it or not.  Rows with `polygon_km2`
    go into the second dict: they describe a synthetic polygon to add around
    that node (see the module docstring) and leave the node itself alone.
    Rows with a local reference go into the third: they position a place OSM
    does not have (`lat` / `lon`, required there and forbidden elsewhere) and
    describe the node -- or, with `polygon_km2`, the square -- to add for it."""
    by_id, synthetic, points = {}, {}, {}
    if not os.path.exists(path):
        if required:
            raise SystemExit(f"curation file not found: {path}")
        print(f"curation  : {path} (absent -- nothing curated)")
        return by_id, synthetic, points
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if "osm" not in (reader.fieldnames or []):
            raise SystemExit(f"{path}: needs an `osm` column (node/ID, way/ID, "
                             f"relation/ID; several separated by `;`; or local/slug)")
        for n, row in enumerate(reader, start=2):
            where = f"{path}:{n}"
            refs = placelist.parse_osm(row.get("osm"), where)
            pos = placelist.parse_point(row.get("lat"), row.get("lon"), where)
            if not refs:
                continue                      # blank spacer line
            local = refs[0][0] == placelist.LOCAL_TYPE
            if pos and not local:
                raise SystemExit(f"{where}: lat/lon only go with a local reference "
                                 f"(local/<slug>), not with {row['osm']!r}")
            if local and not pos:
                raise SystemExit(f"{where}: {row['osm']} needs `lat` and `lon`")
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
                if len(refs) != 1 or refs[0][0] not in ("n", placelist.LOCAL_TYPE):
                    raise SystemExit(f"{where}: polygon_km2 needs exactly one node "
                                     f"(or local reference) in `osm`")
            else:
                km2 = None
            if local:
                if refs[0] in points:
                    raise SystemExit(f"{where}: second row for {row['osm']}")
                points[refs[0]] = {"lon": pos[0], "lat": pos[1], "km2": km2,
                                   "tags": tags, "label": label, "where": where}
                continue
            if km2 is not None:
                if refs[0] in synthetic:
                    raise SystemExit(f"{where}: second polygon_km2 row for {refs[0][1]}")
                synthetic[refs[0]] = {"km2": km2, "tags": tags, "label": label}
                continue
            if not tags:
                continue                      # a row with nothing to apply yet
            for key in refs:
                by_id.setdefault(key, {"tags": {}, "label": label})
                by_id[key]["tags"].update(tags)
    return by_id, synthetic, points


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


# ------------------------------------------------------------ pre-passes ----
def scan_relations(path, by_id):
    """One id-filtered pass over the relations of the file.  It answers two
    questions at once:

    * which member ways a matched `type=waterway` relation has -- the
      OpenMapTiles waterway layer is built from the member WAYS, so the label
      has to go on them (the main pass applies it only to members carrying the
      relation's own name, so side arms like "Alte Eider" keep theirs)
    * what a matched relation is made of: its `label` / `admin_centre` member
      node and its member ways by ring role -- enough to rebuild its polygon
      and ask the dialect-area index which dialect is spoken inside it.

    -> (members, rel_node, rel_rings) with
       members    {('w', id): (relation key, the relation's OSM name)}
       rel_node   {rel id: node id}
       rel_rings  {rel id: {'outer': [way ids], 'inner': [way ids]}}, the
                  shape names/build_dialect_areas.polygons_for expects"""
    wanted = {i for t, i in by_id if t == "r"}
    members, rel_node, rel_rings = {}, {}, {}
    if not wanted:
        return members, rel_node, rel_rings
    fp = osmium.FileProcessor(path, osmium.osm.RELATION) \
               .with_filter(osmium.filter.IdFilter(wanted))
    for r in fp:
        waterway = r.tags.get("type") == "waterway" or "waterway" in r.tags
        rings = rel_rings.setdefault(r.id, {"outer": [], "inner": []})
        for m in r.members:
            if m.type == "n" and m.role in ("label", "admin_centre"):
                rel_node.setdefault(r.id, m.ref)
            elif m.type == "w":
                rings["inner" if m.role == "inner" else "outer"].append(m.ref)
                if waterway:
                    members.setdefault(("w", m.ref),
                                       (("r", r.id), r.tags.get("name", "")))
    return members, rel_node, rel_rings


def scan_way_nodes(path, way_ids):
    """-> {way id: [node ids]} for the given ways (id-filtered pass)."""
    out = {}
    if not way_ids:
        return out
    fp = osmium.FileProcessor(path, osmium.osm.WAY) \
               .with_filter(osmium.filter.IdFilter(way_ids))
    for w in fp:
        if len(w.nodes):
            out[w.id] = [n.ref for n in w.nodes]
    return out


def scan_node_locations(path, node_ids):
    """-> {node id: (lon, lat)} (id-filtered pass)."""
    out = {}
    if not node_ids:
        return out
    fp = osmium.FileProcessor(path, osmium.osm.NODE) \
               .with_filter(osmium.filter.IdFilter(node_ids))
    for n in fp:
        if n.location.valid():
            out[n.id] = (n.location.lon, n.location.lat)
    return out


def locate_ways_and_relations(path, by_id, rel_node, rel_rings):
    """-> ({('w'|'r', id): [(lon, lat), ...]}, n_from_polygon) for the matched
    ways and relations: the points at which each is asked which dialect is
    spoken there, best first (see `area_of`).  Nodes are not in here: the main
    pass has their location anyway.

    An island is not where its coastline starts.  The first vertex of a way
    lies *on* the outline of the place, i.e. where the dialect area that was
    cut from municipality boundaries has already ended (Amrum's coastline
    begins 1.6 km south of the Amrum municipalities, on the Kniepsand), so
    that point answered "no dialect at all" for exactly the places whose own
    island the area was drawn around.  Whatever closes into a polygon is
    therefore asked at an interior point of that polygon first -- a point of
    the place itself, and still a single point, so the "smallest containing
    area wins" rule of the index is untouched.

    The outline point stays as a second try, because the two miss in opposite
    directions: where an area covers only part of an island (the Langeneß
    municipality holds only the south-west third of Oland) the interior point
    falls outside it while a vertex still lands in it.  An object gets the
    dialect of the first point that is in an area at all, so nothing that had
    one can lose it.  What has no polygon -- an open way, a relation whose
    members the extract does not hold -- is asked only at the old point: the
    relation's `label` / `admin_centre` member, else the first vertex.

    Ring assembly is names/build_dialect_areas.py's -- the same code that
    builds the dialect areas themselves, so a place and the areas it is
    compared against are read out of OSM the same way."""
    way_ids = {i for t, i in by_id if t == "w"}
    for rings in rel_rings.values():
        way_ids |= set(rings["outer"]) | set(rings["inner"])
    ways = scan_way_nodes(path, way_ids)
    node_ids = {n for nodes in ways.values() for n in nodes} | set(rel_node.values())
    locs = scan_node_locations(path, node_ids)
    out, from_polygon, problems = {}, 0, []
    for key in by_id:
        t, i = key
        if t not in ("w", "r"):
            continue
        points = []
        for geom in build_dialect_areas.polygons_for(key, rel_rings, ways, locs, problems):
            if geom.is_empty:
                continue
            try:
                p = geom.representative_point()
            except Exception:          # a ring OSM leaves in a state shapely
                continue               # cannot make a point of; the outline does
            points.append((p.x, p.y))
            from_polygon += 1
            break
        # the old point: the relation's own label node, else the first vertex
        # of the (first) way
        nid = rel_node.get(i) if t == "r" else None
        if nid is None:
            first = ways.get(i) if t == "w" else next(
                (ways[w] for w in rel_rings.get(i, {}).get("outer", []) if w in ways),
                None)
            nid = first[0] if first else None
        if nid in locs:
            points.append(locs[nid])
        if points:
            out[key] = points
    return out, from_polygon


# -------------------------------------------------------------- injector ----
class Injector:
    def __init__(self, writer, by_id, by_qid, reg, areas=None, coords=None,
                 curation=None, dry_run=False, members=None, synthetic=None,
                 points=None):
        self.members = members or {}
        # local references (places OSM has no object for): a node of their
        # own, or a synthetic polygon, written with the synthetic polygon
        # nodes (see `flush`)
        self.points = points or {}
        self.added_points = []      # (node id, key, label, lon, lat, tags) for the report
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
        self.reg = reg
        self.areas = areas
        self.coords = coords or {}
        self.curation = curation or {}
        self.dry_run = dry_run
        self.hits = collections.Counter()
        self.tag_hits = collections.Counter()      # name:<tag> -> objects
        self.area_hits = collections.Counter()     # frasch:dialect -> objects
        self.local_hits = 0
        self.seen_keys = set()
        self.qid_hits = collections.Counter()
        self.cur_hits = collections.Counter()
        self.seen_cur = set()
        self.n_objects = 0

    def area_of(self, key, o):
        """The dialect spoken where this object lies, or None.  A node is
        asked at its own location, a way / relation at the points
        `locate_ways_and_relations` found for it, best first."""
        if self.areas is None:
            return None
        if key[0] == "n":
            if not o.location.valid():
                return None
            return self.areas.lookup(o.location.lon, o.location.lat)
        for lon, lat in self.coords.get(key, ()):
            tag = self.areas.lookup(lon, lat)
            if tag:
                return tag
        return None

    def flush(self, t):
        """Write the synthetic nodes (t='w': before the first way) or ways
        (t='r': before the first relation)."""
        if t == "w" and not self.flushed["n"]:
            self.flushed["n"] = True
            for key, p in self.points.items():
                rows = self.by_id.get(key)
                if rows is None:
                    continue        # no name-list row uses it (reported in run)
                lon, lat = p["lon"], p["lat"]
                area_tag = self.areas.lookup(lon, lat) if self.areas else None
                tags = point_tags(rows, area_tag, self.reg, p["tags"], p["where"])
                self.seen_keys.add(key)
                for k in tags:
                    if k.startswith("name:"):
                        self.tag_hits[k] += 1
                if DIALECT_KEY in tags:
                    self.area_hits[tags[DIALECT_KEY]] += 1
                if LOCAL_KEY in tags:
                    self.local_hits += 1
                if p["km2"] is not None:
                    # an area-like place: only the label square, no node
                    self.pending.append({"key": key, "label": p["label"], "km2": p["km2"],
                                         "lon": lon, "lat": lat, "tags": tags})
                    continue
                self.hits["n"] += 1
                self.max_id["n"] += 1
                if not self.dry_run:
                    self.w.add_node(osmium.osm.mutable.Node(
                        id=self.max_id["n"], version=1, visible=True,
                        location=(lon, lat), tags=tags))
                self.added_points.append((self.max_id["n"], key, p["label"], lon, lat, tags))
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
        hit = self.by_id.get(key)            # [row, ...]
        area_key = key
        if hit is not None:
            self.seen_keys.add(key)
        if hit is None and self.members:
            mem = self.members.get(key)
            if mem is not None:
                rel_key, rel_name = mem
                own = o.tags.get("name")
                if own and (own == rel_name or o.tags.get("name:de") == rel_name):
                    hit = self.by_id.get(rel_key) or []
                    area_key = rel_key      # the member inherits the river's area
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
        tags = dict(o.tags)
        if hit is not None:
            self.hits[t] += 1
            new = name_tags(hit, self.area_of(area_key, o), self.reg)
            for k in new:
                if k.startswith("name:"):
                    self.tag_hits[k] += 1
            if DIALECT_KEY in new:
                self.area_hits[new[DIALECT_KEY]] += 1
            if LOCAL_KEY in new:
                self.local_hits += 1
            tags.update(new)
        if cur is not None:
            # curation runs last and wins: it may override frasch:kind or place
            tags.update(cur["tags"])
        if synth is not None:
            # the polygon inherits the node's (curated) names and dialect, then
            # the row's tags
            ptags = {k: v for k, v in tags.items()
                     if k == "name" or k.startswith("name:")
                     or k in (DIALECT_KEY, LOCAL_KEY, VARIETY_KEY, REF_KEY)}
            ptags.update(synth["tags"])
            self.pending.append({"key": key, "label": synth["label"], "km2": synth["km2"],
                                 "lon": o.location.lon, "lat": o.location.lat, "tags": ptags})
        if self.dry_run:
            return
        self.w.add(o.replace(tags=tags))


def run(inp, out, names_csv, dialects_csv, areas_geojson, dry_run=False,
        curation_csv=None, curation_required=False, areas_required=False):
    reg = dialects.read(dialects_csv)
    by_id, by_qid, used, conflicts = load_names(names_csv, reg)
    local_keys = sorted(k for k in by_id if k[0] == placelist.LOCAL_TYPE)
    print(f"name list : {names_csv}")
    print(f"dialects  : {dialects_csv} -> {len(reg)} columns "
          f"({', '.join(dialects.tags(reg))})")
    print(f"usable    : {used} rows -> {len(by_id) - len(local_keys)} OSM ids + "
          f"{len(by_qid)} wikidata QIDs"
          + (f" + {len(local_keys)} local reference(s)" if local_keys else ""))
    for ckey, column, kept, kept_line, dropped, line in conflicts:
        print(f"  ! {placelist.format_osm([ckey])} claimed twice in `{column}`: "
              f"keeping {kept!r} (line {kept_line}), ignoring {dropped!r} "
              f"(places.csv line {line})")

    areas = None
    if areas_geojson and os.path.exists(areas_geojson):
        areas = dialects.AreaIndex.from_geojson(areas_geojson)
        print(f"areas     : {areas_geojson} -> {len(areas)} polygon(s): "
              f"{areas.summary()}")
    elif areas_required:
        raise SystemExit(f"dialect area file not found: {areas_geojson}")
    else:
        print(f"areas     : {areas_geojson or 'off'} (no {DIALECT_KEY}; "
              f"{LOCAL_KEY} only from the `local` column). "
              f"Build it with names/build_dialect_areas.py")

    curation, synthetic, points = (load_curation(curation_csv, curation_required)
                                   if curation_csv else ({}, {}, {}))
    if curation:
        print(f"curation  : {curation_csv} -> {len(curation)} OSM ids "
              f"({sum(1 for c in curation.values() if MINZOOM_KEY in c['tags'])} with "
              f"{MINZOOM_KEY}, "
              f"{sum(1 for c in curation.values() if MAXZOOM_KEY in c['tags'])} with "
              f"{MAXZOOM_KEY})")
    if synthetic:
        print(f"synthetic : {len(synthetic)} polygon(s) to add around nodes")
    if points:
        print(f"local     : {len(points)} local reference(s) positioned in "
              f"{curation_csv}")
    # a local reference is only as good as its curation row: the position
    # lives there, so a missing one stops the build
    unplaced = [k for k in local_keys if k not in points]
    if unplaced:
        lines = "\n".join(f"  {placelist.format_osm([k])}  "
                          f"{placelist.describe(by_id[k][0])} "
                          f"(places.csv line {by_id[k][0]['_line']})" for k in unplaced)
        raise SystemExit(f"{len(unplaced)} local reference(s) in {names_csv} have no "
                         f"row with lat/lon in {curation_csv or 'the curation file '
                         '(which is switched off)'}:\n{lines}")
    check_local(by_id, points, reg)
    unused = sorted(k for k in points if k not in by_id)
    for k in unused:
        print(f"  ! {placelist.format_osm([k])} ({points[k]['label'] or '?'}) is "
              f"positioned in {curation_csv} but no row of {names_csv} uses it "
              f"-- nothing added")

    t0 = time.time()
    members, rel_node, rel_rings = scan_relations(inp, by_id)
    coords, from_polygon = (locate_ways_and_relations(inp, by_id, rel_node, rel_rings)
                            if areas else ({}, 0))
    if members:
        print(f"waterways : {len(members)} member ways of matched waterway relations")
    if areas:
        print(f"positions : {len(coords)} of "
              f"{sum(1 for t, _ in by_id if t in ('w', 'r'))} ways/relations located "
              f"({from_polygon} inside their own polygon, the rest at their label "
              f"node / first vertex; {time.time()-t0:.0f}s in 3 id-filtered pre-passes)")

    writer = None
    if not dry_run:
        # copy the input header so the extract bounds survive (Planetiler uses
        # them; without bounds it renders low-zoom tiles for the whole world)
        writer = osmium.SimpleWriter(out, overwrite=True, header=osmium.io.Reader(inp).header())
    inj = Injector(writer, by_id, by_qid, reg, areas, coords, curation, dry_run,
                   members, synthetic, points)

    t0 = time.time()
    for o in osmium.FileProcessor(inp):
        inj.handle(o, o.type_str())
    inj.finish()
    if writer is not None:
        writer.close()

    missing = sorted(k for k in set(by_id) - inj.seen_keys
                     if k[0] != placelist.LOCAL_TYPE)
    total = sum(inj.hits.values())
    print(f"\nscanned {inj.n_objects:,} objects in {time.time()-t0:.0f}s")
    print(f"tagged  {total} objects: "
          f"{inj.hits['n']} nodes, {inj.hits['w']} ways, {inj.hits['r']} relations"
          + (f" (of these {sum(inj.qid_hits.values())} matched by wikidata: "
             f"{len(inj.qid_hits)} of {len(by_qid)} QIDs present)" if by_qid else "")
          + (f"; {inj.member_hits} same-named member ways of waterway relations"
             if members else ""))
    print("names written per dialect:")
    for d in reg:
        n = inj.tag_hits["name:" + d["tag"]]
        if n:
            print(f"  name:{d['tag']:<15} {n:>5}  {d['label']}")
    print(f"  {LOCAL_KEY:<20} {inj.local_hits:>5}  local form")
    if areas:
        print("objects per dialect area:")
        for tag, n in inj.area_hits.most_common():
            print(f"  {DIALECT_KEY}={tag:<15} {n:>5}")
        if not inj.area_hits:
            print("  (none -- no tagged object lies in a dialect area)")
    if inj.added_points:
        print(f"\nadded {len(inj.added_points)} node(s) for places that are not in OSM:")
        for nid, key, label, lon, lat, tags in inj.added_points:
            print(f"  node/{nid}  {placelist.format_osm([key])} "
                  f"{placelist.describe(by_id[key][0])} at {lat:.5f}, {lon:.5f}: "
                  + ", ".join(f"{a}={b}" for a, b in sorted(tags.items())
                              if not a.startswith("name")))
    if missing:
        print(f"\n{len(missing)} rows reference ids that are not in {os.path.basename(inp)}:")
        for key in missing:
            print(f"  {placelist.format_osm([key])}  "
                  f"{placelist.any_name(by_id[key][0])}")
    if by_qid:
        nf = [q for q in by_qid if not inj.qid_hits[q]]
        if nf:
            print(f"\n{len(nf)} wikidata QIDs not present in the file: "
                  + ", ".join(f"{q} ({placelist.any_name(by_qid[q][0])})"
                              for q in sorted(nf)))

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
    if synthetic or inj.created:
        print(f"\nadded {len(inj.created)} synthetic polygon(s):")
        for wid, nids, label, km2 in inj.created:
            print(f"  way/{wid} (nodes {nids[0]}..{nids[-1]})  {label or '?'}: {km2:g} km²")
        synth_missing = sorted(set(synthetic) - {p['key'] for p in inj.pending
                                                  if p['key'][0] != placelist.LOCAL_TYPE})
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
    ap.add_argument("--dialects", default=DEFAULT_DIALECTS,
                    help="the dialect registry; its tags become the name:* tags")
    ap.add_argument("--areas", default=DEFAULT_AREAS,
                    help="dialect areas as GeoJSON (names/build_dialect_areas.py); "
                         "skipped with a warning when absent")
    ap.add_argument("--curation", default=DEFAULT_CURATION,
                    help="per-feature map tuning (set_tags / minzoom / maxzoom / polygon_km2); "
                         "default names/curation.csv, skipped when absent")
    ap.add_argument("--no-curation", action="store_true",
                    help="ignore the curation file entirely")
    ap.add_argument("--no-areas", action="store_true",
                    help="ignore the dialect areas entirely")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be tagged, write nothing")
    a = ap.parse_args(argv)
    if not a.dry_run and os.path.abspath(a.infile) == os.path.abspath(a.outfile):
        raise SystemExit("refusing to overwrite the input file")
    return run(a.infile, a.outfile, a.names, a.dialects,
               None if a.no_areas else a.areas, a.dry_run,
               curation_csv=None if a.no_curation else a.curation,
               curation_required=a.curation != DEFAULT_CURATION,
               # an explicitly named area file must exist; the default one is
               # optional (the injector then warns and skips frasch:dialect)
               areas_required=os.path.abspath(a.areas) != DEFAULT_AREAS)


if __name__ == "__main__":
    sys.exit(main())
