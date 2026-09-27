#!/usr/bin/env python3
"""The dialect registry (names/dialects.csv) and the name logic built on it.

North Frisian is not one language variety but a dozen, and the map shows more
than one of them.  `names/dialects.csv` is the single list of the dialects the
project knows; everything else derives from it: the name columns of
names/places.csv (placelist.py), the `name:<tag>` tags the injector writes,
Planetiler's `--languages` list (`dialects.py --tags` in tiles/build.sh), the
search index and the frontend's selector (web/src/generated/dialects.json).
Adding a dialect is therefore one line in the registry plus a column in
places.csv -- no code change.

| column | meaning |
|---|---|
| `tag`    | BCP 47 language tag, always `frr-x-<subtag>`; no registered subtags for North Frisian dialects exist, so private use it is |
| `column` | the column of names/places.csv that holds this dialect's names |
| `label`  | how the dialect is written in the UI (its German/endonym name) |
| `status` | `living` or `extinct` (extinct dialects still label the map in the local view -- Südergoesharde) |
| `view`   | `yes` = selectable as a map language in the frontend |
| `note`   | free text: which area speaks it |

One name belongs to a place beyond its dialect columns:

* `local` -- the form the people of the place itself use where it differs from
  the dialect of the surrounding area (sub-dialects such as Fahretoft's
  Foortuftinge).  Empty means "same as the area's dialect".  `dialect_name`
  and `local_name` below implement those two fallbacks; the area a place lies
  in comes from `AreaIndex` (names/dialect_areas.geojson).

CLI:  `names/dialects.py`          prints the registry
      `names/dialects.py --tags`   prints `frr-x-mooring,frr-x-wieding,...`
                                   (tiles/build.sh feeds it to Planetiler)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import placelist  # noqa: E402

DEFAULT_PATH = placelist.DIALECTS_PATH
DEFAULT_AREAS = os.path.join(HERE, "dialect_areas.geojson")

FIELDS = ["tag", "column", "label", "status", "view", "note"]
STATUSES = {"living", "extinct"}
VIEWS = {"yes", "no"}

LOCAL_COLUMN = "local"

_TAG = re.compile(r"frr-x-[a-z0-9]{1,8}(-[a-z0-9]{1,8})*$")


def row_problem(row: dict, seen_tags=(), seen_cols=()) -> str | None:
    """What is wrong with one registry row (`seen_*`: the tags and columns of
    the rows above it), or None.  Shared with names/check.py."""
    if not _TAG.fullmatch(row["tag"]):
        # BCP 47 allows at most 8 characters per private-use subtag
        return (f"bad tag {row['tag']!r} -- expected frr-x-<subtag>, subtags "
                f"[a-z0-9] and at most 8 characters each")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", row["column"]):
        return f"bad column name {row['column']!r}"
    if row["column"] == LOCAL_COLUMN:
        return f"{row['column']!r} is a reserved column of places.csv, not a dialect"
    if row["tag"] in seen_tags or row["column"] in seen_cols:
        return f"duplicate tag/column {row['tag']}/{row['column']}"
    if row["status"] not in STATUSES:
        return f"status {row['status']!r} (living / extinct)"
    if row["view"] not in VIEWS:
        return f"view {row['view']!r} (yes / no)"
    if not row["label"]:
        return "no label"
    return None


def read(path: str = DEFAULT_PATH) -> list[dict]:
    """-> the registry rows in file order, validated."""
    if not os.path.exists(path):
        raise SystemExit(f"dialect registry not found: {path}")
    reg, seen_tags, seen_cols = [], set(), set()
    with placelist.open_csv(path) as fh:
        reader = csv.DictReader(fh)
        what = placelist.csv_header_problem(reader.fieldnames or [], FIELDS)
        if what:
            raise SystemExit(f"{path}: {what}")
        for row in reader:
            n = reader.line_num
            row = {k: (v or "").strip() for k, v in row.items() if k}
            if not row["tag"]:
                continue                       # blank spacer line
            what = row_problem(row, seen_tags, seen_cols)
            if what:
                raise SystemExit(f"{path}:{n}: {what}")
            seen_tags.add(row["tag"])
            seen_cols.add(row["column"])
            reg.append(row)
    if not reg:
        raise SystemExit(f"{path}: no dialects")
    return reg


def tags(reg) -> list[str]:
    return [d["tag"] for d in reg]


def columns(reg) -> list[str]:
    return [d["column"] for d in reg]


def column_of(reg, tag: str) -> str:
    for d in reg:
        if d["tag"] == tag:
            return d["column"]
    raise SystemExit(f"unknown dialect tag {tag!r}")


def tag_of_column(reg, column: str) -> str:
    for d in reg:
        if d["column"] == column:
            return d["tag"]
    raise SystemExit(f"unknown dialect column {column!r}")


def label_of(reg, tag: str) -> str:
    for d in reg:
        if d["tag"] == tag:
            return d["label"]
    return tag


# --------------------------------------------------------------- names ----
def dialect_name(row: dict, tag: str, area_tag: str | None, reg) -> str:
    """The name of a place in one dialect, with one fallback: the dialect of
    the place's own area falls back to the `local` column -- a sub-dialect
    form such as Fahretoft's `Brouersweerw` IS the name in the area's
    dialect, it is just not the form the rest of the area uses."""
    name = placelist.primary(row.get(column_of(reg, tag)))
    if not name and area_tag == tag:
        name = placelist.primary(row.get(LOCAL_COLUMN))
    return name


def local_name(row: dict, area_tag: str | None, reg) -> str:
    """What the people of the place themselves call it: the `local` column,
    or -- when it is empty -- the name in the dialect of the area the place
    lies in.  This is what the "local dialect" map view labels with."""
    name = placelist.primary(row.get(LOCAL_COLUMN))
    if not name and area_tag:
        name = dialect_name(row, area_tag, area_tag, reg)
    return name


def variety(row: dict) -> str:
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

    def __init__(self, polygons):
        # polygons: [(tag, shapely polygon)] -- already exploded into single
        # polygons, so "smallest wins" compares the actual island, not the
        # union of every Hallig
        from shapely import STRtree
        self.polygons = polygons
        self.geoms = [g for _, g in polygons]
        self.tree = STRtree(self.geoms) if self.geoms else None

    @classmethod
    def from_geojson(cls, path: str = DEFAULT_AREAS):
        try:
            from shapely.geometry import shape
        except ImportError:                      # pragma: no cover
            raise SystemExit("shapely is needed for the dialect areas "
                             "(run `uv sync` in the repo root)") from None
        with open(path, encoding="utf-8") as fh:
            fc = json.load(fh)
        polygons = []
        for feat in fc.get("features", []):
            tag = (feat.get("properties") or {}).get("dialect")
            if not tag:
                raise SystemExit(f"{path}: a feature has no `dialect` property")
            geom = shape(feat["geometry"])
            polygons.append((tag, geom))
        # explode MultiPolygons: one entry per island / municipality blob
        flat = []
        for tag, geom in polygons:
            for g in getattr(geom, "geoms", [geom]):
                flat.append((tag, g))
        flat.sort(key=lambda tg: tg[1].area)     # smallest first -> first hit wins
        return cls(flat)

    def lookup(self, lon, lat) -> str | None:
        if self.tree is None:
            return None
        from shapely.geometry import Point
        pt = Point(float(lon), float(lat))
        best = None
        for i in self.tree.query(pt):
            tag, geom = self.polygons[i]
            if geom.covers(pt):
                if best is None or geom.area < best[1]:
                    best = (tag, geom.area)
        return best[0] if best else None

    def __len__(self):
        return len(self.polygons)

    def summary(self) -> str:
        n = {}
        for tag, _ in self.polygons:
            n[tag] = n.get(tag, 0) + 1
        return ", ".join(f"{t} ({c})" for t, c in sorted(n.items()))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=DEFAULT_PATH)
    ap.add_argument("--tags", action="store_true",
                    help="print the language tags as a comma-separated list "
                         "(tiles/build.sh feeds them to Planetiler)")
    ap.add_argument("--columns", action="store_true",
                    help="print the places.csv columns instead")
    a = ap.parse_args(argv)
    reg = read(a.registry)
    if a.tags:
        print(",".join(tags(reg)))
    elif a.columns:
        print(",".join(columns(reg)))
    else:
        for d in reg:
            print(f"{d['tag']:<16} {d['column']:<10} {d['label']:<18} "
                  f"{d['status']:<7} view={d['view']:<4} {d['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
