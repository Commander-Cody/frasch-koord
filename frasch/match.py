#!/usr/bin/env python3
"""Fill the empty `osm` / `wikidata` cells of names/places.csv.

Matching is EXACT after normalisation -- no fuzzy matching.  The German names
of a row (the Danish ones where a row has no German name) are compared against
the candidates' name, name:de, name:da, short_name, official_name, alt_name
and old_name.
Candidates come from names/work/candidates.jsonl (see build_candidates.py).

What gets written where
  names/places.csv        only `osm`, `wikidata` and `status` of the rows the
                          matcher owns: rows with an empty `osm` + `wikidata`
                          cell, and rows it filled earlier (`status=auto`).
                          A row a human has filled in (any `osm`/`wikidata`
                          with a status other than `auto`) or marked `skip`
                          is never touched.  Review the result with `git diff`.
  names/work/matches.csv  per-row details of the run: what was matched, the
                          decisive tags, lon/lat, the candidate list of
                          ambiguous rows.  Git-ignored.
  names/REPORT.md         the hand-review worklist.  Depends on the inputs
                          alone (no date), so an unchanged run leaves it as is.
  names/work/match-extracts.json
                          the extracts the candidates came from (the header of
                          candidates.jsonl) -- the next run warns when that set
                          changed.  Git-ignored; lives next to the candidates.
  With --dry-run only work/matches.csv is written.

Ranking / decision
  1. keep only candidates whose tags are compatible with the row's `kind`
  2. cluster the survivors geographically (30 km)
  3. `matched`   - one cluster, or exactly one cluster satisfies the row's
                   location hint, or exactly one cluster is inside North Frisia
                   while every other cluster is far away
     `ambiguous` - several plausible clusters, or the best name hit lies
                   outside North Frisia while a weaker one lies inside (all
                   candidates are listed in the `candidates` column:
                   type/id:name:place:dist_km)
     `not_found` - no name match at all
  Countries are resolved through the Wikidata API instead of OSM (cached in
  names/work/wikidata-countries.json).  When a lookup fails -- or `--offline`
  without a cached answer -- the country row keeps its cells
  (`lookup_failed` in matches.csv) and the run exits with status 1.

Changed extracts
  A row the matcher filled from an object of one extract alone loses it when
  the candidates are rebuilt without that extract -- the Danish places (Fanø,
  Hoyer, Ripen, Röm, ...) exist only in the Denmark extract.  So every run
  compares the extract files of candidates.jsonl with those of the last real
  run, and warns on stderr when one was added or dropped.  A newer download of
  the same extract (only its replication timestamp differs) is no warning.

places.csv is written in one step (never half), and not at all if it changed
on disk during the run; names/work/.lock keeps match.py and
`curate.py apply` from running at the same time.

Run:  .venv/bin/python names/match.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, TypedDict

from frasch import candidates, cli, files, paths, placelist
from frasch.candidates import ISLAND_PLACES, Candidate, decisive_tags, osm_key
from frasch.errors import PipelineError
from frasch.geo import NF_CENTRE, haversine, in_north_frisia
from frasch.hints import Circle, HintResolver
from frasch.nameindex import NameIndex, norm
from frasch.placelist import (
    OsmRef,
    PlaceRow,
    Ref,
    Row,
    any_name,
    format_osm,
    local_ref,
    osm_refs,
    owned_by_matcher,
    parse_osm,
    primary,
    variants,
)
from frasch.provenance import ExtractStamp

if TYPE_CHECKING:
    import requests

CSV_PATH = placelist.DEFAULT_PATH
CAND_PATH = paths.CANDIDATES
MATCH_PATH = paths.MATCHES
REPORT_PATH = paths.REPORT
WD_CACHE = paths.WIKIDATA_CACHE
EXTRACTS_STATE = "match-extracts.json"      # next to the candidates file

MATCH_COLUMNS = ["id", "line", "kind", "name", "de", "osm", "wikidata", "status",
                 "result", "match_name", "match_tags", "lon", "lat",
                 "candidates", "note"]

CLUSTER_KM = 3.0        # objects this close describe the same feature
SEPARATION_KM = 30.0    # a winner must be this far from every rival
BOUNDARY_QID_KM = 10.0  # a boundary further from a place node is a namesake

# `match_row`'s result for a row: its cells plus the MATCH_COLUMNS and
# osm_type / osm_id -- a line of work/matches.csv
MatchResult = dict[str, str]


class RankedCandidate(Candidate):
    """A candidate record with the best name-field rank (`NameIndex.lookup`)
    any of the row's names found it with."""
    rank: int


class Cluster(TypedDict):
    """Candidates that describe one feature, and their mean position (None
    when no member has a location)."""
    members: list[Candidate]
    lon: float | None
    lat: float | None


class PlacedCluster(Cluster):
    """A cluster and where it lies: against the row's location hint, and
    against North Frisia."""
    hint_ok: bool
    hint_d: float | None
    nf_d: float | None
    in_nf: bool

# -------------------------------------------------------- kind / tag rules ---
SETTLEMENT_PLACES = {"city", "town", "village", "hamlet", "isolated_dwelling",
                     "locality", "suburb", "neighbourhood", "borough",
                     "quarter", "farm", "municipality"}


def kind_ok(kind: str, tags: Mapping[str, str], cls: Sequence[str]) -> bool:
    place = tags.get("place")
    nat = tags.get("natural")
    bnd = tags.get("boundary")
    lvl = tags.get("admin_level")
    lu = tags.get("landuse")

    if kind == "settlement":
        if place in SETTLEMENT_PLACES:
            return True
        return bnd == "administrative" and lvl in ("6", "7", "8", "9", "10", "11")
    if kind == "koog":
        if place in SETTLEMENT_PLACES | {"polder"}:
            return True
        return bool(bnd in ("administrative", "protected_area") or lu
                    or nat in ("water", "wetland"))
    if kind == "harde":
        return bnd in ("historic", "political", "administrative") or place == "region"
    if kind in ("island", "hallig"):
        if place in ISLAND_PLACES or nat in ISLAND_PLACES | {"peninsula"}:
            return True
        if kind == "hallig" and place in SETTLEMENT_PLACES:
            return True
        return bnd == "administrative" and lvl in ("8", "9", "10", "11")
    if kind == "sand":
        return (nat in {"sand", "shoal", "beach", "mud", "reef", "wetland"}
                or place in ISLAND_PLACES | {"locality"})
    if kind == "warft":
        if place in {"isolated_dwelling", "farm", "locality", "hamlet",
                     "village", "neighbourhood"}:
            return True
        if lu in {"residential", "farmyard", "meadow"}:
            return True
        return bool(tags.get("man_made") or tags.get("historic"))
    if kind == "landscape":
        if place in {"region", "county", "state", "district", "province",
                     "island", "archipelago"}:
            return True
        if nat in {"peninsula", "ridge", "hill", "archipelago"}:
            return True
        return bnd in {"administrative", "historic", "political"}
    if kind == "water":
        if nat in {"water", "bay", "strait", "wetland", "spring", "sand"}:
            return True
        if tags.get("water") or tags.get("waterway"):
            return True
        return place == "sea" or bnd in {"maritime", "place"}
    if kind == "road":
        return bool(tags.get("highway"))
    if kind == "country":
        return bnd == "administrative" and lvl == "2"
    if kind == "helgoland":
        return bool(place or nat or tags.get("man_made") or tags.get("historic")
                    or tags.get("water") or tags.get("waterway"))
    return True                                   # kind == other


def is_waterway_relation(rec: Candidate) -> bool:
    """A `type=waterway` relation: the whole river, grouping its ways.  It
    carries no `waterway` tag of its own, so `kind_ok` does not take it for
    water."""
    return rec["t"] == "r" and rec["tags"].get("type") == "waterway"


def canonical(kind: str, cands: list[RankedCandidate]) -> list[RankedCandidate]:
    """Narrow a candidate set to the object(s) that really *are* the feature.

    Rivers are split into dozens of `waterway=river` ways spread over more than
    the clustering distance, and islands carry both a coastline way and several
    place nodes.  If OSM has the canonical object (a `type=waterway` relation,
    a `place=island` polygon, a `place=sea` relation), only that is considered.
    """
    if kind == "water":
        strong = [c for c in cands
                  if is_waterway_relation(c) or c["tags"].get("place") == "sea"]
        if strong:
            return strong
        strong = [c for c in cands
                  if c["t"] in ("w", "r")
                  and (c["tags"].get("natural") == "water"
                       or c["tags"].get("water"))]
        if strong:
            return strong
    elif kind in ("settlement", "warft", "koog"):
        strong = [c for c in cands if c["tags"].get("place")]
        if strong:
            return strong
    elif kind in ("island", "hallig", "sand"):
        strong = [c for c in cands
                  if c["t"] in ("w", "r")
                  and (c["tags"].get("place") in ISLAND_PLACES
                       or c["tags"].get("natural") in ISLAND_PLACES | {"peninsula"})]
        if strong:
            return strong
    return cands


def type_bonus(kind: str, rec: Candidate) -> int:
    t, tags = rec["t"], rec["tags"]
    place = tags.get("place")
    if kind in ("settlement", "warft", "koog"):
        # OpenMapTiles labels settlements from the place NODE
        if t == "n" and place:
            return 30
        if t == "r" and tags.get("boundary") == "administrative":
            return 12
        if t == "w" and place:
            return 8
        return 2
    if kind in ("island", "hallig", "sand"):
        if t in ("w", "r") and (place in ISLAND_PLACES
                                or tags.get("natural") in ISLAND_PLACES):
            return 30
        if t == "n" and place:
            return 18
        return 4
    if kind == "water":
        if t in ("w", "r") and (tags.get("natural") or tags.get("water")
                                or place == "sea"):
            return 25
        if tags.get("waterway"):
            return 20
        return 6
    if kind == "landscape":
        if t == "r" and (tags.get("boundary") or place):
            return 25
        if t == "n" and (place or tags.get("natural")):
            return 22
        return 6
    if kind == "road":
        return 20 if t == "w" else 4
    return 10 if t == "n" else 6


# --------------------------------------------------------------- wikidata ----
WD_API = "https://www.wikidata.org/w/api.php"
# Wikimedia's User-Agent policy wants a way to reach the operator
WD_USER_AGENT = ("frasch-maps name pipeline/0.1 (North Frisian map; "
                 "https://github.com/Commander-Cody/frasch-koord/issues)")
WD_COUNTRY_CLASSES = {"Q6256", "Q3624078", "Q1763527", "Q112099", "Q185441"}


def read_wikidata_cache(cache_path: str = WD_CACHE) -> dict[str, str]:
    """The cached lookups, `{German name: QID or ""}` (`""` = the lookup worked
    and found no country item).  A damaged file stops the run: starting from
    an empty cache would look like "not found" for every country offline."""
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError) as exc:
        raise PipelineError(f"{cache_path}: cannot read the Wikidata cache ({exc}) "
                         f"-- delete the file to query Wikidata afresh") from None
    if not (isinstance(cache, dict)
            and all(isinstance(k, str) and isinstance(v, str)
                    for k, v in cache.items())):
        raise PipelineError(f"{cache_path}: not a {{name: QID}} object -- delete "
                         f"the file to query Wikidata afresh")
    return cache


def _wikidata_country(session: requests.Session, name: str) -> str:
    """The QID of the country item Wikidata finds for a German name, `""` when
    it finds none.  Raises when the lookup itself fails -- that is not the same
    as "no such country" and must not clear a row."""
    r = session.get(WD_API, params={"action": "wbsearchentities", "search": name,
                                    "language": "de", "uselang": "de",
                                    "type": "item", "limit": "10",
                                    "format": "json"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "error" in data or "search" not in data:
        raise RuntimeError(f"wbsearchentities: {data.get('error') or data}")
    hits: list[str] = [h["id"] for h in data["search"]]
    if not hits:
        return ""
    r2 = session.get(WD_API, params={"action": "wbgetentities",
                                     "ids": "|".join(hits[:10]),
                                     "props": "claims|labels",
                                     "languages": "de",
                                     "format": "json"}, timeout=30)
    r2.raise_for_status()
    data = r2.json()
    if "error" in data or "entities" not in data:
        raise RuntimeError(f"wbgetentities: {data.get('error') or data}")
    ents = data["entities"]
    for h in hits:
        e = ents.get(h) or {}
        vals: set[str] = set()
        for c in e.get("claims", {}).get("P31", []):
            try:
                vals.add(c["mainsnak"]["datavalue"]["value"]["id"])
            except (KeyError, TypeError):
                pass                                 # novalue / somevalue
        if vals & WD_COUNTRY_CLASSES:
            return h
    return ""


def wikidata_countries(names: Iterable[str], cache_path: str = WD_CACHE,
                       offline: bool = False) -> tuple[dict[str, str], set[str]]:
    """German country name -> QID, via wbsearchentities + wbgetentities.

    -> (qids, failed): `qids[name]` is the QID, or `""` when Wikidata has no
    country item of that name; a name in `failed` has no answer at all (the
    lookup failed, or `offline` and not cached) -- its row must keep what it
    has."""
    cache = read_wikidata_cache(cache_path)
    todo = [n for n in dict.fromkeys(names) if n and n not in cache]
    failed: set[str] = set()
    if todo and offline:
        failed.update(todo)
    elif todo:
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = WD_USER_AGENT
        for name in todo:
            try:
                cache[name] = _wikidata_country(s, name)
            except Exception as exc:                 # network trouble, API error
                print(f"  wikidata lookup failed for {name}: {exc}", file=sys.stderr)
                failed.add(name)
                continue
            time.sleep(0.4)                          # be polite
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        files.atomic_write(cache_path, json.dumps(
            cache, ensure_ascii=False, indent=1, sort_keys=True))
    return cache, failed


# ------------------------------------------------------------------ match ----
def row_query_names(row: Row) -> list[str]:
    """The German names of the row; the Danish ones for Danish-only rows."""
    return variants(row.get("de")) or variants(row.get("da"))


MINOR_PLACES = {"hamlet", "isolated_dwelling", "locality", "farm",
                "neighbourhood", "suburb", "quarter"}
# these features exist only in North Frisia -- a match elsewhere is wrong
NF_ONLY_KINDS = {"koog", "hallig", "sand", "warft", "harde"}

CORE_MIN_KM = 1.0       # two settlement nodes this close are one village
CORE_PLACES = {"city", "town", "village", "hamlet", "isolated_dwelling",
               "suburb", "neighbourhood", "locality", "farm", "polder"}


def linear_radius(rec: Candidate) -> float | None:
    """How far apart two pieces of the same linear feature may be, or None."""
    if rec["t"] != "w":
        return None
    t = rec["tags"]
    if t.get("waterway"):
        return SEPARATION_KM          # a river runs for tens of kilometres
    if t.get("highway") or t.get("man_made") in ("dyke", "embankment"):
        return 5.0
    return None


def is_linear(rec: Candidate) -> bool:
    return linear_radius(rec) is not None


def is_core(rec: Candidate) -> bool:
    """A settlement node -- two of these more than CORE_MIN_KM apart are two
    different villages, however similar their names."""
    return rec["t"] == "n" and rec["tags"].get("place") in CORE_PLACES


def absorb_boundaries(kind: str, cands: list[RankedCandidate]
                      ) -> tuple[list[RankedCandidate], list[RankedCandidate]]:
    """Prefer the place NODE over its administrative boundary (that is what
    OpenMapTiles labels).  Returns (kept, dropped)."""
    if kind == "landscape":
        # for a landscape/Kreis the boundary usually *is* the feature -- only a
        # real place node (place=county/region/...) beats it
        if not any(c["t"] == "n" and c["tags"].get("place") for c in cands):
            return cands, []
    elif kind not in ("settlement", "warft", "koog", "hallig", "island",
                      "sand", "helgoland"):
        return cands, []            # Harden: the historic boundary is it
    kept: list[RankedCandidate] = []
    dropped: list[RankedCandidate] = []
    for c in cands:
        if c["tags"].get("boundary") == "administrative" and not c["tags"].get("place"):
            dropped.append(c)
        else:
            kept.append(c)
    return (kept or cands), dropped


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


def cluster(cands: Iterable[Candidate]) -> list[Cluster]:
    """Group candidates that describe the same feature.

    Point features merge within CLUSTER_KM; pieces of a linear feature (a river
    split into dozens of ways) merge within SEPARATION_KM; two `core` objects
    (two village nodes with the same name) never merge.
    Records without a location land in their own cluster.
    """
    groups: list[list[Candidate]] = []
    for c in cands:
        r = linear_radius(c) or CLUSTER_KM
        target: list[Candidate] | None = None
        for members in groups:
            for m in members:
                d = haversine(c["lon"], c["lat"], m["lon"], m["lat"])
                if d is None:
                    continue
                if is_core(c) and is_core(m):
                    rr = CORE_MIN_KM      # duplicate nodes of one village only
                else:
                    rr = max(r, linear_radius(m) or CLUSTER_KM)
                if d <= rr:
                    target = members
                    break
            if target:
                break
        if target is None:
            groups.append([c])
        else:
            target.append(c)
    return [_centred(members) for members in groups]


def _centred(members: list[Candidate]) -> Cluster:
    """The cluster of `members`, at their mean position."""
    pts = [(m["lon"], m["lat"]) for m in members
           if m["lon"] is not None and m["lat"] is not None]
    return {"members": members,
            "lon": sum(p[0] for p in pts) / len(pts) if pts else None,
            "lat": sum(p[1] for p in pts) / len(pts) if pts else None}


def fmt_cand(rec: Candidate, hint_pt: Circle | None = None) -> str:
    tags = rec["tags"]
    place = tags.get("place") or tags.get("natural") or tags.get("boundary") \
        or tags.get("waterway") or tags.get("landuse") or tags.get("man_made") \
        or tags.get("highway") or "-"
    d = haversine(rec["lon"], rec["lat"], *NF_CENTRE)
    ds = f"{d:.0f}" if d is not None else "?"
    nm = (tags.get("name") or tags.get("name:de") or "")[:40]
    return f'{rec["t"]}/{rec["id"]}:{nm}:{place}:{ds}'


def fmt_cands(cands: Iterable[RankedCandidate]) -> str:
    """The `candidates` cell: every candidate, best name hit first, then the
    nearest to North Frisia.  Not truncated -- the curation view needs all of
    them (a "Dorfstraße" has hundreds of ways); only REPORT.md shortens it."""
    def key(c: RankedCandidate) -> tuple[int, float, str, int]:
        d = haversine(c["lon"], c["lat"], *NF_CENTRE)
        return (c.get("rank", 99), 1e9 if d is None else d, c["t"], c["id"])
    return ";".join(fmt_cand(c) for c in sorted(cands, key=key))


def _decide(kind: str, plaus: Iterable[Candidate], hint_pt: Circle | None
            ) -> tuple[PlacedCluster | None, str, list[PlacedCluster]]:
    """-> (winner cluster or None, reason, clusters)"""
    clusters = [_placed(cl, hint_pt) for cl in cluster(plaus)]
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
        if all((haversine(cand["lon"], cand["lat"], c["lon"], c["lat"]) or 1e9)
               > SEPARATION_KM for c in clusters if c is not cand):
            return cand, "only candidate in North Frisia", clusters
    return None, "", clusters


def _placed(cl: Cluster, hint_pt: Circle | None) -> PlacedCluster:
    """`cl` with its distance to the location hint and to North Frisia."""
    hint_d = None
    hint_ok = False
    if hint_pt and cl["lon"] is not None:
        hint_d = haversine(cl["lon"], cl["lat"], hint_pt[0], hint_pt[1])
        hint_ok = hint_d is not None and hint_d <= hint_pt[2]
    return {**cl, "hint_ok": hint_ok, "hint_d": hint_d,
            "nf_d": haversine(cl["lon"], cl["lat"], *NF_CENTRE),
            "in_nf": in_north_frisia(cl["lon"], cl["lat"])}


def _suspicious(kind: str, winner: PlacedCluster) -> bool:
    """True if an otherwise clear winner is implausible for a North Frisian
    name list: a Koog/Warft/Hallig outside North Frisia, or a far-away minor
    place (hamlet, isolated dwelling, ...)."""
    if winner["in_nf"]:
        return False
    if kind in NF_ONLY_KINDS:
        return True
    minor = any(m["tags"].get("place") in MINOR_PLACES for m in winner["members"])
    return minor and (winner["nf_d"] or 1e9) > 50


def _outranks_a_hit_in_north_frisia(winner: PlacedCluster,
                                    weaker: Iterable[Candidate]) -> bool:
    """True if a winner outside North Frisia beat a weaker name hit inside it:
    the exact *Ostenfeld* is the village near Rendsburg, while OSM calls the
    one near Husum `Ostenfeld (Husum)`.  Which one the list means is for a
    human to decide."""
    if winner["in_nf"]:
        return False
    return any(in_north_frisia(c["lon"], c["lat"])
               for c in weaker if c not in winner["members"])


def _ambiguous_reason(row: Row, winner: PlacedCluster | None, hint_pt: Circle | None,
                      clusters: Sequence[PlacedCluster]) -> str:
    """Why `match_row` leaves a row for review."""
    if winner is None:
        if hint_pt:
            return f"location hint '{row['hint']}' matched no cluster"
        return f"{len(clusters)} plausible candidates"
    distance = f"{(winner['nf_d'] or 0):.0f} km from North Frisia"
    if _suspicious(row["kind"], winner):
        return f"only match is {distance} ({row['kind']}) -- verify by hand"
    return f"best name hit is {distance}, a weaker one lies inside -- verify by hand"


def match_row(row: Row, index: NameIndex, hints: HintResolver,
              claimed: Mapping[Ref, int] | None = None) -> MatchResult:
    """`claimed`: {(type, id): line} of the objects other rows hold that
    are not the matcher's to give away (see `claimed_objects`)."""
    claimed = claimed or {}
    kind = row["kind"]
    out = dict(row)
    out.update(osm_type="", osm_id="", match_name="", match_tags="",
               lon="", lat="", candidates="")
    if not any_name(row):
        out["status"] = "not_found"
        out["note"] = _addnote(row, "no Frisian name")
        return out

    queries = row_query_names(row)
    if not queries:
        out["status"] = "not_found"
        out["note"] = _addnote(row, "no German/Danish name to match on")
        return out

    best_rank: dict[OsmRef, int] = {}
    recs: dict[OsmRef, Candidate] = {}
    for q in queries:
        for rec, rank in index.lookup(q):
            key = osm_key(rec)
            recs[key] = rec
            if rank < best_rank.get(key, 99):
                best_rank[key] = rank
    cands: list[RankedCandidate] = [{**rec, "rank": best_rank[key]}
                                    for key, rec in recs.items()]
    taken = [c for c in cands if osm_key(c) in claimed]
    cands = [c for c in cands if osm_key(c) not in claimed]
    if not cands:
        out["status"] = "not_found"
        if taken:
            out["note"] = _addnote(row, taken_note(taken, claimed))
        return out

    plaus_all = [c for c in cands if kind_ok(kind, c["tags"], c["cls"])]
    if not plaus_all:
        # the German name exists in OSM, but only on streets / buildings /
        # bus stops -- the feature itself is not mapped.  Not a review task.
        out["status"] = "not_found"
        out["candidates"] = fmt_cands(cands)
        out["note"] = _addnote(row, f"{len(cands)} name match(es), none "
                                    f"compatible with kind={kind}")
        return out
    # set the boundaries aside first: canonical() would drop them, and their
    # wikidata is the fallback for a place node without one
    plaus_all, boundaries = absorb_boundaries(kind, plaus_all)
    plaus_all = canonical(kind, plaus_all)
    top = min(c["rank"] for c in plaus_all)
    plaus = [c for c in plaus_all if c["rank"] == top]

    hint_pt = hints.resolve(row.get("hint", "").split(";")[0].strip())

    winner, reason, clusters = _decide(kind, plaus, hint_pt)
    if winner is not None and _suspicious(kind, winner) and len(plaus_all) > len(plaus):
        # the best-ranked name hit is implausible -- reconsider the weaker hits
        # (OSM disambiguators such as "Kampen (Sylt)", German exonyms, ...)
        w2, r2, c2 = _decide(kind, plaus_all, hint_pt)
        if w2 is not None and not _suspicious(kind, w2):
            winner, reason, clusters, plaus = w2, r2 + " (weaker name hit)", c2, plaus_all

    weaker = [c for c in plaus_all if c["rank"] > top]
    if (winner is None or _suspicious(kind, winner)
            or (not hint_pt                        # a hint's pick is binding
                and _outranks_a_hit_in_north_frisia(winner, weaker))):
        out["status"] = "ambiguous"
        out["candidates"] = fmt_cands(plaus_all)
        out["note"] = _addnote(row, _ambiguous_reason(row, winner, hint_pt, clusters))
        return out

    held = [c for c in taken
            if (kind_ok(kind, c["tags"], c["cls"])
                or (kind == "water" and is_waterway_relation(c)))
            and len(cluster(winner["members"] + [c])) == 1]
    if held:
        # another row holds part of this very feature (a piece of the same
        # river, or the relation that is the whole river): the rest is not
        # free for a second name
        out["status"] = "not_found"
        out["candidates"] = fmt_cands(plaus_all)
        out["note"] = _addnote(row, taken_note(held, claimed))
        return out

    best = max(winner["members"],
               key=lambda r: (type_bonus(kind, r)
                              + (8 if r["tags"].get("wikidata") else 0)
                              + (4 if r["tags"].get("name:de") else 0)
                              - ((haversine(r["lon"], r["lat"], *NF_CENTRE) or 500) / 200)))
    qid = best["tags"].get("wikidata", "")
    if not qid:      # fall back to a sibling's / the boundary relation's wikidata
        qid = next((r["tags"]["wikidata"] for r in winner["members"]
                    if r["tags"].get("wikidata")), "") or boundary_qid(best, boundaries)
    # a linear feature (river, dyke, street) is split into many ways -- tag all
    # of them, otherwise only a fragment of the river gets the Frisian label
    ids = [str(best["id"])]
    if is_linear(best):
        bn = norm(best["tags"].get("name", ""))
        ids = sorted({str(m["id"]) for m in winner["members"]
                      if m["t"] == best["t"] and is_linear(m)
                      and norm(m["tags"].get("name", "")) == bn}, key=int)
    out.update(
        osm_type=placelist.TYPE_NAME[best["t"]],
        osm_id=";".join(ids),
        match_name=best["tags"].get("name") or best["tags"].get("name:de", ""),
        match_tags=decisive_tags(best),
        lon="" if best["lon"] is None else f'{best["lon"]:.6f}',
        lat="" if best["lat"] is None else f'{best["lat"]:.6f}',
        wikidata=qid,
        status="matched",
    )
    if len(winner["members"]) > 1 or len(clusters) > 1:
        out["candidates"] = fmt_cands(plaus)
    out["note"] = _addnote(row, f"auto: {reason}") if reason != "single cluster" \
        else _addnote(row, "")
    return out


def report_cands(cell: str, limit: int = 20) -> str:
    """A `candidates` cell shortened for REPORT.md (the full list is in
    work/matches.csv and the curation view)."""
    parts = [p for p in (cell or "").split(";") if p]
    if len(parts) <= limit:
        return ";".join(parts)
    return ";".join(parts[:limit]) + f";... (+{len(parts) - limit} more)"


def _addnote(row: Row, txt: str) -> str:
    """Machine remarks go to work/matches.csv and the report, never into
    places.csv (whose `note` column belongs to the owner)."""
    return txt


def taken_note(recs: Iterable[Candidate], claimed: Mapping[Ref, int]) -> str:
    """`way/1 is taken by line 7; ...` for the candidates other rows hold."""
    return "; ".join(f"{format_osm([osm_key(c)])} is taken by line "
                     f"{claimed[osm_key(c)]}" for c in recs)


def claimed_objects(rows: Iterable[PlaceRow]) -> dict[Ref, int]:
    """{(type, id): line} of the OSM objects that rows the matcher does not
    own hold (checked or hand-filled).  It never gives them to another row:
    only one name per object can reach the map."""
    out: dict[Ref, int] = {}
    for r in rows:
        if owned_by_matcher(r):
            continue
        for key in placelist.claimed_refs(r):
            out.setdefault(key, r.line)
    return out


def find_duplicates(rows: Iterable[PlaceRow]) -> dict[Ref, list[PlaceRow]]:
    """Two rows pointing at one OSM object -- usually the list has a place
    twice (two spellings, or two rows from different sheet sections).  Only one of the names can end
    up on the map."""
    by_obj: collections.defaultdict[Ref, list[PlaceRow]] = collections.defaultdict(list)
    for r in rows:
        for key in placelist.claimed_refs(r):
            by_obj[key].append(r)
    return {k: g for k, g in by_obj.items() if len(g) > 1}


# --------------------------------------------------------------- extracts ----
def read_used_extracts(path: str) -> list[ExtractStamp] | None:
    """The extracts the last real run matched against, as the candidates
    header lists them; None before the first such run."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        extracts: list[ExtractStamp] = json.load(fh)["extracts"]
    return extracts


def record_used_extracts(path: str, extracts: Sequence[ExtractStamp]) -> None:
    files.atomic_write(path, json.dumps({"extracts": extracts},
                                            ensure_ascii=False, indent=1) + "\n")


def extract_set_warning(previous: Iterable[ExtractStamp],
                        current: Iterable[ExtractStamp]) -> str | None:
    """The warning for a changed set of extract files, or None.  Only the
    file names count: a refreshed download of the same extract is expected."""
    before = {e["file"] for e in previous}
    now = {e["file"] for e in current}
    if before == now:
        return None
    parts = []
    if now - before:
        parts.append("added: " + ", ".join(sorted(now - before)))
    if before - now:
        parts.append("dropped: " + ", ".join(sorted(before - now)) + " -- `auto` "
                     "rows matched only in a dropped extract get cleared")
    return ("warning: the candidates come from other extracts than the last "
            "match.py run; " + "; ".join(parts)
            + ". Rebuild them with build_candidates.py from every extract "
              "unless that is intended.")


def check_extracts(candidates_path: str, state_path: str) -> list[ExtractStamp] | None:
    """Print the extracts behind the candidates, warn about a changed set, and
    return them (None for a file from before the header)."""
    extracts = candidates.read_header(candidates_path)
    if extracts is None:
        print(f"warning: {candidates_path} names no extracts (written before "
              f"it had a header) -- rebuild it with build_candidates.py",
              file=sys.stderr)
        return None
    print("candidates from " + ", ".join(
        f"{e['file']} ({e['replication_timestamp'] or 'no timestamp'})"
        for e in extracts))
    previous = read_used_extracts(state_path)
    if previous is not None:
        warning = extract_set_warning(previous, extracts)
        if warning:
            print(warning, file=sys.stderr)
    return extracts


# ----------------------------------------------------------------- report ----
def write_report(rows: Sequence[PlaceRow], results: Mapping[str, MatchResult],
                 path: str = REPORT_PATH) -> None:
    """`results` maps a row's id to its match_row() output (only for the rows
    the matcher owns).  The report depends on these alone -- no date, no run
    time -- so a run on unchanged inputs leaves the tracked file as it was."""
    def state(r: Row) -> str:
        if r["kind"] == "not_a_place":
            return "not a place"
        if r["status"] == "skip":
            return "skip"
        if not any_name(r):
            return "no Frisian name"
        if local_ref(r["osm"]):
            return "own point"
        if r["osm"] or r["wikidata"]:
            return "auto" if r["status"] == "auto" else "by hand"
        res = results.get(r["id"])
        return "ambiguous" if res and res["status"] == "ambiguous" else "not found"

    states = ["auto", "by hand", "own point", "ambiguous", "not found", "skip",
              "no Frisian name", "not a place"]
    by_kind: collections.defaultdict[str, collections.Counter[str]] = \
        collections.defaultdict(collections.Counter)
    total: collections.Counter[str] = collections.Counter()
    for r in rows:
        st = state(r)
        by_kind[r["kind"]][st] += 1
        total[st] += 1

    def ref(r: PlaceRow) -> str:
        return f"{r['id']} | {r.line} | {r['kind']} | {any_name(r)} | {primary(r['de']) or primary(r['da'])}"

    L = []
    L.append("# Name matching report\n")
    L.append(f"Generated by `names/match.py` from `names/places.csv` ({len(rows)} rows). "
             "`id` is the row's `id` cell, `line` its line number in that file.\n")
    L.append("Hand-review worklist: for every **ambiguous** row below pick the right "
             "object and write it into the `osm` column of `names/places.csv` "
             "(`node/123`, `way/123`, `relation/123`); for the **not found** rows "
             "look the feature up on openstreetmap.org yourself. Put `ok` in "
             "`status` when you have checked a row (or leave it empty), `skip` when "
             "the row must never be put on the map. `match.py` only ever rewrites "
             "rows with `status=auto` or with empty `osm`/`wikidata` cells. "
             "**own point** rows carry a local reference (`local/<slug>`, a place "
             "OSM does not have, positioned in `names/curation.csv`) and are never "
             "touched.\n")
    L.append("## Counts\n")
    L.append("| kind | " + " | ".join(states) + " | total |")
    L.append("|---|" + "---:|" * (len(states) + 1))
    for kind in dict.fromkeys(r["kind"] for r in rows):
        c = by_kind[kind]
        L.append(f"| {kind} | " + " | ".join(str(c.get(s, 0)) for s in states)
                 + f" | {sum(c.values())} |")
    L.append("| **total** | " + " | ".join(f"**{total.get(s, 0)}**" for s in states)
             + f" | **{len(rows)}** |\n")

    amb = [r for r in rows if state(r) == "ambiguous"]
    L.append(f"## Ambiguous ({len(amb)})\n")
    L.append("`candidates` format: `type/id:name:class:km-from-NF-centre`\n")
    L.append("| id | line | kind | Frisian | German | hint | why | candidates |")
    L.append("|---|---:|---|---|---|---|---|---|")
    for r in amb:
        res = results[r["id"]]
        L.append(f"| {ref(r)} | {r['hint']} | {res.get('note', '')} "
                 f"| `{report_cands(res.get('candidates', ''))}` |")
    L.append("")

    dups = find_duplicates(rows)
    L.append(f"## Rows sharing one OSM object ({len(dups)})\n")
    L.append("The list has these places twice (two spellings, or rows from two "
             "sheet sections). Only one name can be injected -- the first row wins; "
             "decide which, and `skip` the other.\n")
    L.append("| OSM object | rows (line) | Frisian names | German |")
    L.append("|---|---|---|---|")
    for key, g in sorted(dups.items(), key=lambda kv: kv[1][0].line):
        L.append(f"| `{format_osm([key])}` | "
                 + ", ".join(f"{x['id']} ({x.line})" for x in g)
                 + " | " + ", ".join(any_name(x) for x in g)
                 + f" | {primary(g[0]['de'])} |")
    L.append("")

    nf = [r for r in rows if state(r) == "not found"]
    L.append(f"## Not found ({len(nf)})\n")
    L.append("Either the feature is not in OSM at all, or OSM spells it "
             "differently. `near misses` lists objects that do carry the German "
             "name but are the wrong kind of thing (a street, a bus stop, a "
             "building) -- occasionally one of them is still the right answer.\n")
    L.append("| id | line | kind | Frisian | German | note | near misses |")
    L.append("|---|---:|---|---|---|---|---|")
    for r in nf:
        res = results.get(r["id"], {})
        cands = f"`{res.get('candidates', '')[:200]}`" if res.get("candidates") else ""
        L.append(f"| {ref(r)} | {res.get('note', '')} | {cands} |")
    L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def write_matches(rows: Iterable[PlaceRow], results: Mapping[str, MatchResult],
                  index: NameIndex, path: str = MATCH_PATH) -> None:
    """work/matches.csv: one line per places.csv row, with the match details
    (and lon/lat also for rows a human filled in, looked up by id)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MATCH_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            res = results.get(r["id"])
            refs = osm_refs(r["osm"])
            hit = index.by_key.get(refs[0]) if refs else None
            rec = {"id": r["id"], "line": str(r.line), "kind": r["kind"],
                   "name": any_name(r),
                   "de": primary(r["de"]), "osm": r["osm"],
                   "wikidata": r["wikidata"], "status": r["status"]}
            if res is not None:
                rec.update(result=res["status"], match_name=res.get("match_name", ""),
                           match_tags=res.get("match_tags", ""), lon=res.get("lon", ""),
                           lat=res.get("lat", ""), candidates=res.get("candidates", ""),
                           note=res.get("note", ""))
            else:
                rec["result"] = "skip" if r["status"] == "skip" else \
                    "not a place" if r["kind"] == "not_a_place" else \
                    "own point" if local_ref(r["osm"]) else \
                    "by hand" if (r["osm"] or r["wikidata"]) else ""
                if hit is not None:
                    rec.update(match_name=hit["tags"].get("name", ""),
                               match_tags=decisive_tags(hit),
                               lon="" if hit["lon"] is None else f'{hit["lon"]:.6f}',
                               lat="" if hit["lat"] is None else f'{hit["lat"]:.6f}')
            w.writerow(rec)


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=CSV_PATH)
    ap.add_argument("--candidates", default=CAND_PATH)
    ap.add_argument("--matches", default=MATCH_PATH)
    ap.add_argument("--report", default=REPORT_PATH)
    ap.add_argument("--offline", action="store_true",
                    help="do not call the Wikidata API (use the cache only)")
    ap.add_argument("--wikidata-cache", default=WD_CACHE,
                    help="country lookups already made (default: %(default)s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="write only work/matches.csv (git-ignored); leave "
                         "places.csv and REPORT.md alone")
    ap.add_argument("--extracts-state",
                    help="the extracts the last run used (default: "
                         f"{EXTRACTS_STATE} next to --candidates)")
    args = ap.parse_args(argv)
    if args.extracts_state is None:
        args.extracts_state = os.path.join(
            os.path.dirname(os.path.abspath(args.candidates)), EXTRACTS_STATE)

    with placelist.lock(args.names):
        return run(args)


def run(args: argparse.Namespace) -> int:
    t0 = time.time()
    rows, fields = placelist.read(args.names)
    print(f"loaded {len(rows)} rows from {args.names}")

    extracts = check_extracts(args.candidates, args.extracts_state)
    index = NameIndex(candidates.read_records(args.candidates))
    print(f"indexed {len(index.recs):,} candidates / "
          f"{len(index.by_name):,} distinct normalised names "
          f"({time.time()-t0:.0f}s)")
    hints = HintResolver(index)

    todo = [r for r in rows if owned_by_matcher(r) and any_name(r)]
    claimed = claimed_objects(rows)
    country_rows = [r for r in todo if r["kind"] == "country"]
    qids, wd_failed = wikidata_countries([primary(r["de"]) for r in country_rows],
                                         cache_path=args.wikidata_cache,
                                         offline=args.offline)
    unresolved: list[PlaceRow] = []

    results: dict[str, MatchResult] = {}
    changed: collections.Counter[str] = collections.Counter()
    for r in todo:
        before = (r["osm"], r["wikidata"], r["status"])
        if r["kind"] == "country" and primary(r["de"]) in wd_failed:
            # no answer is not "no country": leave the row as it is
            unresolved.append(r)
            results[r["id"]] = dict(
                r, osm_type="", osm_id="", candidates="", match_tags="",
                match_name="", lon="", lat="", status="lookup_failed",
                note="Wikidata lookup failed -- row left unchanged")
            continue
        if r["kind"] == "country":
            qid = qids.get(primary(r["de"]), "")
            o = dict(r, osm_type="", osm_id="", candidates="", match_tags="",
                     match_name="", lon="", lat="")
            if qid:
                o.update(wikidata=qid, status="matched", match_name=primary(r["de"]),
                         match_tags="wikidata", note="auto: wikidata")
            else:
                o.update(wikidata="", status="not_found",
                         note="no Wikidata country item found")
        else:
            o = match_row(r, index, hints, claimed)
        results[r["id"]] = o
        if o["status"] == "matched":
            r["osm"] = format_osm(parse_osm(
                "; ".join(f"{o['osm_type']}/{i}" for i in o["osm_id"].split(";") if i)))
            r["wikidata"] = o["wikidata"]
            r["status"] = "auto"
        else:                                  # lost / never had a match
            r["osm"], r["wikidata"], r["status"] = "", "", ""
        after = (r["osm"], r["wikidata"], r["status"])
        if after != before:
            changed["filled" if after[2] == "auto" and before[2] != "auto"
                    else "cleared" if before[2] == "auto" and not after[2]
                    else "changed"] += 1

    if not args.dry_run:
        placelist.write(rows, args.names, fields)
        write_report(rows, results, args.report)
        if extracts is not None:
            record_used_extracts(args.extracts_state, extracts)
    write_matches(rows, results, index, args.matches)

    cnt = collections.Counter(o["status"] for o in results.values())
    print(f"matcher owns {len(todo)} of {len(rows)} rows: "
          + ", ".join(f"{v} {k}" for k, v in cnt.most_common()))
    print(f"places.csv: {changed['filled']} rows filled, {changed['cleared']} cleared, "
          f"{changed['changed']} changed"
          + (" (dry run -- not written)" if args.dry_run else ""))
    print("wrote", args.matches, *(() if args.dry_run else ("and", args.report)))
    print(f"done in {time.time()-t0:.0f}s")
    if unresolved:
        print(f"error: no Wikidata answer for {len(unresolved)} country row(s) "
              + ("(--offline and not in the cache)" if args.offline
                 else "(lookup failed, see above)")
              + " -- left unchanged: "
              + ", ".join(placelist.describe(r) for r in unresolved), file=sys.stderr)
        return 1
    return 0

