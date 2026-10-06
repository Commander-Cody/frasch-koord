"""The name logic built on the dialect registry (frasch.registry), and
the dialect areas.

One name belongs to a place beyond its dialect columns:

* `local` -- the form the people of the place itself use where it differs from
  the dialect of the surrounding area (sub-dialects such as Fahretoft's
  Foortuftinge).  Empty means "same as the area's dialect".  `dialect_name`
  and `local_name` below implement those two fallbacks; the area a place lies
  in comes from `AreaIndex` (names/dialect_areas.geojson).  Where the list
  gives no local name at all, OSM's own Frisian name is it inside a dialect
  area (`osm_local_name`).

The command that prints and exports the registry is `frasch dialects` (frasch.registry).
"""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping
from typing import TypedDict

from shapely.geometry.base import BaseGeometry

from frasch import placelist, tables
from frasch.errors import Invalid, PipelineError, Problem
from frasch.placelist import OsmRef, Row
from frasch.registry import LOCAL_COLUMN, Registry


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
            refs = _area_refs(row, known, first_line)
        except Invalid as exc:
            problems.append(Problem(path, n, exc.reason))
            continue
        first_line.update((r, n) for r in refs)
        rows.append(
            {
                "line": n,
                "dialect": row["dialect"],
                "name": row["name"],
                "note": row["note"],
                "osm": placelist.format_osm(refs),
                "refs": refs,
            }
        )
    return rows, tables.by_line(problems)


def _area_refs(row: Row, known: Collection[str], first_line: Mapping[OsmRef, int]) -> list[OsmRef]:
    """The areas a row of the list names (`first_line`: those of the rows
    above it, with their line); `Invalid` when the row breaks a rule."""
    if row["dialect"] not in known:
        raise Invalid("", f"unknown dialect {row['dialect']!r} (not in names/dialects.csv)")
    refs = placelist.parse_osm(row["osm"])
    if not refs:
        raise Invalid("", "no OSM reference")
    area_refs = [osm for ref in refs if (osm := placelist.as_osm_ref(ref)) and osm[0] in ("w", "r")]
    if len(area_refs) < len(refs):
        # a node can never be a polygon, and `local/` names an object of our
        # own invention (curation.csv), not an OSM boundary
        bad = [r for r in refs if r not in area_refs]
        raise Invalid(
            "", f"{placelist.format_osm(bad)}: only way/ or relation/ references are allowed here"
        )
    taken = [r for r in area_refs if r in first_line]
    if taken:
        raise Invalid(
            "", f"{placelist.format_osm(taken[:1])} is already on line {first_line[taken[0]]}"
        )
    return area_refs


# --------------------------------------------------------------- names ----
def dialect_name(row: Row, tag: str, area_tag: str | None, reg: Registry) -> str:
    """The name of a place in one dialect, with one fallback: the dialect of
    the place's own area falls back to the `local` column -- a sub-dialect
    form such as Fahretoft's `Brouersweerw` IS the name in the area's
    dialect, it is just not the form the rest of the area uses."""
    name = placelist.primary(row.get(reg.column_of(tag)))
    if not name and area_tag == tag:
        name = placelist.primary(row.get(LOCAL_COLUMN))
    return name


def local_name(row: Row, area_tag: str | None, reg: Registry) -> str:
    """What the people of the place themselves call it: the `local` column,
    or -- when it is empty -- the name in the dialect of the area the place
    lies in.  This is what the "local dialect" map view labels with."""
    name = placelist.primary(row.get(LOCAL_COLUMN))
    if not name and area_tag:
        name = dialect_name(row, area_tag, area_tag, reg)
    return name


def osm_local_name(name_frr: str | None, area_tag: str | None) -> str:
    """OSM's own Frisian name (`name:frr`) as the local name of an object
    the name list gives none -- inside a dialect area only.  There it is
    almost always the form the place itself uses; outside it is a Frisian
    exonym (Pinneberg -> Pinebärj), which the local view must not show (#81)."""
    return (name_frr or "") if area_tag else ""


def variety(row: Row) -> str:
    """The remark on the primary `local` variant -- the name of the local
    variety (`Brouersweerw (Foortuftinge)` -> `Foortuftinge`), which the UI
    can show next to the name.  `""` when there is none."""
    return placelist.remark(row.get(LOCAL_COLUMN))


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
