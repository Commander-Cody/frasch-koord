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
      `names/dialects.py --export web/src/generated/dialects.json`
                                   writes the registry the frontend compiles
                                   in (every column but `note`)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

from frasch import paths, placelist

DEFAULT_PATH = placelist.DIALECTS_PATH
DEFAULT_AREAS = paths.DIALECT_AREAS
# what DEFAULT_AREAS is built from (names/build_dialect_areas.py)
AREA_LIST_PATH = paths.DIALECT_AREA_LIST

FIELDS = ["tag", "column", "label", "status", "view", "note"]
EXPORT_FIELDS = FIELDS[:-1]            # what the frontend gets: all but `note`
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


def area_rows(path: str, reg) -> tuple[list[dict], list[tuple[int, str]]]:
    """-> (rows, problems) of the dialect area list (names/dialect_areas.csv):
    one dict per row that follows its rules -- `line`, `dialect`, `name`,
    `note`, `osm` (normalised) and `refs` (parsed) -- and `(line, reason)` for
    every one that does not.  The one reading of the file's rules, shared by
    names/build_dialect_areas.py (which stops at the first problem) and
    names/check.py (which lists them).

    An OSM reference belongs to one row only: the review overlay's
    `?areas&area=` links name a row by it."""
    known = set(tags(reg))
    rows, problems, first_line = [], [], {}
    with placelist.open_csv(path) as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in ("dialect", "osm") if c not in (reader.fieldnames or [])]
        if missing:
            return [], [(1, f"missing column(s) {', '.join(missing)}")]
        for n, row in enumerate(reader, start=2):
            tag = (row.get("dialect") or "").strip()
            if not tag and not (row.get("osm") or "").strip():
                continue                                  # blank spacer line
            if tag not in known:
                problems.append((n, f"unknown dialect {tag!r} (not in names/dialects.csv)"))
                continue
            try:
                refs = placelist.parse_osm(row.get("osm"))
            except placelist.Invalid as exc:
                problems.append((n, exc.reason))
                continue
            if not refs:
                problems.append((n, "no OSM reference"))
                continue
            bad = [r for r in refs if r[0] not in ("w", "r")]
            if bad:
                # a node can never be a polygon, and `local/` names an object
                # of our own invention (curation.csv), not an OSM boundary
                problems.append((n, f"{placelist.format_osm(bad)}: only way/ "
                                    f"or relation/ references are allowed here"))
                continue
            taken = [r for r in refs if r in first_line]
            if taken:
                problems.append((n, f"{placelist.format_osm(taken[:1])} is already "
                                    f"on line {first_line[taken[0]]}"))
                continue
            first_line.update((r, n) for r in refs)
            rows.append({"line": n, "dialect": tag,
                         "name": (row.get("name") or "").strip(),
                         "note": (row.get("note") or "").strip(),
                         "osm": placelist.format_osm(refs), "refs": refs})
    return rows, problems


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
    ap.add_argument("--export", metavar="PATH",
                    help="write the registry as JSON for the frontend "
                         "(web/src/generated/dialects.json)")
    a = ap.parse_args(argv)
    reg = read(a.registry)
    if a.export:
        os.makedirs(os.path.dirname(os.path.abspath(a.export)), exist_ok=True)
        placelist.atomic_write(a.export, json.dumps(
            [{k: d[k] for k in EXPORT_FIELDS} for d in reg],
            ensure_ascii=False, separators=(",", ":")) + "\n")
    elif a.tags:
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
