"""Read / write names/places.csv -- the hand-edited name list.

The file is the single source of truth for every North Frisian label on the
map.  Its conventions (see names/README.md):

* a name cell may hold several variants separated by `;` -- the first one is
  the primary name (the map label).  A `;` inside a remark does not separate
  variants (`Huađer; Huuger (Sölring; Wisinge)` is two names)
* `(...)` after a variant is a remark about it (local variety, source), never
  part of the name
* one column per dialect (`mooring`, `wieding`, ... -- the list comes from
  names/dialects.csv, the registry), plus `local` (the form the people of
  the place itself use when it differs from the dialect of the area, e.g.
  Fahretoft)
* `osm` holds one or more OSM references: `node/123`, `way/1; way/2` -- or
  ONE local reference `local/<slug>` for a place OSM does not have.  The
  slug keys a row of names/curation.csv that carries the position (`lat` /
  `lon`); the injector adds a node (or a label polygon) of its own for it
* `status` is `auto` (written by match.py, recomputed on every run), `ok`
  (checked by a human), `skip` (never put on the map) or empty

Everything here is deliberately small and dependency-free so that both
names/match.py and tiles/inject_names.py can share it.  The dialect-aware
name logic (which column a tag maps to, the fallbacks) lives one layer up in
names/dialects.py, which builds on this module -- that is why the registry is
read here with a plain csv reader instead of through dialects.py: the
dependency must point in one direction only.
"""
from __future__ import annotations

import contextlib
import csv
import errno
import hashlib
import io
import os
import re
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "places.csv")
DIALECTS_PATH = os.path.join(HERE, "dialects.csv")
CURATION_PATH = os.path.join(HERE, "curation.csv")


def _registry_columns(path: str = DIALECTS_PATH) -> list[str]:
    """The dialect columns in registry order (`mooring`, `wieding`, ...)."""
    if not os.path.exists(path):
        raise SystemExit(f"dialect registry not found: {path}")
    with open(path, encoding="utf-8", newline="") as fh:
        cols = [(r.get("column") or "").strip() for r in csv.DictReader(fh)]
    cols = [c for c in cols if c]
    if not cols:
        raise SystemExit(f"{path}: no dialect columns")
    return cols


# `local` is not a dialect of its own: it holds the sub-dialect form of the
# place itself.  It sits next to the first (= Mooring) dialect column.
DIALECT_COLUMNS = _registry_columns()
EXTRA_NAME_COLUMNS = ["local"]
NAME_COLUMNS = [DIALECT_COLUMNS[0]] + EXTRA_NAME_COLUMNS + DIALECT_COLUMNS[1:]
COLUMNS = (["kind"] + NAME_COLUMNS
           + ["de", "hint", "da", "osm", "wikidata", "status", "note"])

KINDS = {"settlement", "koog", "harde", "island", "hallig", "sand", "warft",
         "landscape", "water", "road", "country", "helgoland", "not_a_place"}
STATUSES = {"", "auto", "ok", "skip"}

OSM_TYPES = {"node": "n", "way": "w", "relation": "r"}
# `local/<slug>`: not an OSM object but a place of our own, positioned in
# names/curation.csv.  Keyed like the others, with the slug as its id.
LOCAL_TYPE = "l"
TYPE_NAME = {v: k for k, v in OSM_TYPES.items()} | {LOCAL_TYPE: "local"}
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"

_REMARK = re.compile(r"\(([^()]*)\)")


def _split(cell: str | None) -> list[str]:
    """Split a name cell on `;` -- but not inside brackets, because a remark
    may itself list several dialects: `Huađer; Huuger (Sölring; Wisinge)` is
    two variants, not three."""
    out, buf, depth = [], [], 0
    for ch in cell or "":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def parts(cell: str | None) -> list[tuple[str, str]]:
    """`"Rübel; Rübbel (wisinge)"` -> `[("Rübel", ""), ("Rübbel", "wisinge")]`.

    The remark comes back without its brackets; several brackets on one
    variant are joined with `; `.  Variants without a name are dropped."""
    out = []
    for part in _split(cell):
        remarks = [m.group(1).strip() for m in _REMARK.finditer(part)]
        name = _REMARK.sub("", part).strip().rstrip("?").strip()
        if name:
            out.append((name, "; ".join(r for r in remarks if r)))
    return out


def variants(cell: str | None) -> list[str]:
    """`"Rübel; Rübbel (wisinge)"` -> `["Rübel", "Rübbel"]` (remarks stripped)."""
    out = []
    for name, _ in parts(cell):
        if name not in out:
            out.append(name)
    return out


def primary(cell: str | None) -> str:
    v = variants(cell)
    return v[0] if v else ""


def remark(cell: str | None) -> str:
    """The remark of the PRIMARY variant of a cell (`""` when it has none)."""
    p = parts(cell)
    return p[0][1] if p else ""


def label(row: dict, column: str = "mooring") -> str:
    """The map label of a row for one dialect column (its primary variant)."""
    return primary(row.get(column))


def any_name(row: dict) -> str:
    """The row's Frisian name in any dialect -- the answer to "does this row
    carry a Frisian name at all?".  Mooring first, then `local`, then the
    other dialects in registry order."""
    for column in NAME_COLUMNS:
        name = primary(row.get(column))
        if name:
            return name
    return ""


def parse_osm(cell: str | None, where: str = "") -> list[tuple[str, int | str]]:
    """`"way/12; way/13"` -> `[("w", 12), ("w", 13)]`;
    `"local/westerheide-amrum"` -> `[("l", "westerheide-amrum")]`.

    A local reference stands alone: it is the whole cell, never one of
    several."""
    out = []
    for ref in (cell or "").split(";"):
        ref = ref.strip()
        if not ref:
            continue
        m = re.fullmatch(rf"(node|way|relation)/(\d+)|(local)/({_SLUG})", ref)
        if not m:
            raise SystemExit(f"{where}: bad reference {ref!r} (expected node/ID, "
                             f"way/ID, relation/ID or local/slug with a slug of "
                             f"lowercase letters, digits and hyphens)")
        if m.group(3):
            out.append((LOCAL_TYPE, m.group(4)))
        else:
            out.append((OSM_TYPES[m.group(1)], int(m.group(2))))
    if len(out) > 1 and any(t == LOCAL_TYPE for t, _ in out):
        raise SystemExit(f"{where}: a local reference stands alone, it cannot be "
                         f"combined with other references: {cell!r}")
    return out


def format_osm(refs) -> str:
    return "; ".join(f"{TYPE_NAME[t]}/{i}" for t, i in refs)


def local_ref(cell: str | None) -> str | None:
    """The slug when the cell is a local reference (`local/<slug>`), else None.

    Places OSM does not have (Harden, most Köge, vanished Halligen, a Warft
    nobody has mapped) get a reference of our own; names/curation.csv
    positions it and says how the map treats it, the injector adds the object,
    the search index takes the position from there, and `match.py` leaves the
    row alone."""
    refs = parse_osm(cell)
    if refs and refs[0][0] == LOCAL_TYPE:
        return refs[0][1]
    return None


def entry_id(row: dict) -> str:
    """The row's identity as the rest of the project spells it: its FIRST OSM
    reference (`node/240042766`, `local/huelltoft`), or -- for a row that has
    none, i.e. the countries -- its Wikidata QID.  `""` when it has neither.

    The injector writes it into the tiles as `frasch:ref` and the exporter
    uses it as the id of a search-index entry, which is how a click on a map
    label finds the row it came from; the two must therefore derive the same
    string, and that is why it lives here.  A row claiming several objects
    gives all of them the same ref -- they are one place.
    """
    refs = parse_osm(row.get("osm"))
    if refs:
        return format_osm(refs[:1])
    return (row.get("wikidata") or "").strip()


def parse_point(lat: str | None, lon: str | None, where: str = ""):
    """`("54.65097", "8.34019")` -> `(8.34019, 54.65097)` as (lon, lat) floats,
    None when both cells are empty.  One without the other is an error."""
    lat = (lat or "").strip()
    lon = (lon or "").strip()
    if not lat and not lon:
        return None
    if not (lat and lon):
        raise SystemExit(f"{where}: `lat` and `lon` go together "
                         f"(got lat={lat or '-'}, lon={lon or '-'})")
    try:
        flat, flon = float(lat), float(lon)
    except ValueError:
        raise SystemExit(f"{where}: lat/lon {lat!r}/{lon!r} are not numbers "
                         f"(decimal degrees, e.g. 54.65097 / 8.34019)")
    if not (-90 <= flat <= 90 and -180 <= flon <= 180):
        raise SystemExit(f"{where}: lat/lon {flat}/{flon} out of range")
    return flon, flat


def local_points(path: str = CURATION_PATH) -> dict[str, tuple[float, float]]:
    """`{slug: (lon, lat)}` for every local reference in names/curation.csv --
    the positions of the places OSM does not have.  Just the coordinates: the
    full curation logic (set_tags, zooms, polygons) lives in
    tiles/inject_names.py, which validates the same rows more strictly."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        if "osm" not in fields:
            raise SystemExit(f"{path}: needs an `osm` column")
        for n, row in enumerate(reader, start=2):
            where = f"{path}:{n}"
            refs = parse_osm(row.get("osm"), where)
            pos = parse_point(row.get("lat"), row.get("lon"), where)
            if not refs:
                continue
            if refs[0][0] != LOCAL_TYPE:
                if pos:
                    raise SystemExit(f"{where}: lat/lon only go with a local "
                                     f"reference (local/<slug>), not with {row['osm']!r}")
                continue
            slug = refs[0][1]
            if pos is None:
                raise SystemExit(f"{where}: local/{slug} needs `lat` and `lon`")
            if slug in out:
                raise SystemExit(f"{where}: second row for local/{slug}")
            out[slug] = pos
    return out


def read(path: str = DEFAULT_PATH):
    """-> (rows, fieldnames).  Every row gets `_line`, its physical line number
    in the file (header = 1), which is how REPORT.md refers to rows."""
    with open(path, "rb") as fh:
        data = fh.read()
    # remembered so that `write` can tell whether someone else (match.py,
    # curate.py apply, a spreadsheet) wrote the file in the meantime
    _read_digests[os.path.abspath(path)] = digest(data)
    with io.StringIO(data.decode("utf-8"), newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        if "lat" in fields or "lon" in fields:
            raise SystemExit(f"{path}: `lat`/`lon` moved to names/curation.csv "
                             f"(2026-09-18): reference the place as local/<slug> "
                             f"in `osm` and delete the two columns.")
        missing = [c for c in COLUMNS if c not in fields]
        if missing:
            raise SystemExit(f"{path}: missing column(s) {missing} "
                             f"(dialect columns come from names/dialects.csv)")
        rows = []
        for n, row in enumerate(reader, start=2):
            if None in row:                      # more cells than columns
                raise SystemExit(f"{path}:{n}: row has more cells than the header "
                                 f"(a stray comma?): {row[None]}")
            row = {k: (v or "").strip() for k, v in row.items()}
            row["_line"] = n
            if row["kind"] not in KINDS:
                raise SystemExit(f"{path}:{n}: unknown kind {row['kind']!r}")
            if row["status"] not in STATUSES:
                raise SystemExit(f"{path}:{n}: unknown status {row['status']!r} "
                                 f"(auto / ok / skip / empty)")
            parse_osm(row["osm"], f"{path}:{n}")
            if row["wikidata"] and not re.fullmatch(r"Q\d+", row["wikidata"]):
                raise SystemExit(f"{path}:{n}: bad wikidata id {row['wikidata']!r}")
            if row["wikidata"] and local_ref(row["osm"]):
                raise SystemExit(f"{path}:{n}: a local reference is for a place "
                                 f"OSM does not have -- it cannot have a wikidata id")
            rows.append(row)
    return rows, fields


def write(rows, path: str = DEFAULT_PATH, fields=None):
    """Write the name list -- atomically, and only if nobody else changed the
    file since this process `read` it.

    The file is the source of truth and holds uncommitted hand edits, so a
    crash or Ctrl-C half-way must not leave it truncated (the rows go to a
    temporary file that then replaces the original in one step), and a run
    must not overwrite what a spreadsheet or another script saved while it
    was busy (it stops instead; re-run it)."""
    fields = fields or COLUMNS
    expect = _read_digests.get(os.path.abspath(path))
    if expect is None:
        raise RuntimeError(f"placelist.write({path!r}) without a placelist.read "
                           f"of it first -- nothing to check for changes against")
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n",
                       extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    data = buf.getvalue().encode("utf-8")
    atomic_write(path, data, expect=expect)
    _read_digests[os.path.abspath(path)] = digest(data)


# ------------------------------------------------------------ safe writes ---
_read_digests: dict[str, str] = {}      # abspath -> sha256 of what `read` saw

MISSING = "missing"                     # `expect` for a file that must not exist


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(path: str) -> str:
    """The sha256 of a file's bytes, or MISSING -- what `atomic_write`
    compares against to notice a concurrent change."""
    try:
        with open(path, "rb") as fh:
            return digest(fh.read())
    except FileNotFoundError:
        return MISSING


class Conflict(SystemExit):
    """The file changed on disk between reading and writing it."""


def atomic_write(path: str, data: bytes | str, expect: str | None = None):
    """Replace `path` with `data` in one step: write a temporary file next to
    it, flush it to disk, then `os.replace` it over the original.  A crash at
    any point leaves either the old or the new file, never half of one.

    `expect` (a `fingerprint`) makes it refuse -- with `Conflict`, leaving the
    file alone -- when the file no longer is what the caller read."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{os.path.basename(path)}.",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            mode = os.stat(path).st_mode & 0o7777
        except FileNotFoundError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp, mode)
        if expect is not None and fingerprint(path) != expect:
            raise Conflict(f"{path} changed on disk while this was running "
                           f"(a spreadsheet, match.py or curate.py apply?) -- "
                           f"not overwriting it.  Nothing was written; save or "
                           f"commit the other change and run this again.")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    with contextlib.suppress(OSError):  # make the rename itself durable
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)


@contextlib.contextmanager
def lock(names_path: str = DEFAULT_PATH):
    """Hold `work/.lock` next to the name list for the duration of a
    read-modify-write run, so that match.py and curate.py apply never run at
    the same time.  Advisory (`flock`): a spreadsheet does not take it -- that
    is what the check in `write` is for."""
    import fcntl                        # POSIX only; the pipeline runs in WSL
    work = os.path.join(os.path.dirname(os.path.abspath(names_path)), "work")
    os.makedirs(work, exist_ok=True)
    lock_path = os.path.join(work, ".lock")
    with open(lock_path, "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise
            raise SystemExit(f"{lock_path} is held: another match.py or "
                             f"curate.py apply is running -- wait for it to "
                             f"finish") from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def describe(row: dict) -> str:
    """One-line human reference to a row for messages and the report."""
    name = any_name(row) or "-"
    de = primary(row.get("de")) or primary(row.get("da")) or "-"
    return f"{name} ({de})"
