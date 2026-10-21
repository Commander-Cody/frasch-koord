"""What a run of the injector counts and records, for its report
(frasch.inject.report).  The parts that do the work write it -- the claims,
the synthetic objects, the injector itself -- and none of them reads it."""

from __future__ import annotations

import collections
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import NamedTuple

from frasch.placenames import DIALECT_KEY, LANGUAGE_PREFIX, LOCAL_KEY
from frasch.refs import OsmRef, Ref


class AddedPoint(NamedTuple):
    """The node added for a place OSM does not have (a local reference)."""

    node_id: int
    key: Ref
    lon: float
    lat: float
    tags: dict[str, str]


class AddedSquare(NamedTuple):
    """A synthetic polygon: its way and corner nodes, and what it is around
    -- a node of the extract, or the position of a local reference."""

    way_id: int
    node_ids: list[int]
    key: Ref
    label: str
    km2: float


class SkippedCarrier(NamedTuple):
    """An object that carries a row's QID but is not place-like (#55)."""

    ref: OsmRef
    name: str
    qid: str


@dataclass
class Stats:
    """What one run did to the extract."""

    scanned: int = 0  # the objects of the extract
    # the objects a row tagged, by OSM type letter
    tagged: collections.Counter[str] = field(default_factory=collections.Counter)
    # of these: name:<tag> -> objects, frasch:dialect -> objects, with a frasch:local
    names: collections.Counter[str] = field(default_factory=collections.Counter)
    dialects: collections.Counter[str] = field(default_factory=collections.Counter)
    local: int = 0
    # the objects whose local name is OSM's, in the language of their area
    # (`name:frr`, or `name:nds` in a Low Saxon one): those rows claim
    # (counted in `local` too), and those no row claims
    osm_local_claimed: int = 0
    osm_local_unclaimed: int = 0
    # the references of the name list the extract has an object for
    found: set[Ref] = field(default_factory=set)
    member_ways: int = 0  # tagged as a same-named member of a waterway relation
    qid_carriers: int = 0  # tagged through their QID alone
    # the rows' QIDs that some object of the extract carries, whatever
    # matched that object
    present_qids: set[str] = field(default_factory=set)
    skipped_carriers: list[SkippedCarrier] = field(default_factory=list)
    curated: set[OsmRef] = field(default_factory=set)  # the objects curation tagged
    added_points: list[AddedPoint] = field(default_factory=list)
    added_squares: list[AddedSquare] = field(default_factory=list)

    def tag(self, osm_type: str, tags: Mapping[str, str]) -> None:
        """Count an object of this type that a row gives `tags`."""
        self.tagged[osm_type] += 1
        self.names.update(key for key in tags if key.startswith(LANGUAGE_PREFIX))
        if DIALECT_KEY in tags:
            self.dialects[tags[DIALECT_KEY]] += 1
        if LOCAL_KEY in tags:
            self.local += 1
