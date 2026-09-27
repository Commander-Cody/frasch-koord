#!/usr/bin/env python3
"""Check the hand-edited name files for damage -- all of it, with line numbers.

    .venv/bin/python names/check.py            # exit 1 if anything is wrong
    .venv/bin/python names/check.py --fix      # first give new rows an id

`placelist.read` stops at the first problem it cannot live with and
silently accepts some it can (a row with a comma too few is padded, and its
names shift one column to the left).  This reads the files as raw CSV
instead and lists every problem it finds, so that one run shows everything a
spreadsheet export or a hand edit broke.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass

import dialects
import placelist


# the tile attribute a curation row may set to point a label at a row
REF_TAG = "frasch:ref"

# the name columns: `;`-separated variants with `(…)` remarks, the
# conventions names/README.md sets for every name cell
VARIANT_COLUMNS = placelist.NAME_COLUMNS + ["de", "da"]


@dataclass(frozen=True)
class Problem:
    path: str
    line: int
    message: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.message}"


# a variant: the name, then optional remarks, each after one space
_VARIANT = re.compile(r"(?P<name>[^()]*?)(?: \([^()]*\))*")
# a `;` with anything but no space before it and exactly one after it
_BAD_SEPARATOR = re.compile(r"\s;|;(?! \S)")


def cell_problem(cell: str) -> str | None:
    """What is wrong with the syntax of one name cell (see the conventions in
    names/README.md), or None.  `placelist.parts` reads a damaged cell
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
    for variant in placelist.split_variants(cell):
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
    names = [name for name, _ in placelist.parts(cell)]
    twice = [name for i, name in enumerate(names) if name in names[:i]]
    if twice:
        return f"{', '.join(twice)} twice"
    return None


def _rows(path):
    """-> (header, [(line, cells), ...]) of a CSV file.  Blank lines are left
    out, as the readers skip them, but still counted: `line` is the line an
    editor sees the row on, as in placelist.read's `_line`."""
    with placelist.open_csv(path) as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        rows = [(reader.line_num, cells) for cells in reader if cells]
    return header, rows


def row_ids(path) -> set[str]:
    """The `id` cells of the name list, whatever else is wrong with it."""
    header, rows = _rows(path)
    if "id" not in header:
        return set()
    column = header.index("id")
    return {cells[column].strip() for _, cells in rows if len(cells) > column}


def check_curation(path, ids) -> tuple[list[Problem], set[str]]:
    """-> (the problems in names/curation.csv, the slugs of the local
    references it positions).  The rules are those the tile build enforces
    (`placelist.curation_rows`), plus: a `frasch:ref` set by hand must be the
    id of a row of the name list (`ids`) -- it is how the place card finds
    the row a label belongs to."""
    entries, problems = placelist.curation_rows(path)
    for e in entries:
        ref = e["tags"].get(REF_TAG)
        if ref is not None and ref not in ids:
            problems.append((e["line"], f"{REF_TAG}={ref} names no row of the "
                                        f"name list (it takes a row's `id`)"))
    positioned = {e["local"] for e in entries if e["local"]}
    problems.sort(key=lambda p: p[0])
    return [Problem(path, n, what) for n, what in problems], positioned


def check_dialects(path) -> list[Problem]:
    """The problems in the dialect registry, names/dialects.csv."""
    header, rows = _rows(path)
    if (what := placelist.csv_header_problem(header, dialects.FIELDS)):
        return [Problem(path, 1, what)]
    problems, seen_tags, seen_cols = [], set(), set()
    for n, cells in rows:
        if (what := placelist.cell_count_problem(cells, header)):
            problems.append(Problem(path, n, what))
            continue
        row = {k: v.strip() for k, v in zip(header, cells, strict=True)}
        if not row["tag"]:
            continue                                  # blank spacer line
        what = dialects.row_problem(row, seen_tags, seen_cols)
        if what:
            problems.append(Problem(path, n, what))
        seen_tags.add(row["tag"])
        seen_cols.add(row["column"])
    return problems


def check_places(path, curation, positioned) -> list[Problem]:
    """The problems in the name list; `positioned` are the local references
    `curation` has a position for."""
    header, rows = _rows(path)
    if (what := placelist.header_problem(header)):
        return [Problem(path, 1, what)]   # without its columns no row can be read
    problems = []
    claimed = {}              # `way/1` or `Q1` -> line of the first row
    ids = {}                  # id -> line of the first row
    for n, cells in rows:
        def problem(message, n=n):
            problems.append(Problem(path, n, message))

        if (what := placelist.cell_count_problem(cells, header)):
            problem(what)   # its columns cannot be trusted, nothing else is
            continue
        row = {k: v.strip() for k, v in zip(header, cells, strict=True)}
        for what in placelist.row_problems(row):
            problem(what)
        if (what := placelist.id_problem(row, ids)):
            problem(what)
        ids.setdefault(row["id"], n)
        for column in VARIANT_COLUMNS:
            if row[column] and (what := cell_problem(row[column])):
                problem(f"{column}: {what}: {row[column]!r}")
        if _BAD_SEPARATOR.search(row["osm"]):
            problem(f"osm: references are separated by `; `: {row['osm']!r}")
        try:
            slug = placelist.local_ref(row["osm"])
            refs = placelist.claimed_refs(row)
        except placelist.Invalid:
            slug, refs = None, []                 # row_problems reported it
        if slug and slug not in positioned:
            problem(f"local/{slug} has no row with `lat`/`lon` in {curation}")
        keys = [placelist.format_osm([ref]) for ref in refs]
        if row["wikidata"] and row["status"] != "skip":
            keys.append(row["wikidata"])
        for key in keys:
            if key in claimed:
                problem(f"{key} is already claimed by line {claimed[key]} "
                        f"-- only one name can go on the map")
            claimed.setdefault(key, n)
    return problems


def check(places=placelist.DEFAULT_PATH,
          curation=placelist.CURATION_PATH,
          registry=placelist.DIALECTS_PATH) -> list[Problem]:
    """Every problem in the name list `places`, the map curation `curation`
    and the dialect registry `registry`, file by file, in file order."""
    places, curation, registry = map(os.fspath, (places, curation, registry))
    curation_problems, positioned = check_curation(curation, row_ids(places))
    return (check_places(places, curation, positioned)
            + curation_problems + check_dialects(registry))


def markdown(problems) -> str:
    """The result as a Markdown table, for the summary page of a CI run."""
    out = ["### names/check.py", ""]
    if not problems:
        return "\n".join(out + ["no problems", ""]) + "\n"
    out += [f"{len(problems)} problem(s):", "", "| where | problem |", "|---|---|"]
    for p in problems:
        path = os.path.relpath(p.path)
        if path.startswith(".."):             # not under the working directory
            path = os.path.abspath(p.path)
        message = p.message.replace("|", "\\|")
        out.append(f"| `{path}:{p.line}` | {message} |")
    return "\n".join(out + [""]) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--curation", default=placelist.CURATION_PATH)
    ap.add_argument("--dialects", default=placelist.DIALECTS_PATH)
    ap.add_argument("--fix", action="store_true",
                    help="first give every row of the name list without an "
                         "`id` one (placelist.fill_ids)")
    ap.add_argument("--summary", metavar="FILE",
                    help="also append the result as Markdown to FILE "
                         "(CI passes $GITHUB_STEP_SUMMARY)")
    a = ap.parse_args(argv)
    if a.fix:
        with placelist.lock(a.names):
            given = placelist.fill_ids(a.names)
        print(f"gave {given} row(s) an id", file=sys.stderr)
    problems = check(a.names, a.curation, a.dialects)
    for p in problems:
        print(p)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as fh:
            fh.write(markdown(problems))
    print(f"{len(problems)} problem(s)" if problems else "no problems",
          file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
