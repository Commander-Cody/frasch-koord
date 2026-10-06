"""Reading and writing the hand-edited CSV tables: the name list, the map
curation, the dialect registry and the dialect area list.

They are edited by hand, some in a spreadsheet, and this is the one place
that parses them.  Each file's own module (frasch.placelist,
frasch.curationlist, frasch.registry, frasch.dialects) reads its file through
`read_table` and adds only the rules of its rows."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

from frasch import files
from frasch.errors import Problem

SEMICOLON_SEPARATED = (
    "the cells are separated by `;`, not `,` (a German-locale "
    "spreadsheet export?) -- save it as comma-separated CSV"
)


@dataclass(frozen=True)
class Table:
    """The CSV file at `path` as `read_table` found it: its bytes (`data`),
    the `header`, the `rows` whose cells line up with it as `(line, cells)`
    -- `line` is the line an editor sees the row on --, and the `problems`
    that keep the rest from being read."""

    path: str
    data: bytes
    header: list[str]
    rows: list[tuple[int, list[str]]]
    problems: list[Problem]

    @property
    def digest(self) -> str:
        """What `files.atomic_write` compares against to notice that someone
        else wrote the file in the meantime."""
        return files.digest(self.data)

    def records(self) -> Iterator[tuple[int, dict[str, str]]]:
        """The rows as `(line, {column: cell})`, the cells stripped."""
        for line, cells in self.rows:
            yield line, {k: v.strip() for k, v in zip(self.header, cells, strict=True)}


def by_line(problems: Iterable[Problem]) -> list[Problem]:
    """The problems of one file in the order of its lines."""
    return sorted(problems, key=lambda p: p.line)


def _decode(data: bytes) -> str:
    """The text of a CSV file.  A spreadsheet's "CSV UTF-8" starts it with a
    byte order mark, which would otherwise end up in the first column's
    name."""
    return data.decode("utf-8-sig")


def unreadable_header(fields: Sequence[str]) -> str | None:
    """What makes a CSV header unreadable whatever its columns should be -- a
    `;`-separated export, a column named twice -- or None."""
    if len(fields) == 1 and ";" in fields[0]:
        return SEMICOLON_SEPARATED
    twice = sorted({c for c in fields if fields.count(c) > 1})
    if twice:
        return f"column(s) named twice: {', '.join(twice)}"
    return None


def missing_columns(fields: Sequence[str], required: Sequence[str]) -> str | None:
    """The `required` columns a CSV header lacks, as a problem, or None."""
    missing = [c for c in required if c not in fields]
    if missing:
        return f"missing column(s) {', '.join(missing)}"
    return None


def _cell_count_problem(cells: Sequence[str], header: Sequence[str]) -> str | None:
    """A row whose cells do not line up with the header's columns: a comma
    too many or too few, and every cell after it is in the wrong column."""
    if len(cells) != len(header):
        return f"{len(cells)} cells, the header has {len(header)} (a comma too many or too few?)"
    return None


def read_table(path: str, required: Sequence[str] = ()) -> Table:
    """Read one of the hand-edited CSV files, which must have the `required`
    columns.  Without a readable header it has no rows, only the problem."""
    with open(path, "rb") as fh:
        data = fh.read()
    reader = csv.reader(io.StringIO(_decode(data), newline=""))
    header = next(reader, [])
    if what := unreadable_header(header) or missing_columns(header, required):
        return Table(path, data, header, [], [Problem(path, 1, what)])
    rows: list[tuple[int, list[str]]] = []
    problems: list[Problem] = []
    for cells in reader:
        if not cells:
            continue  # a blank line
        if what := _cell_count_problem(cells, header):
            problems.append(Problem(path, reader.line_num, what))
        else:
            rows.append((reader.line_num, cells))
    return Table(path, data, header, rows, problems)


def write_rows(
    fields: Sequence[str], rows: Iterable[Mapping[str, str]], *, header: bool = True
) -> bytes:
    """A CSV file of `rows` under the header `fields`: of each row the cells
    of those columns, empty where it has none.  Without `header` only the
    rows, to append to a file that has one."""
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    if header:
        writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fields})
    return buf.getvalue().encode("utf-8")
