"""Fill the empty `osm` / `wikidata` cells of names/places.csv.

Matching is EXACT after normalisation -- no fuzzy matching.  The German names
of a row (the Danish ones where a row has no German name) are compared against
the candidates' name, name:de, name:da, short_name, official_name, alt_name
and old_name.
Candidates come from names/work/candidates.jsonl (`frasch candidates`).

What gets written where
  names/places.csv        only `osm`, `wikidata` and `status` of the rows the
                          matcher owns (`placelist.state`): rows with an
                          empty `osm` + `wikidata` cell, and rows it filled
                          earlier (`status=auto`).
                          A row a human has filled in (any `osm`/`wikidata`
                          with a status other than `auto`) or marked `skip`
                          is never touched.  Review the result with `git diff`.
                          Only one row holds an object or a Wikidata item
                          (`placelist.claims`): the matcher gives a row
                          neither what a row it leaves alone holds nor what
                          it gave a row further up in this run -- of two rows
                          for one place the second stays unmatched, with
                          "... is taken by row <id>".
  names/work/matches.jsonl
                          the result of every row the matcher owns
                          (frasch.matchfile): what was matched, the decisive
                          tags, lon/lat, the candidates a reviewer should
                          see.  Git-ignored.
  names/REPORT.md         the hand-review worklist (frasch.matchreport).
                          Depends on the inputs alone (no date), so an
                          unchanged run leaves it as is.
                          Its last line is the stamp of what it was written
                          from (frasch.provenance): the name list as the run
                          left it, the dialect registry and the extracts the
                          candidates came from (the header of candidates.jsonl).
                          `frasch check-outputs` fails on a report from another
                          name list, and the next run warns when the set of
                          extracts changed.
  With --dry-run only work/matches.jsonl is written.

Ranking / decision
  1. keep only candidates whose tags are compatible with the row's `kind`
     (its rule, frasch.kinds)
  2. cluster the survivors geographically (frasch.clusters: objects within
     3 km are one feature, the pieces of a river within 30 km)
  3. `matched`   - one cluster, or exactly one cluster satisfies the row's
                   location hint, or exactly one cluster is inside North Frisia
                   while every other cluster is far away
     `ambiguous` - several plausible clusters, or the best name hit lies
                   outside North Frisia while a weaker one lies inside (all
                   candidates are listed with the result)
     `not_found` - no name match at all
  Countries are resolved through the Wikidata API instead of OSM
  (frasch.wikidata, cached in names/work/wikidata-countries.json).  When a
  lookup fails -- or `--offline` without a cached answer -- the country row
  keeps its cells (`lookup_failed` in matches.jsonl) and the run exits with
  status 1.

Changed extracts
  A row the matcher filled from an object of one extract alone loses it when
  the candidates are rebuilt without that extract -- the Danish places (Fanø,
  Hoyer, Ripen, Röm, ...) exist only in the Denmark extract.  So every run
  compares the extract files of candidates.jsonl with those the report of the
  last real run names, and warns on stderr when one was added or dropped.  A newer download of
  the same extract (only its replication timestamp differs) is no warning.

places.csv is written in one step (never half), and not at all if it changed
on disk during the run; names/work/.lock keeps `frasch match` and
`frasch curate apply` from running at the same time.

Run:  frasch match [--dry-run] [--offline]
"""

from __future__ import annotations

import collections
import dataclasses
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple

from frasch import (
    candidates,
    cli,
    dialects,
    files,
    geo,
    kinds,
    matchfile,
    matchreport,
    osmtags,
    placelist,
    refs,
    wikidata,
)
from frasch.candidates import Candidate, osm_key
from frasch.clusters import SEPARATION_KM, PlacedCluster, cluster, is_linear, placed, same_feature
from frasch.dialects import Registry
from frasch.geo import haversine, in_north_frisia
from frasch.hints import Circle, HintResolver
from frasch.kinds import Boundary, KindRule
from frasch.matchresult import MatchResult, Outcome, RankedCandidate
from frasch.namecell import primary, variants
from frasch.nameindex import NameIndex, norm
from frasch.paths import Workspace
from frasch.placelist import PlaceRow, Reference, Row, any_name
from frasch.provenance import ExtractStamp
from frasch.refs import OsmRef, Ref
from frasch.wikidata import Countries

BOUNDARY_QID_KM = 10.0  # a boundary further from a place node is a namesake
MINOR_PLACE_KM = 50.0  # a hamlet further from North Frisia is no plausible match


# ------------------------------------------------------------- candidates ----
def row_query_names(row: Row) -> list[str]:
    """The German names of the row; the Danish ones for Danish-only rows."""
    return variants(row.get("de")) or variants(row.get("da"))


def _ranked_candidates(index: NameIndex, queries: Iterable[str]) -> list[RankedCandidate]:
    """Every record any of `queries` finds, with the best hit it found it with."""
    found: dict[OsmRef, RankedCandidate] = {}
    for q in queries:
        for hit in index.lookup(q):
            key = osm_key(hit.rec)
            rank, byname = hit.rank, hit.byname
            if key in found:
                rank, byname = min(rank, found[key]["rank"]), byname and found[key]["byname"]
            found[key] = {**hit.rec, "rank": rank, "byname": byname}
    return list(found.values())


def _split_by_rank(
    cands: list[RankedCandidate],
) -> tuple[list[RankedCandidate], list[RankedCandidate]]:
    """-> (the best-ranked name hits, the weaker ones)"""
    top = min(c["rank"] for c in cands)
    return [c for c in cands if c["rank"] == top], [c for c in cands if c["rank"] > top]


def _listed(cands: Iterable[RankedCandidate]) -> tuple[RankedCandidate, ...]:
    """`cands` in the order a reviewer sees them: the best name hit first,
    then the nearest to North Frisia.  All of them -- the curation view needs
    every one (a "Dorfstraße" has hundreds of ways)."""

    def key(c: RankedCandidate) -> tuple[int, float, str, int]:
        d = geo.km_or(geo.from_centre(c["lon"], c["lat"]), unknown=geo.FAR)
        return (c["rank"], d, c["t"], c["id"])

    return tuple(sorted(cands, key=key))


def absorb_boundaries(
    rule: KindRule, cands: list[RankedCandidate]
) -> tuple[list[RankedCandidate], list[RankedCandidate]]:
    """Prefer the place NODE over its administrative boundary (that is what
    OpenMapTiles labels), where the kind's rule says so.  Returns (kept,
    dropped)."""
    if rule.boundary is Boundary.FEATURE:
        return cands, []  # Harden: the historic boundary is it
    if rule.boundary is Boundary.YIELDS_TO_NODE:
        # for a landscape/Kreis the boundary usually *is* the feature -- only a
        # real place node (place=county/region/...) beats it
        if not any(c["t"] == "n" and c["tags"].get("place") for c in cands):
            return cands, []
    kept: list[RankedCandidate] = []
    dropped: list[RankedCandidate] = []
    for c in cands:
        if c["tags"].get("boundary") == "administrative" and not c["tags"].get("place"):
            dropped.append(c)
        else:
            kept.append(c)
    return (kept or cands), dropped


# --------------------------------------------------------------- decision ----
def _decide(
    plaus: Iterable[Candidate], hint_pt: Circle | None
) -> tuple[PlacedCluster | None, str, list[PlacedCluster]]:
    """-> (winner cluster or None, reason, clusters)"""
    clusters = [placed(cl, hint_pt) for cl in cluster(plaus)]
    if hint_pt:
        # the sheet says where the feature lies -- that is binding, also when
        # there is only one candidate (OSM's only "Morsum" is on Sylt, but the
        # sheet means the Morsum on Nordstrand)
        ok = [c for c in clusters if c["hint_ok"]]
        return (ok[0] if len(ok) == 1 else None), "location hint", clusters
    if len(clusters) == 1:
        return clusters[0], "single cluster", clusters
    inside = [c for c in clusters if c["in_nf"]]
    if len(inside) == 1:
        cand = inside[0]
        if all(
            geo.km_or(haversine(cand["lon"], cand["lat"], c["lon"], c["lat"]), unknown=geo.FAR)
            > SEPARATION_KM
            for c in clusters
            if c is not cand
        ):
            return cand, "only candidate in North Frisia", clusters
    return None, "", clusters


def _suspicious(rule: KindRule, winner: PlacedCluster) -> bool:
    """True if an otherwise clear winner is implausible for a North Frisian
    name list: a Koog/Warft/Hallig outside North Frisia, or a far-away minor
    place (hamlet, isolated dwelling, ...)."""
    if winner["in_nf"]:
        return False
    if rule.nf_only:
        return True
    minor = any(m["tags"].get("place") in osmtags.MINOR_PLACES for m in winner["members"])
    return minor and geo.km_or(winner["nf_d"], unknown=geo.FAR) > MINOR_PLACE_KM


def _outranks_a_hit_in_north_frisia(winner: PlacedCluster, weaker: Iterable[Candidate]) -> bool:
    """True if a winner outside North Frisia beat a weaker name hit inside it:
    the exact *Ostenfeld* is the village near Rendsburg, while OSM calls the
    one near Husum `Ostenfeld (Husum)`.  Which one the list means is for a
    human to decide."""
    if winner["in_nf"]:
        return False
    return any(in_north_frisia(c["lon"], c["lat"]) for c in weaker if c not in winner["members"])


def _ambiguous_reason(
    row: Row,
    winner: PlacedCluster | None,
    hint_pt: Circle | None,
    clusters: Sequence[PlacedCluster],
) -> str:
    """Why `match_row` leaves a row for review."""
    if winner is None:
        if hint_pt:
            return f"location hint '{row['hint']}' matched no cluster"
        return f"{len(clusters)} plausible candidates"
    where = (
        "has no known position"
        if winner["nf_d"] is None
        else f"is {winner['nf_d']:.0f} km from North Frisia"
    )
    if _suspicious(kinds.rule(row["kind"]), winner):
        return f"only match {where} ({row['kind']}) -- verify by hand"
    return f"best name hit {where}, a weaker one lies inside -- verify by hand"


class _Decision(NamedTuple):
    """What `_decide_by_rank` made of a row's plausible candidates."""

    winner: PlacedCluster | None
    reason: str
    clusters: list[PlacedCluster]
    plaus: list[RankedCandidate]  # the candidates the decision was made among


def _decide_by_rank(
    rule: KindRule,
    best_hits: list[RankedCandidate],
    plaus_all: list[RankedCandidate],
    hint_pt: Circle | None,
) -> _Decision:
    """`_decide` among the best name hits, and among all of them when the
    best hits' winner is implausible."""
    winner, reason, clusters = _decide(best_hits, hint_pt)
    if winner is not None and _suspicious(rule, winner) and len(plaus_all) > len(best_hits):
        # the best-ranked name hit is implausible -- reconsider the weaker hits
        # (OSM disambiguators such as "Kampen (Sylt)", German exonyms, ...)
        w2, r2, c2 = _decide(plaus_all, hint_pt)
        if w2 is not None and not _suspicious(rule, w2):
            return _Decision(w2, r2 + " (weaker name hit)", c2, plaus_all)
    return _Decision(winner, reason, clusters, best_hits)


def _needs_review(
    rule: KindRule, winner: PlacedCluster, weaker: Iterable[Candidate], hint_pt: Circle | None
) -> bool:
    """True if a winner is too doubtful to take: implausible for the list,
    or a far-away pick over a weaker hit in North Frisia."""
    if _suspicious(rule, winner):
        return True
    # a hint's pick is binding
    return not hint_pt and _outranks_a_hit_in_north_frisia(winner, weaker)


# ------------------------------------------------------------- the winner ----
def _best_member(rule: KindRule, members: list[Candidate]) -> Candidate:
    """The object of a cluster that gets the name."""
    return max(
        members,
        key=lambda r: (
            rule.bonus(r)
            + (kinds.WIKIDATA_BONUS if r["tags"].get("wikidata") else 0)
            + (kinds.GERMAN_NAME_BONUS if r["tags"].get("name:de") else 0)
            - geo.km_or(geo.from_centre(r["lon"], r["lat"]), unknown=kinds.UNPLACED_KM)
            / kinds.KM_PER_POINT
        ),
    )


def boundary_qid(rec: Candidate, boundaries: Iterable[Candidate]) -> str:
    """The `wikidata` a place node without one borrows from its boundary: of
    the relations within BOUNDARY_QID_KM that have one, the most local
    (Gemeinde before Amt before Kreis), the nearest among equals.  `""` if
    none is that close -- a namesake further away is another place."""
    near: list[tuple[int, float, str]] = []
    for b in boundaries:
        d = haversine(rec["lon"], rec["lat"], b["lon"], b["lat"])
        if d is not None and d <= BOUNDARY_QID_KM and b["tags"].get("wikidata"):
            near.append((-admin_level(b), d, b["tags"]["wikidata"]))
    return min(near)[2] if near else ""


def admin_level(rec: Candidate) -> int:
    """The `admin_level` of a boundary relation, 0 if it has none."""
    level = rec["tags"].get("admin_level", "")
    return int(level) if level.isdigit() else 0


def _member_qid(
    best: Candidate, members: list[Candidate], boundaries: list[RankedCandidate]
) -> str:
    """The wikidata of the chosen object, else of a sibling, else of its
    boundary relation."""
    qid = best["tags"].get("wikidata", "")
    if not qid:  # fall back to a sibling's / the boundary relation's wikidata
        qid = next(
            (r["tags"]["wikidata"] for r in members if r["tags"].get("wikidata")), ""
        ) or boundary_qid(best, boundaries)
    return qid


def _member_refs(best: Candidate, members: list[Candidate]) -> tuple[OsmRef, ...]:
    """The objects the name goes on: the chosen one, and for a linear feature
    every piece of it."""
    # a linear feature (river, dyke, street) is split into many ways -- tag all
    # of them, otherwise only a fragment of the river gets the Frisian label
    if not is_linear(best):
        return (osm_key(best),)
    bn = norm(best["tags"].get("name", ""))
    pieces = {
        m["id"]
        for m in members
        if m["t"] == best["t"] and is_linear(m) and norm(m["tags"].get("name", "")) == bn
    }
    return tuple((best["t"], piece) for piece in sorted(pieces))


def _matched(
    rule: KindRule,
    decision: _Decision,
    winner: PlacedCluster,
    boundaries: list[RankedCandidate],
) -> MatchResult:
    """The result of a row the decision's winner matches; `boundaries` are
    the boundary relations set aside for it."""
    members = winner["members"]
    best = _best_member(rule, members)
    lon, lat = best["lon"], best["lat"]
    has_rivals = len(members) > 1 or len(decision.clusters) > 1
    return MatchResult(
        Outcome.MATCHED,
        why="" if decision.reason == "single cluster" else f"auto: {decision.reason}",
        refs=_member_refs(best, members),
        wikidata=_member_qid(best, members, boundaries),
        match_name=osmtags.name_of(best["tags"]),
        match_tags=osmtags.decisive(best["tags"]),
        lonlat=None if lon is None or lat is None else (lon, lat),
        candidates=_listed(decision.plaus) if has_rivals else (),
    )


def _unmatched(
    result: Outcome, why: str, candidates: Iterable[RankedCandidate] = ()
) -> MatchResult:
    """The result of a row the matcher gives no object: why, and the
    candidates a reviewer should see."""
    return MatchResult(result, why, candidates=_listed(candidates))


# ------------------------------------------------------------------ match ----
def match_row(
    row: Row,
    index: NameIndex,
    hints: HintResolver,
    reg: Registry,
    claimed: Claimed | None = None,
) -> MatchResult:
    """`claimed`: what other rows hold, which is not this row's to get."""
    claimed = claimed or Claimed()
    if not any_name(row, reg):
        return _unmatched(Outcome.NOT_FOUND, "no Frisian name")
    queries = row_query_names(row)
    if not queries:
        return _unmatched(Outcome.NOT_FOUND, "no German/Danish name to match on")

    found = _ranked_candidates(index, queries)
    taken = [c for c in found if osm_key(c) in claimed.objects]
    free = [c for c in found if osm_key(c) not in claimed.objects]
    if not free:
        why = claimed.taken_note(taken) if taken else "no name match in OSM"
        return _unmatched(Outcome.NOT_FOUND, why)
    return _match_among(row, free, taken, hints.of_row(row), claimed)


def _match_among(
    row: Row,
    free: list[RankedCandidate],
    taken: list[RankedCandidate],
    hint_pt: Circle | None,
    claimed: Claimed,
) -> MatchResult:
    """The result of a row whose names find the objects `free`, which no
    other row holds, and `taken`, which one does."""
    rule = kinds.rule(row["kind"])
    plaus_all = [c for c in free if rule.accepts(c["tags"])]
    if not plaus_all:
        # the German name exists in OSM, but only on streets / buildings /
        # bus stops -- the feature itself is not mapped.  Not a review task.
        why = f"{len(free)} name match(es), none compatible with kind={rule.name}"
        return _unmatched(Outcome.NOT_FOUND, why, free)
    # set the boundaries aside first: canonical() would drop them, and their
    # wikidata is the fallback for a place node without one
    plaus_all, boundaries = absorb_boundaries(rule, plaus_all)
    plaus_all = rule.canonical(plaus_all)
    best_hits, weaker = _split_by_rank(plaus_all)

    decision = _decide_by_rank(rule, best_hits, plaus_all, hint_pt)
    winner = decision.winner
    if winner is None or _needs_review(rule, winner, weaker, hint_pt):
        why = _ambiguous_reason(row, winner, hint_pt, decision.clusters)
        return _unmatched(Outcome.AMBIGUOUS, why, plaus_all)

    held = claimed.held(rule, taken, winner)
    if held:
        # another row holds part of this very feature (a piece of the same
        # river, or the relation that is the whole river): the rest is not
        # free for a second name
        return _unmatched(Outcome.NOT_FOUND, claimed.taken_note(held), plaus_all)

    return _matched(rule, decision, winner, boundaries)


@dataclass
class Claimed:
    """What the matcher must not give to a row, because another one holds it
    and only one name per object or Wikidata item can reach the map
    (`placelist.claims`): `objects` maps (type, id) and `items` a QID to the
    id of the row that holds it.

    A run starts with what the rows it leaves as they are hold (`of`), and
    each row it matches is added (`give`): of two rows for one place the
    first in the list gets the object.

    A row that holds an object names its whole feature (`held`): one that
    holds a piece of a river, or the relation that is the river, leaves the
    rest of it to no second name.  What the run itself gave out (`given`) is
    not a human's word on where the feature ends, though: it holds the
    feature only against a row that finds the object by one of its own
    names, not by `alt_name` or `old_name` alone (`RankedCandidate.byname`).  The dyke Deezbüll Deich also goes by `alt_name=Deezbülleck` and
    lies at the hamlet of that name -- the row of the dyke takes the dyke,
    not the hamlet."""

    objects: dict[Ref, str] = field(default_factory=dict)
    items: dict[str, str] = field(default_factory=dict)
    given: set[Ref] = field(default_factory=set)

    @classmethod
    def of(cls, rows: Iterable[PlaceRow]) -> Claimed:
        claimed = cls()
        for row in rows:
            claimed._add(row)
        return claimed

    def give(self, row: PlaceRow) -> None:
        """Count what the run wrote into `row` as held by it."""
        self._add(row)
        self.given.update(placelist.claims(row).refs)

    def _add(self, row: PlaceRow) -> None:
        held = placelist.claims(row)
        for ref in held.refs:
            self.objects.setdefault(ref, row["id"])
        if held.qid:
            self.items.setdefault(held.qid, row["id"])

    def held(
        self, rule: KindRule, taken: Iterable[RankedCandidate], winner: PlacedCluster
    ) -> list[RankedCandidate]:
        """The objects of `taken` -- candidates of a row that other rows
        hold -- that are part of the feature the row would get, `winner`."""
        return [
            c
            for c in taken
            if self._holds_feature(c)
            and rule.covers(c)
            and any(same_feature(c, member) for member in winner["members"])
        ]

    def _holds_feature(self, c: RankedCandidate) -> bool:
        """Whether the row that holds `c` holds its whole feature against
        the row whose names found `c`."""
        return osm_key(c) not in self.given or not c["byname"]

    def taken_note(self, recs: Iterable[Candidate]) -> str:
        """`way/1 is taken by row naibel; ...` for the candidates other rows
        hold."""
        return "; ".join(
            f"{refs.format([osm_key(c)])} is taken by row {self.objects[osm_key(c)]}" for c in recs
        )

    def without_taken_item(self, result: MatchResult) -> MatchResult:
        """`result` without a Wikidata item another row holds.  A row matched
        by its item alone -- a country -- is then not found; any other keeps
        its object, which is what it claims first (OSM tags an island and its
        village with one item)."""
        qid = result.wikidata
        if result.result is not Outcome.MATCHED or qid not in self.items:
            return result
        why = f"{qid} is taken by row {self.items[qid]}"
        if not result.refs:
            return MatchResult(Outcome.NOT_FOUND, why)
        return dataclasses.replace(
            result, wikidata="", why="; ".join(filter(None, [result.why, why]))
        )


# -------------------------------------------------------------- countries ----
# The result of a country row Wikidata gave no answer for.
LOOKUP_FAILED = MatchResult(Outcome.LOOKUP_FAILED, "Wikidata lookup failed -- row left unchanged")


def match_country(row: Row, qids: Mapping[str, str]) -> MatchResult:
    """A country row's result: its Wikidata item (`qids`: German name -> QID,
    `""` for a name that is no country's), not an OSM object."""
    name = primary(row["de"])
    qid = qids.get(name, "")
    if not qid:
        return MatchResult(Outcome.NOT_FOUND, "no Wikidata country item found")
    return MatchResult(
        Outcome.MATCHED, "auto: wikidata", wikidata=qid, match_name=name, match_tags="wikidata"
    )


# ---------------------------------------------------------------- the run ----
def run(ws: Workspace, reg: Registry, *, offline: bool = False, dry_run: bool = False) -> int:
    """Match the rows the matcher owns and write the result (see the module
    docstring); -> the exit status.  `offline`: no call to the Wikidata API,
    the cache only.  `dry_run`: only matches.jsonl is written."""
    with files.lock(ws.lock):
        return _run(ws, reg, offline, dry_run)


def _run(ws: Workspace, reg: Registry, offline: bool, dry_run: bool) -> int:
    t0 = time.time()
    names = placelist.read(ws.names, reg)
    rows = names.rows
    print(f"loaded {len(rows)} rows from {ws.names}")
    extracts = _extracts(ws)
    index = NameIndex(candidates.read_records(ws.candidates))
    print(
        f"indexed {len(index.recs):,} candidates / "
        f"{len(index.by_name):,} distinct normalised names "
        f"({time.time() - t0:.0f}s)"
    )
    owned = [r for r in rows if placelist.state(r, reg).matchers]
    sources = _Sources(index, HintResolver(index), reg, _countries(owned, ws, offline))
    results, changed = _match_rows(rows, owned, sources)

    # matches.jsonl first: a run that cannot write it leaves places.csv as it was
    matchfile.write(ws.matches, (sources.entry(r, results[r["id"]]) for r in owned))
    if not dry_run:
        names.write()
        matchreport.write(rows, results, ws.report, reg, matchreport.stamp(ws, extracts))

    outcomes = collections.Counter(results[r["id"]].result for r in owned)
    _print_summary(ws, f"{len(owned)} of {len(rows)}", outcomes, changed, dry_run)
    print(f"done in {time.time() - t0:.0f}s")
    unanswered = [r for r in owned if results[r["id"]].result is Outcome.LOOKUP_FAILED]
    return _unanswered_status(unanswered, reg, offline)


def _print_summary(
    ws: Workspace,
    owned: str,
    outcomes: collections.Counter[Outcome],
    changed: collections.Counter[str],
    dry_run: bool,
) -> None:
    """What the run made of the rows the matcher owns (`owned`: how many of
    how many), what it did to places.csv and which files it wrote."""
    print(
        f"matcher owns {owned} rows: "
        + ", ".join(f"{n} {outcome.value}" for outcome, n in outcomes.most_common())
    )
    print(
        f"places.csv: {changed['filled']} rows filled, {changed['cleared']} cleared, "
        f"{changed['changed']} changed" + (" (dry run -- not written)" if dry_run else "")
    )
    print("wrote", ws.matches, *(() if dry_run else ("and", ws.report)))


def _extracts(ws: Workspace) -> Sequence[ExtractStamp]:
    """The extracts behind the candidates, said on stdout -- with a warning
    on stderr when the report of the last real run names another set."""
    extracts = candidates.extracts(ws.candidates)
    print(
        "candidates from "
        + ", ".join(
            f"{e['file']} ({e['replication_timestamp'] or 'no timestamp'})" for e in extracts
        )
    )
    if warning := matchreport.extracts_warning(ws.report, extracts):
        print(warning, file=sys.stderr)
    return extracts


def _countries(owned: Iterable[PlaceRow], ws: Workspace, offline: bool) -> Countries:
    """The Wikidata items of the country rows among `owned`, with what went
    wrong said on stderr."""
    names = [primary(r["de"]) for r in owned if kinds.rule(r["kind"]).by_item]
    found = wikidata.countries(names, ws.wikidata_cache, offline)
    for warning in found.warnings:
        print(f"  {warning}", file=sys.stderr)
    return found


@dataclass(frozen=True)
class _Sources:
    """What a run matches its rows against."""

    index: NameIndex
    hints: HintResolver
    reg: Registry
    countries: Countries

    def match(self, row: PlaceRow, claimed: Claimed) -> MatchResult:
        """What the run makes of `row`, given what other rows hold."""
        if kinds.rule(row["kind"]).by_item:
            found = match_country(row, self.countries.qids)
        else:
            found = match_row(row, self.index, self.hints, self.reg, claimed)
        return claimed.without_taken_item(found)

    def entry(self, row: PlaceRow, result: MatchResult) -> matchfile.Entry:
        """The line of the matches file for `row` and what the run made of it."""
        return matchfile.entry(row["id"], result, self.hints.of_row(row), self.index)

    def unanswered(self, row: PlaceRow) -> bool:
        """Whether `row` is a country row Wikidata gave no answer for."""
        return kinds.rule(row["kind"]).by_item and primary(row["de"]) in self.countries.failed


def _match_rows(
    rows: Sequence[PlaceRow], owned: Sequence[PlaceRow], sources: _Sources
) -> tuple[dict[str, MatchResult], collections.Counter[str]]:
    """Match the rows the matcher owns, in file order, and write each match
    into its row; -> (the result per row id, how many rows the run filled,
    cleared and changed)."""
    # no answer is not "no country": such a row is left as it is
    results = {r["id"]: LOOKUP_FAILED for r in owned if sources.unanswered(r)}
    todo = [r for r in owned if r["id"] not in results]
    rematched = {r["id"] for r in todo}
    claimed = Claimed.of(r for r in rows if r["id"] not in rematched)

    changed: collections.Counter[str] = collections.Counter()
    for r in todo:
        before = Reference.of(r)
        results[r["id"]] = sources.match(r, claimed)
        _write_back(r, results[r["id"]])
        claimed.give(r)
        if change := _change(before, Reference.of(r)):
            changed[change] += 1
    return results, changed


def _write_back(r: PlaceRow, result: MatchResult) -> None:
    """Put a match into the row as `status=auto`; clear the row otherwise."""
    if result.result is Outcome.MATCHED:
        Reference.auto(result.refs, result.wikidata).write(r)
    else:  # lost / never had a match
        Reference.cleared().write(r)


def _change(before: Reference, after: Reference) -> str | None:
    """`filled`, `cleared` or `changed` -- what the run did to a row's
    reference -- or None when it left it as it was."""
    if after == before:
        return None
    return (
        "filled"
        if after.status == placelist.AUTO and before.status != placelist.AUTO
        else "cleared"
        if before.status == placelist.AUTO and not after.status
        else "changed"
    )


def _unanswered_status(unanswered: Sequence[PlaceRow], reg: Registry, offline: bool) -> int:
    """The run's exit status: 1, with the reason on stderr, when country
    rows got no answer from Wikidata."""
    if not unanswered:
        return 0
    print(
        f"error: no Wikidata answer for {len(unanswered)} country row(s) "
        + ("(--offline and not in the cache)" if offline else "(lookup failed, see above)")
        + " -- left unchanged: "
        + ", ".join(placelist.describe(r, reg) for r in unanswered),
        file=sys.stderr,
    )
    return 1


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("match", __doc__)
    cli.add_workspace_options(
        ap,
        "names",
        "dialects",
        "report",
        "candidates",
        "matches",
        "wikidata_cache",
        "work",
    )
    ap.add_argument(
        "--offline", action="store_true", help="do not call the Wikidata API (use the cache only)"
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="write only work/matches.jsonl (git-ignored); leave places.csv and REPORT.md alone",
    )
    a = ap.parse_args(argv)
    ws = cli.workspace(a)
    return run(ws, dialects.read(ws.dialects), offline=a.offline, dry_run=a.dry_run)
