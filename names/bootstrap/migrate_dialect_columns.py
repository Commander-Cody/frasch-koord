#!/usr/bin/env python3
"""One-off migration: dissolve places.csv's `other` column into one column
per dialect (2026-09-16).  Kept next to import_sheet.py as history.

Until now every North Frisian name that was not Mooring lived in a single
`other` column, its dialect written as a bracket remark: `Fuan (Sölring)`,
`Bakensweerf (Hålifrasch)`, `Gratdün (öömring)`.  The map only ever showed
Mooring, so that was enough.  With one column per dialect (names/dialects.csv)
those remarks become columns, and the older Mooring spellings in `older` turn
out to hold the same thing: `Kläsbel (Kårhiirdinge)` is not an older Mooring
name, it is the Karrharder name.

What it does, row by row:

* every variant of `other` and of `older` is looked at with its bracket remark
  (case-insensitive, `?` stripped).  A remark that names a dialect moves the
  variant into that dialect's column; the remark itself is dropped when it
  says nothing more than the target column already does.
* `Foortuftinge` / `ååstermooring` are not dialects of their own but the local
  speech of one village -- those variants move to the `local` column and keep
  their remark, which is what the frontend shows as the variety.
* the Goesharde remarks (`Gooshiirdinge`, ...) do not say WHICH Goesharde, so
  they can only be sorted with the per-row table GOESHARDE_BY_DE below; while
  it is empty those variants stay in `older` and are reported.
* a variant of `other` with no remark at all cannot be sorted either: it moves
  to `note` (`unsorted other-dialect name: ...`) unless OTHER_OVERRIDES says
  where it belongs.  Nothing is ever silently dropped.
* a `?` in a remark adds `uncertain` to `note` (places.csv keeps no `?` in
  names).

Running it twice is a no-op: the second run finds no `other` column and no
movable remarks in `older`, and cells that did not change keep their exact
text.

Usage:  .venv/bin/python names/bootstrap/migrate_dialect_columns.py
                        [--names names/places.csv] [--dry-run] [--out FILE]
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES_DIR = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, NAMES_DIR)
import placelist  # noqa: E402
import dialects  # noqa: E402

LOCAL = dialects.LOCAL_COLUMN
NOTE = "__note__"          # pseudo target: the variant goes into `note`

# A bracket remark (lowercased, `?` and spaces stripped) -> target column.
DIALECT_BY_REMARK = {
    "halifreesk": "hallig",
    "hålifrasch": "hallig",
    "halifrasch": "hallig",
    "sölring": "solring",
    "salring": "solring",
    "halunder": "halunder",
    "öömring": "oomrang",
    "öömrang": "oomrang",
    "wisinge": "wieding",
    "kårhiirdinge": "karrhard",
    "kårhiirder": "karrhard",
    # not dialects but the speech of a single village -> `local`, remark kept
    "foortuftinge": LOCAL,
    "ååstermooring": LOCAL,
}

# "Goesharde" alone does not say which of the three Goesharden.
GOES_REMARKS = {"gooshiirdinge", "gooshiirder", "goeshiirdinge"}

# Which Goesharde a row belongs to, keyed by the row's primary German name.
# Filled in by the list owner; every unlisted row is reported and its variant
# stays in `older`.  Targets: nordgoes / midgoes / suedgoes.
GOESHARDE_BY_DE: dict[str, str] = {
    # which Goesharde the place lies in (researched 2026-09-16; Wallsbüll lies
    # in Kreis Schleswig-Flensburg and Lundenberg in the old Lundenbergharde,
    # so their Goesharder names stay in `older` for the owner to decide)
    "Mirebüll": "nordgoes",
    "Sterdebüll": "nordgoes",
    "Joldelund": "nordgoes",
    "Riddorf": "nordgoes",
    "Bohnenland": "suedgoes",
    "Hattstedt": "suedgoes",
    "Hattstedtfeld": "suedgoes",
}

# Variants of `other` that carry no remark.  Either a target column for every
# unremarked variant of that row ("Bandixwarf": "hallig"), or one target per
# variant.  A per-variant entry also overrules a remark -- `sweerw` is a
# common noun ("warft"), not a name of Hilligenley.
OTHER_OVERRIDES: dict[str, object] = {
    "Bandixwarf": "hallig",
    "Wyk": {"bi a Wik": "fering"},
    "Hilligenley": {"sweerw": NOTE},
}


def norm_remark(text: str) -> str:
    return text.replace("?", "").strip().casefold()


def distribute_remarks(entries):
    """A remark may hold several dialects for the variants before it:
    `Huađer; Huuger (Sölring; Wisinge)` means Huađer is Sölring and Huuger
    Wiedingharder.  Spread such a remark part-wise over the variants it
    trails, in order."""
    out = [[name, remark] for name, remark in entries]
    for i, (_, remark) in enumerate(entries):
        pieces = [p.strip() for p in remark.split(";") if p.strip()]
        if len(pieces) < 2:
            continue
        start = i - len(pieces) + 1
        if start < 0:
            continue                    # more parts than variants -- leave alone
        for j, piece in enumerate(pieces):
            out[start + j][1] = piece
    return [(name, remark) for name, remark in out]


def classify(remark: str, de: str):
    """-> (target column | NOTE | None, remaining remark, uncertain)

    `None` means "no dialect said" -- the caller decides (a variant of `older`
    stays there, one of `other` cannot be sorted)."""
    uncertain = "?" in remark
    pieces = [p for p in remark.split(",")]
    for i, piece in enumerate(pieces):
        key = norm_remark(piece)
        if key in DIALECT_BY_REMARK:
            col = DIALECT_BY_REMARK[key]
            if col == LOCAL:
                return col, remark.replace("?", "").strip(), uncertain  # keep the variety
            rest = [p.strip() for j, p in enumerate(pieces) if j != i and p.strip()]
            return col, ", ".join(rest).replace("?", "").strip(), uncertain
        if key in GOES_REMARKS:
            col = GOESHARDE_BY_DE.get(de, "")
            if not col:
                return None, remark, uncertain             # unsorted, reported
            rest = [p.strip() for j, p in enumerate(pieces) if j != i and p.strip()]
            return col, ", ".join(rest).replace("?", "").strip(), uncertain
    return None, remark, uncertain


def render(entries) -> str:
    return "; ".join(f"{n} ({r})" if r else n for n, r in entries)


def add_note(row, text):
    note = (row.get("note") or "").strip()
    if text in note:
        return
    row["note"] = f"{note}; {text}" if note else text


def migrate(rows, report):
    """Rewrite the rows in place; append report lines.  -> counters"""
    counts = {"moved": 0, "unsorted": 0, "goesharde": 0}
    for row in rows:
        de = placelist.primary(row.get("de"))
        line = row["_line"]
        for source in ("other", "older"):
            cell = (row.get(source) or "").strip()
            if not cell:
                continue
            entries = distribute_remarks(placelist.parts(cell))
            overrides = OTHER_OVERRIDES.get(de) if source == "other" else None
            keep, changed = [], False
            for name, remark in entries:
                target, rest, uncertain = None, remark, False
                if isinstance(overrides, dict) and name in overrides:
                    target, rest = overrides[name], ""
                elif isinstance(overrides, str) and not remark:
                    target, rest = overrides, ""
                else:
                    target, rest, uncertain = classify(remark, de)
                    key = norm_remark(remark.split(",")[0]) if remark else ""
                    if target is None and key in GOES_REMARKS:
                        report.append(f"{line} | {de or '-'} | {source} | ? | "
                                      f"{render([(name, remark)])} "
                                      f"(no GOESHARDE_BY_DE entry)")
                        counts["goesharde"] += 1
                if target is None and source == "other":
                    # nothing says which dialect this is -- park it in `note`
                    target = NOTE
                if target is None:
                    keep.append((name, remark))
                    continue
                changed = True
                value = render([(name, rest)])
                if target == NOTE:
                    counts["unsorted"] += 1
                    add_note(row, f"unsorted other-dialect name: {value}")
                    report.append(f"{line} | {de or '-'} | {source} | note | {value}")
                else:
                    row[target] = render(placelist.parts(row.get(target))
                                         + [(name, rest)])
                    report.append(f"{line} | {de or '-'} | {source} | {target} | {value}")
                    counts["moved"] += 1
                if uncertain:
                    add_note(row, "uncertain")
            if changed:
                row[source] = render(keep)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--out", default=None, help="write elsewhere (default: in place)")
    ap.add_argument("--dry-run", action="store_true", help="only print the report")
    a = ap.parse_args(argv)

    expect = placelist.fingerprint(a.names)
    with open(a.names, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = []
        for n, row in enumerate(reader, start=2):
            if None in row:
                raise SystemExit(f"{a.names}:{n}: row has more cells than the header")
            row = {k: (v or "").strip() for k, v in row.items()}
            row["_line"] = n
            rows.append(row)
    unknown = [f for f in fields if f not in placelist.COLUMNS and f != "other"]
    if unknown:
        raise SystemExit(f"{a.names}: unknown column(s) {unknown} -- not migrating")

    report = []
    counts = migrate(rows, report)
    print(f"# migration of {a.names} ({len(rows)} rows)")
    print(f"# columns: {', '.join(fields)}")
    print(f"#      ->: {', '.join(placelist.COLUMNS)}\n")
    print("line | de | from | to | value")
    print("\n".join(report) if report else "(nothing to move)")
    print(f"\nmoved {counts['moved']} name(s) into dialect columns, "
          f"{counts['unsorted']} into `note` (unsorted), "
          f"{counts['goesharde']} Goesharde variant(s) left in `older` "
          f"(GOESHARDE_BY_DE is empty)")
    if a.dry_run:
        print("\n(dry run -- nothing written)")
        return 0

    out = a.out or a.names
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=placelist.COLUMNS, lineterminator="\n",
                       extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in placelist.COLUMNS})
    # in place: refuse if the list changed since it was read
    placelist.atomic_write(out, buf.getvalue(),
                           expect=expect if out == a.names else None)
    print(f"\nwrote {out}")
    placelist.read(out)          # the result must load with the new columns
    print(f"{out} reads back cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
