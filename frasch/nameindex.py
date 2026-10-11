"""Names as the matcher compares them, and the index of candidate records by
name that frasch.match and the hint resolver (frasch.hints) look them up in.

Matching is exact after normalisation (`norm`): no fuzzy matching.  An OSM
name value also counts without the annotations OSM adds to it
(`split_name_values`), with a penalty so that a plain hit always wins.
"""

from __future__ import annotations

import collections
import re
import unicodedata
from collections.abc import Iterable
from typing import NamedTuple

from frasch.candidates import Candidate, osm_key
from frasch.osmtags import BYNAME_FIELDS, NAME_FIELD_RANK, UNRANKED
from frasch.refs import OsmRef

# ----------------------------------------------------------- normalisation ---
_UML = {
    "ä": "ae",
    "ö": "oe",
    "ü": "ue",
    "Ä": "ae",
    "Ö": "oe",
    "Ü": "ue",
    "ß": "ss",
    "å": "aa",
    "Å": "aa",
    "ø": "oe",
    "Ø": "oe",
    "æ": "ae",
    "Æ": "ae",
    "é": "e",
    "è": "e",
    "á": "a",
    "à": "a",
}


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    out: list[str] = []
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
_TYPE_PREFIX = re.compile(r"^(?:Kreis|Amt|Stadt|Gemeinde|Hallig|Insel|Landkreis|Flecken)\s+(.+)$")
# the island OSM appends to a place name: `Wyk auf Föhr`, `List auf Sylt`,
# `Norddorf auf Amrum` -- the list writes plain `Wyk`
_AUF_SUFFIX = re.compile(r"^(.+?)\s+auf\s+\S.*$")


def split_name_values(v: str) -> list[tuple[str, int]]:
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


class NameHit(NamedTuple):
    """A record a name finds.  `rank` is that of the best name tag it is
    found by (lower = better, osmtags.NAME_FIELD_RANK plus the penalty of an
    annotated value); `byname` says that every tag it is found by is one of
    osmtags.BYNAME_FIELDS -- the object only also goes by the name."""

    rec: Candidate
    rank: int
    byname: bool


class NameIndex:
    """Candidate records (frasch.candidates) by normalised name.  Every name
    tag of osmtags.NAME_FIELD_RANK and every variant of its value
    (`split_name_values`) is a key; a record found under several keeps its
    best rank.  An object two extracts have is two records: `sources` names
    the extracts (`src`) of each object."""

    def __init__(self, recs: Iterable[Candidate]):
        self.recs = list(recs)
        # norm -> {rec index: (rank, byname)}
        self.by_name: collections.defaultdict[str, dict[int, tuple[int, bool]]] = (
            collections.defaultdict(dict)
        )
        self.sources: dict[OsmRef, tuple[str, ...]] = {}
        for i, rec in enumerate(self.recs):
            key = osm_key(rec)
            self.sources[key] = (*self.sources.get(key, ()), rec["src"])
            for field, rank in NAME_FIELD_RANK.items():
                for part, penalty in split_name_values(rec["tags"].get(field) or ""):
                    self._add(norm(part), i, rank + penalty, field in BYNAME_FIELDS)

    def _add(self, name: str, i: int, rank: int, byname: bool) -> None:
        """Count a hit of the normalised `name` on the record `i`."""
        if not name:
            return
        best, only_bynames = self.by_name[name].get(i, (UNRANKED, True))
        self.by_name[name][i] = (min(best, rank), only_bynames and byname)

    def lookup(self, name: str) -> list[NameHit]:
        """The records `name` finds."""
        hits = self.by_name.get(norm(name), {})
        return [NameHit(self.recs[i], rank, byname) for i, (rank, byname) in hits.items()]
