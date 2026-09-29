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
export (for the positions), names/check.py and `curate.py apply` (which
appends rows) all go through it.
"""
from __future__ import annotations

import csv
import io
import os
from typing import NamedTuple

from frasch import files, paths
from frasch.errors import Invalid, ValidationError
from frasch.placelist import LOCAL_TYPE, format_osm, parse_osm

DEFAULT_PATH = paths.CURATION
COLUMNS = ["osm", "name", "lat", "lon", "set_tags", "minzoom", "maxzoom",
           "polygon_km2", "note"]
MINZOOM_KEY = "frasch:minzoom"
MAXZOOM_KEY = "frasch:maxzoom"

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
def parse_point(lat: str | None, lon: str | None, where: str = ""):
    """`("54.65097", "8.34019")` -> `(8.34019, 54.65097)` as (lon, lat) floats,
    None when both cells are empty.  One without the other is an error."""
    lat = (lat or "").strip()
    lon = (lon or "").strip()
    if not lat and not lon:
        return None
    if not (lat and lon):
        raise Invalid(where, f"`lat` and `lon` go together "
                             f"(got lat={lat or '-'}, lon={lon or '-'})")
    try:
        flat, flon = float(lat), float(lon)
    except ValueError:
        raise Invalid(where, f"lat/lon {lat!r}/{lon!r} are not numbers "
                             f"(decimal degrees, e.g. 54.65097 / 8.34019)") from None
    if not (-90 <= flat <= 90 and -180 <= flon <= 180):
        raise Invalid(where, f"lat/lon {flat}/{flon} out of range")
    return flon, flat


def parse_set_tags(spec: str | None, where: str = "") -> dict[str, str]:
    """`set_tags`: `place=island;frasch:kind=island` ->
    `{"place": "island", "frasch:kind": "island"}`."""
    tags = {}
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


def _zoom(row: dict, column: str, found: list[str]) -> int | None:
    z = row.get(column, "")
    if z and not z.lstrip("-").isdigit():
        found.append(f"{column} {z!r} is not an integer")
    return int(z) if z.lstrip("-").isdigit() else None


def _km2(row: dict, found: list[str]) -> float | None:
    cell = row.get("polygon_km2", "")
    if not cell:
        return None
    try:
        km2 = float(cell)
    except ValueError:
        km2 = 0.0
    if not km2 > 0:
        found.append(f"polygon_km2 {cell!r} is not a positive number")
    return km2


# ------------------------------------------------------------------- rows ---
class _Seen:
    """What the rows above have claimed: one row per local reference, one
    square per node."""

    def __init__(self):
        self.positioned, self.squares = set(), set()


def _entry(n: int, row: dict, seen: _Seen) -> tuple[dict | None, list[str]]:
    """-> (the entry of one row, what is wrong with it); no entry for a row
    without a reference (a spacer) or with a problem."""
    try:
        refs = parse_osm(row.get("osm"))
        pos = parse_point(row.get("lat"), row.get("lon"))
    except Invalid as exc:
        return None, [exc.reason]
    if not refs:
        return None, []
    found = []
    local = refs[0][1] if refs[0][0] == LOCAL_TYPE else None
    if pos and not local:
        found.append(f"lat/lon only go with a local reference "
                     f"(local/<slug>), not with {row['osm']!r}")
    if local and not pos:
        found.append(f"local/{local} needs `lat` and `lon`")
    if local and local in seen.positioned:
        found.append(f"second row for local/{local}")
    try:
        tags = parse_set_tags(row.get("set_tags"))
    except Invalid as exc:
        found.append(exc.reason)
    zooms = {col: _zoom(row, col, found) for col in ("minzoom", "maxzoom")}
    km2 = _km2(row, found)
    if km2 is not None:
        if len(refs) != 1 or refs[0][0] not in ("n", LOCAL_TYPE):
            found.append("polygon_km2 needs exactly one node (or local "
                         "reference) in `osm`")
        elif not local and refs[0] in seen.squares:
            found.append(f"second polygon_km2 row for {format_osm(refs)}")
        seen.squares.add(refs[0])
    if local:
        seen.positioned.add(local)
    if found:
        return None, found
    return {"line": n, "refs": refs, "local": local, "pos": pos, "tags": tags,
            **zooms, "km2": km2, "label": row.get("name", "")}, []


def rows(path: str = DEFAULT_PATH):
    """-> (entries, problems): the rows that follow the file's rules, and
    `(line, reason)` for every one that does not.

    An entry: `line`, `refs` (parsed `osm`), `local` (the slug of a local
    reference, else None), `pos` ((lon, lat) or None), `tags` (`set_tags`),
    `minzoom` / `maxzoom` (int or None), `km2` (float or None) and `label`
    (the `name` cell).  Rows without a reference are spacer lines and left
    out."""
    entries, problems, seen = [], [], _Seen()
    with files.open_csv(path) as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        if (what := files.csv_header_problem(header, ["osm"])):
            return entries, [(1, what)]
        for cells in reader:
            n = reader.line_num
            if not cells:
                continue                          # a blank line
            if (what := files.cell_count_problem(cells, header)):
                problems.append((n, what))        # its columns cannot be trusted
                continue
            entry, found = _entry(n, {k: v.strip() for k, v in zip(header, cells, strict=True)},
                                  seen)
            problems += [(n, what) for what in found]
            if entry:
                entries.append(entry)
    return entries, problems


def _valid_entries(path: str) -> list[dict]:
    entries, problems = rows(path)
    if problems:
        raise ValidationError([f"{path}:{n}: {what}" for n, what in problems])
    return entries


class Curation(NamedTuple):
    """The curation as the injector applies it (see tiles/inject_names.py):

    objects  {('r', 1420555): {'tags': {...}, 'label': 'Nordstrand'}} -- the
             tags to set on an OSM object, the zooms among them
    squares  {('n', 85929111): {'km2': 50.0, 'tags': {...}, 'label': ...}} --
             a synthetic square to add around that node; the node itself is
             left alone
    points   {('l', 'westerheide-amrum'): {'lon', 'lat', 'km2', 'tags',
             'label', 'where'}} -- a place OSM does not have: the node (or,
             with `km2`, the square) to add for it"""
    objects: dict
    squares: dict
    points: dict


def read(path: str = DEFAULT_PATH) -> Curation:
    """The curation; a ValidationError lists every row that breaks the
    rules."""
    curation = Curation({}, {}, {})
    for e in _valid_entries(path):
        tags = dict(e["tags"])
        for col, key in (("minzoom", MINZOOM_KEY), ("maxzoom", MAXZOOM_KEY)):
            if e[col] is not None:
                tags[key] = str(e[col])       # tag values must be strings
        key, label = e["refs"][0], e["label"]
        if e["local"]:
            curation.points[key] = {"lon": e["pos"][0], "lat": e["pos"][1],
                                    "km2": e["km2"], "tags": tags, "label": label,
                                    "where": f"{path}:{e['line']}"}
        elif e["km2"] is not None:
            curation.squares[key] = {"km2": e["km2"], "tags": tags, "label": label}
        elif tags:                            # else nothing to apply yet
            for key in e["refs"]:
                curation.objects.setdefault(key, {"tags": {}, "label": label})
                curation.objects[key]["tags"].update(tags)
    return curation


def local_points(path: str = DEFAULT_PATH) -> dict[str, tuple[float, float]]:
    """`{slug: (lon, lat)}` for every local reference -- the positions of the
    places OSM does not have; `{}` without the file."""
    if not os.path.exists(path):
        return {}
    return {e["local"]: e["pos"] for e in _valid_entries(path) if e["local"]}


# -------------------------------------------------------------- appending ---
def read_bytes(path: str) -> tuple[bytes | None, list[str]]:
    """-> (the file's bytes, None when it does not exist; its columns).  The
    columns are the file's own (it is hand-edited, so it may have gained
    one); COLUMNS must be among them."""
    if not os.path.exists(path):
        return None, COLUMNS
    with open(path, "rb") as fh:
        data = fh.read()
    fields = next(csv.reader(io.StringIO(files.decode(data), newline="")), None)
    fields = fields or COLUMNS
    missing = [c for c in COLUMNS if c not in fields]
    if missing:
        raise ValidationError(f"{path}: missing column(s) {missing}")
    return data, fields


def appended(data: bytes | None, fields: list[str], new_rows: list[dict]) -> bytes:
    """The whole file with `new_rows` appended: the old bytes (`read_bytes`)
    untouched, the new rows in the file's column order; with a header when
    there was no file."""
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n",
                       extrasaction="ignore")
    if data is None:
        w.writeheader()
        data = b""
    elif data and not data.endswith(b"\n"):
        data += b"\n"
    for r in new_rows:
        w.writerow({k: r.get(k, "") for k in fields})
    return data + buf.getvalue().encode("utf-8")
