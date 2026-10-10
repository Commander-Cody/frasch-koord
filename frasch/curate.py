"""Put the review worklist of `frasch match` on the map, and write the answers
back into the name list.

The matcher leaves two kinds of row for a human: `ambiguous` (several plausible
OSM objects) and `not_found` (no object, or only near misses).  Deciding them
from REPORT.md means looking every candidate up on openstreetmap.org; on a map
the answer is usually obvious at a glance.  So:

    frasch curate export  ->  names/work/curate.json   (the worklist, with the
                          candidates' coordinates and the row's location hint)
       the browser (web/, `?curate`, Vite dev server only) shows them as pins
       and appends one decision per line to names/work/curate-patch.jsonl
    frasch curate apply   <-  names/work/curate-patch.jsonl

What gets written where
  names/work/curate.json   export: the worklist.  Git-ignored, throw it away
                           and re-export whenever the matcher ran again.
  names/places.csv         apply: only `osm`, `wikidata` and `status` of the
                           rows the matcher owns -- the same cells it
                           writes itself, and never a row a human has already decided
                           (status ok/skip, a hand-filled reference, a local
                           reference, `not_a_place`) or one without a Frisian
                           name, and never an object or
                           Wikidata item another row holds: the name list
                           would be refused.  Review with `git diff`.
  names/curation.csv       apply: one appended row per `local` decision (a
                           place OSM does not have -- it needs a position).
  names/work/curate-patch.jsonl
                           apply: renamed to `<stamp>.applied.jsonl` before
                           it is read, so that a decision the browser makes
                           meanwhile starts a fresh patch (`--keep` leaves it
                           alone); an entry apply refused is appended back so
                           it is not lost.  If apply fails, the patch is put
                           back.

Apply checks everything first and then writes curation.csv and places.csv, each
in one step and only if it did not change on disk meanwhile; when the second
write fails, the first is undone, so a failed apply changes neither file.
names/work/.lock keeps it from running at the same time as `frasch match`.

The export never builds the matcher's full candidate index (180k records, most of
a gigabyte): it streams names/work/candidates.jsonl once and keeps only the
records the worklist actually mentions.

Run:  frasch curate                    # = export
      frasch curate apply --dry-run
"""

from __future__ import annotations

import argparse
import collections
import csv
import dataclasses
import functools
import io
import json
import os
import sys
import time
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from typing import Any, Literal, NotRequired, TypedDict, final

import jsonschema

from frasch import (
    candidates,
    cli,
    curationlist,
    dialects,
    errors,
    files,
    geo,
    kinds,
    namecell,
    nameindex,
    osmtags,
    paths,
    placelist,
    refs,
)
from frasch.candidates import Candidate
from frasch.dialects import Registry
from frasch.errors import PipelineError
from frasch.hints import HINT_FALLBACK, Circle, HintResolver
from frasch.paths import StrPath, Workspace
from frasch.placelist import PlaceList, PlaceRow, Reference, Row
from frasch.refs import OsmRef

# The extract (`src` of a candidate) the tiles are built from: only its
# objects can carry an injected name, so it is what "in Schleswig-Holstein"
# means for the curation view.  An object near the border can come from both.
SH_SRC = "schleswig-holstein"

# The results of a match that leave a row for a human.
RESULTS = ("ambiguous", "not_found")

# ------------------------------------------------------------- the worklist ---
# curate.json, as names/curate-worklist.schema.json defines it and
# web/src/dev/curateWorklist.ts reads it

# a candidate as the matcher's `candidates` cell names it (`class` is a
# keyword); `km` is its distance from the centre of North Frisia
_Listed = TypedDict("_Listed", {"ref": str, "name": str, "class": str, "km": int | None})


class ListedCandidate(_Listed):
    key: OsmRef


class WorkCandidate(_Listed):
    lon: float | None
    lat: float | None
    tags: str
    in_sh: bool
    wikidata: NotRequired[str]


class WorkRow(TypedDict):
    id: str
    line: int
    kind: str
    result: str
    name: str
    names: dict[str, str]
    name_de: str
    name_da: str
    de: str
    da: str
    hint: str
    note: str
    why: str
    hint_point: list[float] | None
    candidates: list[WorkCandidate]


class Worklist(TypedDict):
    bbox: list[float]
    kind_order: list[str]
    polygon_kinds: list[str]
    class_keys: list[str]
    settlement_places: list[str]
    results: list[str]
    rows: list[WorkRow]


# ------------------------------------------------------------- candidates ---
def parse_candidates(cell: str | None) -> list[ListedCandidate]:
    """The `candidates` column of work/matches.csv -> one dict per candidate.

    `match.fmt_cand` writes `type/id:name:class:km` joined by `;` and escapes
    nothing, so a name with a colon in it is only readable from the ends: the
    reference stops at the first colon, class and km are the last two fields.
    (A name with a `;` would still split wrongly -- fmt_cand truncates names to
    40 characters, so that stays a theoretical loss.)
    """
    out: list[ListedCandidate] = []
    for part in (cell or "").split(";"):
        part = part.strip()
        if not part:
            continue
        head, _, km = part.rpartition(":")
        head, _, cls = head.rpartition(":")
        ref, _, name = head.partition(":")
        t, _, ident = ref.partition("/")
        if t not in refs.TYPE_NAME or not ident.isdigit():
            print(f"  ignoring unreadable candidate {part!r}", file=sys.stderr)
            continue
        out.append(
            {
                "key": (t, int(ident)),
                "ref": f"{refs.TYPE_NAME[t]}/{ident}",
                "name": name,
                "class": cls,
                "km": int(km) if km.isdigit() else None,
            }
        )
    return out


def stream_records(
    path: StrPath, keys: Collection[OsmRef], hint_norms: Collection[str]
) -> list[Candidate]:
    """One pass over work/candidates.jsonl, keeping the records the worklist
    refers to (by id) and those a location hint could name (by normalised
    name) -- roughly a thousand of 180 000."""
    kept: list[Candidate] = []
    for rec in candidates.read_records(path):
        if (rec["t"], rec["id"]) in keys:
            kept.append(rec)
            continue
        if not hint_norms:
            continue
        for field in osmtags.NAME_FIELDS:
            v = rec["tags"].get(field)
            if v and any(
                nameindex.norm(p) in hint_norms for p, _pen in nameindex.split_name_values(v)
            ):
                kept.append(rec)
                break
    return kept


# ----------------------------------------------------------------- export ---
def work_candidate(listed: ListedCandidate, rec: Candidate | None, in_sh: bool) -> WorkCandidate:
    """A candidate as the worklist shows it: with its position and what it is,
    when candidates.jsonl still has its record."""
    c: WorkCandidate = {
        "ref": listed["ref"],
        "name": listed["name"],
        "class": listed["class"],
        "km": listed["km"],
        "lon": None,
        "lat": None,
        "tags": "",
        "in_sh": False,
    }
    if rec is None:  # candidates.jsonl rebuilt since the run
        return c
    c["lon"], c["lat"] = rec["lon"], rec["lat"]
    c["tags"] = osmtags.decisive(rec["tags"])
    c["in_sh"] = in_sh
    if rec["tags"].get("wikidata"):
        c["wikidata"] = rec["tags"]["wikidata"]
    return c


def export(ws: Workspace, reg: Registry) -> None:
    """Write the worklist for the browser: the rows the last match left for
    a human, with their candidates."""
    work = _read_work(ws, reg)
    index = _read_index(ws.candidates, work.matches)
    out = _work_rows(work.matches, index, reg)
    _write_worklist(ws.worklist, out)
    _print_export_summary(ws, out, work)


@dataclasses.dataclass
class _Work:
    """The rows of work/matches.csv for the worklist, and how many it left out."""

    matches: list[tuple[PlaceRow, dict[str, str]]]
    stale: int = 0  # deleted from places.csv since the run
    unowned: int = 0  # decided by hand since the run


def _read_work(ws: Workspace, reg: Registry) -> _Work:
    """The `ambiguous` and `not_found` rows of the last match the matcher
    still owns, each with its places.csv row."""
    matches = ws.matches
    rows = placelist.read(ws.names, reg).rows
    by_id = {r["id"]: r for r in rows}
    if not os.path.exists(matches):
        raise PipelineError(f"{matches} not found -- run `frasch match` first")

    work = _Work([])
    with open(matches, encoding="utf-8", newline="") as fh:
        for m in csv.DictReader(fh):
            if m["result"] not in RESULTS:
                continue
            row = by_id.get(m["id"])
            if row is None:  # deleted from places.csv since the run
                work.stale += 1
                continue
            if not placelist.state(row, reg).matchers:
                work.unowned += 1  # decided by hand since the last run
                continue
            work.matches.append((row, m))
    return work


def _first_hint(row: PlaceRow) -> str:
    """The place a row's `hint` names first."""
    return row["hint"].split(";")[0].strip()


def _read_index(
    path: StrPath, work: Iterable[tuple[PlaceRow, dict[str, str]]]
) -> nameindex.NameIndex:
    """The name index of the candidates.jsonl records the worklist needs: its
    candidates, and what its location hints could name."""
    keys: set[OsmRef] = set()
    hint_norms: set[str] = set()
    for row, m in work:
        for c in parse_candidates(m["candidates"]):
            keys.add(c["key"])
        key = nameindex.norm(_first_hint(row))
        if key and key not in HINT_FALLBACK:
            hint_norms.add(key)

    t0 = time.time()
    index = nameindex.NameIndex(stream_records(path, keys, hint_norms))
    print(
        f"read {path}: kept {len(index.recs):,} records "
        f"({len(keys):,} candidates, {len(hint_norms)} hint names, "
        f"{time.time() - t0:.0f}s)"
    )
    return index


def _work_rows(
    work: Iterable[tuple[PlaceRow, dict[str, str]]], index: nameindex.NameIndex, reg: Registry
) -> list[WorkRow]:
    """One worklist row per match, in the order the browser walks them."""
    hints = HintResolver(index)
    srcs: collections.defaultdict[OsmRef, set[str | None]] = collections.defaultdict(set)
    for rec in index.recs:
        srcs[(rec["t"], rec["id"])].add(rec.get("src"))

    out: list[WorkRow] = []
    for row, m in work:
        cands = _work_candidates(m["candidates"], index, srcs)
        out.append(_work_row(row, m, cands, hints.resolve(_first_hint(row)), reg))
    out.sort(key=lambda r: (kinds.KIND_ORDER.index(r["kind"]), r["line"]))
    return out


def _work_candidates(
    cell: str, index: nameindex.NameIndex, srcs: Mapping[OsmRef, set[str | None]]
) -> list[WorkCandidate]:
    """The candidates of the matcher's `candidates` cell as the worklist shows
    them; `srcs` are the extracts each record of `index` came from."""
    cands = []
    for listed in parse_candidates(cell):
        ref = listed["key"]
        found = index.by_key.get(ref)
        in_sh = found is not None and SH_SRC in srcs[ref]
        cands.append(work_candidate(listed, found, in_sh))
    return cands


def _work_row(
    row: PlaceRow,
    m: dict[str, str],
    cands: list[WorkCandidate],
    hint_pt: Circle | None,
    reg: Registry,
) -> WorkRow:
    """A row of the worklist: the places.csv row, what the matcher said about
    it, its candidates and where its hint points."""
    return {
        "id": row["id"],
        "line": row.line,
        "kind": row["kind"],
        "result": m["result"],
        "name": placelist.any_name(row, reg),
        "names": {c: row[c] for c in placelist.name_columns(reg) if row[c]},
        "name_de": namecell.primary(row["de"]),
        "name_da": namecell.primary(row["da"]),
        "de": row["de"],
        "da": row["da"],
        "hint": row["hint"],
        "note": row["note"],
        "why": m["note"],
        "hint_point": list(hint_pt) if hint_pt else None,
        "candidates": cands,
    }


def _write_worklist(path: str, rows: list[WorkRow]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    worklist: Worklist = {
        "bbox": list(geo.NF_BBOX),
        "kind_order": kinds.KIND_ORDER,
        "polygon_kinds": kinds.POLYGON_KINDS,
        "class_keys": list(osmtags.CLASS_KEYS),
        "settlement_places": sorted(osmtags.SETTLEMENT_PLACES),
        "results": list(RESULTS),
        "rows": rows,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(worklist, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def _print_export_summary(ws: Workspace, rows: list[WorkRow], work: _Work) -> None:
    path = ws.worklist
    # as the docs name the file: `work/matches.csv`, next to the name list
    matches = os.path.relpath(ws.matches, os.path.dirname(ws.names))
    cnt = collections.Counter(r["result"] for r in rows)
    # a candidate has a position only when candidates.jsonl still had its record
    n_pos = sum(c["lon"] is not None for r in rows for c in r["candidates"])
    n_hint = sum(r["hint_point"] is not None for r in rows)
    print(
        f"wrote {len(rows)} rows to {path} "
        f"({os.path.getsize(path) / 1e3:.0f} kB): "
        f"{cnt['ambiguous']} ambiguous, {cnt['not_found']} not found; "
        f"{n_pos} candidates with a position, {n_hint} rows with a hint point"
    )
    if work.unowned:
        print(
            f"note: {work.unowned} row(s) have been decided by hand since "
            f"{matches} was written -- not exported"
        )
    if work.stale:
        print(
            f"note: {work.stale} row(s) of {matches} "
            f"are no longer in places.csv (stale, re-run `frasch match`)"
        )


# ------------------------------------------------------------------ apply ---
class PatchEntry(TypedDict):
    """One line of the patch, as names/curate-patch.schema.json allows it."""

    id: str
    action: Literal["osm", "local", "skip", "clear"]
    line: NotRequired[int]
    kind: NotRequired[str]
    name: NotRequired[str]
    de: NotRequired[str]
    osm: NotRequired[str]
    wikidata: NotRequired[str]
    slug: NotRequired[str]
    lat: NotRequired[float]
    lon: NotRequired[float]
    polygon_km2: NotRequired[float]
    note: NotRequired[str]
    at: NotRequired[str]


@final
@dataclasses.dataclass(frozen=True)
class EntryLine:
    """A valid line of the patch as apply read it."""

    number: int  # its line in the patch
    entry: PatchEntry

    @property
    def value(self) -> object:
        """The line's JSON value, as the patch holds it."""
        return self.entry


@final
@dataclasses.dataclass(frozen=True)
class RefusedLine:
    """A line of the patch that is no valid entry, as apply read it."""

    number: int  # its line in the patch
    value: object  # the line's JSON value, as the patch holds it
    problem: str  # what makes it no valid entry


PatchLine = EntryLine | RefusedLine


def patch_key(value: object) -> str | None:
    """What makes two patch entries decisions about the same row: its id.
    The `line`, `name` and `de` an entry also carries are only there for the
    messages -- they change when the list is edited, the id does not.  None
    for a line (as the patch holds it) without a usable one."""
    ident = value.get("id") if isinstance(value, dict) else None
    return ident if isinstance(ident, str) and ident else None


def read_patch(path: StrPath) -> list[PatchLine]:
    """-> the last entry per row, in line order.  The browser appends, never
    rewrites, so a row decided twice simply has two lines; `clear` withdraws,
    whatever line either was sent with.

    A line that breaks the patch schema counts like any other: apply
    refuses and keeps it, and as the newest line about its row it holds
    back the row's earlier decision.  A line without a usable id is a
    decision of its own, never swallowed by a later one."""

    def not_json(n: int, exc: ValueError) -> None:
        print(f"{path}:{n}: not JSON ({exc}) -- ignored", file=sys.stderr)

    last: dict[str | tuple[str, int], PatchLine] = {}
    with open(path, encoding="utf-8") as fh:
        for line in patch_lines(fh, not_json):
            last[patch_key(line.value) or ("line", line.number)] = line
    return sorted(last.values(), key=_patch_order)


def patch_lines(
    text: Iterable[str], not_json: Callable[[int, ValueError], object] = lambda n, exc: None
) -> Iterator[PatchLine]:
    """The lines of a patch (its text, a newline-ended line at a time, as
    a file gives it) as apply reads them, blank ones left out; a line that
    is no JSON goes to `not_json` with its number instead."""
    for n, line in enumerate(text, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except ValueError as exc:
            not_json(n, exc)
            continue
        yield patch_line(value, n)


def patch_line(value: Any, n: int) -> PatchLine:
    """One parsed line of the patch as apply handles it: the entry plus its
    line, or the line's value and what makes it no valid entry."""
    why = (
        schema_problem(value)
        if isinstance(value, dict)
        else "not a JSON object (curate-patch.schema.json)"
    )
    if why:
        return RefusedLine(n, value, why)
    entry: PatchEntry = value  # valid: the schema's shape
    return EntryLine(n, entry)


def _patch_order(line: PatchLine) -> tuple[int, int]:
    """Places.csv order (the row's `line` when the worklist was exported),
    then patch order."""
    row_line = line.entry.get("line") if isinstance(line, EntryLine) else None
    return (row_line or 0, line.number)


def _names_of(line: PatchLine) -> str:
    """`name / de` of the row a line is about, for the messages."""
    fields = line.value if isinstance(line.value, dict) else {}
    return f"{fields.get('name')} / {fields.get('de')}"


@functools.cache
def patch_validator() -> jsonschema.Draft202012Validator:
    with open(paths.PATCH_SCHEMA, encoding="utf-8") as fh:
        return jsonschema.Draft202012Validator(json.load(fh))


def schema_problem(entry: object) -> str | None:
    """What breaks names/curate-patch.schema.json in one entry, or None."""
    error = next(iter(sorted(patch_validator().iter_errors(entry), key=str)), None)
    if error is None:
        return None
    where = "/".join(map(str, error.absolute_path))
    return f"{where + ': ' if where else ''}{error.message} (curate-patch.schema.json)"


def owner_problem(row: PlaceRow, names: PlaceList) -> str | None:
    """Why apply refuses an entry's row of the list `names` before looking
    at its decision, or None: the row must be the matcher's to fill."""
    if not placelist.state(row, names.reg).matchers:
        return (
            f"{names.path}:{row.line} is not the matcher's to fill "
            f"(status={row['status'] or 'empty'}, osm={row['osm'] or '-'})"
        )
    return None


def decide(entry: PatchEntry, row: dict[str, str], claimed: Mapping[str, int]) -> str | None:
    """Write an `osm` or `skip` decision into `row`; -> why not, or None.
    `claimed` is what the other rows of the list hold (claim -> line): a row
    cannot be given what one of them claims.  The decision is the row's
    whole reference: nothing of what the matcher gave it stays."""
    if entry["action"] == "skip":
        Reference.skipped().write(row)
        return None
    try:
        chosen = refs.parse(entry.get("osm"))
    except errors.Invalid as exc:
        return str(exc)
    if not chosen:
        return "action=osm without an `osm` reference"
    if any(t == refs.LOCAL_TYPE for t, _ in chosen):
        return "a local reference is action=local, not action=osm"
    picked = Reference.checked(chosen, entry.get("wikidata", ""))
    taken = placelist.claim_problems(placelist.Claims(chosen, picked.wikidata).keys, claimed)
    if taken:
        return "; ".join(taken)
    picked.write(row)
    return None


def decide_local(
    entry: PatchEntry, row: dict[str, str], used_slugs: set[str]
) -> tuple[str | None, dict[str, str] | None]:
    """Write a `local` decision -- a place OSM does not have -- into `row`;
    -> (why not, or None; the curation row that positions it)."""
    slug = entry.get("slug")
    if not slug:
        return "action=local needs a `slug`", None
    if slug in used_slugs:
        return f"local/{slug} is already taken", None
    lat, lon = entry.get("lat"), entry.get("lon")
    if lat is None or lon is None:
        return "action=local needs `lat` and `lon`", None
    Reference.local(slug).write(row)
    used_slugs.add(slug)
    cur = {c: "" for c in curationlist.COLUMNS}
    cur.update(
        osm=row["osm"], lat=fmt_deg(lat), lon=fmt_deg(lon), note=(entry.get("note") or "").strip()
    )
    if (km2 := entry.get("polygon_km2")) is not None:
        # the README's Koog route: no labelled node, only a square of that
        # area -- and OpenMapTiles labels a polygon only as island
        cur.update(polygon_km2=f"{km2:g}", set_tags="place=island")
    return None, cur


def decision_text(entry: PatchEntry, row: Row, curation: str) -> str:
    """What an applied decision changed, for the log."""
    if entry["action"] == "skip":
        return "status = skip"
    if entry["action"] == "osm":
        return (
            f"osm = {row['osm']}"
            + (f", wikidata = {entry['wikidata']}" if entry.get("wikidata") else "")
            + ", status = ok"
        )
    text = (
        f"osm = {row['osm']}, status = ok; "
        f"{curation} += {fmt_deg(entry['lat'])}/{fmt_deg(entry['lon'])}"
    )
    if (km2 := entry.get("polygon_km2")) is not None:
        return text + f", polygon_km2 = {km2:g}"
    if not kinds.rule(row["kind"]).point_place:
        text += (
            f"\n    warning: kind={row['kind']} has no default `place=` "
            f"(`point_place` in frasch/kinds.py) -- put one into the curation row's "
            f"`set_tags` before the next build"
        )
    return text


def curation_name(row: Row, reg: Registry) -> str:
    """The free-text label of the appended curation row -- German, else Danish,
    else Frisian, plus the hint, so the file stays readable by a human."""
    name = placelist.point_name(row, reg)
    return f"{name} ({row['hint']})" if row["hint"] else name


def fmt_deg(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".")


def apply(ws: Workspace, reg: Registry, *, dry_run: bool = False, keep: bool = False) -> int:
    """Write the decisions of the workspace's patch into its name list and
    curation (see the module docstring); -> how many it refused.  Those stay
    in the patch; a problem that stops the whole apply raises.  `dry_run`:
    say what would change and write nothing.  `keep`: leave the patch file
    where it is."""
    with files.lock(ws.lock):
        return _apply(ws, reg, dry_run, keep)


def _apply(ws: Workspace, reg: Registry, dry_run: bool, keep: bool) -> int:
    names, curation, patch = ws.names, ws.curation, ws.patch
    # Everything that can refuse the whole run is checked before the patch is
    # touched: the name list, and curation.csv (read once, kept as bytes, so
    # the rows appended to it land after exactly what was checked).
    lists = _read_lists(names, curation, reg)
    if not os.path.exists(patch):
        raise PipelineError(
            f"{patch} not found -- decide some rows in the browser first (web/, `?curate`)"
        )
    # Take the patch out of the browser's way first, then read it: the dev
    # server appends with O_APPEND, so a decision made from now on starts
    # a fresh patch file instead of landing in one that is being archived.
    snapshot = None if dry_run or keep else _take_snapshot(patch)

    cur_written: str | None = None  # digest of the curation.csv apply wrote
    decisions = _Decisions()
    try:
        for line in read_patch(snapshot or patch):
            _decide_entry(line, lists, decisions)

        if dry_run:
            print(
                f"dry run: {decisions.applied} row(s) would change, "
                f"{len(decisions.new_curation)} curation row(s) would be appended, "
                f"{decisions.refused} refused -- nothing written"
            )
            return decisions.refused

        if decisions.applied:
            # curation.csv first, places.csv last: when the places.csv write
            # fails (a spreadsheet saved it meanwhile, say), the curation rows
            # come out again, so a `local/<slug>` row never lands without its
            # position and a failed apply leaves both files as they were
            if decisions.new_curation:
                cur_text = curationlist.appended(
                    lists.cur_data, lists.cur_fields, decisions.new_curation
                )
                files.atomic_write(curation, cur_text, expect=lists.cur_digest)
                cur_written = files.digest(cur_text)
            lists.places.write()
    except BaseException:
        if cur_written:
            added = [c["osm"] for c in decisions.new_curation]
            unwrite_curation(curation, lists.cur_data, cur_written, added)
        if snapshot:
            restore_patch(snapshot, patch)
            print(f"nothing applied -- {patch} restored", file=sys.stderr)
        raise

    if snapshot:
        _keep_refused(snapshot, patch, decisions.kept_back)
    print(
        f"{decisions.applied} row(s) written to {names}, "
        f"{len(decisions.new_curation)} appended to {curation}, {decisions.refused} refused"
    )
    return decisions.refused


@dataclasses.dataclass
class _Lists:
    """The name list and curation.csv, as apply checked them."""

    places: PlaceList
    curation: str
    used_slugs: set[str]  # local/<slug> references curation.csv or a row has
    cur_data: bytes | None  # None = there is no curation.csv
    cur_fields: list[str]
    cur_digest: str

    @functools.cached_property
    def by_id(self) -> dict[str, PlaceRow]:
        return {r["id"]: r for r in self.places.rows}

    def claimed_by_others(self, row: PlaceRow) -> dict[str, int]:
        """What the rows of the list but `row` hold, as it stands now with
        the decisions applied so far: claim -> the line of its row."""
        return {
            key: other.line
            for other in self.places.rows
            if other is not row
            for key in placelist.claims(other).keys
        }


def _read_lists(names: str, curation: str, reg: Registry) -> _Lists:
    places = placelist.read(names, reg)
    used_slugs = set(curationlist.local_points(curation))
    cur_data, cur_fields = curationlist.read_bytes(curation)
    cur_digest = files.digest(cur_data) if cur_data is not None else files.MISSING
    used_slugs.update(r.local for r in places.rows if r.local)
    return _Lists(places, curation, used_slugs, cur_data, cur_fields, cur_digest)


def _take_snapshot(patch: str) -> str:
    """Rename the patch to `<stamp>.applied.jsonl`; -> the new name."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    root, ext = os.path.splitext(patch)
    snapshot = f"{root}.{stamp}.applied{ext}"
    os.rename(patch, snapshot)
    return snapshot


@dataclasses.dataclass
class _Decisions:
    """What apply made of the patch's entries."""

    applied: int = 0
    new_curation: list[dict[str, str]] = dataclasses.field(default_factory=list)
    # refused entries survive the archiving
    kept_back: list[PatchLine] = dataclasses.field(default_factory=list)

    @property
    def refused(self) -> int:
        return len(self.kept_back)

    def refuse(self, line: PatchLine, why: str) -> None:
        self.kept_back.append(line)
        print(f"  refused patch line {line.number} ({_names_of(line)}): {why}")


def _decide_entry(line: PatchLine, lists: _Lists, decisions: _Decisions) -> None:
    """Write one entry of the patch into its row, or refuse it."""
    if isinstance(line, RefusedLine):
        decisions.refuse(line, line.problem)
        return
    e = line.entry
    if e["action"] == "clear":
        return  # withdrawn in the browser
    row = lists.by_id.get(e["id"])
    if row is None:
        decisions.refuse(
            line, f"no row with id {e['id']!r} in {lists.places.path} (deleted since the export?)"
        )
        return
    why = owner_problem(row, lists.places)
    if why is None:
        why = _decide_row(e, row, lists, decisions.new_curation)
    if why:
        decisions.refuse(line, why)
        return
    print(
        f"  {lists.places.path}:{row.line} {placelist.describe(row, lists.places.reg)}: "
        f"{decision_text(e, row, lists.curation)}"
    )
    decisions.applied += 1


def _decide_row(
    entry: PatchEntry, row: PlaceRow, lists: _Lists, new_curation: list[dict[str, str]]
) -> str | None:
    """Write a decision into the matcher's `row`, a `local` one's curation
    row into `new_curation`; -> why not, or None."""
    if entry["action"] != "local":
        return decide(entry, row, lists.claimed_by_others(row))
    why, cur = decide_local(entry, row, lists.used_slugs)
    if cur:
        cur["name"] = curation_name(row, lists.places.reg)
        new_curation.append(cur)
    return why


def _keep_refused(snapshot: str, patch: str, kept_back: Sequence[PatchLine]) -> None:
    """Say where the applied patch went, and append what apply refused back
    to the live one."""
    print(f"patch applied, moved to {snapshot}")
    if kept_back:
        # a refused decision is not lost: it goes back into the patch (and
        # so stays "done" in the browser) until fixed or cleared
        n = append_back(patch, kept_back)
        print(
            f"{n} refused entr{'y' if n == 1 else 'ies'} kept in {patch}"
            + (
                f" ({len(kept_back) - n} decided again in the browser meanwhile)"
                if n < len(kept_back)
                else ""
            )
        )


def append_back(path: str, refused: Iterable[PatchLine]) -> int:
    """Append refused lines to the live patch -- appending, never
    rewriting, because the dev server may be appending to it too.  A line
    whose row has been decided again since then is dropped: the newer
    decision wins, as it would in `read_patch`.  -> how many were appended."""
    newer: set[str] = set()
    ends_nl = True
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        ends_nl = not text or text.endswith("\n")
        # line by line as a file is read (not `splitlines`, which also ends
        # a line inside a JSON string that holds a U+2028)
        keys = (patch_key(line.value) for line in patch_lines(io.StringIO(text)))
        newer = {key for key in keys if key}
    lines = [
        json.dumps(line.value, ensure_ascii=False) + "\n"
        for line in refused
        if patch_key(line.value) not in newer
    ]
    if lines:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(("" if ends_nl else "\n") + "".join(lines))
    return len(lines)


def restore_patch(snapshot: str, path: str) -> None:
    """Undo taking the snapshot after a failed apply: the snapshot becomes the
    patch again, followed by whatever the browser appended in the meantime."""
    while True:
        try:
            os.link(snapshot, path)  # unlike rename, never overwrites
            os.unlink(snapshot)
            return
        except FileExistsError:
            pass
        # the browser started a new patch: move it aside (the next pick starts
        # yet another, hence the loop) and put its entries after the old ones
        newer = f"{snapshot}.newer"
        os.rename(path, newer)
        with open(newer, "rb") as fh:
            text = fh.read()
        with open(snapshot, "rb") as fh:
            old = fh.read()
        with open(snapshot, "ab") as fh:
            fh.write((b"" if not old or old.endswith(b"\n") else b"\n") + text)
        os.unlink(newer)


def unwrite_curation(path: str, old: bytes | None, written: str, added: Sequence[str]) -> None:
    """Undo apply's curation.csv write after the places.csv write failed: put
    back `old` (its bytes before; None = there was no file), unless someone
    changed the file after apply wrote it (`written`, its digest) -- then say
    which rows to take out by hand."""
    try:
        if old is not None:
            files.atomic_write(path, old, expect=written)
        elif files.fingerprint(path) == written:
            os.unlink(path)
        else:
            raise errors.Conflict(f"{path} changed on disk meanwhile")
    except (OSError, errors.PipelineError) as exc:
        print(
            f"error: could not take the new rows out of {path} again ({exc}) "
            f"-- delete the rows for {', '.join(added)} by hand before the next "
            f"apply",
            file=sys.stderr,
        )
    else:
        print(f"{path} put back as it was", file=sys.stderr)


# ------------------------------------------------------------------- main ---
@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    argparser, apply_only = parser()
    args = argparser.parse_args(
        with_subcommand(sys.argv[1:] if argv is None else argv, argparser, apply_only)
    )
    ws = cli.workspace(args)
    reg = dialects.read(ws.dialects)
    if args.cmd == "apply":
        return 1 if apply(ws, reg, dry_run=args.dry_run, keep=args.keep) else 0
    export(ws, reg)
    return 0


def with_subcommand(
    argv: Sequence[str], argparser: argparse.ArgumentParser, apply_only: Collection[str]
) -> list[str]:
    """`argv`, with `export` in front when it names no subcommand: export is
    what one runs every time.  An option only `apply` takes stops it then
    (`frasch curate --dry-run` meant `apply --dry-run`)."""
    if argv and argv[0] in ("export", "apply", "-h", "--help"):
        return list(argv)
    if option := next((a for a in argv if a.split("=")[0] in apply_only), None):
        argparser.error(
            f"{option} belongs to `apply`: did you mean `frasch curate apply {' '.join(argv)}`?"
        )
    return ["export", *argv]


def options_of(argparser: argparse.ArgumentParser) -> set[str]:
    return {o for action in argparser._actions for o in action.option_strings}


def parser() -> tuple[argparse.ArgumentParser, set[str]]:
    """-> (the parser, the options only its `apply` subcommand takes)."""
    ap = cli.parser("curate", __doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="write the worklist for the browser", allow_abbrev=False)
    cli.add_workspace_options(ex, "names", "dialects", "matches", "candidates", "worklist", "work")

    ap_ = sub.add_parser("apply", help="write the browser's decisions back", allow_abbrev=False)
    cli.add_workspace_options(ap_, "names", "dialects", "curation", "patch", "work")
    ap_.add_argument(
        "--dry-run", action="store_true", help="print what would change and write nothing"
    )
    ap_.add_argument(
        "--keep", action="store_true", help="do not rename the patch file after applying it"
    )
    return ap, options_of(ap_) - options_of(ex)
