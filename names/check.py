#!/usr/bin/env python3
"""Check the hand-edited name files for damage -- all of it, with line numbers.

    .venv/bin/python names/check.py            # exit 1 if anything is wrong

`placelist.read` stops at the first problem it cannot live with and
silently accepts some it can (a row with a comma too few is padded, and its
names shift one column to the left).  This reads the files as raw CSV
instead and lists every problem it finds, so that one run shows everything a
spreadsheet export or a hand edit broke.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
from dataclasses import dataclass

import dialects
import placelist


# the columns following the name-cell conventions (`;` variants, remarks)
NAME_CELLS = placelist.NAME_COLUMNS + ["de", "hint", "da"]


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
    """-> (header, csv.reader over the rest) of a CSV file, as the pipeline
    reads it (a spreadsheet's byte order mark does no harm)."""
    with open(path, "rb") as fh:
        reader = csv.reader(io.StringIO(placelist.decode(fh.read()), newline=""))
    return next(reader, []), reader


def _header_problem(path, header, required) -> Problem | None:
    """A header that no row of the file can be read with."""
    if placelist.semicolon_separated(header):
        return Problem(path, 1, placelist.SEMICOLON_SEPARATED)
    twice = sorted({c for c in header if header.count(c) > 1})
    if twice:
        return Problem(path, 1, f"column(s) named twice: {', '.join(twice)}")
    missing = [c for c in required if c not in header]
    if missing:
        return Problem(path, 1, f"missing column(s) {', '.join(missing)}")
    return None


def _reason(exc: SystemExit) -> str:
    """The message of one of placelist's errors, without its empty `where`."""
    return str(exc).removeprefix(": ")


def check_curation(path) -> tuple[list[Problem], set[str]]:
    """-> (the problems in names/curation.csv, the slugs of the local
    references it positions).  The rules are those tiles/inject_names.py's
    `load_curation` enforces when it builds the tiles."""
    header, reader = _rows(path)
    if (bad := _header_problem(path, header, ["osm"])):
        return [bad], set()
    problems, positioned = [], set()
    for n, cells in enumerate(reader, start=2):
        def problem(message, n=n):
            problems.append(Problem(path, n, message))

        row = {k: v.strip() for k, v in zip(header, cells, strict=False)}
        try:
            refs = placelist.parse_osm(row.get("osm"), "osm")
        except SystemExit as exc:
            problem(str(exc))
            continue
        try:
            pos = placelist.parse_point(row.get("lat"), row.get("lon"))
        except SystemExit as exc:
            problem(_reason(exc))
            continue
        if not refs:
            continue                              # blank spacer line
        local = refs[0][1] if refs[0][0] == placelist.LOCAL_TYPE else None
        if pos and not local:
            problem(f"lat/lon only go with a local reference (local/<slug>), "
                    f"not with {row['osm']!r}")
        if local and not pos:
            problem(f"local/{local} needs `lat` and `lon`")
        elif local and local in positioned:
            problem(f"second row for local/{local}")
        elif local:
            positioned.add(local)
        for pair in (row.get("set_tags") or "").split(";"):
            key, eq, _ = pair.partition("=")
            if pair.strip() and not (eq and key.strip()):
                problem(f"set_tags entry {pair.strip()!r} is not key=value")
        for col in ("minzoom", "maxzoom"):
            z = row.get(col) or ""
            if z and not z.lstrip("-").isdigit():
                problem(f"{col} {z!r} is not an integer")
        km2 = row.get("polygon_km2") or ""
        if km2:
            try:
                if float(km2) <= 0:
                    raise ValueError
            except ValueError:
                problem(f"polygon_km2 {km2!r} is not a positive number")
            if len(refs) != 1 or refs[0][0] not in ("n", placelist.LOCAL_TYPE):
                problem("polygon_km2 needs exactly one node (or local reference) "
                        "in `osm`")
    return problems, positioned


def check_dialects(path) -> list[Problem]:
    """The problems in the dialect registry, names/dialects.csv."""
    header, reader = _rows(path)
    if (bad := _header_problem(path, header, dialects.FIELDS)):
        return [bad]
    problems, seen_tags, seen_cols = [], set(), set()
    for n, cells in enumerate(reader, start=2):
        row = dict.fromkeys(dialects.FIELDS, "") | {
            k: v.strip() for k, v in zip(header, cells, strict=False)}
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
    header, reader = _rows(path)
    if (bad := _header_problem(path, header, placelist.COLUMNS)):
        return [bad]                      # without its columns no row can be read
    problems = []
    claimed = {}              # `way/1` or `Q1` -> line of the first row
    # numbered like placelist.read's `_line`, which REPORT.md and curate use
    for n, cells in enumerate(reader, start=2):
        def problem(message, n=n):
            problems.append(Problem(path, n, message))

        if len(cells) != len(header):
            # the columns of such a row cannot be trusted, so nothing else
            # in it is worth checking
            problem(f"{len(cells)} cells, the header has {len(header)} "
                    f"(a comma too many or too few?)")
            continue
        row = {k: v.strip() for k, v in zip(header, cells, strict=True)}
        if row["kind"] not in placelist.KINDS:
            problem(f"unknown kind {row['kind']!r}")
        if row["status"] not in placelist.STATUSES:
            problem(f"unknown status {row['status']!r} (auto / ok / skip / empty)")
        for column in NAME_CELLS:
            if row[column] and (what := cell_problem(row[column])):
                problem(f"{column}: {what}: {row[column]!r}")
        try:
            refs = placelist.parse_osm(row["osm"], "osm")
        except SystemExit as exc:
            problem(str(exc))
            refs = []
        if _BAD_SEPARATOR.search(row["osm"]):
            problem(f"osm: references are separated by `; `: {row['osm']!r}")
        slug = refs[0][1] if refs and refs[0][0] == placelist.LOCAL_TYPE else None
        if slug and slug not in positioned:
            problem(f"local/{slug} has no row with `lat`/`lon` in {curation}")
        if slug and row["wikidata"]:
            problem("a local reference is for a place OSM does not have -- "
                    "it cannot have a wikidata id")
        if row["wikidata"] and not re.fullmatch(r"Q\d+", row["wikidata"]):
            problem(f"bad wikidata id {row['wikidata']!r}")
        if row["status"] != "skip":     # a skipped row puts nothing on the map
            keys = [placelist.format_osm([ref]) for ref in refs]
            for key in keys + ([row["wikidata"]] if row["wikidata"] else []):
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
    curation_problems, positioned = check_curation(curation)
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
        where = f"{path}:{p.line}"
        out.append(f"| `{where}` | {p.message.replace('|', chr(92) + '|')} |")
    return "\n".join(out + [""]) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--curation", default=placelist.CURATION_PATH)
    ap.add_argument("--dialects", default=placelist.DIALECTS_PATH)
    ap.add_argument("--summary", metavar="FILE",
                    help="also append the result as Markdown to FILE "
                         "(CI passes $GITHUB_STEP_SUMMARY)")
    a = ap.parse_args(argv)
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
