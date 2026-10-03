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

The command that prints and exports the registry is frasch.export_dialects.
"""

from __future__ import annotations

import csv
import json
from typing import TypedDict

from shapely.geometry.base import BaseGeometry

from frasch import files, paths, placelist
from frasch.errors import Invalid, ValidationError
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


def area_rows(path: str, reg: Registry) -> tuple[list[AreaRow], list[tuple[int, str]]]:
    """-> (rows, problems) of the dialect area list (names/dialect_areas.csv):
    one dict per row that follows its rules -- `line`, `dialect`, `name`,
    `note`, `osm` (normalised) and `refs` (parsed) -- and `(line, reason)` for
    every one that does not.  The one reading of the file's rules, shared by
    frasch.build_dialect_areas (which stops at the first problem) and
    frasch.check (which lists them).

    An OSM reference belongs to one row only: the review overlay's
    `?areas&area=` links name a row by it."""
    known = set(reg.tags)
    rows: list[AreaRow] = []
    problems: list[tuple[int, str]] = []
    first_line: dict[OsmRef, int] = {}
    with files.open_csv(path) as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in ("dialect", "osm") if c not in (reader.fieldnames or [])]
        if missing:
            return [], [(1, f"missing column(s) {', '.join(missing)}")]
        for n, row in enumerate(reader, start=2):
            tag = (row.get("dialect") or "").strip()
            if not tag and not (row.get("osm") or "").strip():
                continue  # blank spacer line
            if tag not in known:
                problems.append((n, f"unknown dialect {tag!r} (not in names/dialects.csv)"))
                continue
            try:
                refs = placelist.parse_osm(row.get("osm"))
            except Invalid as exc:
                problems.append((n, exc.reason))
                continue
            if not refs:
                problems.append((n, "no OSM reference"))
                continue
            area_refs = [
                osm for ref in refs if (osm := placelist.as_osm_ref(ref)) and osm[0] in ("w", "r")
            ]
            if len(area_refs) < len(refs):
                # a node can never be a polygon, and `local/` names an object
                # of our own invention (curation.csv), not an OSM boundary
                bad = [r for r in refs if r not in area_refs]
                problems.append(
                    (
                        n,
                        f"{placelist.format_osm(bad)}: only way/ "
                        f"or relation/ references are allowed here",
                    )
                )
                continue
            taken = [r for r in area_refs if r in first_line]
            if taken:
                problems.append(
                    (
                        n,
                        f"{placelist.format_osm(taken[:1])} is already "
                        f"on line {first_line[taken[0]]}",
                    )
                )
                continue
            first_line.update((r, n) for r in area_refs)
            rows.append(
                {
                    "line": n,
                    "dialect": tag,
                    "name": (row.get("name") or "").strip(),
                    "note": (row.get("note") or "").strip(),
                    "osm": placelist.format_osm(area_refs),
                    "refs": area_refs,
                }
            )
    return rows, problems


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
    names/dialect_areas.geojson (built by names/build_dialect_areas.py).

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
    def from_geojson(cls, path: str = paths.DIALECT_AREAS) -> AreaIndex:
        from shapely.geometry import shape

        with open(path, encoding="utf-8") as fh:
            fc = json.load(fh)
        polygons: list[tuple[str, BaseGeometry]] = []
        for feat in fc.get("features", []):
            tag = (feat.get("properties") or {}).get("dialect")
            if not tag:
                raise ValidationError(f"{path}: a feature has no `dialect` property")
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
