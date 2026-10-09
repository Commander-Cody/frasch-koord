"""Read / append names/curation.csv -- the per-object map tuning.

One row per OSM object (or `local/<slug>` reference) the map treats
differently from what OpenMapTiles would make of it (names/README.md, "Map
curation"):

* `set_tags` -- `k=v` pairs separated by `;`, applied verbatim by the injector
* `minzoom` / `maxzoom` -- become the tile attributes `frasch:minzoom` /
  `frasch:maxzoom`
* `polygon_km2` -- a synthetic square of that area around one node (or local
  reference) that carries the label instead
* `lat` / `lon` -- the position of a place OSM does not have; required on a
  local reference, forbidden on any other

This module is the one reading of the file's rules: the injector, the search
export (for the positions), frasch.check_inputs and frasch.curate's `apply` (which
appends rows) all go through it.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping, Sequence
from typing import NamedTuple, TypedDict

from frasch import refs, tables
from frasch.errors import Invalid, Problem, ValidationError
from frasch.geo import LonLat
from frasch.placenames import MAXZOOM_KEY, MINZOOM_KEY
from frasch.refs import LOCAL_TYPE, Ref
from frasch.tables import Table

COLUMNS = ["osm", "name", "lat", "lon", "set_tags", "minzoom", "maxzoom", "polygon_km2", "note"]
MAX_ZOOM = 24  # the deepest zoom a map style knows

# The default `place=` of the node the injector adds for a local reference, by
# the row's kind.  Only kinds whose OSM equivalent is unambiguous are listed;
# any other kind needs `place=...` in the curation row's `set_tags` (and a look
# at whether OpenMapTiles keeps that tag: it has no `place=locality` at all,
# and `isolated_dwelling` nodes only from z14 while `hamlet` nodes come at z11
# -- which is why a Warft is a hamlet here, as OSM's own Hallig Warften are).
POINT_TAGS = {
    "settlement": {"place": "hamlet"},
    "warft": {"place": "hamlet"},
    "island": {"place": "island"},
    "hallig": {"place": "island"},
}


# ------------------------------------------------------------------ cells ---
def parse_point(lat: str | None, lon: str | None, where: str = "") -> LonLat | None:
    """`("54.65097", "8.34019")` -> `(8.34019, 54.65097)` as (lon, lat) floats,
    None when both cells are empty.  One without the other is an error."""
    lat = (lat or "").strip()
    lon = (lon or "").strip()
    if not lat and not lon:
        return None
    if not (lat and lon):
        raise Invalid(
            where, f"`lat` and `lon` go together (got lat={lat or '-'}, lon={lon or '-'})"
        )
    try:
        flat, flon = float(lat), float(lon)
    except ValueError:
        raise Invalid(
            where,
            f"lat/lon {lat!r}/{lon!r} are not numbers (decimal degrees, e.g. 54.65097 / 8.34019)",
        ) from None
    if not (-90 <= flat <= 90 and -180 <= flon <= 180):
        raise Invalid(where, f"lat/lon {flat}/{flon} out of range")
    return flon, flat


def parse_set_tags(spec: str | None, where: str = "") -> dict[str, str]:
    """`set_tags`: `place=island;frasch:kind=island` ->
    `{"place": "island", "frasch:kind": "island"}`."""
    tags: dict[str, str] = {}
    for pair in (spec or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise Invalid(where, f"set_tags entry {pair!r} is not key=value")
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            raise Invalid(where, f"set_tags entry {pair!r} has an empty key")
        tags[k] = v
    return tags


def _zoom(row: Mapping[str, str], column: str, found: list[str]) -> int | None:
    cell = row[column]
    if not cell:
        return None
    try:
        zoom = int(cell)
    except ValueError:
        found.append(f"{column} {cell!r} is not an integer")
        return None
    if not 0 <= zoom <= MAX_ZOOM:
        found.append(f"{column} {cell!r} is not a zoom (0-{MAX_ZOOM})")
    return zoom


def _zooms(row: Mapping[str, str], found: list[str]) -> tuple[int | None, int | None]:
    minzoom, maxzoom = _zoom(row, "minzoom", found), _zoom(row, "maxzoom", found)
    if minzoom is not None and maxzoom is not None and maxzoom < minzoom:
        found.append(f"maxzoom {maxzoom} is below minzoom {minzoom}")
    return minzoom, maxzoom


def _km2(row: Mapping[str, str], found: list[str]) -> float | None:
    cell = row["polygon_km2"]
    if not cell:
        return None
    try:
        km2 = float(cell)
    except ValueError:
        km2 = 0.0
    if not 0 < km2 < math.inf:
        found.append(f"polygon_km2 {cell!r} is not a positive number")
    return km2


# ------------------------------------------------------------------- rows ---
class _Seen:
    """What the rows above have claimed: one row per local reference, one
    square per node, one tuning row (neither of those) per OSM object."""

    def __init__(self) -> None:
        self.positioned: set[str] = set()
        self.squares: set[Ref] = set()
        self.tuned: dict[Ref, int] = {}  # -> the line of its row

    def tune(self, n: int, objects: Sequence[Ref]) -> list[str]:
        """Claim `objects` for the tuning row on line `n`; -> the objects an
        earlier tuning row claimed already."""
        found = [
            f"second row for {refs.format([ref])} (line {self.tuned[ref]})"
            for ref in objects
            if ref in self.tuned
        ]
        for ref in objects:
            self.tuned.setdefault(ref, n)
        return found


class Entry(TypedDict):
    """One row of the file that follows its rules, see `rows`."""

    line: int
    refs: list[Ref]
    local: str | None
    pos: LonLat | None
    tags: dict[str, str]
    minzoom: int | None
    maxzoom: int | None
    km2: float | None
    label: str


def _entry(n: int, row: Mapping[str, str], seen: _Seen) -> tuple[Entry | None, list[str]]:
    """-> (the entry of one row, what is wrong with it); no entry for a row
    without a reference (a spacer) or with a problem."""
    try:
        objects = refs.parse(row["osm"])
        pos = parse_point(row["lat"], row["lon"])
    except Invalid as exc:
        return None, [exc.reason]
    if not objects:
        return None, []
    found: list[str] = []
    local = refs.local_of(objects)
    if pos and not local:
        found.append(
            f"lat/lon only go with a local reference (local/<slug>), not with {row['osm']!r}"
        )
    if local and not pos:
        found.append(f"local/{local} needs `lat` and `lon`")
    if local and local in seen.positioned:
        found.append(f"second row for local/{local}")
    try:
        tags = parse_set_tags(row["set_tags"])
    except Invalid as exc:
        found.append(exc.reason)
    minzoom, maxzoom = _zooms(row, found)
    km2 = _km2(row, found)
    if km2 is not None:
        if len(objects) != 1 or objects[0][0] not in ("n", LOCAL_TYPE):
            found.append("polygon_km2 needs exactly one node (or local reference) in `osm`")
        elif not local and objects[0] in seen.squares:
            found.append(f"second polygon_km2 row for {refs.format(objects)}")
        seen.squares.add(objects[0])
    elif not local:
        found += seen.tune(n, objects)
    if local:
        seen.positioned.add(local)
    if found:
        return None, found
    return {
        "line": n,
        "refs": objects,
        "local": local,
        "pos": pos,
        "tags": tags,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "km2": km2,
        "label": row["name"],
    }, []


def _table(path: str) -> Table:
    """The file as it is on disk -- the one place that opens it, and that
    says which columns it must have."""
    return tables.read_table(path, COLUMNS)


def rows(path: str) -> tuple[list[Entry], list[Problem]]:
    """-> (entries, problems): the rows that follow the file's rules, and
    what is wrong with the others.

    An entry: `line`, `refs` (parsed `osm`), `local` (the slug of a local
    reference, else None), `pos` ((lon, lat) or None), `tags` (`set_tags`),
    `minzoom` / `maxzoom` (int or None), `km2` (float or None) and `label`
    (the `name` cell).  Rows without a reference are spacer lines and left
    out."""
    table = _table(path)
    entries: list[Entry] = []
    problems = list(table.problems)
    seen = _Seen()
    for n, row in table.records():
        entry, found = _entry(n, row, seen)
        problems += [Problem(path, n, what) for what in found]
        if entry:
            entries.append(entry)
    return entries, tables.by_line(problems)


def _valid_entries(path: str) -> list[Entry]:
    entries, problems = rows(path)
    if problems:
        raise ValidationError(problems)
    return entries


class Tuning(TypedDict):
    """The tags to set on an OSM object, and the curation row's `name`."""

    tags: dict[str, str]
    label: str


class Square(Tuning):
    km2: float


class LocalPoint(Tuning):
    lon: float
    lat: float
    km2: float | None
    where: str


class Curation(NamedTuple):
    """The curation as the injector applies it (see frasch.inject_names):

    objects  {('r', 1420555): {'tags': {...}, 'label': 'Nordstrand'}} -- the
             tags to set on an OSM object, the zooms among them
    squares  {('n', 85929111): {'km2': 50.0, 'tags': {...}, 'label': ...}} --
             a synthetic square to add around that node; the node itself is
             left alone
    points   {('l', 'westerheide-amrum'): {'lon', 'lat', 'km2', 'tags',
             'label', 'where'}} -- a place OSM does not have: the node (or,
             with `km2`, the square) to add for it"""

    objects: dict[Ref, Tuning]
    squares: dict[Ref, Square]
    points: dict[Ref, LocalPoint]


def read(path: str) -> Curation:
    """The curation; a ValidationError lists every row that breaks the
    rules."""
    curation = Curation({}, {}, {})
    for e in _valid_entries(path):
        tags = dict(e["tags"])
        for key, zoom in ((MINZOOM_KEY, e["minzoom"]), (MAXZOOM_KEY, e["maxzoom"])):
            if zoom is not None:
                tags[key] = str(zoom)  # tag values must be strings
        ref, label, km2 = e["refs"][0], e["label"], e["km2"]
        if (pos := e["pos"]) is not None:  # only a local reference has one
            curation.points[ref] = {
                "lon": pos[0],
                "lat": pos[1],
                "km2": km2,
                "tags": tags,
                "label": label,
                "where": f"{path}:{e['line']}",
            }
        elif km2 is not None:
            curation.squares[ref] = {"km2": km2, "tags": tags, "label": label}
        elif tags:  # else nothing to apply yet
            for ref in e["refs"]:  # one row per object (`rows`)
                curation.objects[ref] = {"tags": dict(tags), "label": label}
    return curation


def local_points(path: str) -> dict[str, LonLat]:
    """`{slug: (lon, lat)}` for every local reference -- the positions of the
    places OSM does not have; `{}` without the file."""
    if not os.path.exists(path):
        return {}
    return {local: pos for e in _valid_entries(path) if (local := e["local"]) and (pos := e["pos"])}


# -------------------------------------------------------------- appending ---
def read_bytes(path: str) -> tuple[bytes | None, list[str]]:
    """-> (the file's bytes, None when it does not exist; its columns).  The
    columns are the file's own (it is hand-edited, so it may have gained
    one); COLUMNS are among them."""
    if not os.path.exists(path):
        return None, COLUMNS
    table = _table(path)
    if table.problems:
        raise ValidationError(table.problems)
    return table.data, table.header


def appended(data: bytes | None, fields: list[str], new_rows: Iterable[Mapping[str, str]]) -> bytes:
    """The whole file with `new_rows` appended: the old bytes (`read_bytes`)
    untouched, the new rows in the file's column order; with a header when
    there was no file."""
    if data is None:
        return tables.write_rows(fields, new_rows)
    if data and not data.endswith(b"\n"):
        data += b"\n"
    return data + tables.write_rows(fields, new_rows, header=False)
