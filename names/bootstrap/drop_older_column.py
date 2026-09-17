#!/usr/bin/env python3
"""One-off (2026-09-16): dissolve the `older` column of names/places.csv.

`older` came from the sheet's *Oudere noome* column and was documented as
"older Mooring spellings".  Looking at the rows whose only name sat there
showed something else: Sölring forms with đ and ā for Sylt, Fering forms for
Föhr, Halunder for Helgoland -- the island dialects' own names, filed as
"older" because the sheet had no better column.  Since the map now has a
column per dialect and knows which dialect is spoken where
(names/dialect_areas.geojson), the column goes away:

* a name in an island or Hallig area (Sölring, Fering, Öömrang, Halunder,
  Halligfriesisch) is that dialect's name -> moved into its column
* a name in a mainland Harde other than the Bökingharde is moved into that
  Harde's column only when OSM's `name:frr` for the object uses the same
  form -- evidence that this is what locals write; otherwise it counts as an
  alternative Mooring form
* an alternative Mooring form becomes the Mooring name when `mooring` is
  empty and is dropped when `mooring` is filled (the owner's decision; the
  sheet export in this directory keeps every dropped spelling)

When a variant moves into a column that already has a name, it is appended
as a further variant (never overriding the primary).  Bracket remarks
travel with their variant.  A full report of every cell is printed.

Usage:  .venv/bin/python names/bootstrap/drop_older_column.py [--dry-run]
Needs names/work/matches.csv and names/work/candidates.jsonl (match.py /
build_candidates.py output) for the positions and OSM's name:frr.
"""
from __future__ import annotations

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, NAMES)
import dialects  # noqa: E402
import placelist  # noqa: E402

PLACES = placelist.DEFAULT_PATH
MATCHES = os.path.join(NAMES, "work", "matches.csv")
CANDIDATES = os.path.join(NAMES, "work", "candidates.jsonl")

ISLAND_TAGS = {"frr-x-fering", "frr-x-oomrang", "frr-x-solring",
               "frr-x-halunder", "frr-x-hallig"}
MOORING = "frr-x-mooring"


def norm(s: str) -> str:
    return " ".join(s.lower().replace("-", " ").split())


def osm_frr_names(rows) -> dict:
    """{(t, id): name:frr} for every object the list references."""
    wanted = set()
    for r in rows:
        for key in placelist.parse_osm(r.get("osm")):
            wanted.add(key)
    out = {}
    if not wanted or not os.path.exists(CANDIDATES):
        return out
    with open(CANDIDATES, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            key = (rec["t"], rec["id"])
            if key in wanted and rec["tags"].get("name:frr"):
                out[key] = rec["tags"]["name:frr"]
    return out


def merge_into(cell: str, entries) -> str:
    """Append (name, remark) entries to a `;`-separated cell, skipping names
    already present."""
    have = {norm(n) for n in placelist.variants(cell)}
    parts = [cell.strip()] if cell.strip() else []
    for name, remark in entries:
        if norm(name) in have:
            continue
        have.add(norm(name))
        parts.append(f"{name} ({remark})" if remark else name)
    return "; ".join(parts)


def main(argv=None):
    dry = "--dry-run" in (argv or sys.argv[1:])
    with open(PLACES, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    if "older" not in fields:
        print("no `older` column -- nothing to do")
        return 0
    reg = dialects.read()
    areas = dialects.AreaIndex.from_geojson(dialects.DEFAULT_AREAS)
    coords = {}
    with open(MATCHES, encoding="utf-8", newline="") as fh:
        for m in csv.DictReader(fh):
            if m["lon"]:
                coords[int(m["line"])] = (float(m["lon"]), float(m["lat"]))
    frr = osm_frr_names(rows)

    report = []
    counts = {"moved": 0, "merged": 0, "dropped": 0}
    for n, row in enumerate(rows, start=2):
        cell = (row.get("older") or "").strip()
        if not cell:
            continue
        de = placelist.primary(row.get("de")) or placelist.primary(row.get("da"))
        entries = placelist.parts(cell)
        area = areas.lookup(*coords[n]) if n in coords else None
        target = None
        why = ""
        if area in ISLAND_TAGS:
            target, why = area, "island/Hallig area"
        elif area and area != MOORING:
            osm_names = {norm(frr[k]) for k in placelist.parse_osm(row.get("osm")) if k in frr}
            if osm_names & {norm(nm) for nm, _ in entries}:
                target, why = area, "OSM name:frr uses this form"
        if target:
            col = dialects.column_of(reg, target)
            before = row.get(col, "")
            row[col] = merge_into(before, entries)
            counts["moved"] += 1
            report.append((n, de, area or "-", f"-> {col} ({why})", cell,
                           "" if row[col] != before else "already there"))
        elif not (row.get("mooring") or "").strip():
            row["mooring"] = cell
            counts["merged"] += 1
            report.append((n, de, area or "-", "-> mooring (was the only Mooring name)", cell, ""))
        else:
            counts["dropped"] += 1
            report.append((n, de, area or "-", "dropped (alternative Mooring form)", cell,
                           f"mooring={row['mooring']}"))
        row["older"] = ""

    print("line | de | area | action | older cell | note")
    for line in report:
        print(" | ".join(str(x) for x in line))
    print(f"\nmoved {counts['moved']} cell(s) into dialect columns, merged {counts['merged']} "
          f"into `mooring`, dropped {counts['dropped']} alternative Mooring spellings")
    if dry:
        print("(dry run -- nothing written)")
        return 0
    fields = [f for f in fields if f != "older"]
    with open(PLACES, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"wrote {PLACES} without the `older` column")
    return 0


if __name__ == "__main__":
    sys.exit(main())
