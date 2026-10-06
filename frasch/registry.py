"""The dialect registry, names/dialects.csv: the single list of the dialects
the project knows.

North Frisian is not one language variety but a dozen, and the map shows more
than one of them.  Everything else derives from this list: the name columns of
names/places.csv (frasch.placelist), the `name:<tag>` tags the injector
writes, Planetiler's `--languages` list (`frasch dialects --tags` in
tiles/build.sh), the search index and the frontend's selector
(web/src/generated/dialects.json).  Adding a dialect is therefore one line in
the registry plus a column in places.csv -- no code change.

| column | meaning |
|---|---|
| `tag`    | BCP 47 language tag, always `frr-x-<subtag>`; no registered subtags for North Frisian dialects exist, so private use it is |
| `column` | the column of names/places.csv that holds this dialect's names |
| `label`  | how the dialect is written in the UI (its German/endonym name) |
| `status` | `living` or `extinct` (extinct dialects still label the map in the local view -- Südergoesharde) |
| `view`   | `yes` = selectable as a map language in the frontend |
| `note`   | free text: which area speaks it |

This is the one reader of the file.  A command reads the registry of its
workspace once (`read`), and whatever needs it takes the `Registry` as a
parameter.

`frasch dialects` hands it to the rest of the build:

    frasch dialects            prints the registry
    frasch dialects --tags     prints `frr-x-mooring,frr-x-wieding,...`
                               (tiles/build.sh feeds it to Planetiler)

and `frasch build dialects` writes the registry the frontend compiles in
(`export_json`: web/src/generated/dialects.json, every column but `note`).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Collection, Iterator, Mapping, Sequence
from typing import Literal, TypedDict

from frasch import cli, files, tables
from frasch.errors import PipelineError, Problem, ValidationError

FIELDS = ["tag", "column", "label", "status", "view", "note"]
EXPORT_FIELDS = FIELDS[:-1]  # what the frontend gets: all but `note`
STATUSES = {"living", "extinct"}
VIEWS = {"yes", "no"}

# The places.csv column that is not a dialect of its own: the form the people
# of the place itself use (frasch.dialects), so no dialect may be called that.
LOCAL_COLUMN = "local"

_TAG = re.compile(r"frr-x-[a-z0-9]{1,8}(-[a-z0-9]{1,8})*$")


class Dialect(TypedDict):
    """One row of the registry: the FIELDS."""

    tag: str
    column: str
    label: str
    status: str
    view: str
    note: str


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
    if not _TAG.fullmatch(row["tag"]):
        # BCP 47 allows at most 8 characters per private-use subtag
        return (
            f"bad tag {row['tag']!r} -- expected frr-x-<subtag>, subtags "
            f"[a-z0-9] and at most 8 characters each"
        )
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
    return Dialect(
        tag=row["tag"],
        column=row["column"],
        label=row["label"],
        status=row["status"],
        view=row["view"],
        note=row["note"],
    )


def read(path: str) -> Registry:
    """The registry, validated; a ValidationError lists every problem."""
    found, problems = rows(path)
    if problems:
        raise ValidationError(problems)
    return Registry(found)


def export_json(reg: Registry, path: str) -> None:
    """Write the registry the frontend compiles in: every column but `note`."""
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
    ap.add_argument("--columns", action="store_true", help="print the places.csv columns instead")
    a = ap.parse_args(argv)
    ws = cli.workspace(a)
    reg = read(ws.dialects)
    if a.tags:
        print(",".join(reg.tags))
    elif a.columns:
        print(",".join(reg.columns))
    else:
        for d in reg:
            print(
                f"{d['tag']:<16} {d['column']:<10} {d['label']:<18} "
                f"{d['status']:<7} view={d['view']:<4} {d['note']}"
            )
    return 0
