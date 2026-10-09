"""The name list, names/places.csv: its columns, its rows and what they
hold, and reading and writing the file.

The file is the single source of truth for every North Frisian label on the
map.  Its conventions (see names/README.md):

* one column per dialect (`mooring`, `wieding`, ... -- the list comes from
  the dialect registry, frasch.dialects), plus `local` (the form the people of
  the place itself use when it differs from the dialect of the area, e.g.
  Fahretoft); a name cell reads as frasch.namecell says
* `osm` holds the references of the row (frasch.refs): one or more OSM
  objects, or ONE local reference for a place OSM does not have, which
  names/curation.csv positions
* `status` is `auto` (written by the matcher, recomputed on every run), `ok`
  (checked by a human), `skip` (never put on the map) or empty
* `id` is the row's own key, which every other file names it by

`read` gives the list as a `PlaceList`, which also writes it back.  It
refuses a list that breaks the rules of `rows` -- among them that only one
row holds an object or a Wikidata item (`claims`).  The column layout depends
on the dialect registry: the functions that need it take a `Registry`.
Which names a place gets from its row is frasch.placenames' rule.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple

from frasch import files, refs, tables
from frasch.dialects import LOCAL_COLUMN, Registry
from frasch.errors import Invalid, PipelineError, Problem, ValidationError
from frasch.namecell import primary
from frasch.refs import SLUG, OsmRef, Ref
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

WIKIDATA_ID = re.compile(r"Q\d+")

# A row's cells, column -> stripped text: what the functions that only read a
# row take, so that a row built by hand (a test, a patch) will do as well.
Row = Mapping[str, str]


class PlaceRow(dict[str, str]):
    """A row of the name list as `read` returns it: its cells, `line`, its
    physical line number in the file (header = 1) -- for the messages that
    point an editor at it --, and the references of its `osm` cell, parsed
    (`refs`)."""

    def __init__(self, cells: Mapping[str, str], line: int):
        super().__init__(cells)
        self.line = line
        self._parsed: tuple[str, list[Ref]] | None = None  # (the cell, its references)

    @property
    def refs(self) -> list[Ref]:
        """The references of the row's `osm` cell, as the cell is now: the
        matcher and `curate apply` rewrite it."""
        cell = self["osm"]
        if self._parsed is None or self._parsed[0] != cell:
            self._parsed = (cell, refs.parse(cell))
        return self._parsed[1]

    @property
    def osm_refs(self) -> list[OsmRef]:
        """Those of its references that name an OSM object."""
        return refs.osm_only(self.refs)

    @property
    def local(self) -> str | None:
        """The slug of its local reference, for a place OSM does not have."""
        return refs.local_of(self.refs)


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


def owned_by_matcher(row: Row) -> bool:
    """May the matcher (and `frasch curate apply`) (re)write this row's osm /
    wikidata / status?  Not a row a human decided -- `ok`/`skip`, a
    hand-filled reference, a local reference, `not_a_place` -- only one it
    filled itself (`auto`) or one with nothing in it yet."""
    if refs.local_of(_refs(row)):
        return False  # a local reference: OSM has no object for it
    if row["kind"] == "not_a_place" or row["status"] in ("ok", "skip"):
        return False
    if row["status"] == "auto":
        return True
    return not row["osm"] and not row["wikidata"]


class Claims(NamedTuple):
    """What a row holds for itself, see `claims`: the objects its `osm` cell
    names (`refs`) and its Wikidata item (`qid`, `""` for none)."""

    refs: list[Ref]
    qid: str

    @property
    def keys(self) -> list[str]:
        """Each claim as the list spells it: `way/1`, `Q35`."""
        return [refs.format([ref]) for ref in self.refs] + ([self.qid] if self.qid else [])


def claims(row: Row) -> Claims:
    """What a row holds for itself: the objects of its `osm` cell and its
    Wikidata item -- nothing for a `skip` row, which never reaches the map.
    It holds them also while it is `not_a_place` or has no Frisian name yet
    (`on_map` is the narrower question).  Only one row can hold an object or
    an item: the injector labels it once, so a second claim is a problem of
    the list (`rows`)."""
    if row["status"] == "skip":
        return Claims([], "")
    return Claims(_refs(row), row["wikidata"])


def _refs(row: Row) -> list[Ref]:
    """The references of a row's `osm` cell: parsed already for a row of the
    list, now for one built by hand."""
    return row.refs if isinstance(row, PlaceRow) else refs.parse(row.get("osm"))


def on_map(row: Row, reg: Registry) -> bool:
    """Whether a row puts names on the map: it claims an object or an item,
    is a place (not `not_a_place`) and has a Frisian name.  The injector
    labels these rows' objects, and the search index lists them."""
    held = claims(row)
    return bool(held.refs or held.qid) and row["kind"] != "not_a_place" and bool(any_name(row, reg))


def header_problem(fields: Sequence[str], reg: Registry) -> str | None:
    """What is wrong with the header of the name list, or None."""
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
        local = refs.local_of(_refs(row))
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
    rows = [PlaceRow(dict(zip(header, cells, strict=True)), n) for n, cells in found.rows]
    taken = {r["id"].strip() for r in rows if r.get("id", "").strip()}
    given = 0
    for r in rows:
        if not r.get("id", "").strip():
            r["id"] = new_id(r, taken, reg)
            taken.add(r["id"])
            given += 1
    if given or fields is not header:
        PlaceList(path, reg, fields, rows, found.digest).write()
    return given


def table(path: str) -> Table:
    """The name list as it is on disk -- the one place that opens it."""
    if not os.path.exists(path):
        raise PipelineError(f"name list not found: {path}")
    return tables.read_table(path)


def ids(names: Table) -> set[str]:
    """The `id` cells of the rows of the name list, whatever rule they break.
    A row whose cells do not line up with the header is not among them, and
    under an unreadable header none is."""
    if "id" not in names.header:
        return set()
    return {row["id"] for _, row in names.records()}


def claim_problems(held: Sequence[str], claimed: Mapping[str, int]) -> list[str]:
    """Which of a row's claims (`held`, as `Claims.keys` spells them) a row
    above it holds already (`claimed`: claim -> line)."""
    return [
        f"{key} is already claimed by line {claimed[key]} -- only one name can go on the map"
        for key in held
        if key in claimed
    ]


def _claim_keys(row: Row) -> list[str]:
    """What a row claims, as `Claims.keys` spells it -- of an unreadable
    `osm` cell (`row_problems` says so) nothing."""
    try:
        return claims(row).keys
    except Invalid:
        return claims({**row, "osm": ""}).keys


def rows(names: Table, reg: Registry) -> tuple[list[PlaceRow], list[Problem]]:
    """-> (rows, problems): every row of the name list (`names`, see `table`)
    whose cells line up with the header -- identified by its `id`, knowing
    its `line` -- and what is wrong with the file by the rules `read`
    enforces: those of a row's cells, and across the rows a unique id and
    one row per object or Wikidata item (`claims`).  A row that breaks one
    is among the rows all the same: frasch.check_inputs has more to say
    about it.  Without its columns the list has no rows."""
    if what := header_problem(names.header, reg):
        return [], [Problem(names.path, 1, what)]
    found = [PlaceRow(cells, n) for n, cells in names.records()]
    problems = list(names.problems)
    seen: dict[str, int] = {}  # id -> the line of its row
    claimed: dict[str, int] = {}  # `way/1` or `Q35` -> the line of the row that holds it
    for row in found:
        held = _claim_keys(row)
        whats = [*row_problems(row), id_problem(row, seen), *claim_problems(held, claimed)]
        problems += [Problem(names.path, row.line, what) for what in whats if what]
        seen.setdefault(row["id"], row.line)
        claimed.update((key, row.line) for key in held if key not in claimed)
    return found, tables.by_line(problems)


@dataclass
class PlaceList:
    """The name list at `path` as `read` found it: its `rows`, under the
    columns `fields` (those of the registry `reg`, and any of the editor's
    own), and the `digest` of the file they were read from."""

    path: str
    reg: Registry
    fields: list[str]
    rows: list[PlaceRow]
    digest: str

    def write(self) -> None:
        """Write the rows back -- atomically, and only if nobody else changed
        the file since it was read.

        The file is the source of truth and holds uncommitted hand edits, so
        a crash or Ctrl-C half-way must not leave it truncated (the rows go
        to a temporary file that then replaces the original in one step), and
        a run must not overwrite what a spreadsheet or another script saved
        while it was busy (it stops instead with `Conflict`; re-run it)."""
        data = tables.write_rows(self.fields, self.rows)
        files.atomic_write(self.path, data, expect=self.digest)
        self.digest = files.digest(data)


def read(path: str, reg: Registry) -> PlaceList:
    """The name list.  A row is identified by its `id` and knows its `line`.
    A ValidationError lists everything that breaks the rules."""
    found = table(path)
    place_rows, problems = rows(found, reg)
    if problems:
        raise ValidationError(problems)
    return PlaceList(path, reg, found.header, place_rows, found.digest)


def describe(row: Row, reg: Registry) -> str:
    """One-line human reference to a row for messages and the report."""
    name = any_name(row, reg) or "-"
    de = primary(row.get("de")) or primary(row.get("da")) or "-"
    return f"{name} ({de})"
