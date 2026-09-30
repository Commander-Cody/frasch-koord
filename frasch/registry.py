"""The dialect registry, names/dialects.csv: the single list of the dialects
the project knows.

North Frisian is not one language variety but a dozen, and the map shows more
than one of them.  Everything else derives from this list: the name columns of
names/places.csv (frasch.placelist), the `name:<tag>` tags the injector
writes, Planetiler's `--languages` list (`dialects.py --tags` in
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

This is the one reader of the file.  Whatever needs the registry takes a
`Registry` as a parameter; `default()` reads names/dialects.csv the first
time it is asked for, never at import.
"""
from __future__ import annotations

import csv
import functools
import os
import re
from collections.abc import Collection, Iterator, Mapping
from typing import Literal, TypedDict

from frasch import files, paths
from frasch.errors import PipelineError, ValidationError

FIELDS = ["tag", "column", "label", "status", "view", "note"]
EXPORT_FIELDS = FIELDS[:-1]            # what the frontend gets: all but `note`
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

    def label_of(self, tag: str) -> str:
        """The dialect's UI label; the tag itself for one the registry does
        not know."""
        return next((d["label"] for d in self.dialects if d["tag"] == tag), tag)

    def _find(self, field: Literal["tag", "column"], value: str) -> Dialect:
        for d in self.dialects:
            if d[field] == value:
                return d
        raise ValidationError(f"unknown dialect {field} {value!r} "
                              f"(not in the dialect registry)")


def row_problem(row: Mapping[str, str], seen_tags: Collection[str] = (),
                seen_cols: Collection[str] = ()) -> str | None:
    """What is wrong with one registry row (`seen_*`: the tags and columns of
    the rows above it), or None."""
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


def rows(path: str) -> tuple[list[Dialect], list[tuple[int, str]]]:
    """-> (dialects, problems): the rows of the registry that follow its
    rules, and `(line, reason)` for every one that does not.  A registry
    without a dialect is one problem."""
    if not os.path.exists(path):
        raise PipelineError(f"dialect registry not found: {path}")
    with files.open_csv(path) as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        if (what := files.csv_header_problem(header, FIELDS)):
            return [], [(1, what)]
        found: list[Dialect] = []
        problems: list[tuple[int, str]] = []
        seen_tags: set[str] = set()
        seen_cols: set[str] = set()
        for cells in reader:
            n = reader.line_num
            if not cells:
                continue
            if (what := files.cell_count_problem(cells, header)):
                problems.append((n, what))
                continue
            row = {k: v.strip() for k, v in zip(header, cells, strict=True)}
            if not row["tag"]:
                continue                       # blank spacer line
            if (what := row_problem(row, seen_tags, seen_cols)):
                problems.append((n, what))
            else:
                found.append(_dialect(row))
            seen_tags.add(row["tag"])
            seen_cols.add(row["column"])
    if not found and not problems:
        problems.append((1, "no dialects"))
    return found, problems


def _dialect(row: Mapping[str, str]) -> Dialect:
    return Dialect(tag=row["tag"], column=row["column"], label=row["label"],
                   status=row["status"], view=row["view"], note=row["note"])


def read(path: str = paths.DIALECTS) -> Registry:
    """The registry, validated; a ValidationError lists every problem."""
    found, problems = rows(path)
    if problems:
        raise ValidationError([f"{path}:{n}: {what}" for n, what in problems])
    return Registry(found)


@functools.cache
def default() -> Registry:
    """names/dialects.csv, read on first use."""
    return read(paths.DIALECTS)
