"""Names as the matcher compares them, and the index of candidate records by
name that names/match.py and the curation export (names/curate.py) look
them up in.

Matching is exact after normalisation (`norm`): no fuzzy matching.  An OSM
name value also counts without the annotations OSM adds to it
(`split_name_values`), with a penalty so that a plain hit always wins.
"""
from __future__ import annotations

import collections
import re
import unicodedata
from collections.abc import Iterable

from frasch.candidates import Candidate, osm_key

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
_TYPE_PREFIX = re.compile(
    r"^(?:Kreis|Amt|Stadt|Gemeinde|Hallig|Insel|Landkreis|Flecken)\s+(.+)$")
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


class NameIndex:
    """Candidate records (frasch.candidates) by normalised name, and by
    reference.  Every name tag of NAME_FIELD_RANK and every variant of its
    value (`split_name_values`) is a key; a record found under several
    keeps its best rank."""

    def __init__(self, recs: Iterable[Candidate]):
        self.recs = list(recs)
        # norm -> {rec index: rank}
        self.by_name: collections.defaultdict[str, dict[int, int]] = collections.defaultdict(dict)
        self.by_key = {osm_key(rec): rec for rec in self.recs}
        for i, rec in enumerate(self.recs):
            for field, rank in NAME_FIELD_RANK.items():
                for part, penalty in split_name_values(rec["tags"].get(field) or ""):
                    n = norm(part)
                    if n and rank + penalty < self.by_name[n].get(i, 99):
                        self.by_name[n][i] = rank + penalty

    def lookup(self, name: str) -> list[tuple[Candidate, int]]:
        """-> [(record, name-field rank)]"""
        n = norm(name)
        if not n:
            return []
        return [(self.recs[i], r) for i, r in self.by_name.get(n, {}).items()]
