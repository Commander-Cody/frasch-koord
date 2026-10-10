"""names/dialect_areas.csv + OSM extract(s) -> names/dialect_areas.geojson.

Which dialect is spoken where is a question about *areas*, not about single
places: a Warft on Hallig Hooge is Halligfriesisch even when the name list
says nothing about it, and the name of a place whose own column is empty is
still the name of the dialect around it.  `dialect_areas.csv` answers it the
only way that stays maintainable: by naming the OSM municipalities (and, where
a municipality is the wrong unit, the island polygons) that belong to each
dialect.  This command turns those references into geometry.

    frasch areas <in.osm.pbf> [<in.osm.pbf> ...] [--allow-missing] [--no-parts]

The result is **committed**: it is a handful of kilobytes, the injector and
the search exporter need it on every build, and a planet build must not have
to re-extract boundaries.  Re-run it when dialect_areas.csv changes or when a
municipality boundary in OSM has moved -- with a Schleswig-Holstein extract
(`tiles/data/schleswig-holstein-latest.osm.pbf`), which covers every Frisian
area there is.

A reference from dialect_areas.csv that produced no geometry at all (wrong
extract, a typo'd id, an object deleted upstream) stops the run before either
file is written -- a *silently smaller* dialect area is worse than a build
that fails, since nothing else would ever notice the gap.  `--allow-missing`
builds anyway, the same way a partial/unclosed ring already only warns: that
ring's object did produce *some* geometry, just not all of it. Both outputs
are written atomically (`files.atomic_write`) and only once every
reference has been resolved and every polygon assembled, so a failed or
interrupted run never leaves a truncated or half-updated file, and each one's
`properties.built_from` records the git blob hash of dialect_areas.csv and
dialects.csv plus the file name and replication timestamp of every extract
read, so a stale file can be told apart from a current one.

Two files come out of one run, from the same in-memory geometry so that they
cannot disagree:

  --areas  one Feature per *dialect*, municipalities dissolved.  This is
           the lookup file: the injector and the search exporter read it
           through dialect_areas.AreaIndex ("smallest containing area wins").
  --parts  one Feature per *municipality*, carrying the `name` and the
           research `note` of its dialect_areas.csv row -- plus the Kreis
           Nordfriesland municipalities that no row claims at all, marked
           `assigned: false`.  This one is for the review overlay only
           (web `?areas`, see web/src/dev/AreaPanel.tsx); a reviewer needs
           to see which municipality got which dialect and why, and an
           unassigned one is a hole in the coverage.  `--no-parts` leaves
           it unwritten.

  NOTHING in the Python pipeline may read --parts.  Its features are
  municipalities, not dialects, so feeding it to AreaIndex would silently
  change the unit of every dialect lookup.  The unassigned features carry no
  `dialect` property at all, which makes AreaIndex refuse the file outright
  rather than quietly loading it.

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
import json
import math
import os
import time
from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple, NotRequired, TypedDict

import osmium
from shapely.geometry.base import BaseGeometry

from frasch import cli, dialect_areas, dialects, files, osmgeom, osmscan, refs
from frasch.dialect_areas import AreaRow
from frasch.dialects import Dialect, Registry
from frasch.errors import PipelineError, ValidationError
from frasch.geo import LonLat
from frasch.osmscan import Rings
from frasch.paths import StrPath, Workspace
from frasch.provenance import BuiltFrom, ExtractStamp, Stamp
from frasch.refs import OsmRef

SIMPLIFY_DEG = 0.0005  # ~50 m
# Neighbouring municipalities are simplified independently, so a shared
# boundary drifts by up to the tolerance in *each* of them.  At 0.0005 that is
# a ~50 m crack between two areas that actually touch -- 2-3 px at the zoom the
# review happens at.  0.0001 is sub-pixel below z16.
PARTS_SIMPLIFY_DEG = 0.0001  # ~11 m
ROUND = 5

# German municipality key, used to scope the "not assigned to any dialect"
# features.  Every admin_level=8 relation in the Schleswig-Holstein extract
# carries one of these keys, and Kreis Nordfriesland is 01054 -- the district
# that is (or was) Frisian-speaking, so a municipality outside it is not a gap
# in the dialect map but simply not part of it.  Helgoland is the one assigned
# area outside (Kreis Pinneberg, 01056); it is named by the CSV, so the scan
# never has to find it.
AGS_KEYS = ("de:regionalschluessel", "de:amtlicher_gemeindeschluessel")
DEFAULT_UNASSIGNED_AGS = "01054"


class DialectProperties(TypedDict):
    """A feature of --areas: one dialect."""

    dialect: str
    label: str


class PartProperties(TypedDict):
    """A feature of --parts, as names/dialect-area-parts.schema.json defines
    it: one municipality; one that no row assigns (`assigned` false) has no
    dialect and no row."""

    fid: int
    assigned: bool
    name: str
    osm: str
    km2: float
    dialect: NotRequired[str]
    note: NotRequired[str]
    line: NotRequired[int]


class Feature[P](TypedDict):
    """A GeoJSON Feature as written here, `properties` of the file's kind."""

    type: str
    properties: P
    geometry: object


class CollectionProperties(TypedDict):
    """The file's own properties: what it was built from, and how."""

    source: str
    simplify_deg: float
    built_from: BuiltFrom
    unit: NotRequired[str]
    unassigned_ags: NotRequired[str]


class FeatureCollection[P](TypedDict):
    type: str
    properties: CollectionProperties
    features: list[Feature[P]]


def read_areas(
    path: str, reg: Registry
) -> tuple[dict[OsmRef, str], dict[OsmRef, str], list[AreaRow]]:
    """-> ({(type, id): dialect_tag}, {(type, id): label}, [row]) in file order.

    The rows are those of `dialect_areas.area_rows` -- {"line", "dialect", "name",
    "note", "osm", "refs"} -- for the per-municipality parts output.  The two
    indexes stay keyed by OSM reference because that is what the dissolve
    loop and the "not in the extract" report need.
    """
    if not os.path.exists(path):
        raise PipelineError(f"dialect area list not found: {path}")
    rows, problems = dialect_areas.area_rows(path, reg)
    if problems:
        raise ValidationError(problems)
    by_ref = {ref: row["dialect"] for row in rows for ref in row["refs"]}
    labels = {ref: row["name"] for row in rows for ref in row["refs"]}
    return by_ref, labels, rows


def read_admin_relations(
    path: str, ags_prefix: str, skip: Container[int]
) -> tuple[dict[int, Rings], dict[int, str]]:
    """Municipality relations of one district that no dialect claims.

    -> ({rel_id: {'outer': [...], 'inner': [...]}}, {rel_id: name})

    Scans every relation rather than filtering by id, because the whole point
    is to find the ones nobody has written down yet.  The filter is the German
    municipality key (`de:regionalschluessel`), not a bounding box: a box would
    also catch the neighbouring Kreise, which are not part of the dialect map
    at all and would read as gaps in it.  `skip` holds the relation ids the
    CSV already assigns.
    """
    rings: dict[int, Rings] = {}
    names: dict[int, str] = {}
    fp = osmium.FileProcessor(path, osmium.osm.RELATION)
    for r in fp:
        if not isinstance(r, osmium.osm.Relation):
            continue
        tags = r.tags
        if tags.get("boundary") != "administrative":
            continue
        if tags.get("admin_level") != "8":
            continue
        if r.id in skip:
            continue
        key = next((tags[k] for k in AGS_KEYS if k in tags), "")
        if not key.startswith(ags_prefix):
            continue
        rings[r.id] = osmscan.rings_of(r)
        names[r.id] = tags.get("name") or ""
    return rings, names


def km2(geom: BaseGeometry) -> float:
    """Rough area in km² (equirectangular around the geometry's centre) --
    for the report only."""
    lat = geom.centroid.y
    return geom.area * (111.32**2) * math.cos(math.radians(lat))


def round_geojson(obj: object, nd: int = ROUND) -> object:
    if isinstance(obj, (list, tuple)):
        return [round_geojson(o, nd) for o in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def stamp(ws: Workspace, extracts: Sequence[ExtractStamp] | None) -> Stamp:
    """What the dialect areas are built from: the area list, the dialect
    registry and the extracts (None: not at hand, see `Stamp`)."""
    return Stamp.of({"dialect_areas.csv": ws.area_list, "dialects.csv": ws.dialects}, extracts)


@dataclass(frozen=True)
class Options:
    """How a build differs from the usual one."""

    simplify: float = SIMPLIFY_DEG
    parts_simplify: float = PARTS_SIMPLIFY_DEG
    # the municipality-key prefix of the district whose unclaimed
    # municipalities join the parts; None: none do
    unassigned_ags: str | None = DEFAULT_UNASSIGNED_AGS
    allow_missing: bool = False  # build although a reference gave no geometry
    parts: bool = True  # build the per-municipality file too


USUAL = Options()


class Parts(NamedTuple):
    """The --parts file, and what its report says about it."""

    fc: FeatureCollection[PartProperties]
    skipped: int  # rows without geometry
    unassigned: int  # municipalities no row claims


class Areas(NamedTuple):
    """What one build gives: the contents of both files."""

    dialects: FeatureCollection[DialectProperties]
    polygons: int
    parts: Parts | None


def build(ws: Workspace, reg: Registry, pbfs: Sequence[StrPath], options: Options = USUAL) -> Areas:
    """The dialect areas of the workspace's area list, from the extracts
    `pbfs`.  Says what it finds as it goes -- a scan takes its time -- and
    writes nothing."""
    by_ref, labels, rows = read_areas(ws.area_list, reg)
    unassigned_ags = options.unassigned_ags if options.parts else None
    print(
        f"area list : {ws.area_list} -> {len(by_ref)} OSM objects, "
        f"{len(set(by_ref.values()))} dialects"
    )

    scan = _Scan()
    for path in pbfs:
        _scan_extract(os.fspath(path), by_ref, unassigned_ags, scan)

    features, total = _dialect_features(reg, by_ref, scan.geoms, options.simplify)
    if not features:
        raise PipelineError("no geometry found -- is the extract the right region?")

    for p in scan.problems:
        print(f"  ! {p}")
    missing = [ref for ref in by_ref if ref not in scan.geoms]
    if missing:
        _report_missing(missing, by_ref, labels, options.allow_missing)

    built_from = stamp(ws, osmscan.extract_stamps(pbfs)).as_json()
    source = os.path.basename(ws.area_list)
    parts = build_parts(source, options, rows, scan, built_from) if options.parts else None
    return Areas(_dialect_fc(source, options.simplify, features, built_from), total, parts)


def write(areas: Areas, ws: Workspace) -> None:
    """Write both files of a build and report on them.  Both were computed
    in full before either is written, so a problem building the parts cannot
    leave the areas written on their own."""
    _write_dialects(ws.areas, areas.dialects, areas.polygons)
    if areas.parts is not None:
        write_parts(ws.parts, areas.parts)


def run(ws: Workspace, reg: Registry, pbfs: Sequence[StrPath], options: Options = USUAL) -> None:
    """Build the dialect areas and write them."""
    write(build(ws, reg, pbfs, options), ws)


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    a = _parse_args(argv)
    ws = cli.workspace(a)
    options = Options(
        simplify=a.simplify,
        parts_simplify=a.parts_simplify,
        unassigned_ags=None if a.no_unassigned else a.unassigned_ags,
        allow_missing=a.allow_missing,
        parts=not a.no_parts,
    )
    run(ws, dialects.read(ws.dialects), a.pbf, options)
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ap = cli.parser("areas", __doc__)
    ap.add_argument("pbf", nargs="+", help="OSM extract(s) holding the areas")
    cli.add_workspace_options(ap, "area_list", "dialects", "areas", "parts")
    ap.add_argument(
        "--simplify",
        type=float,
        default=SIMPLIFY_DEG,
        help=f"tolerance in degrees (default {SIMPLIFY_DEG})",
    )
    ap.add_argument(
        "--no-parts",
        action="store_true",
        help="leave the per-municipality areas of the review overlay (--parts) unwritten",
    )
    ap.add_argument(
        "--parts-simplify",
        type=float,
        default=PARTS_SIMPLIFY_DEG,
        help=f"tolerance for --parts (default "
        f"{PARTS_SIMPLIFY_DEG}); finer than --simplify because "
        f"neighbours are simplified independently and must not "
        f"drift apart",
    )
    ap.add_argument(
        "--unassigned-ags",
        default=DEFAULT_UNASSIGNED_AGS,
        help=f"municipality-key prefix whose unclaimed "
        f"municipalities go into --parts "
        f"(default {DEFAULT_UNASSIGNED_AGS} = Kreis Nordfriesland)",
    )
    ap.add_argument(
        "--no-unassigned",
        action="store_true",
        help="skip the extra relation scan; --parts then holds "
        "only the municipalities the CSV assigns",
    )
    ap.add_argument(
        "--allow-missing",
        action="store_true",
        help="build even when a dialect_areas.csv reference "
        "produced no geometry at all (default: stop and "
        "write nothing)",
    )
    return ap.parse_args(argv)


@dataclass
class _Scan:
    """The polygons found so far, over every extract read."""

    geoms: dict[OsmRef, list[BaseGeometry]] = field(default_factory=dict)  # assigned by the CSV
    free: dict[OsmRef, list[BaseGeometry]] = field(default_factory=dict)  # municipality, no dialect
    free_names: dict[OsmRef, str] = field(default_factory=dict)  # ref -> municipality name
    problems: list[str] = field(default_factory=list)


class _Geometry(NamedTuple):
    """What one extract holds of the objects asked for: relation rings,
    way node lists and node locations."""

    rel: dict[int, Rings]
    ways: dict[int, list[int]]
    nodes: dict[int, LonLat]


def _scan_extract(
    path: str, by_ref: Mapping[OsmRef, str], unassigned_ags: str | None, scan: _Scan
) -> None:
    """Add to `scan` the polygons of the references not found yet, and --
    unless `unassigned_ags` is None -- those of the district's unclaimed
    municipalities."""
    t0 = time.time()
    want = {ref for ref in by_ref if ref not in scan.geoms}
    rel_ids = {i for t, i in want if t == "r"}
    way_ids = {i for t, i in want if t == "w"}
    rel = {i: r["rings"] for i, r in osmscan.relations(path, rel_ids).items()}
    # The unclaimed municipalities ride along in the same way/node passes:
    # their member ways are mostly the *same* ways, since neighbours share
    # a boundary.
    loose: dict[int, Rings] = {}
    loose_names: dict[int, str] = {}
    if unassigned_ags is not None:
        loose, loose_names = _unclaimed_relations(path, unassigned_ags, by_ref, scan.free)
        rel.update(loose)
    geometry = _read_geometry(path, rel, way_ids)
    print(
        f"{os.path.basename(path)}: {len(rel) - len(loose)}/{len(rel_ids)} "
        f"relations, {len(geometry.ways):,} ways, {len(geometry.nodes):,} nodes"
        f"{f', {len(loose)} unclaimed municipalities' if loose else ''} "
        f"({time.time() - t0:.0f}s)"
    )
    for ref in sorted(want):
        polys = osmgeom.polygons_for(ref, *geometry, scan.problems)
        if polys:
            scan.geoms[ref] = polys
    for rel_id in sorted(loose):
        ref = ("r", rel_id)
        # Their own problems are noise: nobody has claimed these, so a
        # broken ring means "not reviewable", not "the data is wrong".
        polys = osmgeom.polygons_for(ref, *geometry, [])
        if polys:
            scan.free[ref] = polys
            scan.free_names[ref] = loose_names.get(rel_id, "")


def _unclaimed_relations(
    path: str, ags_prefix: str, by_ref: Mapping[OsmRef, str], free: Container[OsmRef]
) -> tuple[dict[int, Rings], dict[int, str]]:
    """`read_admin_relations` without the municipalities an earlier extract
    already yielded."""
    claimed = {i for t, i in by_ref if t == "r"}
    loose, loose_names = read_admin_relations(path, ags_prefix, claimed)
    loose = {i: r for i, r in loose.items() if ("r", i) not in free}
    return loose, loose_names


def _read_geometry(path: str, rel: dict[int, Rings], way_ids: set[int]) -> _Geometry:
    """The relations `rel`, plus the ways `way_ids` and every member way of
    `rel`, with the locations of all their nodes."""
    member_ids = {w for r in rel.values() for w in r["outer"] + r["inner"]}
    ways = {i: w["nodes"] for i, w in osmscan.ways(path, way_ids | member_ids).items()}
    node_ids = {n for w in ways.values() for n in w}
    nodes = {i: n["loc"] for i, n in osmscan.nodes(path, node_ids).items()}
    return _Geometry(rel, ways, nodes)


def _dialect_features(
    reg: Registry,
    by_ref: Mapping[OsmRef, str],
    geoms: Mapping[OsmRef, Sequence[BaseGeometry]],
    tol: float,
) -> tuple[list[Feature[DialectProperties]], int]:
    """-> (features, polygon count): one Feature per dialect that has any
    geometry, in registry order, each reported as it is built."""
    features: list[Feature[DialectProperties]] = []
    total = 0
    for d in reg:
        refs = [r for r in by_ref if by_ref[r] == d["tag"] and r in geoms]
        if not refs:
            continue
        feature, n_poly = _dialect_feature(d, refs, geoms, tol)
        features.append(feature)
        total += n_poly
    return features, total


def _dialect_feature(
    d: Dialect,
    refs: Sequence[OsmRef],
    geoms: Mapping[OsmRef, Sequence[BaseGeometry]],
    tol: float,
) -> tuple[Feature[DialectProperties], int]:
    """-> (feature, polygon count): the polygons of `refs` dissolved into
    dialect `d`'s Feature, simplified to `tol`."""
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    geom = unary_union([p for ref in refs for p in geoms[ref]])
    geom = geom.simplify(tol, preserve_topology=True)
    if not geom.is_valid:
        geom = geom.buffer(0)
    n_poly = len(getattr(geom, "geoms", [geom]))
    n_pts = len(json.dumps(mapping(geom)).split(","))
    print(
        f"  {d['tag']:<15} {len(refs):>2} object(s) -> {n_poly:>2} polygon(s), "
        f"{km2(geom):8.1f} km², valid={geom.is_valid}, ~{n_pts} coords"
    )
    feature: Feature[DialectProperties] = {
        "type": "Feature",
        "properties": {"dialect": d["tag"], "label": d["label"]},
        "geometry": round_geojson(mapping(geom)),
    }
    return feature, n_poly


def _report_missing(
    missing: Sequence[OsmRef],
    by_ref: Mapping[OsmRef, str],
    labels: Mapping[OsmRef, str],
    allow_missing: bool,
) -> None:
    """Print the references that produced no geometry; stop the build
    unless `allow_missing`."""
    lines = [f"{len(missing)} object(s) not found in the extract(s):"]
    lines += [
        f"  {refs.format([ref])}  {labels.get(ref) or '?'} ({by_ref[ref]})"
        for ref in sorted(missing)
    ]
    report = "\n".join(lines)
    print(f"\n{report}")
    if not allow_missing:
        # A dialect area silently missing a reference is worse than a
        # stopped build -- nothing downstream would ever notice the gap.
        # Nothing may be written past this point (see the module
        # docstring): both --areas and --parts are still untouched.
        raise PipelineError(
            f"{report}\n\nrun with --allow-missing to build anyway; nothing was written"
        )


def _dialect_fc(
    source: str,
    simplify: float,
    features: list[Feature[DialectProperties]],
    built_from: BuiltFrom,
) -> FeatureCollection[DialectProperties]:
    """The --areas FeatureCollection: one Feature per dialect."""
    return {
        "type": "FeatureCollection",
        "properties": {"source": source, "simplify_deg": simplify, "built_from": built_from},
        "features": features,
    }


def _write_dialects(path: str, fc: FeatureCollection[DialectProperties], total: int) -> None:
    """Write --areas, report on it and check that AreaIndex reads it back."""
    write_geojson(path, fc)
    print(
        f"\nwrote {path} ({len(fc['features'])} features, {total} polygons, "
        f"{os.path.getsize(path) / 1e3:.0f} kB)"
    )
    idx = dialect_areas.AreaIndex.from_geojson(path)
    print(f"reads back as {len(idx)} polygon(s): {idx.summary()}")


def write_geojson(path: str, fc: Mapping[str, object]) -> None:
    """Write one GeoJSON FeatureCollection atomically (files.atomic_write):
    a crash or Ctrl-C half-way must leave either the old file or the new one,
    never a truncated one."""
    data = json.dumps(fc, ensure_ascii=False, separators=(",", ":")) + "\n"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    files.atomic_write(path, data)


def simplified(geom: BaseGeometry, tol: float) -> BaseGeometry:
    """`geom` simplified to `tol`, kept valid."""
    if tol:
        geom = geom.simplify(tol, preserve_topology=True)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def build_parts(
    source: str,
    options: Options,
    rows: Sequence[AreaRow],
    scan: _Scan,
    built_from: BuiltFrom,
) -> Parts:
    """The --parts FeatureCollection -- one Feature per municipality, see the
    module docstring for why this is a separate file from --areas -- with the
    count of rows without geometry (already in the `missing` report).  Pure:
    building it does not touch disk, so it can run to completion before
    anything is written (see `write`)."""
    geoms, free, free_names = scan.geoms, scan.free, scan.free_names
    from shapely.geometry import mapping
    from shapely.ops import unary_union

    features: list[Feature[PartProperties]] = []
    skipped, fid = 0, 0

    for row in rows:
        polys = [p for ref in row["refs"] for p in geoms.get(ref, [])]
        if not polys:
            skipped += 1  # already in the `missing` report
            continue
        geom = simplified(unary_union(polys), options.parts_simplify)
        fid += 1
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "fid": fid,
                    "assigned": True,
                    "dialect": row["dialect"],
                    "name": row["name"],
                    "note": row["note"],
                    "osm": row["osm"],
                    "line": row["line"],
                    "km2": round(km2(geom), 1),
                },
                "geometry": round_geojson(mapping(geom)),
            }
        )

    # No `dialect` key on these on purpose: it is what stops AreaIndex from
    # ever loading this file (see the module docstring).
    for ref in sorted(free, key=lambda r: free_names.get(r, "")):
        geom = simplified(unary_union(free[ref]), options.parts_simplify)
        fid += 1
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "fid": fid,
                    "assigned": False,
                    "name": free_names.get(ref, ""),
                    "osm": refs.format([ref]),
                    "km2": round(km2(geom), 1),
                },
                "geometry": round_geojson(mapping(geom)),
            }
        )

    fc: FeatureCollection[PartProperties]
    fc = {
        "type": "FeatureCollection",
        "properties": {
            "source": source,
            "simplify_deg": options.parts_simplify,
            "unit": "one feature per municipality",
            "unassigned_ags": (options.unassigned_ags or "") if free else "",
            "built_from": built_from,
        },
        "features": features,
    }
    return Parts(fc, skipped, len(free))


def write_parts(path: str, parts: Parts) -> None:
    """Write the --parts FeatureCollection `build_parts` built, and report
    on it."""
    write_geojson(path, parts.fc)
    features = parts.fc["features"]
    print(
        f"wrote {path} ({len(features)} features: "
        f"{len(features) - parts.unassigned} assigned, {parts.unassigned} unassigned"
        f"{f', {parts.skipped} row(s) without geometry' if parts.skipped else ''}, "
        f"{os.path.getsize(path) / 1e3:.0f} kB)"
    )
