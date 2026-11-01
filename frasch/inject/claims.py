"""The name list as claims: which row holds an object of the extract.

A row holds the objects of its `osm` cell, whatever they are.  It holds a
member way of a waterway relation of its cell, if the way carries the
relation's name: the OpenMapTiles waterway layer is built from the ways, so
the label has to go on them.  And it holds every place-like object that
carries its Wikidata QID (see `is_place_like`); for a country, which has no
`osm`, that is the only key.  Objects are matched by id or QID only -- no name
matching happens here, the hand-reviewed list is the single source of truth.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import NamedTuple

import osmium

from frasch import osmscan, placelist, refs
from frasch.dialects import Registry
from frasch.inject.stats import SkippedCarrier, Stats
from frasch.placelist import PlaceRow
from frasch.placenames import GERMAN_KEY
from frasch.refs import OsmRef, Ref

# an object found only through a row's QID is tagged only if it has one of
# these keys (or is a waterway relation): a shop may carry its town's QID (#55)
PLACE_LIKE_KEYS = ("place", "boundary", "natural", "water", "waterway")

# a member way of a claimed waterway relation -> (the relation, its OSM name)
Members = dict[OsmRef, tuple[OsmRef, str]]

# an object's tags: as the extract streams past, or as a pre-pass read them
Tags = osmium.osm.TagList | Mapping[str, str]


class NameList(NamedTuple):
    """The name list as the injector uses it: the rows on the map, each
    under what it claims (`placelist.claims`).

    by_id maps ('w', 12) -> its row (a local reference is the key
    ('l', slug)), by_qid 'Q42' -> its row; `used` is how many rows there are.
    The rows are kept whole because the tags of an object depend on where it
    lies (placenames.resolve), which is only known while the file streams
    past."""

    by_id: dict[Ref, PlaceRow]
    by_qid: dict[str, PlaceRow]
    used: int


def load_names(path: str, reg: Registry) -> NameList:
    by_id: dict[Ref, PlaceRow] = {}
    by_qid: dict[str, PlaceRow] = {}
    on_map = [row for row in placelist.read(path, reg).rows if placelist.on_map(row, reg)]
    for row in on_map:
        held = placelist.claims(row)
        # a river or dyke is split into many OSM ways and all of them need
        # the label
        by_id.update((key, row) for key in held.refs)
        # Every row with a Wikidata QID also tags the other OSM objects that
        # carry that QID (e.g. the offshore place=sea node of the North Sea,
        # the place node next to a matched boundary relation).  Only rows
        # without any OSM id depend on this; for the others it is a bonus.
        if held.qid:
            by_qid[held.qid] = row
    return NameList(by_id, by_qid, len(on_map))


def scan_waterways(path: str, by_id: Iterable[Ref]) -> Members:
    """Which member ways the matched `type=waterway` relations have, in one
    id-filtered pass over the relations (`Claims` gives the row only to
    members carrying the relation's own name, so side arms like "Alte Eider"
    keep theirs)."""
    members: Members = {}
    rel_ids = refs.ids_of(refs.osm_only(by_id), "r")
    for rel_id, rel in osmscan.relations(path, rel_ids).items():
        tags = rel["tags"]
        if not (tags.get("type") == "waterway" or "waterway" in tags):
            continue
        for way_id in rel["member_ways"]:
            members.setdefault(("w", way_id), (("r", rel_id), tags.get("name", "")))
    return members


def is_place_like(tags: Tags) -> bool:
    """Whether an object is a place, an area or a water -- not a shop, a
    building or anything else that may carry a place's QID."""
    return tags.get("type") == "waterway" or any(k in tags for k in PLACE_LIKE_KEYS)


class Claim(NamedTuple):
    """The row that holds an object, and the object whose position says
    where it lies: itself, or for a member way its waterway relation -- the
    member inherits the river's dialect area."""

    row: PlaceRow
    located_as: OsmRef


class Claims:
    """Who holds each object of the extract as it streams past; what it
    finds on the way goes into `stats`."""

    def __init__(self, names: NameList, members: Mapping[OsmRef, tuple[OsmRef, str]], stats: Stats):
        self._names = names
        self._members = members
        self._stats = stats

    def row_for(self, key: OsmRef, tags: Tags) -> Claim | None:
        """The claim on this object, None when no row holds it -- by its own
        reference, as a same-named member way of a waterway relation, or by
        its QID."""
        self._note_qid(tags)
        row = self._names.by_id.get(key)
        if row is not None:
            self._stats.found.add(key)
            return Claim(row, key)
        return self._as_member(key, tags) or self._by_qid(key, tags)

    def _note_qid(self, tags: Tags) -> None:
        """Remember the row QID this object carries, if any, as present."""
        qid = tags.get("wikidata")
        if qid is not None and qid in self._names.by_qid:
            self._stats.present_qids.add(qid)

    def _as_member(self, key: OsmRef, tags: Tags) -> Claim | None:
        """The claim of the waterway relation this way is a member of, if it
        carries the relation's name."""
        member = self._members.get(key)
        if member is None:
            return None
        relation, name = member
        own = tags.get("name")
        if not (own and (own == name or tags.get(GERMAN_KEY) == name)):
            return None
        self._stats.member_ways += 1
        return Claim(self._names.by_id[relation], relation)

    def _by_qid(self, key: OsmRef, tags: Tags) -> Claim | None:
        """The claim of the row whose `wikidata` QID this object carries, if
        any and if the object is place-like."""
        qid = tags.get("wikidata")
        if not qid or qid not in self._names.by_qid:
            return None
        if not is_place_like(tags):
            self._stats.skipped_carriers.append(SkippedCarrier(key, tags.get("name") or "?", qid))
            return None
        self._stats.qid_carriers += 1
        return Claim(self._names.by_qid[qid], key)
