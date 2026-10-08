"""Read / write names/places.csv -- the hand-edited name list.

The file is the single source of truth for every North Frisian label on the
map.  Its conventions (see names/README.md):

* a name cell may hold several variants separated by `;` -- the first one is
  the primary name (the map label).  A `;` inside a remark does not separate
  variants (`Huađer; Huuger (Sölring; Wisinge)` is two names)
* `(...)` after a variant is a remark about it (local variety, source), never
  part of the name
* one column per dialect (`mooring`, `wieding`, ... -- the list comes from
  the dialect registry, frasch.registry), plus `local` (the form the people of
  the place itself use when it differs from the dialect of the area, e.g.
  Fahretoft)
* `osm` holds one or more OSM references: `node/123`, `way/1; way/2` -- or
  ONE local reference `local/<slug>` for a place OSM does not have.  The
  slug keys a row of names/curation.csv that carries the position (`lat` /
  `lon`); the injector adds a node (or a label polygon) of its own for it
* `status` is `auto` (written by the matcher, recomputed on every run), `ok`
  (checked by a human), `skip` (never put on the map) or empty

Everything here is deliberately small and free of OSM libraries so that the
matcher, the injector and the checks can all share it.  The column layout
depends on the dialect registry: the functions that need it take a
`Registry` (frasch.registry).  The dialect-aware name logic (the fallbacks)
lives one layer up in frasch.dialects.
"""

from __future__ import annotations

import contextlib
import errno
import os
import re
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence

from frasch import files, tables
from frasch.errors import Invalid, PipelineError, Problem, ValidationError
from frasch.registry import LOCAL_COLUMN, Registry
from frasch.tables import Table


def name_columns(reg: Registry) -> list[str]:
    """The name columns in the order `any_name` tries them: the first
    (= Mooring) dialect, `local` -- the sub-dialect form of the place itself,
    not a dialect of its own -- then the other dialects."""
    dialect_columns = reg.columns
    return [dialect_columns[0], LOCAL_COLUMN] + dialect_columns[1:]


def columns(reg: Registry) -> list[str]:
    """The columns of the name list, in the order it is written in."""
    return (
        ["kind"]
        + name_columns(reg)
        + ["de", "hint", "da", "osm", "wikidata", "status", "note", "id"]
    )


KINDS = {
    "settlement",
    "koog",
    "harde",
    "island",
    "hallig",
    "sand",
    "warft",
    "landscape",
    "water",
    "road",
    "country",
    "helgoland",
    "not_a_place",
}
STATUSES = {"", "auto", "ok", "skip"}

OSM_TYPES = {"node": "n", "way": "w", "relation": "r"}
# `local/<slug>`: not an OSM object but a place of our own, positioned in
# names/curation.csv.  Keyed like the others, with the slug as its id.
LOCAL_TYPE = "l"
TYPE_NAME = {v: k for k, v in OSM_TYPES.items()} | {LOCAL_TYPE: "local"}
# the shape of a row id and of a local reference's slug
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
WIKIDATA_ID = re.compile(r"Q\d+")

_REMARK = re.compile(r"\(([^()]*)\)")

# A row's cells, column -> stripped text: what the functions that only read a
# row take, so that a row built by hand (a test, a patch) will do as well.
Row = Mapping[str, str]
# One reference of an `osm` cell as `parse_osm` returns it: `("w", 12)` for
# an OSM object, `("l", "westerheide-amrum")` for a local one.
Ref = tuple[str, int | str]
# one that names an OSM object: a node, way or relation id
OsmRef = tuple[str, int]


class PlaceRow(dict[str, str]):
    """A row of the name list as `read` returns it: its cells, and `line`,
    its physical line number in the file (header = 1) -- for the messages
    that point an editor at it."""

    def __init__(self, cells: Mapping[str, str], line: int):
        super().__init__(cells)
        self.line = line


def split_variants(cell: str | None) -> list[str]:
    """Split a name cell on `;` -- but not inside brackets, because a remark
    may itself list several dialects: `Huađer; Huuger (Sölring; Wisinge)` is
    two variants, not three."""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
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
    out: list[tuple[str, str]] = []
    for part in split_variants(cell):
        remarks = [m.group(1).strip() for m in _REMARK.finditer(part)]
        name = _REMARK.sub("", part).strip().rstrip("?").strip()
        if name:
            out.append((name, "; ".join(r for r in remarks if r)))
    return out


def variants(cell: str | None) -> list[str]:
    """`"Rübel; Rübbel (wisinge)"` -> `["Rübel", "Rübbel"]` (remarks stripped)."""
    out: list[str] = []
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


def label(row: Row, column: str = "mooring") -> str:
    """The map label of a row for one dialect column (its primary variant)."""
    return primary(row.get(column))


def any_name(row: Row, reg: Registry) -> str:
    """The row's Frisian name in any dialect -- the answer to "does this row
    carry a Frisian name at all?".  Mooring first, then `local`, then the
    other dialects in registry order."""
    for column in name_columns(reg):
        name = primary(row.get(column))
        if name:
            return name
    return ""


def point_name(row: Row, reg: Registry) -> str:
    """The generic `name` of the node the injector adds for a row OSM does
    not have (a local reference): its German name, else its Danish one, else
    any Frisian one.  The search index gives the row the same, so the card
    names such a place as its map label does."""
    return primary(row.get("de")) or primary(row.get("da")) or any_name(row, reg)


def on_map(row: Row, reg: Registry) -> bool:
    """Whether a row puts names on the map: it has a Frisian name and is
    neither `skip` nor `not_a_place`.  The injector labels these rows'
    objects, and the search index lists them."""
    return row["status"] != "skip" and row["kind"] != "not_a_place" and bool(any_name(row, reg))


def owned_by_matcher(row: Row) -> bool:
    """May the matcher (and `frasch curate apply`) (re)write this row's osm /
    wikidata / status?  Not a row a human decided -- `ok`/`skip`, a
    hand-filled reference, a local reference, `not_a_place` -- only one it
    filled itself (`auto`) or one with nothing in it yet."""
    if local_ref(row["osm"]):
        return False  # a local reference: OSM has no object for it
    if row["kind"] == "not_a_place" or row["status"] in ("ok", "skip"):
        return False
    if row["status"] == "auto":
        return True
    return not row["osm"] and not row["wikidata"]


def parse_osm(cell: str | None, where: str = "") -> list[Ref]:
    """`"way/12; way/13"` -> `[("w", 12), ("w", 13)]`;
    `"local/westerheide-amrum"` -> `[("l", "westerheide-amrum")]`.

    A local reference stands alone: it is the whole cell, never one of
    several."""
    out: list[Ref] = []
    for ref in (cell or "").split(";"):
        ref = ref.strip()
        if not ref:
            continue
        m = re.fullmatch(rf"(node|way|relation)/(\d+)|(local)/({SLUG.pattern})", ref)
        if not m:
            raise Invalid(
                where,
                f"bad reference {ref!r} (expected node/ID, "
                f"way/ID, relation/ID or local/slug with a slug "
                f"of lowercase letters, digits and hyphens)",
            )
        if m.group(3):
            out.append((LOCAL_TYPE, m.group(4)))
        else:
            out.append((OSM_TYPES[m.group(1)], int(m.group(2))))
    if len(out) > 1 and any(t == LOCAL_TYPE for t, _ in out):
        raise Invalid(
            where,
            f"a local reference stands alone, it cannot be "
            f"combined with other references: {cell!r}",
        )
    return out


def as_osm_ref(ref: Ref) -> OsmRef | None:
    """The reference as one to an OSM object; None for a local one."""
    t, i = ref
    return (t, i) if isinstance(i, int) else None


def local_slug(ref: Ref) -> str | None:
    """The slug of a local reference; None for one to an OSM object."""
    _, i = ref
    return i if isinstance(i, str) else None


def osm_refs(cell: str | None, where: str = "") -> list[OsmRef]:
    """The references to OSM objects of an `osm` cell -- none for a local
    reference."""
    return [osm for ref in parse_osm(cell, where) if (osm := as_osm_ref(ref))]


def format_osm(refs: Iterable[Ref]) -> str:
    return "; ".join(f"{TYPE_NAME[t]}/{i}" for t, i in refs)


def local_ref(cell: str | None) -> str | None:
    """The slug when the cell is a local reference (`local/<slug>`), else None.

    Places OSM does not have (Harden, most Köge, vanished Halligen, a Warft
    nobody has mapped) get a reference of our own; names/curation.csv
    positions it and says how the map treats it, the injector adds the object,
    the search index takes the position from there, and the matcher leaves the
    row alone."""
    refs = parse_osm(cell)
    return local_slug(refs[0]) if refs else None


def claimed_refs(row: Row) -> list[Ref]:
    """The objects a row puts on the map: the references in its `osm` cell,
    none for a `skip` row, which never reaches the map.  Only one row per
    object can: the injector labels an object once."""
    if row["status"] == "skip":
        return []
    return parse_osm(row.get("osm"))


def header_problem(fields: Sequence[str], reg: Registry) -> str | None:
    """What is wrong with the header of the name list, or None."""
    if "lat" in fields or "lon" in fields:
        return (
            "`lat`/`lon` moved to names/curation.csv (2026-09-18): reference "
            "the place as local/<slug> in `osm` and delete the two columns"
        )
    if what := tables.unreadable_header(fields):
        return what
    what = tables.missing_columns(fields, columns(reg))
    if what and "id" not in fields:
        what += " (`frasch check-inputs --fix` adds `id`)"
    elif what:
        what += " (dialect columns come from names/dialects.csv)"
    return what


def row_problems(row: Row) -> list[str]:
    """What is wrong with one row of the name list (its cells stripped), in
    the rules `read` enforces.  frasch.check_inputs adds the stricter ones."""
    out: list[str] = []
    if row["kind"] not in KINDS:
        out.append(f"unknown kind {row['kind']!r}")
    if row["status"] not in STATUSES:
        out.append(f"unknown status {row['status']!r} (auto / ok / skip / empty)")
    try:
        local = local_ref(row["osm"])
    except Invalid as exc:
        out.append(exc.reason)
        local = None
    if row["wikidata"] and not WIKIDATA_ID.fullmatch(row["wikidata"]):
        out.append(f"bad wikidata id {row['wikidata']!r}")
    if row["wikidata"] and local:
        out.append(
            "a local reference is for a place OSM does not have -- it cannot have a wikidata id"
        )
    return out


def id_problem(row: Row, seen: dict[str, int]) -> str | None:
    """What is wrong with a row's `id` -- missing, malformed, or used by an
    earlier row (`seen`: id -> line) -- or None."""
    ident = row["id"]
    if not ident:
        return "no id (run `frasch check-inputs --fix` to give new rows one)"
    if not SLUG.fullmatch(ident):
        return (
            f"bad id {ident!r} (lowercase letters, digits and hyphens; "
            f"run `frasch check-inputs --fix` for a new row)"
        )
    if ident in seen:
        return f"id {ident} is already used on line {seen[ident]}"
    return None


# the letters NFKD does not take apart into a base letter and a diacritic
_ASCII_FOLD = str.maketrans(
    {"ß": "ss", "æ": "ae", "Æ": "ae", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d"}
)


def slug(text: str) -> str:
    """`"Schörkewärw"` -> `"schorkewarw"`, `"e Strönj"` -> `"e-stronj"`:
    lowercase ASCII letters and digits, the rest folded or turned into
    hyphens."""
    text = unicodedata.normalize("NFKD", text.translate(_ASCII_FOLD))
    text = text.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def new_id(row: Row, taken: set[str], reg: Registry) -> str:
    """An id for a row that has none: the slug of its Frisian name (German,
    then Danish, when it has none), with `-2`, `-3`, ... when that is taken."""
    base = (
        slug(any_name(row, reg))
        or slug(primary(row.get("de")))
        or slug(primary(row.get("da")))
        or "row"
    )
    ident, n = base, 1
    while ident in taken:
        n += 1
        ident = f"{base}-{n}"
    return ident


def fill_ids(path: str, reg: Registry) -> int:
    """Give every row of the name list without an `id` one (`new_id`), and
    the file the `id` column when it has none -- the one step that both
    introduced the ids and keeps new rows keyed.  An id, once written, never
    changes.  Writes nothing when every row has one.  -> the number of ids
    given.

    It takes the file's cells as they are, because `read` refuses a row
    without an id; a row whose cells do not line up with the header stops it,
    since there is no telling which cell would be the id."""
    found = table(path)
    if found.problems:
        raise ValidationError(found.problems)
    header = found.header
    fields = header if "id" in header else header + ["id"]
    if what := header_problem(fields, reg):
        raise ValidationError([Problem(path, 1, what)])
    rows = [dict(zip(header, cells, strict=True)) for _, cells in found.rows]
    taken = {r["id"].strip() for r in rows if r.get("id", "").strip()}
    given = 0
    for r in rows:
        if not r.get("id", "").strip():
            r["id"] = new_id(r, taken, reg)
            taken.add(r["id"])
            given += 1
    if given or fields is not header:
        write(rows, path, fields)
    return given


def table(path: str) -> Table:
    """The name list as it is on disk -- the one place that opens it."""
    if not os.path.exists(path):
        raise PipelineError(f"name list not found: {path}")
    found = tables.read_table(path)
    # remembered so that `write` can tell whether someone else (the matcher,
    # the curation, a spreadsheet) wrote the file in the meantime
    _read_digests[os.path.abspath(path)] = found.digest
    return found


def ids(names: Table) -> set[str]:
    """The `id` cells of the rows of the name list, whatever rule they break.
    A row whose cells do not line up with the header is not among them, and
    under an unreadable header none is."""
    if "id" not in names.header:
        return set()
    return {row["id"] for _, row in names.records()}


def rows(names: Table, reg: Registry) -> tuple[list[PlaceRow], list[Problem]]:
    """-> (rows, problems): every row of the name list (`names`, see `table`)
    whose cells line up with the header -- identified by its `id`, knowing
    its `line` -- and what is wrong with the file by the rules `read`
    enforces.  A row that breaks one is among the rows all the same:
    frasch.check_inputs has more to say about it.  Without its columns the
    list has no rows."""
    if what := header_problem(names.header, reg):
        return [], [Problem(names.path, 1, what)]
    found = [PlaceRow(cells, n) for n, cells in names.records()]
    problems = list(names.problems)
    seen: dict[str, int] = {}
    for row in found:
        whats = [*row_problems(row), id_problem(row, seen)]
        problems += [Problem(names.path, row.line, what) for what in whats if what]
        seen.setdefault(row["id"], row.line)
    return found, tables.by_line(problems)


def read(path: str, reg: Registry) -> tuple[list[PlaceRow], list[str]]:
    """-> (rows, fieldnames).  A row is identified by its `id` and knows its
    `line`.  A ValidationError lists everything that breaks the rules."""
    found = table(path)
    place_rows, problems = rows(found, reg)
    if problems:
        raise ValidationError(problems)
    return place_rows, found.header


def write(rows: Iterable[Row], path: str, fields: Sequence[str]) -> None:
    """Write the name list -- atomically, and only if nobody else changed the
    file since this process `read` it.

    The file is the source of truth and holds uncommitted hand edits, so a
    crash or Ctrl-C half-way must not leave it truncated (the rows go to a
    temporary file that then replaces the original in one step), and a run
    must not overwrite what a spreadsheet or another script saved while it
    was busy (it stops instead with `Conflict`; re-run it)."""
    expect = _read_digests.get(os.path.abspath(path))
    if expect is None:
        raise RuntimeError(
            f"placelist.write({path!r}) without a placelist.read "
            f"of it first -- nothing to check for changes against"
        )
    data = tables.write_rows(fields, rows)
    files.atomic_write(path, data, expect=expect)
    _read_digests[os.path.abspath(path)] = files.digest(data)


_read_digests: dict[str, str] = {}  # abspath -> sha256 of what `read` saw


@contextlib.contextmanager
def lock(lock_path: str) -> Iterator[None]:
    """Hold the workspace's lock file for the duration of a read-modify-write
    run, so that `frasch match` and `frasch curate apply` never run at the
    same time.  Advisory (`flock`): a spreadsheet does not take it -- that is
    what the check in `write` is for."""
    import fcntl  # POSIX only; the pipeline runs in WSL

    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    with open(lock_path, "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise
            raise PipelineError(
                f"{lock_path} is held: another `frasch match` or "
                f"`frasch curate apply` is running -- wait for it to "
                f"finish"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def describe(row: Row, reg: Registry) -> str:
    """One-line human reference to a row for messages and the report."""
    name = any_name(row, reg) or "-"
    de = primary(row.get("de")) or primary(row.get("da")) or "-"
    return f"{name} ({de})"
