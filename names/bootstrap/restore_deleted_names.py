#!/usr/bin/env python3
"""Restore names that were deleted from names/places.csv but belong in a
dialect column (2026-09-17).

Between the sheet import and the first commit the owner deleted names from
the list to clean it up, and in doing so also stripped bracket remarks such
as `(Hålifrasch)`.  When the columns were restructured (see
migrate_dialect_columns.py and drop_older_column.py) the scripts could no
longer see that `Ualöön` or the Langeneß `-weerw` Warften were Hallig
Frisian, and dropped them as alternative Mooring spellings.  A comparison
of the sheet export with the committed and the current list produced
`restore_proposal.csv` next to this script (one line per lost name with a
suggested column, confidence, and the reasoning); `restore_review.csv` is
an independent second opinion on the dialect assignment.

This script applies the proposal to names/places.csv:

* only lines whose `suggested_column` is a real column of places.csv
* only names of a place that still exists (`current_row_line` set); a
  whole deleted row is reported, never re-created
* `--min-confidence high|medium|low` (default medium) filters on the
  proposal's confidence; `--only-agreed` additionally requires the review's
  verdict to be `agree`
* the name is appended as a further variant of the target column and never
  replaces the primary name; names already present are skipped; the sheet's
  remark travels along unless it merely names the target dialect

Edit `restore_proposal.csv` first if you disagree with a suggestion (change
`suggested_column`, or set it to `keep deleted`), then run:

    .venv/bin/python names/bootstrap/restore_deleted_names.py --dry-run
    .venv/bin/python names/bootstrap/restore_deleted_names.py

Re-running is a no-op once the names are in.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, NAMES)
import dialects  # noqa: E402
import placelist  # noqa: E402

PROPOSAL = os.path.join(HERE, "restore_proposal.csv")
REVIEW = os.path.join(HERE, "restore_review.csv")
LEVELS = {"high": 3, "medium": 2, "low": 1}

# sheet remarks that only name the dialect (redundant inside that column)
DIALECT_REMARKS = {
    "wieding": {"wisinge", "wising"},
    "karrhard": {"kårhiirdinge", "kårhiirder", "kaarhiirdinge"},
    "nordgoes": {"gooshiirdinge", "gooshiirder", "goeshiirdinge"},
    "midgoes": {"gooshiirdinge", "gooshiirder", "goeshiirdinge"},
    "suedgoes": {"gooshiirdinge", "gooshiirder", "goeshiirdinge"},
    "fering": {"fering", "fäiring", "fairing"},
    "oomrang": {"öömrang", "öömring", "oomrang"},
    "solring": {"sölring", "salring", "solring"},
    "hallig": {"halifreesk", "hålifrasch", "halifrasch"},
    "halunder": {"halunder"},
    "mooring": {"mooring"},
}


def norm(s: str) -> str:
    return " ".join(s.lower().replace("-", " ").split())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proposal", default=PROPOSAL)
    ap.add_argument("--review", default=REVIEW)
    ap.add_argument("--min-confidence", choices=LEVELS, default="medium")
    ap.add_argument("--only-agreed", action="store_true",
                    help="skip names the review did not mark `agree`")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    reg = dialects.read()
    columns = set(dialects.columns(reg)) | {dialects.LOCAL_COLUMN}
    verdict = {}
    if os.path.exists(a.review):
        with open(a.review, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                verdict[(r["sheet_row"], r["name"])] = r["verdict"]

    rows, fields = placelist.read()
    by_line = {r["_line"]: r for r in rows}
    with open(a.proposal, encoding="utf-8", newline="") as fh:
        proposal = list(csv.DictReader(fh))

    added, skipped, present = [], [], []
    for p in proposal:
        col = p["suggested_column"]
        if col not in columns:
            continue
        if LEVELS.get(p["confidence"], 0) < LEVELS[a.min_confidence]:
            skipped.append((p, f"confidence {p['confidence']}"))
            continue
        v = verdict.get((p["sheet_row"], p["name"]))
        if a.only_agreed and v != "agree":
            skipped.append((p, f"review says {v or 'nothing'}"))
            continue
        if not p["current_row_line"]:
            skipped.append((p, "row no longer exists (deleted on purpose?)"))
            continue
        row = by_line.get(int(p["current_row_line"]))
        if row is None:
            skipped.append((p, "line not found -- places.csv changed since the proposal"))
            continue
        name = p["name"].strip()
        if norm(name) in {norm(v) for v in placelist.variants(row.get(col))}:
            present.append((p, row))
            continue
        remark = p["remark"].strip().rstrip("?").strip()
        if remark.lower() in DIALECT_REMARKS.get(col, set()):
            remark = ""
        piece = f"{name} ({remark})" if remark else name
        row[col] = f"{row[col]}; {piece}" if row.get(col) else piece
        added.append((p, row))

    print("line | de | column | added | now")
    for p, row in added:
        print(f"{row['_line']} | {placelist.primary(row['de']) or placelist.primary(row['da'])} | "
              f"{p['suggested_column']} | {p['name']} | {row[p['suggested_column']]}")
    if present:
        print(f"\n{len(present)} already present, e.g. "
              + ", ".join(p["name"] for p, _ in present[:6]))
    if skipped:
        print(f"\n{len(skipped)} skipped:")
        for p, why in skipped:
            print(f"  sheet row {p['sheet_row']} {p['de']}: {p['name']} -> {p['suggested_column']}: {why}")
    print(f"\nadded {len(added)} name(s)")
    if a.dry_run:
        print("(dry run -- nothing written)")
        return 0
    if added:
        placelist.write(rows, fields=fields)
        print(f"wrote {placelist.DEFAULT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
