"""Read / append names/curation.csv -- the per-object map tuning.

One row per OSM object (or `local/<slug>` reference) the map treats
differently from what OpenMapTiles would make of it (names/README.md, "Map
curation"):

* `set_tags` -- `k=v` pairs separated by `;`, applied verbatim by the injector
* `minzoom` / `maxzoom` -- become the tile attributes `frasch:minzoom` /
  `frasch:maxzoom`
* `polygon_km2` -- a synthetic square of that area for one object (or local
  reference) that carries its label instead
* `lat` / `lon` -- the position of a place OSM does not have, required on a
  local reference; and the centre of a way's or relation's square, required
  with its `polygon_km2` -- that is where the place lies.  A node's square
  is centred on the node; no other row has them

This module is the one reading of the file's rules: the injector, the search
export (for the positions), frasch.check_inputs and frasch.curate's `apply` (which
appends rows) all go through it.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple, TypedDict

from frasch import files, refs, tables
from frasch.errors import Invalid, Problem, ValidationError
from frasch.geo import LonLat
from frasch.placenames import MAXZOOM_KEY, MINZOOM_KEY
from frasch.refs import OsmRef, Ref
from frasch.tables import Table

COLUMNS = ["osm", "name", "lat", "lon", "set_tags", "minzoom", "maxzoom", "polygon_km2", "note"]
MAX_ZOOM = 24  # the deepest zoom a map style knows


# ------------------------------------------------------------------ cells ---
def parse_point(lat: str | None, lon: str | None) -> LonLat | None:
    """`("54.65097", "8.34019")` -> `(8.34019, 54.65097)` as (lon, lat) floats,
    None when both cells are empty.  One without the other is an error."""
    lat = (lat or "").strip()
    lon = (lon or "").strip()
    if not lat and not lon:
        return None
    if not (lat and lon):
        raise Invalid(f"`lat` and `lon` go together (got lat={lat or '-'}, lon={lon or '-'})")
    try:
        flat, flon = float(lat), float(lon)
    except ValueError:
        raise Invalid(
            f"lat/lon {lat!r}/{lon!r} are not numbers (decimal degrees, e.g. 54.65097 / 8.34019)",
        ) from None
    if not (-90 <= flat <= 90 and -180 <= flon <= 180):
        raise Invalid(f"lat/lon {flat}/{flon} out of range")
    return flon, flat


def parse_set_tags(spec: str | None) -> dict[str, str]:
    """`set_tags`: `place=island;frasch:kind=island` ->
    `{"place": "island", "frasch:kind": "island"}`."""
    tags: dict[str, str] = {}
    for pair in (spec or "").split(";"):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise Invalid(f"set_tags entry {pair!r} is not key=value")
        k, v = pair.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            raise Invalid(f"set_tags entry {pair!r} has an empty key")
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
    row per OSM object."""

    def __init__(self) -> None:
        self.positioned: set[str] = set()
        self.tuned: dict[Ref, int] = {}  # -> the line of its row

    def tune(self, n: int, objects: Sequence[Ref]) -> list[str]:
        """Claim `objects` for the row on line `n`; -> the objects an earlier
        row claimed already."""
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


def _position_problems(
    objects: Sequence[Ref], local: str | None, pos: LonLat | None, km2: float | None
) -> list[str]:
    """What is wrong with a row's `lat`/`lon`: a local reference needs them
    (its position), a square on a way or relation needs them (its centre),
    and no other row may have them -- a node's square is centred on the
    node."""
    if local:
        return [] if pos else [f"local/{local} needs `lat` and `lon`"]
    where = refs.format(objects)
    on_a_node = objects[0][0] == "n"
    if pos is None:
        if km2 is not None and len(objects) == 1 and not on_a_node:
            return [
                f"polygon_km2 on {where} needs `lat` and `lon`, the centre of its square "
                f"(a way or relation has no point of its own to centre it on)"
            ]
        return []
    if on_a_node:
        if km2 is not None:
            return [f"lat/lon on {where}: a node's square is centred on the node -- empty them"]
        return [f"lat/lon on {where}: a node has a position of its own -- empty them"]
    if km2 is None:
        return [
            f"lat/lon on {where} only centre the square of a way or relation: give the "
            f"row `polygon_km2`, or empty them (a position of its own is only a local "
            f"reference's, local/<slug>)"
        ]
    return []


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
    km2 = _km2(row, found)
    found += _position_problems(objects, local, pos, km2)
    if local and local in seen.positioned:
        found.append(f"second row for local/{local}")
    try:
        tags = parse_set_tags(row["set_tags"])
    except Invalid as exc:
        found.append(exc.reason)
    minzoom, maxzoom = _zooms(row, found)
    if km2 is not None and len(objects) != 1:
        found.append("polygon_km2 needs exactly one object (or local reference) in `osm`")
    if local:
        seen.positioned.add(local)
    else:
        found += seen.tune(n, objects)
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
    return _rows(_table(path))


def _rows(table: Table) -> tuple[list[Entry], list[Problem]]:
    """`rows` of the file as it was read."""
    entries: list[Entry] = []
    problems = list(table.problems)
    seen = _Seen()
    for n, row in table.records():
        entry, found = _entry(n, row, seen)
        problems += [Problem(table.path, n, what) for what in found]
        if entry:
            entries.append(entry)
    return entries, tables.by_line(problems)


def _valid_entries(table: Table) -> list[Entry]:
    entries, problems = _rows(table)
    if problems:
        raise ValidationError(problems)
    return entries


class Tuning(TypedDict):
    """The tags to set on an OSM object, and the curation row's `name`."""

    tags: dict[str, str]
    label: str


class Square(Tuning):
    km2: float
    centre: LonLat | None


class LocalPoint(Tuning):
    lon: float
    lat: float
    km2: float | None
    where: str


class Curation(NamedTuple):
    """The curation as the injector applies it (see frasch.inject_names):

    objects  {('r', 1420555): {'tags': {...}, 'label': 'Nordstrand'}} -- the
             tags to set on an OSM object, the zooms among them
    squares  {('w', 1163568825): {'km2': 2.1, 'centre': (8.6981, 54.676),
             'tags': {...}, 'label': ...}} -- a synthetic square to add for
             that object, centred on `centre` (None for a node: on the
             node); it replaces the object's own place label
    points   {('l', 'westerheide-amrum'): {'lon', 'lat', 'km2', 'tags',
             'label', 'where'}} -- a place OSM does not have: the node (or,
             with `km2`, the square) to add for it"""

    objects: dict[Ref, Tuning]
    squares: dict[Ref, Square]
    points: dict[Ref, LocalPoint]

    @property
    def centres(self) -> dict[OsmRef, LonLat]:
        """The centre of each square on a way or relation: where that place
        lies."""
        return {
            osm: centre
            for ref, square in self.squares.items()
            if (osm := refs.as_osm_ref(ref)) and (centre := square["centre"])
        }


def read(path: str) -> Curation:
    """The curation; a ValidationError lists every row that breaks the
    rules."""
    curation = Curation({}, {}, {})
    for e in _valid_entries(_table(path)):
        tags = dict(e["tags"])
        for key, zoom in ((MINZOOM_KEY, e["minzoom"]), (MAXZOOM_KEY, e["maxzoom"])):
            if zoom is not None:
                tags[key] = str(zoom)  # tag values must be strings
        ref, label, km2, pos = e["refs"][0], e["label"], e["km2"], e["pos"]
        if pos is not None and e["local"]:
            curation.points[ref] = {
                "lon": pos[0],
                "lat": pos[1],
                "km2": km2,
                "tags": tags,
                "label": label,
                "where": f"{path}:{e['line']}",
            }
        elif km2 is not None:
            curation.squares[ref] = {"km2": km2, "centre": pos, "tags": tags, "label": label}
        elif tags:  # else nothing to apply yet
            for ref in e["refs"]:  # one row per object (`rows`)
                curation.objects[ref] = {"tags": dict(tags), "label": label}
    return curation


def positions(path: str) -> dict[Ref, LonLat]:
    """`{reference: (lon, lat)}` for every row with a position: where a
    place OSM does not have lies (a local reference), and the centre of the
    square on a way or relation, which is where that place lies; `{}`
    without the file."""
    if not os.path.exists(path):
        return {}
    curation = read(path)
    local: dict[Ref, LonLat] = {ref: (p["lon"], p["lat"]) for ref, p in curation.points.items()}
    return local | dict(curation.centres)


# -------------------------------------------------------------- appending ---
@dataclass(frozen=True)
class Appendable:
    """The file as `frasch curate apply` appends to it (`read_for_appending`):
    read once, so that its new rows land after exactly the bytes whose rows
    were checked."""

    path: str
    data: bytes | None  # None: there is no file
    # its columns: the file's own (it is hand-edited, so it may have gained
    # one), COLUMNS among them
    fields: list[str]
    slugs: frozenset[str]  # the local references it positions

    @property
    def digest(self) -> str:
        """What `files.atomic_write` compares against to notice that someone
        else wrote the file in the meantime."""
        return files.MISSING if self.data is None else files.digest(self.data)

    def with_rows(self, new_rows: Iterable[Mapping[str, str]]) -> bytes:
        """The whole file with `new_rows` appended: the old bytes untouched,
        the new rows in the file's column order; with a header when there
        was no file."""
        if self.data is None:
            return tables.write_rows(self.fields, new_rows)
        data = self.data if not self.data or self.data.endswith(b"\n") else self.data + b"\n"
        return data + tables.write_rows(self.fields, new_rows, header=False)


def read_for_appending(path: str) -> Appendable:
    """The file, for rows to be appended to it; a ValidationError lists
    every row that breaks the rules."""
    if not os.path.exists(path):
        return Appendable(path, None, COLUMNS, frozenset())
    table = _table(path)
    slugs = frozenset(local for e in _valid_entries(table) if (local := e["local"]))
    return Appendable(path, table.data, table.header, slugs)
