"""The registry of the local varieties, names/dialects.csv: the single list
of the varieties the project knows -- the North Frisian dialects, and Low
Saxon and Synnejysk, the other local languages of Schleswig.

North Frisian is not one language variety but a dozen, and the map shows more
than one of them.  Wherever the code says "Frisian" it means the rows of
`language` `frr`; Low Saxon (`nds`) and Synnejysk (`jut`) have names of their
own in the list, but they are never a row's Frisian name, a row is named by
them only when it has no Frisian, German or Danish one
(`placelist.naming_columns`), and no map view is in them.
Everything else derives from this list: the name columns of
names/places.csv (frasch.placelist), the `name:<tag>` tags the injector
writes, Planetiler's `--languages` list (`frasch dialects --tags` in
tiles/build.sh), the search index and the frontend's selector
(web/src/dialects/generated/dialects.json).  Adding a variety is therefore one line in
the registry plus a column in places.csv -- and, the one thing in the code, its
colour in the dialect-area review view (`DIALECT_COLORS` in
web/src/dev/areas/areaLayers.ts, which a test holds to the registry's tags).

| column | meaning |
|---|---|
| `tag`    | BCP 47 language tag, `<language>` or `<language>-x-<subtag>`; a Frisian one always `frr-x-<subtag>` -- no registered subtags for North Frisian dialects exist, so private use it is, and a bare `frr` is OSM's Frisian of no dialect |
| `language` | ISO 639 code of the language the variety belongs to: `frr`, `nds`, `jut` |
| `column` | the column of names/places.csv that holds this dialect's names |
| `label`  | how the dialect is written in the UI (its German/endonym name) |
| `status` | `living` or `extinct` (extinct dialects still label the map in the local view -- Südergoesharde) |
| `view`   | `yes` = selectable as a map language in the frontend; Frisian rows only |
| `note`   | free text: which area speaks it |

This is the one reader of the file.  A command reads the registry of its
workspace once (`read`), and whatever needs it takes the `Registry` as a
parameter.

`frasch dialects` hands it to the rest of the build:

    frasch dialects            prints the registry
    frasch dialects --tags     prints `frr-x-mooring,frr-x-wieding,...`
                               (tiles/build.sh feeds it to Planetiler)

and `frasch build dialects` writes the registry the frontend compiles in
(`export_json`: web/src/dialects/generated/dialects.json, every column but
`column` and `note`).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Collection, Iterator, Mapping, Sequence
from typing import Literal, TypedDict, cast

from frasch import cli, files, tables
from frasch.errors import PipelineError, Problem, ValidationError

STATUSES = {"living", "extinct"}
VIEWS = {"yes", "no"}

# The places.csv column that is not a dialect of its own: the form the people
# of the place itself use (frasch.placenames), so no dialect may be called that.
LOCAL_COLUMN = "local"

# The language of the North Frisian dialects: OSM's `name:frr` is Frisian of
# no particular dialect, so a Frisian row needs a private-use subtag.
FRISIAN = "frr"

_LANGUAGE = re.compile(r"[a-z]{2,3}")
# BCP 47 allows at most 8 characters per private-use subtag
_TAG = re.compile(r"(?P<language>[a-z]{2,3})(-x(-[a-z0-9]{1,8})+)?")


class Dialect(TypedDict):
    """One row of the registry: a cell per column of the file."""

    tag: str
    language: str
    column: str
    label: str
    status: str
    view: str
    note: str


FIELDS = list(Dialect.__annotations__)  # the columns of the file, in its order
# What the frontend gets: all but `column` (places.csv is no business of the
# browser) and `note`.
EXPORT_FIELDS = [f for f in FIELDS if f not in ("column", "note")]


class Registry:
    """The dialects in file order."""

    def __init__(self, dialects: list[Dialect]):
        self.dialects = list(dialects)

    def __iter__(self) -> Iterator[Dialect]:
        return iter(self.dialects)

    def __len__(self) -> int:
        return len(self.dialects)

    @property
    def tags(self) -> list[str]:
        return [d["tag"] for d in self.dialects]

    @property
    def columns(self) -> list[str]:
        return [d["column"] for d in self.dialects]

    @property
    def frisian(self) -> list[Dialect]:
        """The North Frisian dialects, in file order."""
        return [d for d in self.dialects if d["language"] == FRISIAN]

    @property
    def non_frisian(self) -> list[Dialect]:
        """The local varieties of the other languages (Low Saxon, Synnejysk), in file order."""
        return [d for d in self.dialects if d["language"] != FRISIAN]

    def language_of(self, tag: str) -> str:
        return self._find("tag", tag)["language"]

    def column_of(self, tag: str) -> str:
        return self._find("tag", tag)["column"]

    def tag_of_column(self, column: str) -> str:
        return self._find("column", column)["tag"]

    def _find(self, field: Literal["tag", "column"], value: str) -> Dialect:
        for d in self.dialects:
            if d[field] == value:
                return d
        raise PipelineError(f"unknown dialect {field} {value!r} (not in the dialect registry)")


def row_problem(
    row: Mapping[str, str], seen_tags: Collection[str] = (), seen_cols: Collection[str] = ()
) -> str | None:
    """What is wrong with one registry row (`seen_*`: the tags and columns of
    the rows above it), or None."""
    if what := tag_problem(row["tag"], row["language"]):
        return what
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
    if row["view"] == "yes" and row["language"] != FRISIAN:
        return (
            f"view 'yes' for a variety of {row['language']!r} -- "
            f"only a Frisian dialect ({FRISIAN}) can be a map view"
        )
    if not row["label"]:
        return "no label"
    return None


def tag_problem(tag: str, language: str) -> str | None:
    """What is wrong with the tag of a row of `language`, or None: a tag is
    `<language>` or `<language>-x-<subtag>...`, and a Frisian one has a subtag."""
    if not _LANGUAGE.fullmatch(language):
        return f"bad language {language!r} -- expected an ISO 639 code such as {FRISIAN}"
    match = _TAG.fullmatch(tag)
    if not match:
        return (
            f"bad tag {tag!r} -- expected <language> or <language>-x-<subtag>, "
            f"subtags [a-z0-9] and at most 8 characters each"
        )
    if match["language"] != language:
        return (
            f"tag {tag!r} is not of the row's language {language!r} -- "
            f"expected {language} or {language}-x-<subtag>"
        )
    if tag == FRISIAN:
        return (
            f"bare tag {FRISIAN!r} -- a Frisian dialect needs a subtag of its own, "
            f"{FRISIAN}-x-<subtag> (plain {FRISIAN} is OSM's name:{FRISIAN}, "
            f"Frisian of no particular dialect)"
        )
    return None


def rows(path: str) -> tuple[list[Dialect], list[Problem]]:
    """-> (dialects, problems): the rows of the registry that follow its
    rules, and what is wrong with the others.  A registry without a dialect
    is one problem."""
    if not os.path.exists(path):
        raise PipelineError(f"dialect registry not found: {path}")
    table = tables.read_table(path, FIELDS)
    found: list[Dialect] = []
    problems = list(table.problems)
    seen_tags: set[str] = set()
    seen_cols: set[str] = set()
    for n, row in table.records():
        if not row["tag"]:
            continue  # blank spacer line
        if what := row_problem(row, seen_tags, seen_cols):
            problems.append(Problem(path, n, what))
        else:
            found.append(_dialect(row))
        seen_tags.add(row["tag"])
        seen_cols.add(row["column"])
    if not found and not problems:
        problems.append(Problem(path, 1, "no dialects"))
    return found, tables.by_line(problems)


def _dialect(row: Mapping[str, str]) -> Dialect:
    return cast(Dialect, {field: row[field] for field in FIELDS})


def read(path: str) -> Registry:
    """The registry, validated; a ValidationError lists every problem."""
    found, problems = rows(path)
    if problems:
        raise ValidationError(problems)
    return Registry(found)


def export_json(reg: Registry, path: str) -> None:
    """Write the registry the frontend compiles in: every column but `column` and `note`."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    files.atomic_write(
        path,
        json.dumps(
            [{k: v for k, v in d.items() if k in EXPORT_FIELDS} for d in reg],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
    )


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("dialects", __doc__)
    cli.add_workspace_options(ap, "dialects")
    ap.add_argument(
        "--tags",
        action="store_true",
        help="print the language tags as a comma-separated list "
        "(tiles/build.sh feeds them to Planetiler)",
    )
    a = ap.parse_args(argv)
    ws = cli.workspace(a)
    reg = read(ws.dialects)
    if a.tags:
        print(",".join(reg.tags))
    else:
        for d in reg:
            print(
                f"{d['tag']:<16} {d['language']:<4} {d['column']:<10} {d['label']:<18} "
                f"{d['status']:<7} view={d['view']:<4} {d['note']}"
            )
    return 0
