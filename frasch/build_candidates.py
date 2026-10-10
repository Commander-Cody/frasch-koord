"""One pyosmium pass per OSM extract, collecting every named object that could
be a place / water / landscape / Warft / Koog / road / country.

Output: names/work/candidates.jsonl  (one JSON object per line)
  first line  {"header": {"extracts": [{"file", "replication_timestamp"}, ...]}}
              -- the extracts it was built from (frasch.candidates); `frasch match` warns
              when that set changes between two of its runs
  then        {"src","t","id","lon","lat","tags":{...}}  per candidate
              (frasch.candidates), with the tags the pipeline reads
              (frasch.osmtags.KEPT_KEYS) and no other

Tag filter (object must carry a name the matcher looks for,
frasch.osmtags.NAME_FIELDS, AND one of):
  place=*, natural=<water-ish/island-ish>, water=*, waterway=*, landuse=*,
  boundary=administrative|political|historic|maritime|land_area|place|
           protected_area,
  man_made=*, historic=*,
  highway=*  -- only inside North Frisia (frasch.geo.NF_BBOX, Helgoland included)
  -- the class tags (frasch.osmtags.CLASS_KEYS) -- or, as a near miss a
  reviewer may still pick though no kind matches on it:
  amenity=harbour, harbour=*, leisure=marina, admin_level=*, wikidata=*,
  wikipedia=*

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

Run:  frasch candidates tiles/data/*.osm.pbf
"""

from __future__ import annotations

import array
import bisect
import collections
import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from typing import IO

import osmium

from frasch import candidates, cli, files, geo, osmscan
from frasch.geo import LonLat
from frasch.osmtags import CLASS_KEYS, KEPT_KEYS, NAME_FIELDS, Tags
from frasch.paths import Workspace

NATURAL_KEEP = {
    "water",
    "bay",
    "strait",
    "wetland",
    "sand",
    "shoal",
    "beach",
    "island",
    "islet",
    "archipelago",
    "peninsula",
    "cape",
    "reef",
    "mud",
    "dune",
    "spring",
    "glacier",
    "isthmus",
    "hill",
    "ridge",
}
BOUNDARY_KEEP = {
    "administrative",
    "political",
    "historic",
    "maritime",
    "land_area",
    "place",
    "protected_area",
}
# The values of a class tag that make an object a candidate; of a class tag
# that is not listed, any value does.
KEEP_VALUES = {"natural": NATURAL_KEEP, "boundary": BOUNDARY_KEEP}
# The class tags that make a candidate only inside North Frisia: named roads.
NF_ONLY_CLASSES = {"highway"}
# What else makes a named object a candidate, by the name the scan counts it
# under: nothing a kind matches on, but a near miss a reviewer may still pick.
ALSO_KEPT: tuple[tuple[str, Callable[[Tags], bool]], ...] = (
    ("harbour", lambda tags: "harbour" in tags or tags.get("amenity") == "harbour"),
    ("marina", lambda tags: tags.get("leisure") == "marina"),
    ("admin_level", lambda tags: "admin_level" in tags),
    ("wikidata", lambda tags: "wikidata" in tags),
    ("wikipedia", lambda tags: "wikipedia" in tags and "wikidata" not in tags),
)


def kept_for(tags: Tags, in_north_frisia: bool) -> list[str]:
    """Why a named object is a candidate -- its class tags, and what else
    keeps it (ALSO_KEPT) --, nothing if it is none.  `in_north_frisia`:
    whether it lies there."""

    def is_class(key: str) -> bool:
        if key not in tags or (key in NF_ONLY_CLASSES and not in_north_frisia):
            return False
        return key not in KEEP_VALUES or tags[key] in KEEP_VALUES[key]

    return [key for key in CLASS_KEYS if is_class(key)] + [
        name for name, holds in ALSO_KEPT if holds(tags)
    ]


class WayCentroids:
    """Compact way_id -> centroid store, looked up by bisection.

    Ways must arrive in ascending id order, as they do in a sorted extract
    (Geofabrik's are).  Out-of-order input raises: the lookup would silently
    miss, and every relation would lose its position."""

    def __init__(self) -> None:
        self.ids = array.array("q")
        self.lon = array.array("f")
        self.lat = array.array("f")

    def add(self, wid: int, lon: float, lat: float) -> None:
        if self.ids and wid < self.ids[-1]:
            raise ValueError(
                f"way {wid} comes after way {self.ids[-1]}: the "
                f"extract is not sorted by id -- sort it first "
                f"(`osmium sort in.osm.pbf -o sorted.osm.pbf`)"
            )
        self.ids.append(wid)
        self.lon.append(lon)
        self.lat.append(lat)

    def get(self, wid: int) -> LonLat | None:
        i = bisect.bisect_left(self.ids, wid)
        if i < len(self.ids) and self.ids[i] == wid:
            return self.lon[i], self.lat[i]
        return None


def first_location(w: osmium.osm.Way) -> LonLat | None:
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


def way_centroid(w: osmium.osm.Way, sample: int = 12) -> LonLat | None:
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


def has_name(tags: osmium.osm.TagList) -> bool:
    """Whether an object carries a name the matcher looks for (works on the
    C++ TagList, before the tags are copied)."""
    return any(key in tags for key in NAME_FIELDS)


def process(
    pbf: str, src: str, out: IO[str], counts: collections.Counter[str], idx: str = "flex_mem"
) -> None:
    ways = WayCentroids()
    t0 = time.time()
    n_seen = 0
    fp = osmium.FileProcessor(pbf).with_locations(idx)
    for o in fp:
        n_seen += 1
        otags = o.tags
        lon: float | None
        lat: float | None

        if isinstance(o, osmium.osm.Way):
            # every way gets a cheap position so that relation centroids can be
            # averaged from their member ways further down the file
            c = first_location(o)
            if c:
                ways.add(o.id, c[0], c[1])
            if not otags or not has_name(otags):
                continue
            lon, lat = way_centroid(o) or c or (None, None)
        elif isinstance(o, osmium.osm.Node):
            if not otags or not has_name(otags):
                continue
            loc = o.location
            lon, lat = (loc.lon, loc.lat) if loc.valid() else (None, None)
        elif isinstance(o, osmium.osm.Relation):
            if not otags or not has_name(otags):
                continue
            lon, lat = _relation_centroid(o, ways) or (None, None)
        else:  # an area or a changeset: never a candidate
            continue

        tags = dict(otags)
        why = kept_for(tags, geo.in_north_frisia(lon, lat))
        if not why:
            continue
        rec = _record(o, src, lon, lat, tags)
        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        counts.update(why)
        counts["_total"] += 1
        counts["_total_" + rec["t"]] += 1
    print(
        f"  {src}: {n_seen:,} objects scanned, "
        f"{len(ways.ids):,} way centroids cached, {time.time() - t0:.0f}s",
        file=sys.stderr,
    )


def _relation_centroid(r: osmium.osm.Relation, ways: WayCentroids) -> LonLat | None:
    """Average of the cached positions of a relation's member ways."""
    sx = sy = 0.0
    n = 0
    for m in r.members:
        if m.type == "w":
            cc = ways.get(m.ref)
            if cc:
                sx += cc[0]
                sy += cc[1]
                n += 1
    if not n:
        return None
    return sx / n, sy / n


def _record(
    o: osmium.osm.Node | osmium.osm.Way | osmium.osm.Relation,
    src: str,
    lon: float | None,
    lat: float | None,
    tags: Tags,
) -> candidates.Candidate:
    """The record of a candidate at (lon, lat): of its `tags`, those the
    pipeline reads."""
    return {
        "src": src,
        "t": o.type_str(),  # 'n' | 'w' | 'r'
        "id": o.id,
        "lon": round(lon, 6) if lon is not None else None,
        "lat": round(lat, 6) if lat is not None else None,
        "tags": {key: tags[key] for key in KEPT_KEYS if key in tags},
    }


def run(ws: Workspace, pbfs: Sequence[str], index: str = "flex_mem") -> None:
    """Scan the extracts `pbfs` into the workspace's candidates file and
    count what was found; `index`: pyosmium's node-location index."""
    os.makedirs(os.path.dirname(ws.candidates), exist_ok=True)
    counts: collections.Counter[str] = collections.Counter()
    t0 = time.time()
    with files.replacing(ws.candidates, text=True) as fh:
        fh.write(
            json.dumps(candidates.header(osmscan.extract_stamps(pbfs)), ensure_ascii=False) + "\n"
        )
        for p in pbfs:
            src = os.path.basename(p).split("-latest")[0].split(".")[0]
            print(f"scanning {p} ...", file=sys.stderr)
            process(p, src, fh, counts, index)

    print(f"\nwrote {counts['_total']:,} candidates to {ws.candidates} in {time.time() - t0:.0f}s")
    print(
        f"  nodes {counts['_total_n']:,}  ways {counts['_total_w']:,}  "
        f"relations {counts['_total_r']:,}"
    )
    print("counts by tag class (an object can count in several):")
    for k, v in sorted(counts.items()):
        if not k.startswith("_"):
            print(f"  {v:8,d}  {k}")


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("candidates", __doc__)
    ap.add_argument("pbf", nargs="+", help="OSM extracts to scan")
    cli.add_workspace_options(ap, "candidates", "work")
    ap.add_argument(
        "--location-index",
        default="flex_mem",
        help="pyosmium node-location index (default flex_mem)",
    )
    a = ap.parse_args(argv)
    run(cli.workspace(a), a.pbf, a.location_index)
    return 0
