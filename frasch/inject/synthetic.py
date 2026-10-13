"""The objects the injector adds to the extract.

A *local place* is a row whose `osm` is a local reference (`local/<slug>`),
a place OSM does not have; the curation row of that reference positions it.
It becomes a new node at that position (`point_tags`) -- or, with the row's
`polygon_km2`, only a synthetic square.

A *synthetic square* is a closed way of a given area (`square_around`):
around a local place, or around a node of the extract whose curation row has
a `polygon_km2`.  It is how a landform without an OSM polygon gets a label
from the zoom OpenMapTiles gives polygons of that size, instead of the z12 it
gives `place=island` nodes.

`SyntheticObjects` gives them their ids and writes them where the file's
order wants them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import NamedTuple

import osmium

from frasch import kinds, placenames, placeobjects, refs
from frasch.curationlist import LocalPoint, Square
from frasch.dialect_areas import AreaIndex
from frasch.dialects import Registry
from frasch.errors import PipelineError
from frasch.geo import LonLat
from frasch.inject.stats import AddedPoint, AddedSquare, Stats
from frasch.inject.writer import Writer
from frasch.placelist import PlaceRow
from frasch.placenames import (
    DIALECT_KEY,
    KIND_KEY,
    LANGUAGE_PREFIX,
    LOCAL_KEY,
    REF_KEY,
    VARIETY_KEY,
)
from frasch.refs import OsmRef, Ref

# what a square around a node of the extract takes over from the node, with
# its `name` and every `name:*`
INHERITED_KEYS = ("name", DIALECT_KEY, LOCAL_KEY, VARIETY_KEY, REF_KEY)
KM_PER_DEGREE = 111.32


def square_around(lon: float, lat: float, km2: float) -> list[LonLat]:
    """Corners of a square of `km2` km² centred on (lon, lat), as (lon, lat).

    Its interior point -- where Planetiler puts a polygon label -- is the
    centre, i.e. the node."""
    half_km = math.sqrt(km2) / 2
    dlat = half_km / KM_PER_DEGREE
    dlon = half_km / (KM_PER_DEGREE * math.cos(math.radians(lat)))
    return [
        (lon - dlon, lat - dlat),
        (lon + dlon, lat - dlat),
        (lon + dlon, lat + dlat),
        (lon - dlon, lat + dlat),
    ]


# ---------------------------------------------------------- local places ----
class LocalPlace(NamedTuple):
    """A place OSM does not have: its local reference, the curation row that
    positions it, and the tags of its node or square."""

    key: Ref
    point: LocalPoint
    tags: dict[str, str]


def point_tags(
    row: PlaceRow,
    point: LocalPoint,
    areas: AreaIndex,
    reg: Registry,
) -> dict[str, str]:
    """The tag dict of the node added for a local reference: the `place=`
    its kind defaults to, a `name` (the German one -- the Frisian ones live
    in `name:<tag>` like everywhere else; without it OpenMapTiles would drop
    the node), the name tags, and last the curation row's own tags, which
    win."""
    obj = placeobjects.local_point(row, (point["lon"], point["lat"]), reg)
    place = kinds.rule(row["kind"]).point_place
    tags = {"place": place} if place else {}
    if "name" in obj:
        tags["name"] = obj["name"]
    tags.update(placenames.as_tags(placenames.resolve(row, obj, areas, reg)))
    tags.update(point["tags"])
    if "place" not in tags:
        raise PipelineError(
            f"{point['where']}: kind {row['kind']!r} (places.csv line "
            f"{row.line}) has no default place= (`point_place` in "
            f"frasch/kinds.py) -- give the curation row "
            f"`place=...` in set_tags"
        )
    return tags


def local_places(
    by_id: Mapping[Ref, PlaceRow],
    points: Mapping[Ref, LocalPoint],
    areas: AreaIndex,
    reg: Registry,
) -> list[LocalPlace]:
    """The local references a row of the name list uses, each with its tags
    -- checked before anything is written: the node needs a `place=` (see
    `point_tags`), and a square only labels as `place=island`.  OpenMapTiles
    takes hamlets, villages etc. from POINTS only, so any other value on a
    polygon would silently label nothing."""
    places = [
        LocalPlace(key, point, point_tags(by_id[key], point, areas, reg))
        for key, point in points.items()
        if key in by_id
    ]
    for place in places:
        if place.point["km2"] is not None and place.tags["place"] != "island":
            raise PipelineError(
                f"{place.point['where']}: polygon_km2 on {refs.format([place.key])} "
                f"needs place=island (got place={place.tags['place']}; "
                f"OpenMapTiles labels polygons only as islands) -- "
                f"put `place=island` in set_tags, keep {KIND_KEY}"
            )
    return places


# ------------------------------------------------------- what is written ----
@dataclass
class _Square:
    """A synthetic square waiting to be written; `node_ids` once its corner
    nodes are."""

    key: Ref
    label: str
    km2: float
    centre: LonLat
    tags: dict[str, str]
    node_ids: list[int] = field(default_factory=list)


class SyntheticObjects:
    """Writes the added objects in between those of the extract: the new
    nodes before the first way and the new ways before the first relation,
    so that the file stays in node/way/relation order with ascending ids
    (Planetiler and osmium both expect that).  Their ids continue above the
    highest one of the extract."""

    def __init__(self, writer: Writer, places: Sequence[LocalPlace], stats: Stats):
        self._writer = writer
        self._places = places
        self._stats = stats
        self._squares: list[_Square] = []
        self._max_id = {"n": 0, "w": 0}
        self._nodes_written = False
        self._ways_written = False

    def passing(self, key: OsmRef) -> None:
        """An object of the extract comes by, about to be written: its id is
        taken, and the added objects that belong before it go first."""
        osm_type, osm_id = key
        if osm_type == "w":
            self._write_nodes()
        elif osm_type == "r":
            self._write_ways()
        if osm_type in self._max_id:
            self._max_id[osm_type] = max(self._max_id[osm_type], osm_id)

    def add_square(
        self, key: OsmRef, square: Square, centre: LonLat, node_tags: Mapping[str, str]
    ) -> None:
        """Queue the square curation puts around a node of the extract: it
        inherits the node's (curated) names and dialect, then gets the tags
        of its own curation row."""
        tags = {
            k: v
            for k, v in node_tags.items()
            if k in INHERITED_KEYS or k.startswith(LANGUAGE_PREFIX)
        }
        tags.update(square["tags"])
        self._squares.append(_Square(key, square["label"], square["km2"], centre, tags))

    def finish(self) -> None:
        """Write what is still waiting, for an extract that ends before any
        way or relation."""
        self._write_ways()

    def _write_nodes(self) -> None:
        if self._nodes_written:
            return
        self._nodes_written = True
        for place in self._places:
            self._add_local_place(place)
        for square in self._squares:
            square.node_ids = [
                self._add_node(corner) for corner in square_around(*square.centre, square.km2)
            ]

    def _write_ways(self) -> None:
        self._write_nodes()
        if self._ways_written:
            return
        self._ways_written = True
        for square in self._squares:
            self._add_square_way(square)

    def _add_local_place(self, place: LocalPlace) -> None:
        """The node of a local place -- or, for an area-like one, only its
        square, no node."""
        key, point, tags = place
        centre = (point["lon"], point["lat"])
        self._stats.found.add(key)
        if point["km2"] is not None:
            self._stats.tag("w", tags)
            self._squares.append(_Square(key, point["label"], point["km2"], centre, tags))
            return
        self._stats.tag("n", tags)
        node_id = self._add_node(centre, tags)
        self._stats.added_points.append(AddedPoint(node_id, key, *centre, tags))

    def _add_node(self, location: LonLat, tags: Mapping[str, str] | None = None) -> int:
        """Write a new node and return its id."""
        self._max_id["n"] += 1
        self._writer.add_node(
            osmium.osm.mutable.Node(
                id=self._max_id["n"], version=1, visible=True, location=location, tags=tags or {}
            )
        )
        return self._max_id["n"]

    def _add_square_way(self, square: _Square) -> None:
        """The closed way of a square, through its corner nodes."""
        self._max_id["w"] += 1
        self._writer.add_way(
            osmium.osm.mutable.Way(
                id=self._max_id["w"],
                version=1,
                visible=True,
                nodes=square.node_ids + square.node_ids[:1],
                tags=square.tags,
            )
        )
        self._stats.added_squares.append(
            AddedSquare(self._max_id["w"], square.node_ids, square.key, square.label, square.km2)
        )
