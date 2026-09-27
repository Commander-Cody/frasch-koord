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
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "places.csv")
DIALECTS_PATH = os.path.join(HERE, "dialects.csv")
CURATION_PATH = os.path.join(HERE, "curation.csv")


def open_csv(path: str):
    """Open one of the hand-edited CSV files for reading.  A spreadsheet's
    "CSV UTF-8" starts it with a byte order mark, which would otherwise end up
    in the first column's name."""
    return open(path, encoding="utf-8-sig", newline="")


def decode(data: bytes) -> str:
    """`open_csv` for a file already read as bytes."""
    return data.decode("utf-8-sig")


def _registry_columns(path: str = DIALECTS_PATH) -> list[str]:
    """The dialect columns in registry order (`mooring`, `wieding`, ...)."""
    if not os.path.exists(path):
        raise SystemExit(f"dialect registry not found: {path}")
    with open_csv(path) as fh:
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
           + ["de", "hint", "da", "osm", "wikidata", "status", "note", "id"])

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


def split_variants(cell: str | None) -> list[str]:
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
    for part in split_variants(cell):
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


class Invalid(SystemExit):
    """A cell that breaks the rules of its file.  A script that does not
    catch it stops with `where: reason`; names/check.py, which collects every
    problem instead, takes the bare `reason`."""

    def __init__(self, where: str, reason: str):
        super().__init__(f"{where}: {reason}" if where else reason)
        self.reason = reason


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
            raise Invalid(where, f"bad reference {ref!r} (expected node/ID, "
                                 f"way/ID, relation/ID or local/slug with a slug "
                                 f"of lowercase letters, digits and hyphens)")
        if m.group(3):
            out.append((LOCAL_TYPE, m.group(4)))
        else:
            out.append((OSM_TYPES[m.group(1)], int(m.group(2))))
    if len(out) > 1 and any(t == LOCAL_TYPE for t, _ in out):
        raise Invalid(where, f"a local reference stands alone, it cannot be "
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


def claimed_refs(row: dict) -> list:
    """The objects a row puts on the map: the references in its `osm` cell,
    none for a `skip` row, which never reaches the map.  Only one row per
    object can: the injector labels an object once."""
    if row["status"] == "skip":
        return []
    return parse_osm(row.get("osm"))


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
    """curation.csv's `set_tags`: `place=island;frasch:kind=island` ->
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


def curation_rows(path: str = CURATION_PATH):
    """-> (entries, problems): the rows of names/curation.csv that follow its
    rules, and `(line, reason)` for every one that does not.  The one reading
    of the file's rules, shared by `local_points`, tiles/inject_names.py
    (which stop at the first problem) and names/check.py (which lists them).

    An entry: `line`, `refs` (parsed `osm`), `local` (the slug of a local
    reference, else None), `pos` ((lon, lat) or None),
    `tags` (`set_tags`), `minzoom` / `maxzoom` (int or None), `km2` (float or
    None) and `label` (the `name` cell).  Rows without a reference are blank
    spacer lines and left out."""
    entries, problems = [], []
    polygons, positioned = set(), set()
    with open_csv(path) as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        what = csv_header_problem(header, ["osm"])
        if what:
            return entries, [(1, what)]
        for cells in reader:
            n = reader.line_num
            if not cells:
                continue                          # a blank line
            what = cell_count_problem(cells, header)
            if what:
                problems.append((n, what))        # its columns cannot be trusted
                continue
            row = {k: v.strip() for k, v in zip(header, cells, strict=True)}
            try:
                refs = parse_osm(row.get("osm"))
                pos = parse_point(row.get("lat"), row.get("lon"))
            except Invalid as exc:
                problems.append((n, exc.reason))
                continue
            if not refs:
                continue
            found = []
            local = refs[0][1] if refs[0][0] == LOCAL_TYPE else None
            if pos and not local:
                found.append(f"lat/lon only go with a local reference "
                             f"(local/<slug>), not with {row['osm']!r}")
            if local and not pos:
                found.append(f"local/{local} needs `lat` and `lon`")
            if local and local in positioned:
                found.append(f"second row for local/{local}")
            try:
                tags = parse_set_tags(row.get("set_tags"))
            except Invalid as exc:
                found.append(exc.reason)
            zooms = {}
            for col in ("minzoom", "maxzoom"):
                z = row.get(col, "")
                if z and not z.lstrip("-").isdigit():
                    found.append(f"{col} {z!r} is not an integer")
                zooms[col] = int(z) if z.lstrip("-").isdigit() else None
            km2 = row.get("polygon_km2", "")
            if km2:
                try:
                    km2 = float(km2)
                    if not km2 > 0:
                        raise ValueError
                except ValueError:
                    found.append(f"polygon_km2 {row['polygon_km2']!r} is not a "
                                 f"positive number")
                if len(refs) != 1 or refs[0][0] not in ("n", LOCAL_TYPE):
                    found.append("polygon_km2 needs exactly one node (or local "
                                 "reference) in `osm`")
                elif not local and refs[0] in polygons:
                    found.append(f"second polygon_km2 row for {format_osm(refs)}")
                polygons.add(refs[0])
            else:
                km2 = None
            if local:
                positioned.add(local)
            if found:
                problems += [(n, what) for what in found]
                continue
            entries.append({"line": n, "refs": refs, "local": local, "pos": pos,
                            "tags": tags,
                            **zooms, "km2": km2, "label": row.get("name", "")})
    return entries, problems


def local_points(path: str = CURATION_PATH) -> dict[str, tuple[float, float]]:
    """`{slug: (lon, lat)}` for every local reference in names/curation.csv --
    the positions of the places OSM does not have.  Just the coordinates: the
    rest of the curation (set_tags, zooms, polygons) is tiles/inject_names.py's
    business."""
    if not os.path.exists(path):
        return {}
    entries, problems = curation_rows(path)
    if problems:
        n, what = problems[0]
        raise SystemExit(f"{path}:{n}: {what}")
    return {e["local"]: e["pos"] for e in entries if e["local"]}


SEMICOLON_SEPARATED = ("the cells are separated by `;`, not `,` (a German-locale "
                       "spreadsheet export?) -- save it as comma-separated CSV")


def csv_header_problem(fields, required) -> str | None:
    """What makes a CSV header unreadable -- a `;`-separated export, a column
    named twice, a missing one -- or None."""
    if len(fields) == 1 and ";" in fields[0]:
        return SEMICOLON_SEPARATED
    twice = sorted({c for c in fields if fields.count(c) > 1})
    if twice:
        return f"column(s) named twice: {', '.join(twice)}"
    missing = [c for c in required if c not in fields]
    if missing:
        return f"missing column(s) {', '.join(missing)}"
    return None


def cell_count_problem(cells, header) -> str | None:
    """A row whose cells do not line up with the header's columns: a comma
    too many or too few, and every cell after it is in the wrong column."""
    if len(cells) != len(header):
        return (f"{len(cells)} cells, the header has {len(header)} "
                f"(a comma too many or too few?)")
    return None


def header_problem(fields) -> str | None:
    """What is wrong with the header of the name list, or None."""
    if "lat" in fields or "lon" in fields:
        return ("`lat`/`lon` moved to names/curation.csv (2026-09-18): reference "
                "the place as local/<slug> in `osm` and delete the two columns")
    what = csv_header_problem(fields, COLUMNS)
    if what and "id" not in fields:
        what += " (names/check.py --fix adds `id`)"
    elif what and what.startswith("missing"):
        what += " (dialect columns come from names/dialects.csv)"
    return what


def row_problems(row: dict) -> list[str]:
    """What is wrong with one row of the name list (its cells stripped), in
    the rules `read` enforces.  names/check.py adds the stricter ones."""
    out = []
    if row["kind"] not in KINDS:
        out.append(f"unknown kind {row['kind']!r}")
    if row["status"] not in STATUSES:
        out.append(f"unknown status {row['status']!r} (auto / ok / skip / empty)")
    try:
        local = local_ref(row["osm"])
    except Invalid as exc:
        out.append(exc.reason)
        local = None
    if row["wikidata"] and not re.fullmatch(r"Q\d+", row["wikidata"]):
        out.append(f"bad wikidata id {row['wikidata']!r}")
    if row["wikidata"] and local:
        out.append("a local reference is for a place OSM does not have -- it "
                   "cannot have a wikidata id")
    return out


def id_problem(row: dict, seen: dict[str, int]) -> str | None:
    """What is wrong with a row's `id` -- missing, malformed, or used by an
    earlier row (`seen`: id -> line) -- or None."""
    ident = row["id"]
    if not ident:
        return "no id (run names/check.py --fix to give new rows one)"
    if not re.fullmatch(_SLUG, ident):
        return (f"bad id {ident!r} (lowercase letters, digits and hyphens; "
                f"run names/check.py --fix for a new row)")
    if ident in seen:
        return f"id {ident} is already used on line {seen[ident]}"
    return None


# the letters NFKD does not take apart into a base letter and a diacritic
_ASCII_FOLD = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "ae", "ø": "o", "Ø": "o",
                             "đ": "d", "Đ": "d"})


def slug(text: str) -> str:
    """`"Schörkewärw"` -> `"schorkewarw"`, `"e Strönj"` -> `"e-stronj"`:
    lowercase ASCII letters and digits, the rest folded or turned into
    hyphens."""
    text = unicodedata.normalize("NFKD", text.translate(_ASCII_FOLD))
    text = text.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def new_id(row: dict, taken: set[str]) -> str:
    """An id for a row that has none: the slug of its Frisian name (German,
    then Danish, when it has none), with `-2`, `-3`, ... when that is taken."""
    base = (slug(any_name(row)) or slug(primary(row.get("de")))
            or slug(primary(row.get("da"))) or "row")
    ident, n = base, 1
    while ident in taken:
        n += 1
        ident = f"{base}-{n}"
    return ident


def fill_ids(path: str = DEFAULT_PATH) -> int:
    """Give every row of the name list without an `id` one (`new_id`), and
    the file the `id` column when it has none -- the one step that both
    introduced the ids and keeps new rows keyed.  An id, once written, never
    changes.  Writes nothing when every row has one.  -> the number of ids
    given.

    It reads the file as raw CSV, because `read` refuses a row without an id;
    a row whose cells do not line up with the header stops it, since there is
    no telling which cell would be the id."""
    with open(path, "rb") as fh:
        data = fh.read()
    reader = csv.reader(io.StringIO(decode(data), newline=""))
    header = next(reader, [])
    fields = header if "id" in header else header + ["id"]
    what = header_problem(fields)
    if what:
        raise SystemExit(f"{path}: {what}")
    rows = []
    for cells in reader:
        if not cells:
            continue
        what = cell_count_problem(cells, header)
        if what:
            raise SystemExit(f"{path}:{reader.line_num}: {what}")
        rows.append(dict(zip(header, cells, strict=True)))
    taken = {r["id"].strip() for r in rows if r.get("id", "").strip()}
    given = 0
    for r in rows:
        if not r.get("id", "").strip():
            r["id"] = new_id(r, taken)
            taken.add(r["id"])
            given += 1
    if given or fields is not header:
        _read_digests[os.path.abspath(path)] = digest(data)
        write(rows, path, fields)
    return given


def read(path: str = DEFAULT_PATH):
    """-> (rows, fieldnames).  A row is identified by its `id`; it also gets
    `_line`, its physical line number in the file (header = 1), for the
    messages that point an editor at it."""
    with open(path, "rb") as fh:
        data = fh.read()
    # remembered so that `write` can tell whether someone else (match.py,
    # curate.py apply, a spreadsheet) wrote the file in the meantime
    _read_digests[os.path.abspath(path)] = digest(data)
    with io.StringIO(decode(data), newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        what = header_problem(fields)
        if what:
            raise SystemExit(f"{path}: {what}")
        rows, seen = [], {}
        for row in reader:
            n = reader.line_num                  # blank lines count too
            if None in row:                      # more cells than columns
                raise SystemExit(f"{path}:{n}: row has more cells than the header "
                                 f"(a stray comma?): {row[None]}")
            row = {k: (v or "").strip() for k, v in row.items()}
            row["_line"] = n
            problems = row_problems(row) + [id_problem(row, seen)]
            problems = [p for p in problems if p]
            if problems:
                raise SystemExit(f"{path}:{n}: {problems[0]}")
            seen[row["id"]] = n
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
