"""names/work/curate.json -- the review worklist of `frasch match`, as the
curation view (web/, `?curate`) puts it on the map.

The matcher leaves two kinds of row for a human: `ambiguous` (several
plausible OSM objects) and `not_found` (no object, or only near misses).
`export` writes those the matcher still owns, with the candidates'
coordinates and the row's location hint, as names/curate-worklist.schema.json
defines the file and web/src/dev/curate/worklist.ts reads it -- and, for the
places the view creates (#113), the name columns a new row has and the names
every row of the list has, which a new one may repeat.

It reads no candidates: everything the worklist shows of them the matcher
wrote into names/work/matches.jsonl (frasch.matchfile).  The file is
git-ignored: throw it away and export again whenever the matcher ran.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import os
from collections.abc import Iterable
from typing import NotRequired, TypedDict

from frasch import files, geo, kinds, matchfile, namecell, osmtags, placelist
from frasch.dialects import Registry
from frasch.matchresult import Outcome
from frasch.paths import Workspace
from frasch.placelist import PlaceRow

# The results of a match that leave a row for a human.
RESULTS = tuple(outcome.value for outcome in Outcome if outcome.for_review)


# a candidate as the matches file lists it (`matchfile.ListedCandidate`),
# without the rank of its name hit (`class` is a keyword)
WorkCandidate = TypedDict(
    "WorkCandidate",
    {
        "ref": str,
        "name": str,
        "class": str,
        "km": int | None,
        "lon": float | None,
        "lat": float | None,
        "tags": str,
        "in_sh": bool,
        "wikidata": NotRequired[str],
    },
)


class WorkRow(TypedDict):
    id: str
    line: int
    kind: str
    result: str
    name: str
    names: dict[str, str]
    name_de: str
    name_da: str
    slug_suggestion: str
    de: str
    da: str
    hint: str
    note: str
    why: str
    hint_point: list[float] | None
    candidates: list[WorkCandidate]


class ListedPlace(TypedDict):
    """A row of the name list, as a new place's duplicate warning shows it."""

    id: str
    kind: str
    names: dict[str, str]


class Worklist(TypedDict):
    bbox: list[float]
    kind_order: list[str]
    name_columns: list[str]
    non_frisian_columns: list[str]
    polygon_kinds: list[str]
    class_keys: list[str]
    settlement_places: list[str]
    results: list[str]
    rows: list[WorkRow]
    places: list[ListedPlace]


@dataclasses.dataclass(frozen=True)
class ExportReport:
    """What an export wrote, for the command to print."""

    rows: int  # the rows of the worklist
    unowned: int  # left out: decided by hand since the match
    stale: int  # left out: deleted from places.csv since the match
    log: list[str]  # what it wrote and what it left out, a line each


def export(ws: Workspace, reg: Registry) -> ExportReport:
    """Write the worklist for the browser: the rows the last match left for
    a human, with their candidates; -> what it wrote."""
    places = placelist.read(ws.names, reg).rows
    work = _read_work(ws, places, reg)
    rows = _work_rows(work.matches, reg)
    _write_worklist(ws.worklist, rows, [_listed_place(row, reg) for row in places], reg)
    return ExportReport(len(rows), work.unowned, work.stale, _summary(ws, rows, work))


@dataclasses.dataclass
class _Work:
    """The lines of work/matches.jsonl for the worklist, and how many it left out."""

    matches: list[tuple[PlaceRow, matchfile.Entry]]
    stale: int = 0  # deleted from places.csv since the run
    unowned: int = 0  # decided by hand since the run


def _read_work(ws: Workspace, places: Iterable[PlaceRow], reg: Registry) -> _Work:
    """The `ambiguous` and `not_found` rows of the last match the matcher
    still owns, each with its row of the name list (`places`)."""
    by_id = {r["id"]: r for r in places}
    work = _Work([])
    for m in matchfile.read(ws.matches):
        if not Outcome(m["result"]).for_review:
            continue
        row = by_id.get(m["id"])
        if row is None:  # deleted from places.csv since the run
            work.stale += 1
        elif not placelist.state(row, reg).matchers:
            work.unowned += 1  # decided by hand since the last run
        else:
            work.matches.append((row, m))
    return work


def _work_rows(work: Iterable[tuple[PlaceRow, matchfile.Entry]], reg: Registry) -> list[WorkRow]:
    """One worklist row per match, in the order the browser walks them."""
    out = [_work_row(row, m, reg) for row, m in work]
    out.sort(key=lambda r: (kinds.KIND_ORDER.index(r["kind"]), r["line"]))
    return out


def _work_row(row: PlaceRow, m: matchfile.Entry, reg: Registry) -> WorkRow:
    """A row of the worklist: the places.csv row, and what the matcher said
    about it -- why it left it, its candidates and where its hint points."""
    name = placelist.any_name(row, reg)
    name_de = namecell.primary(row["de"])
    return {
        "id": row["id"],
        "line": row.line,
        "kind": row["kind"],
        "result": m["result"],
        "name": name,
        "names": {c: row[c] for c in placelist.name_columns(reg) if row[c]},
        "name_de": name_de,
        "name_da": namecell.primary(row["da"]),
        "slug_suggestion": placelist.slug(name_de or name),
        "de": row["de"],
        "da": row["da"],
        "hint": row["hint"],
        "note": row["note"],
        "why": m["why"],
        "hint_point": m["hint_point"],
        "candidates": [_work_candidate(c) for c in m["candidates"]],
    }


def _work_candidate(listed: matchfile.ListedCandidate) -> WorkCandidate:
    """A candidate as the worklist shows it."""
    shown: WorkCandidate = {
        "ref": listed["ref"],
        "name": listed["name"],
        "class": listed["class"],
        "km": listed["km"],
        "lon": listed["lon"],
        "lat": listed["lat"],
        "tags": listed["tags"],
        "in_sh": listed["in_sh"],
    }
    if "wikidata" in listed:
        shown["wikidata"] = listed["wikidata"]
    return shown


def _listed_place(row: PlaceRow, reg: Registry) -> ListedPlace:
    """A row as the worklist lists every row: its non-empty name cells, raw."""
    columns = [*placelist.name_columns(reg), "de", "da"]
    return {"id": row["id"], "kind": row["kind"], "names": {c: row[c] for c in columns if row[c]}}


def _write_worklist(
    path: str, rows: list[WorkRow], places: list[ListedPlace], reg: Registry
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    worklist: Worklist = {
        "bbox": list(geo.NF_BBOX),
        "kind_order": kinds.KIND_ORDER,
        "name_columns": placelist.name_columns(reg),
        "non_frisian_columns": placelist.non_frisian_columns(reg),
        "polygon_kinds": kinds.POLYGON_KINDS,
        "class_keys": list(osmtags.CLASS_KEYS),
        "settlement_places": sorted(osmtags.SETTLEMENT_PLACES),
        "results": list(RESULTS),
        "rows": rows,
        "places": places,
    }
    # in one step: the dev server may be reading the file
    files.atomic_write(path, json.dumps(worklist, ensure_ascii=False, indent=1) + "\n")


def _summary(ws: Workspace, rows: list[WorkRow], work: _Work) -> list[str]:
    """What the export wrote and what it left out, a line each."""
    path = ws.worklist
    # as the docs name the file: `work/matches.jsonl`, next to the name list
    matches = os.path.relpath(ws.matches, os.path.dirname(ws.names))
    cnt = collections.Counter(r["result"] for r in rows)
    # a candidate has no position when the scan could not place its object
    n_pos = sum(c["lon"] is not None for r in rows for c in r["candidates"])
    n_hint = sum(r["hint_point"] is not None for r in rows)
    said = [
        f"wrote {len(rows)} rows to {path} "
        f"({os.path.getsize(path) / 1e3:.0f} kB): "
        f"{cnt['ambiguous']} ambiguous, {cnt['not_found']} not found; "
        f"{n_pos} candidates with a position, {n_hint} rows with a hint point"
    ]
    if work.unowned:
        said.append(
            f"note: {work.unowned} row(s) have been decided by hand since "
            f"{matches} was written -- not exported"
        )
    if work.stale:
        said.append(
            f"note: {work.stale} row(s) of {matches} "
            f"are no longer in places.csv (stale, re-run `frasch match`)"
        )
    return said
