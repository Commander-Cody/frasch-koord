"""The dialect areas, built on the dialect registry (frasch.dialects): which
dialect is spoken where.  The one reader of the area list,
names/dialect_areas.csv (`area_rows`), the lookup over the areas built from
it, names/dialect_areas.geojson (`AreaIndex`), and the dialect spoken where
an object of the objects file lies (`dialect_at`).

Which names a place gets from the dialect of the area it lies in is
frasch.placenames' rule.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from typing import TypedDict

from shapely.geometry.base import BaseGeometry

from frasch import refs, tables
from frasch.dialects import Registry
from frasch.errors import Invalid, PipelineError, Problem
from frasch.objects import LocatedObject
from frasch.refs import OsmRef


class AreaRow(TypedDict):
    """A row of the dialect area list, see `area_rows`."""

    line: int
    dialect: str
    name: str
    note: str
    osm: str
    refs: list[OsmRef]


AREA_COLUMNS = ["dialect", "osm", "name", "note"]


def area_rows(path: str, reg: Registry) -> tuple[list[AreaRow], list[Problem]]:
    """-> (rows, problems) of the dialect area list (names/dialect_areas.csv):
    one dict per row that follows its rules -- `line`, `dialect`, `name`,
    `note`, `osm` (normalised) and `refs` (parsed) -- and what is wrong with
    the others.  The one reading of the file's rules, shared by
    frasch.build_dialect_areas (which stops on a problem) and
    frasch.check_inputs (which lists them).

    An OSM reference belongs to one row only: the review overlay's
    `?areas&area=` links name a row by it."""
    table = tables.read_table(path, AREA_COLUMNS)
    known = set(reg.tags)
    rows: list[AreaRow] = []
    problems = list(table.problems)
    first_line: dict[OsmRef, int] = {}
    for n, row in table.records():
        if not row["dialect"] and not row["osm"]:
            continue  # blank spacer line
        try:
            areas = _area_refs(row, known, first_line)
        except Invalid as exc:
            problems.append(Problem(path, n, exc.reason))
            continue
        first_line.update((r, n) for r in areas)
        rows.append(
            {
                "line": n,
                "dialect": row["dialect"],
                "name": row["name"],
                "note": row["note"],
                "osm": refs.format(areas),
                "refs": areas,
            }
        )
    return rows, tables.by_line(problems)


def _area_refs(
    row: Mapping[str, str], known: Collection[str], first_line: Mapping[OsmRef, int]
) -> list[OsmRef]:
    """The areas a row of the list names (`first_line`: those of the rows
    above it, with their line); `Invalid` when the row breaks a rule."""
    if row["dialect"] not in known:
        raise Invalid("", f"unknown dialect {row['dialect']!r} (not in names/dialects.csv)")
    named = refs.parse(row["osm"])
    if not named:
        raise Invalid("", "no OSM reference")
    area_refs = [osm for ref in named if (osm := refs.as_osm_ref(ref)) and osm[0] in ("w", "r")]
    if len(area_refs) < len(named):
        # a node can never be a polygon, and `local/` names an object of our
        # own invention (curation.csv), not an OSM boundary
        bad = [r for r in named if r not in area_refs]
        raise Invalid("", f"{refs.format(bad)}: only way/ or relation/ references are allowed here")
    taken = [r for r in area_refs if r in first_line]
    if taken:
        raise Invalid("", f"{refs.format(taken[:1])} is already on line {first_line[taken[0]]}")
    return area_refs


# --------------------------------------------------------------- areas ----
class AreaIndex:
    """Which dialect is spoken where: point-in-polygon against
    names/dialect_areas.geojson (built by `frasch areas`).

    The smallest polygon containing the point wins, so a small area inside a
    larger one of another dialect is answered correctly -- the Hamburger
    Hallig (Halligfriesisch) lies inside the municipality Reußenköge.
    """

    def __init__(self, polygons: list[tuple[str, BaseGeometry]]):
        # polygons: [(tag, shapely polygon)] -- already exploded into single
        # polygons, so "smallest wins" compares the actual island, not the
        # union of every Hallig
        from shapely import STRtree

        self.polygons = polygons
        self.geoms = [g for _, g in polygons]
        self.tree = STRtree(self.geoms) if self.geoms else None

    @classmethod
    def from_geojson(cls, path: str) -> AreaIndex:
        from shapely.geometry import shape

        with open(path, encoding="utf-8") as fh:
            fc = json.load(fh)
        polygons: list[tuple[str, BaseGeometry]] = []
        for feat in fc.get("features", []):
            tag = (feat.get("properties") or {}).get("dialect")
            if not tag:
                raise PipelineError(f"{path}: a feature has no `dialect` property")
            geom = shape(feat["geometry"])
            polygons.append((tag, geom))
        # explode MultiPolygons: one entry per island / municipality blob
        flat: list[tuple[str, BaseGeometry]] = []
        for tag, geom in polygons:
            for g in getattr(geom, "geoms", [geom]):
                flat.append((tag, g))
        flat.sort(key=lambda tg: tg[1].area)  # smallest first -> first hit wins
        return cls(flat)

    def lookup(self, lon: float | str, lat: float | str) -> str | None:
        if self.tree is None:
            return None
        from shapely.geometry import Point

        pt = Point(float(lon), float(lat))
        best: tuple[str, float] | None = None
        for i in self.tree.query(pt):
            tag, geom = self.polygons[i]
            if geom.covers(pt):
                if best is None or geom.area < best[1]:
                    best = (tag, geom.area)
        return best[0] if best else None

    def __len__(self) -> int:
        return len(self.polygons)

    def summary(self) -> str:
        n: dict[str, int] = {}
        for tag, _ in self.polygons:
            n[tag] = n.get(tag, 0) + 1
        return ", ".join(f"{t} ({c})" for t, c in sorted(n.items()))


# ------------------------------------------------- the dialect of an object ---
# OSM's admin_level of a German municipality; anything lower is a Kreis or an
# Amt, which spans several dialects
MUNICIPALITY_LEVEL = 8


def dialect_at(obj: LocatedObject, areas: AreaIndex | None) -> str | None:
    """The dialect spoken where an object of the objects file lies, or None:
    the area around its point, else the area around its outline point.

    The two points miss in opposite directions: an island's coastline runs
    outside the municipality boundaries the areas are cut from (Amrum), while
    an area may cover only part of an island (the Langeneß municipality holds
    only the south-west third of Oland), so the point inside the island falls
    outside it and a vertex still lands in it.  The first point that is in an
    area at all wins, so nothing that had a dialect can lose it.

    An administrative area above municipality level gets none: Kreis
    Nordfriesland would otherwise be "Nordergoesharde" because its interior
    point happens to lie there."""
    if areas is None or obj.get("admin_level", MUNICIPALITY_LEVEL) < MUNICIPALITY_LEVEL:
        return None
    points = [(obj["lon"], obj["lat"])]
    if "outline" in obj:
        points.append((obj["outline"][0], obj["outline"][1]))
    for lon, lat in points:
        tag = areas.lookup(lon, lat)
        if tag:
            return tag
    return None
