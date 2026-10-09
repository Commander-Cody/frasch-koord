"""Check the hand-edited name files for damage -- all of it, with line numbers.

    frasch check-inputs            # exit 1 if anything is wrong
    frasch check-inputs --fix      # first give new rows an id

The commands refuse a file that breaks the rules they cannot live with, each
its own file and only when it gets to it.  This reads all four with their
own readers and lists every problem they find, plus the stricter rules of the
name cells, so that one run shows everything a spreadsheet export or a hand
edit broke.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Container, Sequence
from typing import NamedTuple

from frasch import (
    cli,
    curationlist,
    dialect_areas,
    dialects,
    errors,
    files,
    namecell,
    placelist,
    placenames,
    tables,
)
from frasch.dialects import Registry
from frasch.errors import Problem
from frasch.paths import Workspace
from frasch.placelist import PlaceRow
from frasch.tables import Table


# a variant: the name, then optional remarks, each after one space
_VARIANT = re.compile(r"(?P<name>[^()]*?)(?: \([^()]*\))*")
# a `;` with anything but no space before it and exactly one after it
_BAD_SEPARATOR = re.compile(r"\s;|;(?! \S)")


def cell_problem(cell: str) -> str | None:
    """What is wrong with the syntax of one name cell (see the conventions in
    names/README.md), or None.  `namecell.parts` reads a damaged cell
    anyway, just differently from what the editor meant."""
    depth = 0
    for ch in cell:
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if depth not in (0, 1):
            return "unbalanced or nested brackets"
    if depth:
        return "unbalanced brackets"
    if _BAD_SEPARATOR.search(cell):
        return "variants are separated by `; ` (no space before, one after)"
    for variant in namecell.split_variants(cell):
        m = _VARIANT.fullmatch(variant.strip())
        if not m:
            return f"text after a remark in {variant.strip()!r}"
        name = m.group("name")
        if not name:
            return "an empty variant"
        if name != name.strip() or "  " in name:
            return f"stray spaces in {name!r}"
        if "?" in name:
            return f"`?` in {name!r} -- say `uncertain` in `note` instead"
    names = [name for name, _ in namecell.parts(cell)]
    twice = [name for i, name in enumerate(names) if name in names[:i]]
    if twice:
        return f"{', '.join(twice)} twice"
    return None


def check_curation(path: str, ids: Container[str]) -> tuple[list[Problem], set[str]]:
    """-> (the problems in names/curation.csv, the slugs of the local
    references it positions).  The rules are those the tile build enforces
    (`curationlist.rows`), plus: a `frasch:ref` set by hand must be the
    id of a row of the name list (`ids`) -- it is how the place card finds
    the row a label belongs to."""
    entries, problems = curationlist.rows(path)
    for e in entries:
        ref = e["tags"].get(placenames.REF_KEY)
        if ref is not None and ref not in ids:
            problems.append(
                Problem(
                    path,
                    e["line"],
                    f"{placenames.REF_KEY}={ref} names no row of the "
                    f"name list (it takes a row's `id`)",
                )
            )
    positioned = {e["local"] for e in entries if e["local"]}
    return tables.by_line(problems), positioned


def check_dialects(path: str) -> tuple[Registry | None, list[Problem]]:
    """-> (the sound rows of the dialect registry, names/dialects.csv -- None
    when there are none --, the problems in it)."""
    found, problems = dialects.rows(path)
    return (Registry(found) if found else None, problems)


def check_dialect_areas(path: str, reg: Registry) -> list[Problem]:
    """The problems in the dialect area list, names/dialect_areas.csv, by the
    rules the area build enforces (`dialect_areas.area_rows`)."""
    _rows, problems = dialect_areas.area_rows(path, reg)
    return problems


def check_places(
    names: Table, curation: str, positioned: Container[str], reg: Registry
) -> list[Problem]:
    """The problems in the name list (`names`), whose columns `reg` says:
    those `placelist.read` refuses it for, the stricter rules of its name
    cells, and a local reference `curation` has no position for
    (`positioned`: those it has one for)."""
    rows, problems = placelist.rows(names, reg)
    for row in rows:
        whats = _cell_problems(row, reg) + _position_problems(row, curation, positioned)
        problems += [Problem(names.path, row.line, what) for what in whats]
    return tables.by_line(problems)


def _cell_problems(row: PlaceRow, reg: Registry) -> list[str]:
    """What is wrong with the syntax of a row's name cells and of its `osm`
    cell."""
    found = [
        f"{column}: {what}: {row[column]!r}"
        for column in variant_columns(reg)
        if row[column] and (what := cell_problem(row[column]))
    ]
    if _BAD_SEPARATOR.search(row["osm"]):
        found.append(f"osm: references are separated by `; `: {row['osm']!r}")
    return found


def _position_problems(row: PlaceRow, curation: str, positioned: Container[str]) -> list[str]:
    """A row's local reference that `curation` has no position for."""
    try:
        slug = row.local
    except errors.Invalid:
        return []  # `placelist.rows` reported it
    if slug and slug not in positioned:
        return [f"local/{slug} has no row with `lat`/`lon` in {curation}"]
    return []


def variant_columns(reg: Registry) -> list[str]:
    """The name columns: `;`-separated variants with `(…)` remarks, the
    conventions names/README.md sets for every name cell."""
    return placelist.name_columns(reg) + ["de", "da"]


def check(ws: Workspace) -> list[Problem]:
    """Every problem in the name list, the map curation, the dialect registry
    and the dialect area list of the workspace, file by file, in file order.
    The name list is checked against the sound rows of the registry (not at
    all when it has none, the registry's problems say why), the area list
    only against a sound registry."""
    reg, registry_problems = check_dialects(ws.dialects)
    return _check(ws, reg, registry_problems)


def _check(ws: Workspace, reg: Registry | None, registry_problems: list[Problem]) -> list[Problem]:
    """`check`, with the registry as `check_dialects` read it."""
    names = placelist.table(ws.names)
    curation_problems, positioned = check_curation(ws.curation, placelist.ids(names))
    place_problems = check_places(names, ws.curation, positioned, reg) if reg else []
    area_problems = check_dialect_areas(ws.area_list, reg) if reg and not registry_problems else []
    return place_problems + curation_problems + registry_problems + area_problems


def fill_ids(ws: Workspace, reg: Registry) -> None:
    """Give every row of the name list without an `id` one, and say how many
    got one -- or why none did: the report `check` gives lists that problem
    and every other one."""
    try:
        with files.lock(ws.lock):
            print(f"gave {placelist.fill_ids(ws.names, reg)} row(s) an id", file=sys.stderr)
    except errors.PipelineError as exc:
        print(f"no id given: {exc}", file=sys.stderr)


def markdown(problems: Sequence[Problem]) -> str:
    """The result as a Markdown table, for the summary page of a CI run."""
    out = ["### frasch check-inputs", ""]
    if not problems:
        return "\n".join(out + ["no problems", ""]) + "\n"
    out += [f"{len(problems)} problem(s):", "", "| where | problem |", "|---|---|"]
    for p in problems:
        path = os.path.relpath(p.path)
        if path.startswith(".."):  # not under the working directory
            path = os.path.abspath(p.path)
        message = p.message.replace("|", "\\|")
        out.append(f"| `{path}:{p.line}` | {message} |")
    return "\n".join(out + [""]) + "\n"


class Checked(NamedTuple):
    """What `run` found: the problems, and the dialect registry as it read
    it -- the sound rows, so the whole of it when there are no problems."""

    problems: list[Problem]
    registry: Registry | None


def run(ws: Workspace, *, fix: bool = False, summary: str | None = None) -> Checked:
    """Check the workspace's hand-edited files and print what is wrong with
    them.  `fix`: first give the name list's new rows an id.  `summary`: a
    file to append the result to as Markdown."""
    reg, registry_problems = check_dialects(ws.dialects)
    if fix and reg and not registry_problems:
        fill_ids(ws, reg)
    elif fix:
        print(f"no id given: {ws.dialects} has problems", file=sys.stderr)
    problems = _check(ws, reg, registry_problems)
    for p in problems:
        print(p)
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(markdown(problems))
    print(f"{len(problems)} problem(s)" if problems else "no problems", file=sys.stderr)
    return Checked(problems, reg)


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("check-inputs", __doc__.split("\n\n")[0])
    cli.add_workspace_options(ap, "names", "curation", "dialects", "area_list", "work")
    ap.add_argument(
        "--fix",
        action="store_true",
        help="first give every row of the name list without an `id` one (placelist.fill_ids)",
    )
    ap.add_argument(
        "--summary",
        metavar="FILE",
        help="also append the result as Markdown to FILE (CI passes $GITHUB_STEP_SUMMARY)",
    )
    a = ap.parse_args(argv)
    return 1 if run(cli.workspace(a), fix=a.fix, summary=a.summary).problems else 0
