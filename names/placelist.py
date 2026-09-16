"""Read / write names/places.csv -- the hand-edited name list.

The file is the single source of truth for every North Frisian label on the
map.  Its conventions (see names/README.md):

* a name cell may hold several variants separated by `;` -- the first one is
  the primary name (the map label)
* `(...)` after a variant is a remark about it (local variety, source), never
  part of the name
* `osm` holds one or more OSM references: `node/123`, `way/1; way/2`
* `status` is `auto` (written by match.py, recomputed on every run), `ok`
  (checked by a human), `skip` (never put on the map) or empty

Everything here is deliberately small and dependency-free so that both
names/match.py and tiles/inject_names.py can share it.
"""
from __future__ import annotations

import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "places.csv")

COLUMNS = [
    "kind", "mooring", "older", "other", "de", "hint", "da",
    "osm", "wikidata", "status", "note",
]

KINDS = {"settlement", "koog", "harde", "island", "hallig", "sand", "warft",
         "landscape", "water", "road", "country", "helgoland", "not_a_place"}
STATUSES = {"", "auto", "ok", "skip"}

OSM_TYPES = {"node": "n", "way": "w", "relation": "r"}
TYPE_NAME = {v: k for k, v in OSM_TYPES.items()}

_REMARK = re.compile(r"\s*\([^()]*\)")


def variants(cell: str | None) -> list[str]:
    """`"Rübel; Rübbel (wisinge)"` -> `["Rübel", "Rübbel"]` (remarks stripped)."""
    out = []
    for part in (cell or "").split(";"):
        part = _REMARK.sub("", part).strip().rstrip("?").strip()
        if part and part not in out:
            out.append(part)
    return out


def primary(cell: str | None) -> str:
    v = variants(cell)
    return v[0] if v else ""


def label(row: dict, column: str = "mooring") -> str:
    """The map label of a row for one dialect column.  For Mooring the sheet's
    older names are the fallback when no current name is known."""
    name = primary(row.get(column))
    if not name and column == "mooring":
        name = primary(row.get("older"))
    return name


def parse_osm(cell: str | None, where: str = "") -> list[tuple[str, int]]:
    """`"way/12; way/13"` -> `[("w", 12), ("w", 13)]`."""
    out = []
    for ref in (cell or "").split(";"):
        ref = ref.strip()
        if not ref:
            continue
        m = re.fullmatch(r"(node|way|relation)/(\d+)", ref)
        if not m:
            raise SystemExit(f"{where}: bad OSM reference {ref!r} "
                             f"(expected node/ID, way/ID or relation/ID)")
        out.append((OSM_TYPES[m.group(1)], int(m.group(2))))
    return out


def format_osm(refs) -> str:
    return "; ".join(f"{TYPE_NAME[t]}/{i}" for t, i in refs)


def read(path: str = DEFAULT_PATH):
    """-> (rows, fieldnames).  Every row gets `_line`, its physical line number
    in the file (header = 1), which is how REPORT.md refers to rows."""
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        missing = [c for c in COLUMNS if c not in fields]
        if missing:
            raise SystemExit(f"{path}: missing column(s) {missing}")
        rows = []
        for n, row in enumerate(reader, start=2):
            if None in row:                      # more cells than columns
                raise SystemExit(f"{path}:{n}: row has more cells than the header "
                                 f"(a stray comma?): {row[None]}")
            row = {k: (v or "").strip() for k, v in row.items()}
            row["_line"] = n
            if row["kind"] not in KINDS:
                raise SystemExit(f"{path}:{n}: unknown kind {row['kind']!r}")
            if row["status"] not in STATUSES:
                raise SystemExit(f"{path}:{n}: unknown status {row['status']!r} "
                                 f"(auto / ok / skip / empty)")
            parse_osm(row["osm"], f"{path}:{n}")
            if row["wikidata"] and not re.fullmatch(r"Q\d+", row["wikidata"]):
                raise SystemExit(f"{path}:{n}: bad wikidata id {row['wikidata']!r}")
            rows.append(row)
    return rows, fields


def write(rows, path: str = DEFAULT_PATH, fields=None):
    fields = fields or COLUMNS
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n",
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def describe(row: dict) -> str:
    """One-line human reference to a row for messages and the report."""
    name = label(row) or primary(row.get("other")) or "-"
    de = primary(row.get("de")) or primary(row.get("da")) or "-"
    return f"{name} ({de})"
