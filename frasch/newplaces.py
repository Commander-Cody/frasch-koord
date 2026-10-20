"""The places the curation view created (#113): what a `create` of the patch
(frasch.patch) makes of the name list.

Until `frasch curate apply` the place has a provisional key, `new:<random>`,
which can never be a row id; its decision, an entry of its own, goes by the
same key.  Apply checks the new row by the rules `frasch check-inputs` has
for one row, gives it its id the way `check-inputs --fix` does
(`placelist.new_id`), and inserts it after the last row of its kind.

Nothing here writes: apply (frasch.curate) does.
"""

from __future__ import annotations

import functools
import re

from frasch import check_inputs, patch, placelist, tables
from frasch.decisions import Refused
from frasch.patch import PatchEntry
from frasch.placelist import PlaceList, PlaceRow


@functools.cache
def _provisional_key() -> re.Pattern[str]:
    """The shape of a provisional key, as names/curate-patch.schema.json says it."""
    return re.compile(patch.patch_schema()["$defs"]["provisional_key"]["pattern"])


def is_provisional(key: str) -> bool:
    """Whether `key` is the provisional key of a created place, not a row id."""
    return _provisional_key().search(key) is not None


def new_row(entry: PatchEntry, names: PlaceList) -> PlaceRow:
    """The row a `create` entry makes for the list `names`, with its id --
    or Refused, saying what breaks the rules of a row."""
    cells = _cells(entry, names)
    problems = placelist.row_problems(cells) + check_inputs.cell_problems(cells, names.reg)
    if problems:
        raise Refused("; ".join(problems))
    cells["id"] = placelist.new_id(cells, {r["id"] for r in names.rows}, names.reg)
    return PlaceRow(cells, 0)  # its line is where `insert` puts it


def _cells(entry: PatchEntry, names: PlaceList) -> dict[str, str]:
    """The cells of the new row: its kind, names and note, stripped, the rest
    empty."""
    given = entry.get("names", {})
    if unknown := sorted(set(given) - set(check_inputs.variant_columns(names.reg))):
        raise Refused(f"no name column {', '.join(unknown)} in {names.path}")
    cells = dict.fromkeys(names.fields, "") | {c: cell.strip() for c, cell in given.items()}
    if not any(cells[c] for c in given):
        raise Refused("a new place needs a name")
    cells["kind"] = entry["kind"]
    cells["note"] = entry.get("note", "").strip()
    return cells


def insert(row: PlaceRow, names: PlaceList) -> None:
    """Put the new `row` into the list after the last row of its kind, or at
    the end; it and the rows after it get the lines they will be written at."""
    rows = names.rows
    after = max((n for n, r in enumerate(rows) if r["kind"] == row["kind"]), default=len(rows) - 1)
    row.line = rows[after].line + _height(rows[after], names) if rows else 2
    for later in rows[after + 1 :]:
        later.line += _height(row, names)
    rows.insert(after + 1, row)


def _height(row: PlaceRow, names: PlaceList) -> int:
    """How many lines of the file the row takes: one, unless a cell holds a
    line break."""
    return tables.write_rows(names.fields, [row], header=False).count(b"\n")
