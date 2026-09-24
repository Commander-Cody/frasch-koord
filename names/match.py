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
                          decisive tags, lon/lat and the OSM object's Low Saxon
                          name (both used by export_search_index.py),
                          the candidate list of ambiguous rows.  Git-ignored.
  names/REPORT.md         the hand-review worklist.

Ranking / decision
  1. keep only candidates whose tags are compatible with the row's `kind`
  2. cluster the survivors geographically (30 km)
  3. `matched`   - one cluster, or exactly one cluster satisfies the row's
                   location hint, or exactly one cluster is inside North Frisia
                   while every other cluster is far away
     `ambiguous` - several plausible clusters (all candidates are listed in the
                   `candidates` column: type/id:name:place:dist_km)
     `not_found` - no name match at all
  Countries are resolved through the Wikidata API instead of OSM.

Run:  .venv/bin/python names/match.py
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import re
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import placelist  # noqa: E402
from placelist import any_name, format_osm, label, local_ref, parse_osm, primary, variants  # noqa: E402

CSV_PATH = placelist.DEFAULT_PATH
CAND_PATH = os.path.join(HERE, "work", "candidates.jsonl")
MATCH_PATH = os.path.join(HERE, "work", "matches.csv")
REPORT_PATH = os.path.join(HERE, "REPORT.md")
WD_CACHE = os.path.join(HERE, "work", "wikidata-countries.json")

MATCH_COLUMNS = ["line", "kind", "name", "de", "osm", "wikidata", "status",
                 "result", "match_name", "match_tags", "lon", "lat",
                 "name_nds", "candidates", "note"]

NF_CENTRE = (8.9, 54.7)                      # lon, lat
NF_BBOX = (7.8, 54.15, 9.55, 55.12)   # North Frisia incl. Helgoland
CLUSTER_KM = 3.0        # objects this close describe the same feature
SEPARATION_KM = 30.0    # a winner must be this far from every rival
HINT_KM = 8.0           # a village-sized hint
HINT_KM_ISLAND = 10.0   # a Hallig / small island
HINT_KM_LARGE = 25.0    # Sylt, Foehr, Eiderstedt, a Harde ...

# name tag -> how trustworthy an exact hit on it is (lower = better).  A hit on
# the OSM `name` itself beats a hit on `name:de`, which beats alt/old names:
# otherwise the Danish village Holme (name:de=Holm) outranks the North Frisian
# village Holm (name=Holm).
NAME_FIELD_RANK = {
    "name": 0, "name:de": 1, "official_name": 2, "name:da": 2,
    "short_name": 2,        # Stadt Wyk auf Föhr: short_name=Wyk
    "alt_name": 4, "old_name": 4,
}
NAME_FIELDS = tuple(NAME_FIELD_RANK)

# ----------------------------------------------------------- normalisation ---
_UML = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue",
        "ß": "ss", "å": "aa", "Å": "aa", "ø": "oe", "Ø": "oe", "æ": "ae",
        "Æ": "ae", "é": "e", "è": "e", "á": "a", "à": "a"}


def norm(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    out = []
    for ch in s:
        out.append(_UML.get(ch, ch))
    s = "".join(out)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\-–—_/\.'`’]+", " ", s)
    s = re.sub(r"[^\w ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_PAREN_SUFFIX = re.compile(r"^(.+?)\s*\([^()]*\)\s*$")
# generic type words OSM puts in front of the actual name
_TYPE_PREFIX = re.compile(
    r"^(?:Kreis|Amt|Stadt|Gemeinde|Hallig|Insel|Landkreis|Flecken)\s+(.+)$")
# the island OSM appends to a place name: `Wyk auf Föhr`, `List auf Sylt`,
# `Norddorf auf Amrum` -- the list writes plain `Wyk`
_AUF_SUFFIX = re.compile(r"^(.+?)\s+auf\s+\S.*$")


def split_name_values(v: str):
    """Variants of one OSM name value, as (value, extra rank penalty).

    * multilingual slash lists: `North Sea / Nordsee / Noordzee`
    * OSM's own disambiguators: `Kampen (Sylt)`, `Lister Tief (Sylt Nord)`,
      `Wyk auf Föhr` -- indexed with a penalty so a plain exact hit always
      wins.
    """
    vals = [(v, 0)]
    if " / " in v:
        vals += [(p.strip(), 0) for p in v.split(" / ")]
    if ";" in v:
        vals += [(p.strip(), 0) for p in v.split(";")]
    for x, _ in list(vals):
        m = _PAREN_SUFFIX.match(x)
        if m:
            vals.append((m.group(1).strip(), 2))
        m = _TYPE_PREFIX.match(x)
        if m:
            vals.append((m.group(1).strip(), 2))
        m = _AUF_SUFFIX.match(x)
        if m:
            vals.append((m.group(1).strip(), 2))
    return [(x, pen) for x, pen in vals if x]


def haversine(lon1, lat1, lon2, lat2):
    if None in (lon1, lat1, lon2, lat2):
        return None
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# -------------------------------------------------------- kind / tag rules ---
SETTLEMENT_PLACES = {"city", "town", "village", "hamlet", "isolated_dwelling",
                     "locality", "suburb", "neighbourhood", "borough",
                     "quarter", "farm", "municipality"}
ISLAND_PLACES = {"island", "islet", "archipelago"}


def kind_ok(kind, tags, cls):
    place = tags.get("place")
    nat = tags.get("natural")
    bnd = tags.get("boundary")
    lvl = tags.get("admin_level")
    lu = tags.get("landuse")
    name_l = (tags.get("name") or "").lower()

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


def canonical(kind, cands):
    """Narrow a candidate set to the object(s) that really *are* the feature.

    Rivers are split into dozens of `waterway=river` ways spread over more than
    the clustering distance, and islands carry both a coastline way and several
    place nodes.  If OSM has the canonical object (a `type=waterway` relation,
    a `place=island` polygon, a `place=sea` relation), only that is considered.
    """
    if kind == "water":
        strong = [c for c in cands
                  if (c["t"] == "r" and c["tags"].get("type") == "waterway")
                  or c["tags"].get("place") == "sea"]
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


def type_bonus(kind, rec):
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


# ------------------------------------------------------------------ index ----
class Index:
    def __init__(self, path):
        self.recs = []
        self.by_name = collections.defaultdict(dict)   # norm -> {rec_idx: rank}
        self.by_key = {}                               # (t, id) -> rec
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                i = len(self.recs)
                self.recs.append(rec)
                self.by_key[(rec["t"], rec["id"])] = rec
                for k, rank in NAME_FIELD_RANK.items():
                    v = rec["tags"].get(k)
                    if not v:
                        continue
                    for part, penalty in split_name_values(v):
                        n = norm(part)
                        if not n:
                            continue
                        d = self.by_name[n]
                        if rank + penalty < d.get(i, 99):
                            d[i] = rank + penalty

    def lookup(self, name):
        """-> [(record, name-field rank)]"""
        n = norm(name)
        if not n:
            return []
        return [(self.recs[i], r) for i, r in self.by_name.get(n, {}).items()]


# ------------------------------------------------------------------ hints ----
# Fallback centroids for hints that OSM does not carry as an object
# (the historic Harden) or that are spelled differently in the sheet.
HINT_FALLBACK = {
    "karrharde": (9.02, 54.80, 15.0),
    "boekingharde": (8.85, 54.77, 15.0),
    "wiedingharde": (8.72, 54.88, 12.0),
    "beltringharde": (8.93, 54.58, 12.0),
    "boekingharde osterdeich": (8.85, 54.77, 15.0),
    "nordmarsch": (8.56, 54.63, 6.0),
    "butweel": (8.60, 54.63, 6.0),
    "luett moor": (8.83, 54.55, 6.0),
    "uthlande": (8.60, 54.65, 40.0),
    "dreiharde eck": (8.87, 54.80, 10.0),
    "st peter": (8.640, 54.306, 10.0),
    "sankt peter": (8.640, 54.306, 10.0),
}
# big enough that "X lies on Y" only narrows things down to ~25 km
LARGE_HINTS = {"sylt", "foehr", "amrum", "eiderstedt", "pellworm", "nordstrand",
               "nordfriesland", "dithmarschen", "angeln"}


class HintResolver:
    def __init__(self, index: Index):
        self.index = index
        self.cache = {}

    def resolve(self, hint: str):
        """-> (lon, lat, radius_km) or None"""
        key = norm(hint)
        if not key:
            return None
        if key in self.cache:
            return self.cache[key]
        res = None
        if key in HINT_FALLBACK:
            res = HINT_FALLBACK[key]
        else:
            best, bestscore = None, -1e9
            for rec, _rank in self.index.lookup(hint):
                tags = rec["tags"]
                if not (tags.get("place") or tags.get("natural")
                        or tags.get("boundary") == "administrative"):
                    continue
                if rec["lon"] is None:
                    continue
                d = haversine(rec["lon"], rec["lat"], *NF_CENTRE) or 999
                sc = -d
                if tags.get("place") in ISLAND_PLACES or tags.get("natural") == "peninsula":
                    sc += 40
                if tags.get("place") in ("village", "town", "city", "hamlet"):
                    sc += 30
                if sc > bestscore:
                    best, bestscore = rec, sc
            if best is not None:
                if key in LARGE_HINTS:
                    radius = HINT_KM_LARGE
                elif (best["tags"].get("place") in ISLAND_PLACES
                      or best["tags"].get("natural") in ("island", "islet",
                                                         "peninsula")
                      or best["tags"].get("place") == "region"):
                    radius = HINT_KM_ISLAND
                else:
                    radius = HINT_KM
                res = (best["lon"], best["lat"], radius)
        self.cache[key] = res
        return res


# --------------------------------------------------------------- wikidata ----
def wikidata_countries(names, cache_path=WD_CACHE, offline=False):
    """German country name -> QID, via wbsearchentities + wbgetentities."""
    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path, encoding="utf-8"))
        except Exception:
            cache = {}
    todo = [n for n in names if n and n not in cache]
    if todo and not offline:
        import requests
        s = requests.Session()
        s.headers["User-Agent"] = (
            "frasch-maps name pipeline/0.1 (North Frisian map; "
            "https://github.com/ - contact via repo owner)")
        API = "https://www.wikidata.org/w/api.php"
        COUNTRY_CLASSES = {"Q6256", "Q3624078", "Q1763527", "Q112099", "Q185441"}
        for name in todo:
            qid = ""
            try:
                r = s.get(API, params={"action": "wbsearchentities", "search": name,
                                       "language": "de", "uselang": "de",
                                       "type": "item", "limit": 10,
                                       "format": "json"}, timeout=30)
                hits = [h["id"] for h in r.json().get("search", [])]
                if hits:
                    r2 = s.get(API, params={"action": "wbgetentities",
                                            "ids": "|".join(hits[:10]),
                                            "props": "claims|labels",
                                            "languages": "de",
                                            "format": "json"}, timeout=30)
                    ents = r2.json().get("entities", {})
                    for h in hits:
                        e = ents.get(h) or {}
                        p31 = e.get("claims", {}).get("P31", [])
                        vals = set()
                        for c in p31:
                            try:
                                vals.add(c["mainsnak"]["datavalue"]["value"]["id"])
                            except Exception:
                                pass
                        if vals & COUNTRY_CLASSES:
                            qid = h
                            break
            except Exception as exc:                     # network trouble
                print(f"  wikidata lookup failed for {name}: {exc}", file=sys.stderr)
                continue
            cache[name] = qid
            time.sleep(0.4)                              # be polite
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(cache, open(cache_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, sort_keys=True)
    return cache


# ------------------------------------------------------------------ match ----
def row_query_names(row):
    """The German names of the row; the Danish ones for Danish-only rows."""
    return variants(row.get("de")) or variants(row.get("da"))


MINOR_PLACES = {"hamlet", "isolated_dwelling", "locality", "farm",
                "neighbourhood", "suburb", "quarter"}
# these features exist only in North Frisia -- a match elsewhere is wrong
NF_ONLY_KINDS = {"koog", "hallig", "sand", "warft", "harde"}

CORE_MIN_KM = 1.0       # two settlement nodes this close are one village
CORE_PLACES = {"city", "town", "village", "hamlet", "isolated_dwelling",
               "suburb", "neighbourhood", "locality", "farm", "polder"}


def linear_radius(rec):
    """How far apart two pieces of the same linear feature may be, or None."""
    if rec["t"] != "w":
        return None
    t = rec["tags"]
    if t.get("waterway"):
        return SEPARATION_KM          # a river runs for tens of kilometres
    if t.get("highway") or t.get("man_made") in ("dyke", "embankment"):
        return 5.0
    return None


def is_linear(rec):
    return linear_radius(rec) is not None


def is_core(rec):
    """A settlement node -- two of these more than CORE_MIN_KM apart are two
    different villages, however similar their names."""
    return rec["t"] == "n" and rec["tags"].get("place") in CORE_PLACES


def absorb_boundaries(kind, cands):
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
    kept, dropped = [], []
    for c in cands:
        if c["tags"].get("boundary") == "administrative" and not c["tags"].get("place"):
            dropped.append(c)
        else:
            kept.append(c)
    return (kept or cands), dropped


def cluster(cands):
    """Group candidates that describe the same feature.

    Point features merge within CLUSTER_KM; pieces of a linear feature (a river
    split into dozens of ways) merge within SEPARATION_KM; two `core` objects
    (two village nodes with the same name) never merge.
    Records without a location land in their own cluster.
    """
    clusters = []
    for c in cands:
        r = linear_radius(c) or CLUSTER_KM
        target = None
        for cl in clusters:
            for m in cl["members"]:
                d = haversine(c["lon"], c["lat"], m["lon"], m["lat"])
                if d is None:
                    continue
                if is_core(c) and is_core(m):
                    rr = CORE_MIN_KM      # duplicate nodes of one village only
                else:
                    rr = max(r, linear_radius(m) or CLUSTER_KM)
                if d <= rr:
                    target = cl
                    break
            if target:
                break
        if target is None:
            clusters.append({"members": [c]})
        else:
            target["members"].append(c)
    for cl in clusters:
        pts = [(m["lon"], m["lat"]) for m in cl["members"] if m["lon"] is not None]
        cl["lon"] = sum(p[0] for p in pts) / len(pts) if pts else None
        cl["lat"] = sum(p[1] for p in pts) / len(pts) if pts else None
    return clusters


def fmt_cand(rec, hint_pt=None):
    tags = rec["tags"]
    place = tags.get("place") or tags.get("natural") or tags.get("boundary") \
        or tags.get("waterway") or tags.get("landuse") or tags.get("man_made") \
        or tags.get("highway") or "-"
    d = haversine(rec["lon"], rec["lat"], *NF_CENTRE)
    ds = f"{d:.0f}" if d is not None else "?"
    nm = (tags.get("name") or tags.get("name:de") or "")[:40]
    return f'{rec["t"]}/{rec["id"]}:{nm}:{place}:{ds}'


def fmt_cands(cands):
    """The `candidates` cell: every candidate, best name hit first, then the
    nearest to North Frisia.  Not truncated -- the curation view needs all of
    them (a "Dorfstraße" has hundreds of ways); only REPORT.md shortens it."""
    def key(c):
        d = haversine(c["lon"], c["lat"], *NF_CENTRE)
        return (c.get("rank", 99), 1e9 if d is None else d, c["t"], c["id"])
    return ";".join(fmt_cand(c) for c in sorted(cands, key=key))


def decisive_tags(rec):
    tags = rec["tags"]
    keys = ("place", "natural", "water", "waterway", "boundary", "admin_level",
            "landuse", "man_made", "historic", "highway", "type")
    return ";".join(f"{k}={tags[k]}" for k in keys if k in tags)


def _decide(kind, plaus, hint_pt):
    """-> (winner cluster or None, reason, clusters)"""
    clusters = cluster(plaus)
    for cl in clusters:
        cl["hint_ok"] = False
        cl["hint_d"] = None
        if hint_pt and cl["lon"] is not None:
            d = haversine(cl["lon"], cl["lat"], hint_pt[0], hint_pt[1])
            cl["hint_d"] = d
            cl["hint_ok"] = d is not None and d <= hint_pt[2]
        cl["nf_d"] = haversine(cl["lon"], cl["lat"], *NF_CENTRE)
        cl["in_nf"] = (cl["lon"] is not None
                       and NF_BBOX[0] <= cl["lon"] <= NF_BBOX[2]
                       and NF_BBOX[1] <= cl["lat"] <= NF_BBOX[3])
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


def _suspicious(kind, winner):
    """True if an otherwise clear winner is implausible for a North Frisian
    name list: a Koog/Warft/Hallig outside North Frisia, or a far-away minor
    place (hamlet, isolated dwelling, ...)."""
    if winner["in_nf"]:
        return False
    if kind in NF_ONLY_KINDS:
        return True
    minor = any(m["tags"].get("place") in MINOR_PLACES for m in winner["members"])
    return minor and (winner["nf_d"] or 1e9) > 50


def match_row(row, index: Index, hints: HintResolver):
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

    best_rank, recs = {}, {}
    for q in queries:
        for rec, rank in index.lookup(q):
            key = (rec["t"], rec["id"])
            recs[key] = rec
            if rank < best_rank.get(key, 99):
                best_rank[key] = rank
    cands = []
    for key, rec in recs.items():
        rec = dict(rec)
        rec["rank"] = best_rank[key]
        cands.append(rec)
    if not cands:
        out["status"] = "not_found"
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
    plaus_all = canonical(kind, plaus_all)
    plaus_all, boundaries = absorb_boundaries(kind, plaus_all)
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

    if winner is None or _suspicious(kind, winner):
        out["status"] = "ambiguous"
        out["candidates"] = fmt_cands(plaus_all)
        if winner is not None:
            out["note"] = _addnote(
                row, f"only match is {(winner['nf_d'] or 0):.0f} km from North "
                     f"Frisia ({kind}) -- verify by hand")
        elif hint_pt:
            out["note"] = _addnote(row, f"location hint "
                                        f"'{row['hint']}' matched no cluster")
        else:
            out["note"] = _addnote(row, f"{len(clusters)} plausible candidates")
        return out

    best = max(winner["members"],
               key=lambda r: (type_bonus(kind, r)
                              + (8 if r["tags"].get("wikidata") else 0)
                              + (4 if r["tags"].get("name:de") else 0)
                              - ((haversine(r["lon"], r["lat"], *NF_CENTRE) or 500) / 200)))
    qid = best["tags"].get("wikidata", "")
    if not qid:      # fall back to a sibling's / the boundary relation's wikidata
        for r in winner["members"] + boundaries:
            if r["tags"].get("wikidata"):
                qid = r["tags"]["wikidata"]
                break
    # a linear feature (river, dyke, street) is split into many ways -- tag all
    # of them, otherwise only a fragment of the river gets the Frisian label
    ids = [str(best["id"])]
    if is_linear(best):
        bn = norm(best["tags"].get("name", ""))
        ids = sorted({str(m["id"]) for m in winner["members"]
                      if m["t"] == best["t"] and is_linear(m)
                      and norm(m["tags"].get("name", "")) == bn}, key=int)
    out.update(
        osm_type={"n": "node", "w": "way", "r": "relation"}[best["t"]],
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


def report_cands(cell, limit=20):
    """A `candidates` cell shortened for REPORT.md (the full list is in
    work/matches.csv and the curation view)."""
    parts = [p for p in (cell or "").split(";") if p]
    if len(parts) <= limit:
        return ";".join(parts)
    return ";".join(parts[:limit]) + f";... (+{len(parts) - limit} more)"


def _addnote(row, txt):
    """Machine remarks go to work/matches.csv and the report, never into
    places.csv (whose `note` column belongs to the owner)."""
    return txt


def owned_by_matcher(row):
    """May match.py (re)write this row's osm / wikidata / status?"""
    if local_ref(row["osm"]):
        return False              # a local reference: OSM has no object for it
    if row["kind"] == "not_a_place" or row["status"] == "skip":
        return False
    if row["status"] == "auto":
        return True
    return not row["osm"] and not row["wikidata"]


def find_duplicates(rows):
    """Two rows pointing at one OSM object -- usually the list has a place
    twice (two spellings, or two rows from different sheet sections).  Only one of the names can end
    up on the map."""
    by_obj = collections.defaultdict(list)
    for r in rows:
        if r["status"] == "skip" or not r["osm"]:
            continue
        for key in parse_osm(r["osm"]):
            by_obj[key].append(r)
    return {k: g for k, g in by_obj.items() if len(g) > 1}


# ----------------------------------------------------------------- report ----
def write_report(rows, results, path=REPORT_PATH, timings=None):
    """`results` maps a row's line number to its match_row() output (only for
    the rows the matcher owns)."""
    def state(r):
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
        res = results.get(r["_line"])
        return "ambiguous" if res and res["status"] == "ambiguous" else "not found"

    states = ["auto", "by hand", "own point", "ambiguous", "not found", "skip",
              "no Frisian name", "not a place"]
    by_kind = collections.defaultdict(collections.Counter)
    total = collections.Counter()
    for r in rows:
        st = state(r)
        by_kind[r["kind"]][st] += 1
        total[st] += 1

    def ref(r):
        return f"{r['_line']} | {r['kind']} | {any_name(r)} | {primary(r['de']) or primary(r['da'])}"

    L = []
    L.append("# Name matching report\n")
    L.append(f"Generated by `names/match.py` from `names/places.csv` ({len(rows)} rows). "
             "`line` is the line number in that file.\n")
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
    L.append("| line | kind | Frisian | German | hint | why | candidates |")
    L.append("|---:|---|---|---|---|---|---|")
    for r in amb:
        res = results[r["_line"]]
        L.append(f"| {ref(r)} | {r['hint']} | {res.get('note', '')} "
                 f"| `{report_cands(res.get('candidates', ''))}` |")
    L.append("")

    dups = find_duplicates(rows)
    L.append(f"## Rows sharing one OSM object ({len(dups)})\n")
    L.append("The list has these places twice (two spellings, or rows from two "
             "sheet sections). Only one name can be injected -- the first row wins; "
             "decide which, and `skip` the other.\n")
    L.append("| OSM object | lines | Frisian names | German |")
    L.append("|---|---|---|---|")
    for key, g in sorted(dups.items(), key=lambda kv: kv[1][0]["_line"]):
        L.append(f"| `{format_osm([key])}` | " + ", ".join(str(x["_line"]) for x in g)
                 + " | " + ", ".join(any_name(x) for x in g)
                 + f" | {primary(g[0]['de'])} |")
    L.append("")

    nf = [r for r in rows if state(r) == "not found"]
    L.append(f"## Not found ({len(nf)})\n")
    L.append("Either the feature is not in OSM at all, or OSM spells it "
             "differently. `near misses` lists objects that do carry the German "
             "name but are the wrong kind of thing (a street, a bus stop, a "
             "building) -- occasionally one of them is still the right answer.\n")
    L.append("| line | kind | Frisian | German | note | near misses |")
    L.append("|---:|---|---|---|---|---|")
    for r in nf:
        res = results.get(r["_line"], {})
        cands = f"`{res.get('candidates', '')[:200]}`" if res.get("candidates") else ""
        L.append(f"| {ref(r)} | {res.get('note', '')} | {cands} |")
    L.append("")
    if timings:
        L.append(f"_{timings}_\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def write_matches(rows, results, index, path=MATCH_PATH):
    """work/matches.csv: one line per places.csv row, with the match details
    (and lon/lat also for rows a human filled in, looked up by id).

    `name_nds` is the Low Saxon name of the row's (first) OSM object.  The name
    list has no Low Saxon column, but the map falls back to `name:nds` before
    German, so the search index needs it to name a place as its label does."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MATCH_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            res = results.get(r["_line"])
            refs = parse_osm(r["osm"])
            hit = index.by_key.get(refs[0]) if refs else None
            rec = {"line": r["_line"], "kind": r["kind"],
                   "name": any_name(r),
                   "de": primary(r["de"]), "osm": r["osm"],
                   "wikidata": r["wikidata"], "status": r["status"],
                   "name_nds": hit["tags"].get("name:nds", "") if hit else ""}
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=CSV_PATH)
    ap.add_argument("--candidates", default=CAND_PATH)
    ap.add_argument("--matches", default=MATCH_PATH)
    ap.add_argument("--report", default=REPORT_PATH)
    ap.add_argument("--offline", action="store_true",
                    help="do not call the Wikidata API (use the cache only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="write the report and work/matches.csv, but leave "
                         "places.csv alone")
    args = ap.parse_args(argv)

    t0 = time.time()
    rows, fields = placelist.read(args.names)
    print(f"loaded {len(rows)} rows from {args.names}")

    index = Index(args.candidates)
    print(f"indexed {len(index.recs):,} candidates / "
          f"{len(index.by_name):,} distinct normalised names "
          f"({time.time()-t0:.0f}s)")
    hints = HintResolver(index)

    todo = [r for r in rows if owned_by_matcher(r) and any_name(r)]
    country_rows = [r for r in todo if r["kind"] == "country"]
    qids = wikidata_countries([primary(r["de"]) for r in country_rows],
                              offline=args.offline)

    results = {}
    changed = collections.Counter()
    for r in todo:
        before = (r["osm"], r["wikidata"], r["status"])
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
            o = match_row(r, index, hints)
        results[r["_line"]] = o
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
    write_matches(rows, results, index, args.matches)
    write_report(rows, results, args.report,
                 timings=f"match.py run {time.strftime('%Y-%m-%d %H:%M')}, "
                         f"{time.time()-t0:.0f}s, "
                         f"{len(index.recs):,} candidates")

    cnt = collections.Counter(o["status"] for o in results.values())
    print(f"matcher owns {len(todo)} of {len(rows)} rows: "
          + ", ".join(f"{v} {k}" for k, v in cnt.most_common()))
    print(f"places.csv: {changed['filled']} rows filled, {changed['cleared']} cleared, "
          f"{changed['changed']} changed"
          + (" (dry run -- not written)" if args.dry_run else ""))
    print("wrote", args.matches, "and", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
