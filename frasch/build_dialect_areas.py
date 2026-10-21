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
that fails, since nothing else would ever notice the gap.  The report lists
those references.  `--allow-missing`
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
           research `note` of its dialect_areas.csv row -- plus the
           municipalities of Nordfriesland, Schleswig-Flensburg and
           Flensburg that no row claims at all, marked `assigned: false`.
           This one is for the review overlay only (web `?areas`, see
           web/src/dev/areas/AreaPanel.tsx); a reviewer needs to see which
           municipality got which variety and why, and that an unassigned
           one is Low Saxon by default.  `--no-parts` leaves
           it unwritten.

  NOTHING in the Python pipeline may read --parts.  Its features are
  municipalities, not dialects, so feeding it to AreaIndex would silently
  change the unit of every dialect lookup.  The unassigned features carry no
  `dialect` property at all, which makes AreaIndex refuse the file outright
  rather than quietly loading it.

How the geometry is read: not by letting pyosmium build every area of the
file (which takes a location cache for the whole extract), but in the three
id-filtered passes of osmscan.read_geometry -- the wanted relations, then
their member ways, then those ways' nodes.  The rings are assembled by
frasch.osmgeom; the polygons of one dialect are unioned, simplified
(0.0005 deg, ~50 m -- these are label-lookup areas, not a cadastre) and
written as one Feature per dialect with coordinates rounded to 5 decimals.

The steps are apart: `scan` reads the extracts, `build` makes both files'
contents of what it found -- a pure function, which reads nothing, writes
nothing and prints nothing -- and `run` prints the report and writes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections.abc import Collection, Container, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple, NotRequired, TypedDict

import osmium
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from frasch import cli, dialect_areas, dialects, files, osmgeom, osmscan, refs
from frasch.dialect_areas import AreaRow
from frasch.dialects import Dialect, Registry
from frasch.errors import PipelineError, ValidationError
from frasch.geo import KM_PER_DEGREE
from frasch.osmscan import Geometry
from frasch.paths import StrPath, Workspace
from frasch.provenance import BuiltFrom, ExtractStamp, Stamp
from frasch.refs import OsmRef

SIMPLIFY_DEG = 0.0005  # ~50 m
# Neighbouring municipalities are simplified independently, so a shared
# boundary drifts by up to the tolerance in *each* of them.  At 0.0005 that is
# a ~50 m crack between two areas that actually touch -- 2-3 px at the zoom the
# review happens at.  0.0001 is sub-pixel below z16.
PARTS_SIMPLIFY_DEG = 0.0001  # ~11 m
# the decimals of a coordinate in both GeoJSON files (~1 m)
GEOJSON_DECIMALS = 5

# German municipality key, used to scope the "not assigned to any dialect"
# features.  Every admin_level=8 relation in the Schleswig-Holstein extract
# carries one of these keys.  The districts scanned are Schleswig south of
# the border, where the area list says which variety is spoken: Kreis
# Nordfriesland (01054), Kreis Schleswig-Flensburg (01059) and Flensburg
# (01001).  A municipality there that no row claims is Low Saxon by default;
# one outside them is simply not part of the dialect map.  Helgoland is the
# one assigned area outside (Kreis Pinneberg, 01056); it is named by the CSV,
# so the scan never has to find it.  Kreis Rendsburg-Eckernförde's part of
# Schleswig is Low Saxon by default and needs no review.
AGS_KEYS = ("de:regionalschluessel", "de:amtlicher_gemeindeschluessel")
DEFAULT_UNASSIGNED_AGS = ("01054", "01059", "01001")


class DialectProperties(TypedDict):
    """A feature of --areas: one dialect."""

    dialect: str
    label: str


class PartIdentity(TypedDict):
    """What a feature of --parts is the area of: the row of the area list
    that assigns it, or a municipality no row assigns (`assigned` false) --
    one without a dialect and without a row."""

    assigned: bool
    name: str
    osm: str
    dialect: NotRequired[str]
    note: NotRequired[str]
    line: NotRequired[int]


class PartProperties(PartIdentity):
    """A feature of --parts, as names/dialect-area-parts.schema.json defines
    it: one municipality."""

    km2: float


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
    unassigned_ags: NotRequired[list[str]]


class FeatureCollection[P](TypedDict):
    type: str
    properties: CollectionProperties
    features: list[Feature[P]]


def read_areas(path: str, reg: Registry) -> list[AreaRow]:
    """The rows of the dialect area list in file order, as
    `dialect_areas.area_rows` reads them -- {"line", "dialect", "name",
    "note", "osm", "refs"}; stops on the rows that break the list's rules,
    naming all of them."""
    if not os.path.exists(path):
        raise PipelineError(f"dialect area list not found: {path}")
    rows, problems = dialect_areas.area_rows(path, reg)
    if problems:
        raise ValidationError(problems)
    return rows


def claimed_by(rows: Iterable[AreaRow]) -> dict[OsmRef, AreaRow]:
    """-> {reference: the row that names it}, in file order.  A reference
    is on one row only (`dialect_areas.area_rows`); one written twice there
    is one all the same."""
    return {ref: row for row in rows for ref in row["refs"]}


def km2(geom: BaseGeometry) -> float:
    """Rough area in km² (equirectangular around the geometry's centre) --
    for the report only."""
    lat = geom.centroid.y
    return geom.area * (KM_PER_DEGREE**2) * math.cos(math.radians(lat))


def round_geojson(obj: object) -> object:
    if isinstance(obj, (list, tuple)):
        return [round_geojson(o) for o in obj]
    if isinstance(obj, float):
        return round(obj, GEOJSON_DECIMALS)
    return obj


def simplified(geom: BaseGeometry, tol: float) -> BaseGeometry:
    """`geom` simplified to `tol`, kept valid."""
    if tol:
        geom = geom.simplify(tol, preserve_topology=True)
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def stamp(ws: Workspace, extracts: Sequence[ExtractStamp] | None) -> Stamp:
    """What the dialect areas are built from: the area list, the dialect
    registry and the extracts (None: not at hand, see `Stamp`)."""
    return Stamp.of({"dialect_areas.csv": ws.area_list, "dialects.csv": ws.dialects}, extracts)


@dataclass(frozen=True)
class Options:
    """How a build differs from the usual one."""

    simplify: float = SIMPLIFY_DEG
    parts_simplify: float = PARTS_SIMPLIFY_DEG
    # the municipality-key prefixes of the districts whose unclaimed
    # municipalities join the parts; none: none do
    unassigned_ags: tuple[str, ...] = DEFAULT_UNASSIGNED_AGS
    allow_missing: bool = False  # write although a reference gave no geometry
    parts: bool = True  # build the per-municipality file too

    @property
    def scanned_ags(self) -> tuple[str, ...]:
        """The districts the scan looks for unclaimed municipalities in:
        none when the parts, the only file that shows them, are not built."""
        return self.unassigned_ags if self.parts else ()


USUAL = Options()


class Source(NamedTuple):
    """What both files record of where they come from."""

    name: str  # the area list's file name
    built_from: BuiltFrom


class Municipality(NamedTuple):
    """A municipality of the scanned districts that no row of the area list claims."""

    name: str
    polygon: BaseGeometry


@dataclass
class Scan:
    """What the extracts hold of the areas, over every extract read."""

    claimed: dict[OsmRef, BaseGeometry] = field(default_factory=dict)  # by the area list
    unclaimed: dict[OsmRef, Municipality] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)  # with the rings of a claimed area
    report: list[str] = field(default_factory=list)  # a line per extract read


class Parts(NamedTuple):
    """The --parts file, and what its report says about it."""

    fc: FeatureCollection[PartProperties]
    skipped: int  # rows without geometry
    unassigned: int  # municipalities no row claims


class Areas(NamedTuple):
    """What one build gives: the contents of both files, and what there is
    to say about them."""

    dialects: FeatureCollection[DialectProperties]
    polygons: int
    parts: Parts | None
    report: list[str]
    missing: int  # references that gave no geometry, listed in the report


def scan(
    pbfs: Iterable[StrPath], claimed: Collection[OsmRef], unassigned_ags: Sequence[str]
) -> Scan:
    """Read out of the extracts `pbfs` the polygons of the references
    `claimed` and of the municipalities of the districts `unassigned_ags`
    (municipality-key prefixes) that are none of them.  An extract is asked only for the
    references no earlier one held."""
    found = Scan()

    def read(pbf: StrPath, wanted: set[OsmRef]) -> dict[OsmRef, BaseGeometry]:
        started = time.time()
        # The unclaimed municipalities ride along in the same way/node
        # passes: their member ways are mostly the *same* ways, since
        # neighbours share a boundary.
        loose = _unclaimed_relations(pbf, unassigned_ags, {*claimed, *found.unclaimed})
        geometry = osmscan.read_geometry(pbf, wanted, loose)
        found.report.append(_extract_line(pbf, wanted, geometry, len(loose), time.time() - started))
        found.unclaimed.update(_municipalities(loose, geometry))
        return _polygons(sorted(wanted), geometry, found.problems)

    found.claimed = osmscan.across(pbfs, claimed, read)
    return found


def build(
    rows: Sequence[AreaRow], reg: Registry, found: Scan, source: Source, options: Options = USUAL
) -> Areas:
    """The dialect areas of the rows of the area list, from what a scan
    `found` of them.  Pure: it reads no file, writes none and prints
    nothing -- what there is to say is the `report` of the result."""
    claims = claimed_by(rows)
    dissolved = _dissolved(claims, reg, found.claimed, options.simplify)
    if not dissolved:
        raise PipelineError("no geometry found -- is the extract the right region?")
    missing = [(ref, row) for ref, row in claims.items() if ref not in found.claimed]
    report = [
        *map(_dialect_line, dissolved),
        *(f"  ! {problem}" for problem in found.problems),
        *_missing_lines(missing),
    ]
    return Areas(
        dialects=_dialect_fc(source, options.simplify, dissolved),
        polygons=sum(_polygon_count(d.area) for d in dissolved),
        parts=build_parts(rows, found, source, options) if options.parts else None,
        report=report,
        missing=len(missing),
    )


def build_parts(rows: Sequence[AreaRow], found: Scan, source: Source, options: Options) -> Parts:
    """The --parts FeatureCollection -- one Feature per municipality, see the
    module docstring for why this is a separate file from --areas -- with the
    count of rows without geometry (the report lists their references)."""
    assigned = _assigned_parts(rows, found.claimed)
    parts = [*assigned, *_unassigned_parts(found.unclaimed)]
    fc: FeatureCollection[PartProperties] = {
        "type": "FeatureCollection",
        "properties": {
            "source": source.name,
            "simplify_deg": options.parts_simplify,
            "unit": "one feature per municipality",
            "unassigned_ags": list(options.unassigned_ags) if found.unclaimed else [],
            "built_from": source.built_from,
        },
        "features": [
            _part_feature(about, polygons, options.parts_simplify) for about, polygons in parts
        ],
    }
    return Parts(fc, skipped=len(rows) - len(assigned), unassigned=len(found.unclaimed))


def write(areas: Areas, ws: Workspace) -> None:
    """Write both files of a build and report on them.  Both were computed
    in full before either is written, so a problem building the parts cannot
    leave the areas written on their own."""
    _write_dialects(ws.areas, areas.dialects, areas.polygons)
    if areas.parts is not None:
        write_parts(ws.parts, areas.parts)


def run(ws: Workspace, reg: Registry, pbfs: Sequence[StrPath], options: Options = USUAL) -> None:
    """Build the dialect areas, say what the scan and the build found, and
    write them -- unless a reference gave no geometry and
    `options.allow_missing` is off: a dialect area silently missing a
    reference is worse than a stopped build, nothing downstream would ever
    notice the gap."""
    rows = read_areas(ws.area_list, reg)
    claimed = claimed_by(rows)
    print(
        f"area list : {ws.area_list} -> {len(claimed)} OSM objects, "
        f"{len({row['dialect'] for row in rows})} dialects"
    )
    found = scan(pbfs, claimed, options.scanned_ags)
    cli.say(found.report)
    source = Source(
        os.path.basename(ws.area_list), stamp(ws, osmscan.extract_stamps(pbfs)).as_json()
    )
    areas = build(rows, reg, found, source, options)
    cli.say(areas.report)
    if areas.missing and not options.allow_missing:
        raise PipelineError(
            f"{areas.missing} object(s) of {source.name} not found in the extract(s), listed "
            "above -- run with --allow-missing to build anyway; nothing was written"
        )
    write(areas, ws)


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    a = _parse_args(argv)
    ws = cli.workspace(a)
    options = Options(
        unassigned_ags=() if a.no_unassigned else DEFAULT_UNASSIGNED_AGS,
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
        "--no-parts",
        action="store_true",
        help="leave the per-municipality areas of the review overlay (--parts) unwritten",
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


def _unclaimed_relations(
    pbf: StrPath, ags_prefixes: Sequence[str], skip: Container[OsmRef]
) -> dict[int, osmscan.Relation]:
    """The municipality relations of the districts `ags_prefixes` (none: of
    none) that are not among `skip` -- those a row claims or an earlier
    extract held.

    Scans every relation rather than filtering by id, because the whole point
    is to find the ones nobody has written down yet.  The filter is the German
    municipality key (`de:regionalschluessel`), not a bounding box: a box would
    also catch the neighbouring Kreise, which are not part of the dialect map
    at all and would read as gaps in it."""
    if not ags_prefixes:
        return {}
    found = osmscan.relations_where(pbf, lambda tags: _is_municipality_of(tags, ags_prefixes))
    return {i: relation for i, relation in found.items() if ("r", i) not in skip}


def _is_municipality_of(tags: osmium.osm.TagList, ags_prefixes: Sequence[str]) -> bool:
    key = next((tags[k] for k in AGS_KEYS if k in tags), "")
    return (
        tags.get("boundary") == "administrative"
        and _is_municipality(tags)
        and key.startswith(tuple(ags_prefixes))
    )


def _is_municipality(tags: osmium.osm.TagList) -> bool:
    """An admin_level=8 boundary, or a city that is a district of its own
    (kreisfreie Stadt: Flensburg), which OSM tags as the district it is."""
    level = tags.get("admin_level")
    return level == "8" or (level == "6" and tags.get("de:place") == "city")


def _extract_line(
    pbf: StrPath, wanted: Collection[OsmRef], geometry: Geometry, unclaimed: int, seconds: float
) -> str:
    """What one extract held of the references `wanted`, for the report."""
    return (
        f"{os.path.basename(pbf)}: {len(geometry.relations) - unclaimed}"
        f"/{len(refs.ids_of(wanted, 'r'))} "
        f"relations, {len(geometry.ways):,} ways, {len(geometry.nodes):,} nodes"
        f"{f', {unclaimed} unclaimed municipalities' if unclaimed else ''} "
        f"({seconds:.0f}s)"
    )


def _polygons(
    wanted: Iterable[OsmRef], geometry: Geometry, problems: list[str]
) -> dict[OsmRef, BaseGeometry]:
    """-> {ref: polygon} for the references `geometry` holds a polygon of."""
    found = {ref: osmgeom.polygon_of(ref, geometry, problems) for ref in wanted}
    return {ref: polygon for ref, polygon in found.items() if polygon is not None}


def _municipalities(
    loose: Mapping[int, osmscan.Relation], geometry: Geometry
) -> dict[OsmRef, Municipality]:
    """The unclaimed municipalities `loose` that have a polygon, by id."""
    # Their own problems are noise: nobody has claimed these, so a
    # broken ring means "not reviewable", not "the data is wrong".
    polygons = _polygons((("r", i) for i in sorted(loose)), geometry, [])
    return {
        ref: Municipality(loose[ref[1]]["tags"].get("name", ""), polygon)
        for ref, polygon in polygons.items()
    }


class _Dissolved(NamedTuple):
    """A dialect's area: the polygons of its references as one."""

    dialect: Dialect
    objects: int  # the references it is made of
    area: BaseGeometry


def _dissolved(
    claims: Mapping[OsmRef, AreaRow],
    reg: Registry,
    claimed: Mapping[OsmRef, BaseGeometry],
    tol: float,
) -> list[_Dissolved]:
    """The area of every dialect that has any geometry, in registry order,
    simplified to `tol`."""
    polygons: dict[str, list[BaseGeometry]] = {}
    for ref, row in claims.items():
        if ref in claimed:
            polygons.setdefault(row["dialect"], []).append(claimed[ref])
    return [
        _Dissolved(d, len(polygons[d["tag"]]), simplified(unary_union(polygons[d["tag"]]), tol))
        for d in reg
        if polygons.get(d["tag"])
    ]


def _dialect_line(d: _Dissolved) -> str:
    n_pts = len(json.dumps(mapping(d.area)).split(","))
    return (
        f"  {d.dialect['tag']:<15} {d.objects:>2} object(s) -> "
        f"{_polygon_count(d.area):>2} polygon(s), "
        f"{km2(d.area):8.1f} km², valid={d.area.is_valid}, ~{n_pts} coords"
    )


def _polygon_count(geom: BaseGeometry) -> int:
    return len(getattr(geom, "geoms", [geom]))


def _missing_lines(missing: Sequence[tuple[OsmRef, AreaRow]]) -> list[str]:
    """The references that gave no geometry, each with its row's name and
    dialect; nothing when there are none."""
    if not missing:
        return []
    return [
        "",
        f"{len(missing)} object(s) not found in the extract(s):",
        *(
            f"  {refs.format([ref])}  {row['name'] or '?'} ({row['dialect']})"
            for ref, row in sorted(missing, key=lambda found: found[0])
        ),
    ]


def _feature[P](geom: BaseGeometry, properties: P) -> Feature[P]:
    return {"type": "Feature", "properties": properties, "geometry": round_geojson(mapping(geom))}


def _dialect_fc(
    source: Source, simplify: float, dissolved: Iterable[_Dissolved]
) -> FeatureCollection[DialectProperties]:
    """The --areas FeatureCollection: one Feature per dialect."""
    return {
        "type": "FeatureCollection",
        "properties": {
            "source": source.name,
            "simplify_deg": simplify,
            "built_from": source.built_from,
        },
        "features": [
            _feature(d.area, {"dialect": d.dialect["tag"], "label": d.dialect["label"]})
            for d in dissolved
        ],
    }


def _assigned_parts(
    rows: Iterable[AreaRow], claimed: Mapping[OsmRef, BaseGeometry]
) -> list[tuple[PartIdentity, list[BaseGeometry]]]:
    """A part per row that has any geometry, with the polygons of its
    references."""
    parts: list[tuple[PartIdentity, list[BaseGeometry]]] = []
    for row in rows:
        polygons = [claimed[ref] for ref in row["refs"] if ref in claimed]
        if not polygons:
            continue
        about: PartIdentity = {
            "assigned": True,
            "dialect": row["dialect"],
            "name": row["name"],
            "note": row["note"],
            "osm": row["osm"],
            "line": row["line"],
        }
        parts.append((about, polygons))
    return parts


def _unassigned_parts(
    unclaimed: Mapping[OsmRef, Municipality],
) -> list[tuple[PartIdentity, list[BaseGeometry]]]:
    """A part per municipality no row claims, by name."""
    # No `dialect` key on these on purpose: it is what stops AreaIndex from
    # ever loading this file (see the module docstring).
    return [
        ({"assigned": False, "name": found.name, "osm": refs.format([ref])}, [found.polygon])
        for ref, found in sorted(unclaimed.items(), key=lambda item: item[1].name)
    ]


def _part_feature(
    about: PartIdentity, polygons: Sequence[BaseGeometry], tol: float
) -> Feature[PartProperties]:
    """The Feature of one part, assigned or not: its polygons as one,
    simplified to `tol`."""
    # also of a single polygon: the union says where its rings start, and
    # that decides which vertices simplifying keeps
    area = simplified(unary_union(polygons), tol)
    return _feature(area, {**about, "km2": round(km2(area), 1)})


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
