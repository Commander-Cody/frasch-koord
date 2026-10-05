"""Copy an OSM PBF and add North Frisian name / curation tags to it.

    frasch inject <in.osm.pbf> <out.osm.pbf>
                  [--no-areas] [--no-curation] [--dry-run]

Three inputs are merged into the extract -- the name list, the dialect areas
(read together with names/osm_objects.json, which says where each object
lies) and the curation:

`names/places.csv` (the name list) -- one row per place, one column per
dialect (the columns come from `names/dialects.csv`, the registry).  Every row
that is not `skip` tags the object(s) in its `osm` column with

    name:<tag>       for every dialect whose name for the row is non-empty
    name:de          the first variant of the row's `de`, in place of OSM's
                     (the card's German name comes from the list, #61);
                     OSM's stays where the list has none
    frasch:kind      the row's kind (island, hallig, sand, settlement, ...)
    frasch:dialect   the dialect spoken where the object lies
    frasch:local     what the people of the place themselves call it; where
                     the list has no such name, OSM's own `name:frr` inside a
                     dialect area (see the dialect areas below)
    frasch:variety   the name of that local variety, e.g. `Foortuftinge`
    frasch:ref       the row's `id` (`naibel`, `schorkewarw-2`) -- the id of
                     the row's entry in the search index, so that the frontend
                     can go from a clicked label back to the name-list row

Rows with a `wikidata` QID additionally tag every place-like object (one with
a `place`, `boundary`, `natural`, `water` or `waterway` tag, or a waterway
relation) whose `wikidata` tag equals that QID; for the countries, which have
no `osm`, that is the only key.  Any other object carrying the QID -- a shop
mis-tagged with its town's (#55) -- is left alone and reported.

A row whose `osm` is a *local reference* (`local/<slug>`) is a place OSM does
not have (Waasterhias on Amrum, Harden, most Köge).  The same reference keys
a row of `names/curation.csv` that carries its position (`lat` / `lon`) and,
like any curation row, may carry `set_tags` / `minzoom` / `maxzoom` /
`polygon_km2`.  Without `polygon_km2` the injector adds a *new node* at that
position, tagged like any other object plus the `place=` value its `kind`
maps to (curationlist.POINT_TAGS, overridable by `set_tags`) and a `name` -- OpenMapTiles
drops a nameless place node.  With `polygon_km2` no labelled node is written;
only the synthetic square (see curation below) is, which is how an area-like
place (a Koog) gets a label from the zoom OpenMapTiles gives polygons of that
size.  New node ids continue above the highest one in the extract; like the
synthetic polygon nodes they are written before the first way, i.e. after
every original node.

`names/dialect_areas.geojson` (built from `names/dialect_areas.csv` by
`frasch areas`) says which dialect is spoken where.  It
answers two questions that a name list cannot: which of the dialect names is
the *local* one at this spot (`frasch:local`, the "local dialect" map view),
and which dialect a place's own `local` column belongs to.  The smallest area
containing the object wins.  Without the file the injector still runs -- it
warns and writes `frasch:local` only for rows with an explicit `local` name.
Where an object lies comes from `names/osm_objects.json` (`frasch objects`),
and `objects.dialect_at` turns that into a dialect -- the same file and the same
function the search index uses (frasch.searchindex), so a map label
and its search entry cannot disagree (#24).  An object of the name list the
file does not know stops the build.  Objects matched only through their
Wikidata QID are not in it: a node is asked at its own location, a way or
relation gets no dialect.

Inside a dialect area OSM's own `name:frr` is almost always the local form,
outside it is a Frisian exonym (Pinneberg -> Pinebärj).  So an object in an
area whose rows give it no local name gets its `name:frr` as `frasch:local`
(#81), from names/osm_objects.json like its position.  And so does every
object there *no row claims* -- a Warft, a street, a station -- and nothing
else from this rule: a pre-pass finds the objects of the extract that carry
`name:frr` and locates them (`scan_osm_local`), so a new Frisian name in OSM
is on the map with the next build.

`names/curation.csv` (per-feature map tuning) -- for every listed object the
`set_tags` (`k=v` pairs separated by `;`) are applied *verbatim*, after the
name list, so they may override `frasch:kind` or `place`; `minzoom` /
`maxzoom` become the tags `frasch:minzoom` / `frasch:maxzoom`.  Curation
applies to any object in the file, whether the name list mentions it or not (a
place with no Frisian name can still need a `place=island` fix or a minimum
zoom).  A row keyed by a local reference additionally carries `lat` / `lon`
(required there, forbidden on OSM references) and is what *creates* the
object for that reference, see above.  A row with `polygon_km2` does not change its node but adds a
*synthetic* closed way to the file: a square of that area centred on the node,
carrying the node's `name`/`name:*`/`frasch:dialect`/`frasch:local` tags plus
the row's `set_tags` / zooms.  That is how a landform without an OSM polygon
(Nordstrand, a former island that is now a peninsula) gets a label at a chosen
point from the zoom OpenMapTiles gives polygons of that size, instead of the
z12 it gives `place=island` nodes.

Objects are matched by id (or QID) only -- no name matching happens here, so the
hand-reviewed decisions in the CSVs are the single source of truth.  All other
tags are preserved (`o.replace(tags=...)`), as are all objects neither file
mentions.  When two rows claim the same object, the first row in file order
wins per tag and the rest are reported.

The `frasch:*` tags reach the tiles because tiles/build.sh passes them to
Planetiler via `--extra_name_tags`; tag values must therefore be strings.

Used by tiles/build.sh before Planetiler runs.
"""

from __future__ import annotations

import collections
import enum
import os
import time
from collections.abc import Container, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple, NotRequired, TypedDict

import osmium

from frasch import (
    cli,
    curationlist,
    dialects,
    locate,
    osmscan,
    placelist,
    registry,
)
from frasch.curationlist import LocalPoint, Square, Tuning
from frasch.errors import PipelineError, ValidationError
from frasch.geo import LonLat
from frasch.objects import LocatedObject, dialect_at, read_objects
from frasch.paths import Workspace
from frasch.placelist import OsmRef, PlaceRow, Ref, Row
from frasch.registry import Registry

GERMAN_KEY = "name:de"
FRISIAN_KEY = "name:frr"
KIND_KEY = "frasch:kind"
MINZOOM_KEY = curationlist.MINZOOM_KEY
MAXZOOM_KEY = curationlist.MAXZOOM_KEY
DIALECT_KEY = "frasch:dialect"
LOCAL_KEY = "frasch:local"
VARIETY_KEY = "frasch:variety"
REF_KEY = placelist.REF_KEY
# an object found only through a row's QID is tagged only if it has one of
# these keys (or is a waterway relation): a shop may carry its town's QID (#55)
PLACE_LIKE_KEYS = ("place", "boundary", "natural", "water", "waterway")

# an object of the extract the injector copies
_OsmObject = osmium.osm.Node | osmium.osm.Way | osmium.osm.Relation
# (object, column, kept name, its line, dropped name, its line), see `_conflicts`
Conflict = tuple[Ref, str, str, int, str, int]


# (QID, line of the row that keeps it, line of a later row that is ignored)
DuplicateQid = tuple[str, int, int]


# ------------------------------------------------------------ name list ----
class NameList(NamedTuple):
    """The name list as the injector uses it.

    by_id maps ('w', 12) -> [row, ...] in file order (a local reference is
    the key ('l', slug)), by_qid 'Q42' -> [row].  The rows are kept whole
    because the tags of an object depend on where it lies (see `name_tags`),
    which is only known while the file streams past.  `conflicts` and
    `duplicate_qids` are reported, not fatal: the first row wins."""

    by_id: dict[Ref, list[PlaceRow]]
    by_qid: dict[str, list[PlaceRow]]
    used: int
    conflicts: list[Conflict]
    duplicate_qids: list[DuplicateQid]


def load_names(path: str, reg: Registry) -> NameList:
    by_id: dict[Ref, list[PlaceRow]] = {}
    by_qid: dict[str, list[PlaceRow]] = {}
    conflicts: list[Conflict] = []
    duplicate_qids: list[DuplicateQid] = []
    used = 0
    rows, _ = placelist.read(path, reg)
    for row in rows:
        if not placelist.on_map(row, reg):
            continue
        refs = placelist.parse_osm(row["osm"], f"{path}:{row.line}")
        if refs:
            # a river or dyke is split into many OSM ways and all of them
            # need the label
            for key in refs:
                by_id.setdefault(key, []).append(row)
            used += 1
        elif row["wikidata"]:
            used += 1
        # Every row with a Wikidata QID also tags the other OSM objects that
        # carry that QID (e.g. the offshore place=sea node of the North Sea,
        # the place node next to a matched boundary relation).  Only rows
        # without any OSM id depend on this; for the others it is a bonus.
        qid = row["wikidata"]
        if qid in by_qid:
            duplicate_qids.append((qid, by_qid[qid][0].line, row.line))
        elif qid:
            by_qid[qid] = [row]
    for key, claim in by_id.items():
        conflicts += _conflicts(key, claim, reg)
    return NameList(by_id, by_qid, used, conflicts, duplicate_qids)


def _conflicts(key: Ref, rows: Sequence[PlaceRow], reg: Registry) -> list[Conflict]:
    """Which names a second row for the same object loses.  Reported, not
    fatal: the first row in file order wins, per tag."""
    out: list[Conflict] = []
    if len(rows) < 2:
        return out
    for column in reg.columns + [registry.LOCAL_COLUMN]:
        kept, kept_line = "", 0
        for row in rows:
            name = (
                dialects.dialect_name(row, reg.tag_of_column(column), None, reg)
                if column != registry.LOCAL_COLUMN
                else placelist.primary(row[column])
            )
            if not name:
                continue
            if not kept:
                kept, kept_line = name, row.line
            elif name != kept:
                out.append((key, column, kept, kept_line, name, row.line))
    return out


def name_tags(rows: Sequence[Row], area_tag: str | None, reg: Registry) -> dict[str, str]:
    """The full tag dict for one object: a `name:<tag>` per dialect that has a
    name for it, `name:de` where the list has a German name, plus the frasch:*
    attributes.  `rows` are the name-list rows claiming the object, in file
    order -- the first non-empty value wins."""
    tags: dict[str, str] = {}
    for d in reg:
        tags["name:" + d["tag"]] = _first(
            dialects.dialect_name(row, d["tag"], area_tag, reg) for row in rows
        )
    tags[GERMAN_KEY] = _first(placelist.primary(row["de"]) for row in rows)
    tags[KIND_KEY] = _first(row["kind"] for row in rows)
    tags[DIALECT_KEY] = area_tag or ""
    tags[LOCAL_KEY] = _first(dialects.local_name(row, area_tag, reg) for row in rows)
    tags[VARIETY_KEY] = _first(dialects.variety(row) for row in rows)
    tags[REF_KEY] = rows[0]["id"]
    return {k: v for k, v in tags.items() if v}


def _first(values: Iterable[str]) -> str:
    """The first non-empty value, or `""`."""
    return next(filter(None, values), "")


def point_tags(
    rows: Sequence[PlaceRow],
    area_tag: str | None,
    reg: Registry,
    curation_tags: Mapping[str, str],
    where: str = "",
) -> dict[str, str]:
    """The tag dict of the node added for a local reference: the `place=` its
    kind defaults to, a `name` (the German one -- the Frisian ones live in
    `name:<tag>` like everywhere else; without it OpenMapTiles would drop the
    node), the name tags, and last the curation row's own tags, which win."""
    row = rows[0]
    tags = dict(curationlist.POINT_TAGS.get(row["kind"], {}))
    name = placelist.point_name(row, reg)
    if name:
        tags["name"] = name
    tags.update(name_tags(rows, area_tag, reg))
    tags.update(curation_tags)
    if "place" not in tags:
        raise ValidationError(
            f"{where}: kind {row['kind']!r} (places.csv line "
            f"{row.line}) has no default place= (POINT_TAGS in "
            f"frasch/curationlist.py) -- give the curation row "
            f"`place=...` in set_tags"
        )
    return tags


def check_local(
    by_id: Mapping[Ref, Sequence[PlaceRow]], points: Mapping[Ref, LocalPoint], reg: Registry
) -> None:
    """Validate every local reference before anything is written: the node
    needs a `place=` (see point_tags), and a square only labels as
    `place=island` -- OpenMapTiles takes hamlets, villages etc. from POINTS
    only, so any other value on a polygon would silently label nothing."""
    for key, p in points.items():
        rows = by_id.get(key)
        if rows is None:
            continue
        tags = point_tags(rows, None, reg, p["tags"], p["where"])
        if p["km2"] is not None and tags["place"] != "island":
            raise ValidationError(
                f"{p['where']}: polygon_km2 on {placelist.format_osm([key])} "
                f"needs place=island (got place={tags['place']}; "
                f"OpenMapTiles labels polygons only as islands) -- "
                f"put `place=island` in set_tags, keep frasch:kind"
            )


# -------------------------------------------------------------- curation ----
def load_curation(path: str, required: bool = False) -> curationlist.Curation:
    """The curation (curationlist.read), or none when the file is absent --
    unless it was named explicitly (`required`); says which it is."""
    if not os.path.exists(path):
        if required:
            raise PipelineError(f"curation file not found: {path}")
        print(f"curation  : {path} (absent -- nothing curated)")
        return curationlist.Curation({}, {}, {})
    curation = curationlist.read(path)
    objects = curation.objects
    print(
        f"curation  : {path} -> {len(objects)} OSM ids "
        f"({sum(1 for c in objects.values() if MINZOOM_KEY in c['tags'])} with "
        f"{MINZOOM_KEY}, "
        f"{sum(1 for c in objects.values() if MAXZOOM_KEY in c['tags'])} with "
        f"{MAXZOOM_KEY})"
    )
    return curation


def square_around(lon: float, lat: float, km2: float) -> list[LonLat]:
    """Corners of a square of `km2` km² centred on (lon, lat), as (lon, lat).

    Its interior point -- where Planetiler puts a polygon label -- is the
    centre, i.e. the node."""
    import math

    half_km = math.sqrt(km2) / 2
    dlat = half_km / 111.32
    dlon = half_km / (111.32 * math.cos(math.radians(lat)))
    return [
        (lon - dlon, lat - dlat),
        (lon + dlon, lat - dlat),
        (lon + dlon, lat + dlat),
        (lon - dlon, lat + dlat),
    ]


# ------------------------------------------------------------- waterways ----
def scan_waterways(path: str, by_id: Iterable[Ref]) -> dict[OsmRef, tuple[OsmRef, str]]:
    """Which member ways the matched `type=waterway` relations have, in one
    id-filtered pass over the relations.  The OpenMapTiles waterway layer is
    built from the member WAYS, so the label has to go on them (the main pass
    applies it only to members carrying the relation's own name, so side arms
    like "Alte Eider" keep theirs).

    -> {('w', id): (relation key, the relation's OSM name)}"""
    members: dict[OsmRef, tuple[OsmRef, str]] = {}
    rel_ids = {osm[1] for key in by_id if (osm := placelist.as_osm_ref(key)) and osm[0] == "r"}
    for rel_id, rel in osmscan.relations(path, rel_ids).items():
        tags = rel["tags"]
        if not (tags.get("type") == "waterway" or "waterway" in tags):
            continue
        for way_id in rel["member_ways"]:
            members.setdefault(("w", way_id), (("r", rel_id), tags.get("name", "")))
    return members


# ---------------------------------------------------- OSM's Frisian names ----
def scan_osm_local(path: str, areas: dialects.AreaIndex | None) -> dict[OsmRef, str]:
    """OSM's own Frisian name (`name:frr`) of every object of the extract
    that lies in a dialect area -- there it is the local name of an object
    the name list gives none (dialects.osm_local_name, #81).

    One pass finds the objects that carry the tag, whatever they are (a
    place, a street, a station); frasch.locate then says where each lies,
    as it does for the objects of the name list: a node at its own location,
    a way or relation inside its polygon, else at its outline point.

    -> {('w', id): the name}"""
    if areas is None:
        return {}
    names = osmscan.tagged(path, FRISIAN_KEY)
    local = {
        ref: dialects.osm_local_name(names[ref], dialect_at(obj, areas))
        for ref, obj in locate.locate_in(path, set(names)).items()
    }
    return {ref: name for ref, name in local.items() if name}


def unlocated(by_id: Iterable[Ref], objects: Container[OsmRef]) -> list[Ref]:
    """The OSM references of the name list that the objects file does not
    know -- without a position they would get no dialect, and the search
    index, which reads the same file, refuses them too."""
    return sorted(k for k in by_id if k[0] != placelist.LOCAL_TYPE and k not in objects)


# -------------------------------------------------------------- injector ----
def is_place_like(tags: osmium.osm.TagList) -> bool:
    """Whether an object is a place, an area or a water -- not a shop, a
    building or anything else that may carry a place's QID."""
    return tags.get("type") == "waterway" or any(k in tags for k in PLACE_LIKE_KEYS)


class _PendingSquare(TypedDict):
    """A synthetic polygon waiting to be written (see `Injector.flush`);
    `node_ids` once its corner nodes are."""

    key: Ref
    label: str
    km2: float
    lon: float
    lat: float
    tags: dict[str, str]
    node_ids: NotRequired[list[int]]


class Injector:
    """`writer` None is a dry run: everything is counted, nothing written."""

    def __init__(
        self,
        writer: osmium.SimpleWriter | None,
        by_id: Mapping[Ref, Sequence[PlaceRow]],
        by_qid: Mapping[str, Sequence[PlaceRow]],
        reg: Registry,
        areas: dialects.AreaIndex | None = None,
        objects: Mapping[OsmRef, LocatedObject] | None = None,
        curation: Mapping[Ref, Tuning] | None = None,
        members: Mapping[OsmRef, tuple[OsmRef, str]] | None = None,
        synthetic: Mapping[Ref, Square] | None = None,
        points: Mapping[Ref, LocalPoint] | None = None,
        osm_local: Mapping[OsmRef, str] | None = None,
    ):
        self.members = members or {}
        # OSM's own Frisian name of the objects in a dialect area, the local
        # name of those no row claims (see `scan_osm_local`)
        self.osm_local = osm_local or {}
        # local references (places OSM has no object for): a node of their
        # own, or a synthetic polygon, written with the synthetic polygon
        # nodes (see `flush`)
        self.points = points or {}
        # (node id, key, label, lon, lat, tags) for the report
        self.added_points: list[tuple[int, Ref, str, float, float, dict[str, str]]] = []
        # synthetic polygons: collected while the nodes stream past, written as
        # new nodes before the first way and as new ways before the first
        # relation, so the file stays in node/way/relation order with ascending
        # ids (Planetiler and osmium both expect that)
        self.synthetic = synthetic or {}
        self.pending: list[_PendingSquare] = []
        self.max_id = {"n": 0, "w": 0, "r": 0}
        self.flushed = {"n": False, "w": False}
        # (way id, node ids, label, km2) for the report
        self.created: list[tuple[int, list[int], str, float]] = []
        self.member_hits = 0
        self.w = writer
        self.by_id = by_id
        self.by_qid = by_qid
        self.reg = reg
        self.areas = areas
        self.objects = objects or {}
        self.curation = curation or {}
        self.hits: collections.Counter[str] = collections.Counter()
        self.tag_hits: collections.Counter[str] = collections.Counter()  # name:<tag> -> objects
        self.area_hits: collections.Counter[str] = (
            collections.Counter()
        )  # frasch:dialect -> objects
        self.local_hits = 0
        # the objects whose local name is OSM's `name:frr`: those rows claim
        # (counted in `local_hits` too), and those no row claims
        self.osm_local_hits: collections.Counter[str] = collections.Counter()
        self.seen_keys: set[Ref] = set()
        self.qid_hits: collections.Counter[str] = collections.Counter()
        # the rows' QIDs that some object of the file carries, whatever
        # matched that object
        self.present_qids: set[str] = set()
        # (object, its name, QID) of the objects that carry a row's QID but
        # are not place-like, for the report
        self.skipped_carriers: list[tuple[OsmRef, str, str]] = []
        self.cur_hits: collections.Counter[str] = collections.Counter()
        self.seen_cur: set[Ref] = set()
        self.n_objects = 0

    def area_of(self, key: OsmRef, o: _OsmObject) -> str | None:
        """The dialect spoken where this object lies, or None: from the
        objects file (`frasch objects`), which the search index reads too.
        A node found only through its QID is asked at its own location; a
        way or relation found that way gets none."""
        if key in self.objects:
            return dialect_at(self.objects[key], self.areas)
        if isinstance(o, osmium.osm.Node) and o.location.valid():
            return dialect_at({"lon": o.location.lon, "lat": o.location.lat}, self.areas)
        return None

    def name_frr_of(self, key: OsmRef, o: _OsmObject) -> str:
        """OSM's own Frisian name of this object: from the objects file,
        like its area (`area_of`).  An object found only through its QID is
        asked itself."""
        if key in self.objects:
            return self.objects[key].get("name_frr", "")
        return o.tags.get(FRISIAN_KEY) or ""

    def flush(self, t: str) -> None:
        """Write the synthetic nodes (t='w': before the first way) or ways
        (t='r': before the first relation)."""
        if t == "w" and not self.flushed["n"]:
            self.flushed["n"] = True
            self._add_local_points()
            self._add_square_nodes()
        elif t == "r" and not self.flushed["w"]:
            self.flush("w")
            self.flushed["w"] = True
            self._add_square_ways()

    def _add_local_points(self) -> None:
        """The node of every local reference a name-list row uses -- or,
        for an area-like place, its pending square."""
        for key, p in self.points.items():
            rows = self.by_id.get(key)
            if rows is None:
                continue  # no name-list row uses it (reported in run)
            lon, lat = p["lon"], p["lat"]
            area_tag = dialect_at({"lon": lon, "lat": lat}, self.areas)
            tags = point_tags(rows, area_tag, self.reg, p["tags"], p["where"])
            self.seen_keys.add(key)
            self._count_names(tags)
            if p["km2"] is not None:
                # an area-like place: only the label square, no node
                self.hits["w"] += 1
                self.pending.append(
                    _PendingSquare(
                        key=key, label=p["label"], km2=p["km2"], lon=lon, lat=lat, tags=tags
                    )
                )
                continue
            self._add_point_node(key, p, tags)

    def _add_point_node(self, key: Ref, p: LocalPoint, tags: dict[str, str]) -> None:
        self.hits["n"] += 1
        self.max_id["n"] += 1
        if self.w is not None:
            self.w.add_node(
                osmium.osm.mutable.Node(
                    id=self.max_id["n"],
                    version=1,
                    visible=True,
                    location=(p["lon"], p["lat"]),
                    tags=tags,
                )
            )
        self.added_points.append((self.max_id["n"], key, p["label"], p["lon"], p["lat"], tags))

    def _add_square_nodes(self) -> None:
        """The (untagged) corner nodes of every pending square."""
        for square in self.pending:
            ids: list[int] = []
            for lon, lat in square_around(square["lon"], square["lat"], square["km2"]):
                self.max_id["n"] += 1
                ids.append(self.max_id["n"])
                if self.w is not None:
                    self.w.add_node(
                        osmium.osm.mutable.Node(
                            id=ids[-1], version=1, visible=True, location=(lon, lat)
                        )
                    )
            square["node_ids"] = ids

    def _add_square_ways(self) -> None:
        """The closed way of every pending square, through its corner nodes."""
        for square in self.pending:
            self.max_id["w"] += 1
            if self.w is not None:
                self.w.add_way(
                    osmium.osm.mutable.Way(
                        id=self.max_id["w"],
                        version=1,
                        visible=True,
                        nodes=square["node_ids"] + square["node_ids"][:1],
                        tags=square["tags"],
                    )
                )
            self.created.append(
                (self.max_id["w"], square["node_ids"], square["label"], square["km2"])
            )

    def _count_names(self, tags: Mapping[str, str]) -> None:
        """Count an object's name tags, dialect and local name for the report."""
        for k in tags:
            if k.startswith("name:"):
                self.tag_hits[k] += 1
        if DIALECT_KEY in tags:
            self.area_hits[tags[DIALECT_KEY]] += 1
        if LOCAL_KEY in tags:
            self.local_hits += 1

    def finish(self) -> None:
        """For files that end before any way / relation."""
        self.flush("w")
        self.flush("r")

    def handle(self, o: _OsmObject, t: str) -> None:
        """`t` is the OSM type letter (n/w/r), not a name-list kind."""
        self.n_objects += 1
        self._note_qid(o)
        key = (t, o.id)
        self.max_id[t] = max(self.max_id[t], o.id)
        if t != "n":
            self.flush(t)
        synth = self._synthetic_at(key, o)
        hit, area_key = self._rows_for(key, o)  # [row, ...]
        cur = self.curation.get(key)
        if cur is not None:
            self.seen_cur.add(key)
            self.cur_hits[t] += 1
        unclaimed_local = self.osm_local.get(key, "") if hit is None else ""
        if hit is None and cur is None and synth is None and not unclaimed_local:
            if self.w is not None:
                self.w.add(o)
            return
        tags = dict(o.tags)
        if hit is not None:
            self.hits[t] += 1
            new = self._row_tags(hit, area_key, o)
            self._count_names(new)
            tags.update(new)
        elif unclaimed_local:
            self.osm_local_hits["unclaimed"] += 1
            tags[LOCAL_KEY] = unclaimed_local
        if cur is not None:
            # curation runs last and wins: it may override frasch:kind or place
            tags.update(cur["tags"])
        if synth is not None:
            self.pending.append(_square_with_names(key, synth, tags))
        if self.w is not None:
            self.w.add(o.replace(tags=tags))

    def _row_tags(
        self, rows: Sequence[PlaceRow], area_key: OsmRef, o: _OsmObject
    ) -> dict[str, str]:
        """The tags the rows claiming this object give it (`name_tags`).
        Where no row has a local name, OSM's own Frisian name is it, inside
        a dialect area (dialects.osm_local_name)."""
        area_tag = self.area_of(area_key, o)
        tags = name_tags(rows, area_tag, self.reg)
        osm_local = dialects.osm_local_name(self.name_frr_of(area_key, o), area_tag)
        if LOCAL_KEY not in tags and osm_local:
            self.osm_local_hits["claimed"] += 1
            tags[LOCAL_KEY] = osm_local
        return tags

    def _note_qid(self, o: _OsmObject) -> None:
        """Remember the row QID this object carries, if any, as present."""
        qid = o.tags.get("wikidata")
        if qid is not None and qid in self.by_qid:
            self.present_qids.add(qid)

    def _rows_for(self, key: OsmRef, o: _OsmObject) -> tuple[Sequence[PlaceRow] | None, OsmRef]:
        """The name-list rows that claim this object (None for none) -- by
        its own id, as a same-named member way of a claimed waterway
        relation, or by its QID -- and the key whose position gives its
        dialect."""
        hit = self.by_id.get(key)
        if hit is not None:
            self.seen_keys.add(key)
            return hit, key
        member = self._member_rows(key, o)
        if member is not None:
            return member
        return self._qid_rows(key, o), key

    def _member_rows(self, key: OsmRef, o: _OsmObject) -> tuple[Sequence[PlaceRow], OsmRef] | None:
        """The rows of the waterway relation this way is a member of, if it
        carries the relation's name, and the relation's key."""
        mem = self.members.get(key)
        if mem is None:
            return None
        rel_key, rel_name = mem
        own = o.tags.get("name")
        if not (own and (own == rel_name or o.tags.get("name:de") == rel_name)):
            return None
        self.member_hits += 1
        # the member inherits the river's area
        return self.by_id.get(rel_key) or [], rel_key

    def _qid_rows(self, key: OsmRef, o: _OsmObject) -> Sequence[PlaceRow] | None:
        """The row whose `wikidata` QID this object carries, if any and if
        the object is place-like."""
        qid = o.tags.get("wikidata")
        if not qid or qid not in self.by_qid:
            return None
        if not is_place_like(o.tags):
            self.skipped_carriers.append((key, o.tags.get("name") or "?", qid))
            return None
        self.qid_hits[qid] += 1
        return self.by_qid[qid]

    def _synthetic_at(self, key: OsmRef, o: _OsmObject) -> tuple[Square, LonLat] | None:
        """The synthetic square curation puts around this node, and where the
        node is; None for any other object."""
        if not isinstance(o, osmium.osm.Node) or (square := self.synthetic.get(key)) is None:
            return None
        return square, (o.location.lon, o.location.lat)


def _square_with_names(
    key: Ref, synth: tuple[Square, LonLat], tags: Mapping[str, str]
) -> _PendingSquare:
    """The pending square around a curated node: it inherits the node's
    (curated) names and dialect, then the row's tags."""
    square, (lon, lat) = synth
    ptags = {
        k: v
        for k, v in tags.items()
        if k == "name"
        or k.startswith("name:")
        or k in (DIALECT_KEY, LOCAL_KEY, VARIETY_KEY, REF_KEY)
    }
    ptags.update(square["tags"])
    return _PendingSquare(
        key=key, label=square["label"], km2=square["km2"], lon=lon, lat=lat, tags=ptags
    )


@dataclass(frozen=True)
class _Inputs:
    """Everything `run` merges into the extract, loaded and checked."""

    reg: Registry
    names: NameList
    areas: dialects.AreaIndex | None
    curation: curationlist.Curation
    objects: dict[OsmRef, LocatedObject]
    members: dict[OsmRef, tuple[OsmRef, str]]
    osm_local: dict[OsmRef, str]


class Use(enum.Enum):
    """What the injector does about an input it can do without."""

    OFF = "off"  # ignores it
    IF_PRESENT = "if present"  # reads it; goes on without it, saying so, when it is absent
    REQUIRED = "required"  # reads it; stops when it is absent


def run(
    ws: Workspace,
    reg: Registry,
    inp: str,
    out: str,
    *,
    dry_run: bool = False,
    areas: Use = Use.IF_PRESENT,
    curation: Use = Use.IF_PRESENT,
) -> None:
    """Copy the extract `inp` to `out` with the workspace's names, dialect
    areas and curation as tags (see the module docstring), and report what
    was tagged.  `dry_run`: report only, write nothing."""
    curation_csv = None if curation is Use.OFF else ws.curation
    names = load_names(ws.names, reg)
    _print_names(names, ws.names, ws.dialects, reg)
    area_index = _load_areas(None if areas is Use.OFF else ws.areas, areas is Use.REQUIRED)
    curated = _read_curation(curation_csv, curation is Use.REQUIRED)
    _check_local_refs(names.by_id, curated.points, reg, ws.names, curation_csv)
    objects = _load_objects(area_index, names.by_id, reg, ws.names, ws.objects)
    members = scan_waterways(inp, names.by_id)
    if members:
        print(f"waterways : {len(members)} member ways of matched waterway relations")
    osm_local = scan_osm_local(inp, area_index)
    if osm_local:
        print(f"{FRISIAN_KEY}  : {len(osm_local)} object(s) in a dialect area have one in OSM")
    inputs = _Inputs(reg, names, area_index, curated, objects, members, osm_local)

    t0 = time.time()
    inj = _inject(inp, None if dry_run else out, inputs)
    _print_report(inj, inputs, inp, time.time() - t0)
    if dry_run:
        print("\n(dry run -- nothing written)")
    else:
        print(f"\nwrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


def _local_keys(by_id: Iterable[Ref]) -> list[Ref]:
    return sorted(k for k in by_id if k[0] == placelist.LOCAL_TYPE)


def _print_names(names: NameList, names_csv: str, dialects_csv: str, reg: Registry) -> None:
    """What the name list holds, and which rows claim an object or a QID twice."""
    local_keys = _local_keys(names.by_id)
    print(f"name list : {names_csv}")
    print(f"dialects  : {dialects_csv} -> {len(reg)} columns ({', '.join(reg.tags)})")
    print(
        f"usable    : {names.used} rows -> {len(names.by_id) - len(local_keys)} OSM ids + "
        f"{len(names.by_qid)} wikidata QIDs"
        + (f" + {len(local_keys)} local reference(s)" if local_keys else "")
    )
    for ckey, column, kept, kept_line, dropped, line in names.conflicts:
        print(
            f"  ! {placelist.format_osm([ckey])} claimed twice in `{column}`: "
            f"keeping {kept!r} (line {kept_line}), ignoring {dropped!r} "
            f"(places.csv line {line})"
        )
    for qid, kept_line, line in names.duplicate_qids:
        print(f"  ! {qid} claimed twice: keeping line {kept_line}, ignoring places.csv line {line}")


def _load_areas(areas_geojson: str | None, required: bool) -> dialects.AreaIndex | None:
    """The dialect areas, or None (with a warning) when there are none --
    unless the file was named explicitly (`required`)."""
    if areas_geojson and os.path.exists(areas_geojson):
        areas = dialects.AreaIndex.from_geojson(areas_geojson)
        print(f"areas     : {areas_geojson} -> {len(areas)} polygon(s): {areas.summary()}")
        return areas
    if required:
        raise PipelineError(f"dialect area file not found: {areas_geojson}")
    print(
        f"areas     : {areas_geojson or 'off'} (no {DIALECT_KEY}; "
        f"{LOCAL_KEY} only from the `local` column). "
        f"Build it with `just areas`"
    )
    return None


def _read_curation(curation_csv: str | None, required: bool) -> curationlist.Curation:
    """The curation (none when it is switched off), and what it holds."""
    curation = (
        load_curation(curation_csv, required) if curation_csv else curationlist.Curation({}, {}, {})
    )
    if curation.squares:
        print(f"synthetic : {len(curation.squares)} polygon(s) to add around nodes")
    if curation.points:
        print(f"local     : {len(curation.points)} local reference(s) positioned in {curation_csv}")
    return curation


def _check_local_refs(
    by_id: Mapping[Ref, Sequence[PlaceRow]],
    points: Mapping[Ref, LocalPoint],
    reg: Registry,
    names_csv: str,
    curation_csv: str | None,
) -> None:
    """Stop on a local reference without a position, validate the others
    (`check_local`), and warn about positions no row uses."""
    # a local reference is only as good as its curation row: the position
    # lives there, so a missing one stops the build
    unplaced = [k for k in _local_keys(by_id) if k not in points]
    if unplaced:
        lines = "\n".join(
            f"  {placelist.format_osm([k])}  "
            f"{placelist.describe(by_id[k][0], reg)} "
            f"(places.csv line {by_id[k][0].line})"
            for k in unplaced
        )
        raise ValidationError(
            f"{len(unplaced)} local reference(s) in {names_csv} have no "
            f"row with lat/lon in {curation_csv or 'the curation file (which is switched off)'}:\n{
                lines
            }"
        )
    check_local(by_id, points, reg)
    unused = sorted(k for k in points if k not in by_id)
    for k in unused:
        print(
            f"  ! {placelist.format_osm([k])} ({points[k]['label'] or '?'}) is "
            f"positioned in {curation_csv} but no row of {names_csv} uses it "
            f"-- nothing added"
        )


def _load_objects(
    areas: dialects.AreaIndex | None,
    by_id: Mapping[Ref, Sequence[PlaceRow]],
    reg: Registry,
    names_csv: str,
    objects_json: str,
) -> dict[OsmRef, LocatedObject]:
    """Where the name list's objects lie -- needed only with dialect areas,
    and then for every one of them."""
    if not areas:
        return {}
    objects = read_objects(objects_json).by_ref
    missing = unlocated(by_id, objects)
    if missing:
        lines = "\n".join(
            f"  {placelist.format_osm([k])}  {placelist.describe(by_id[k][0], reg)}"
            for k in missing
        )
        raise PipelineError(
            f"{len(missing)} object(s) of {names_csv} are not in "
            f"{objects_json} -- run `just objects` "
            f"to locate them:\n{lines}"
        )
    print(f"objects   : {objects_json} -> {len(objects)} located object(s)")
    return objects


def _inject(inp: str, out: str | None, inputs: _Inputs) -> Injector:
    """Copy `inp` to `out` with the tags added (`out` None: a dry run that
    only counts) and return the injector, which holds the counts."""
    writer: osmium.SimpleWriter | None = None
    if out is not None:
        # copy the input header so the extract bounds survive (Planetiler uses
        # them; without bounds it renders low-zoom tiles for the whole world)
        writer = osmium.SimpleWriter(out, overwrite=True, header=osmscan.header(inp))
    names, curation = inputs.names, inputs.curation
    inj = Injector(
        writer,
        names.by_id,
        names.by_qid,
        inputs.reg,
        inputs.areas,
        inputs.objects,
        curation.objects,
        inputs.members,
        curation.squares,
        curation.points,
        inputs.osm_local,
    )
    for o in osmium.FileProcessor(inp):
        if isinstance(o, (osmium.osm.Node, osmium.osm.Way, osmium.osm.Relation)):
            inj.handle(o, o.type_str())
    inj.finish()
    if writer is not None:
        writer.close()
    return inj


# ---------------------------------------------------------------- report ----
def _print_report(inj: Injector, inputs: _Inputs, inp: str, seconds: float) -> None:
    """What the scan tagged, added and curated, and what it did not find."""
    in_file = os.path.basename(inp)
    _print_tagged(inj, inputs, seconds)
    _print_dialects(inj, inputs.reg, inputs.areas)
    _print_added_points(inj, inputs.names.by_id, inputs.reg)
    _print_not_found(inj, inputs.names, inputs.reg, in_file)
    _print_skipped_carriers(inj, inputs.names.by_qid, inputs.reg)
    if inputs.curation.objects:
        _print_curated(inj, inputs.curation.objects, in_file)
    if inputs.curation.squares or inj.created:
        _print_synthetic(inj, inputs.curation.squares, in_file)


def _print_tagged(inj: Injector, inputs: _Inputs, seconds: float) -> None:
    by_qid = inputs.names.by_qid
    total = sum(inj.hits.values())
    print(f"\nscanned {inj.n_objects:,} objects in {seconds:.0f}s")
    print(
        f"tagged  {total} objects: "
        f"{inj.hits['n']} nodes, {inj.hits['w']} ways, {inj.hits['r']} relations"
        + (
            f" (of these {sum(inj.qid_hits.values())} matched by wikidata: "
            f"{len(inj.present_qids)} of {len(by_qid)} QIDs present)"
            if by_qid
            else ""
        )
        + (
            f"; {inj.member_hits} same-named member ways of waterway relations"
            if inputs.members
            else ""
        )
    )


def _print_dialects(inj: Injector, reg: Registry, areas: dialects.AreaIndex | None) -> None:
    """The names written per dialect and the objects per dialect area."""
    print("names written per dialect:")
    for d in reg:
        n = inj.tag_hits["name:" + d["tag"]]
        if n:
            print(f"  name:{d['tag']:<15} {n:>5}  {d['label']}")
    claimed, unclaimed = inj.osm_local_hits["claimed"], inj.osm_local_hits["unclaimed"]
    print(
        f"  {LOCAL_KEY:<20} {inj.local_hits:>5}  local form"
        + (f" ({claimed} of them OSM's {FRISIAN_KEY})" if claimed else "")
    )
    if unclaimed:
        print(f"  {LOCAL_KEY:<20} {unclaimed:>5}  OSM's {FRISIAN_KEY} on objects no row claims")
    if areas:
        print("objects per dialect area:")
        for tag, n in inj.area_hits.most_common():
            print(f"  {DIALECT_KEY}={tag:<15} {n:>5}")
        if not inj.area_hits:
            print("  (none -- no tagged object lies in a dialect area)")


def _print_added_points(
    inj: Injector, by_id: Mapping[Ref, Sequence[PlaceRow]], reg: Registry
) -> None:
    if not inj.added_points:
        return
    print(f"\nadded {len(inj.added_points)} node(s) for places that are not in OSM:")
    for nid, key, _label, lon, lat, tags in inj.added_points:
        print(
            f"  node/{nid}  {placelist.format_osm([key])} "
            f"{placelist.describe(by_id[key][0], reg)} at {lat:.5f}, {lon:.5f}: "
            + ", ".join(f"{a}={b}" for a, b in sorted(tags.items()) if not a.startswith("name"))
        )


def _print_not_found(inj: Injector, names: NameList, reg: Registry, in_file: str) -> None:
    """The ids and QIDs of the name list that the extract does not have."""
    by_id, by_qid = names.by_id, names.by_qid
    missing = sorted(k for k in set(by_id) - inj.seen_keys if k[0] != placelist.LOCAL_TYPE)
    if missing:
        print(f"\n{len(missing)} rows reference ids that are not in {in_file}:")
        for key in missing:
            print(f"  {placelist.format_osm([key])}  {placelist.any_name(by_id[key][0], reg)}")
    nf = [q for q in by_qid if q not in inj.present_qids]
    if nf:
        print(
            f"\n{len(nf)} wikidata QIDs not present in the file: "
            + ", ".join(f"{q} ({placelist.any_name(by_qid[q][0], reg)})" for q in sorted(nf))
        )


def _print_skipped_carriers(
    inj: Injector, by_qid: Mapping[str, Sequence[PlaceRow]], reg: Registry
) -> None:
    """The objects that carry a row's QID but are left alone (#55)."""
    if not inj.skipped_carriers:
        return
    print(
        f"\n{len(inj.skipped_carriers)} objects carry a QID of the list "
        "but are not place-like -- not tagged:"
    )
    for (t, i), name, qid in inj.skipped_carriers:
        print(f"  {t}/{i}  {name}: {qid} ({placelist.any_name(by_qid[qid][0], reg)})")


def _print_curated(inj: Injector, curation: Mapping[Ref, Tuning], in_file: str) -> None:
    cur_total = sum(inj.cur_hits.values())
    print(
        f"\ncurated {cur_total} objects: {inj.cur_hits['n']} nodes, "
        f"{inj.cur_hits['w']} ways, {inj.cur_hits['r']} relations"
    )
    for k in sorted(inj.seen_cur):
        print(
            f"  {k[0]}/{k[1]}  {curation[k]['label'] or '?'}: "
            + ", ".join(f"{a}={b}" for a, b in sorted(curation[k]["tags"].items()))
        )
    cur_missing = sorted(set(curation) - inj.seen_cur)
    if cur_missing:
        print(f"\n{len(cur_missing)} curation rows reference ids that are not in {in_file}:")
        for t, i in cur_missing:
            print(f"  {t}/{i}  {curation[(t, i)]['label'] or '?'}")


def _print_synthetic(inj: Injector, synthetic: Mapping[Ref, Square], in_file: str) -> None:
    print(f"\nadded {len(inj.created)} synthetic polygon(s):")
    for wid, nids, label, km2 in inj.created:
        print(f"  way/{wid} (nodes {nids[0]}..{nids[-1]})  {label or '?'}: {km2:g} km²")
    synth_missing = sorted(
        set(synthetic) - {p["key"] for p in inj.pending if p["key"][0] != placelist.LOCAL_TYPE}
    )
    for t, i in synth_missing:
        print(
            f"  ! {t}/{i} {synthetic[(t, i)]['label'] or '?'}: node not in "
            f"{in_file}, no polygon added"
        )


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("inject", __doc__)
    ap.add_argument("infile")
    ap.add_argument("outfile")
    # a file named here must exist; the default areas and curation are
    # optional (the injector then says so and goes on without them)
    cli.add_workspace_options(ap, "names", "dialects", "areas", "objects", "curation")
    ap.add_argument("--no-curation", action="store_true", help="ignore the curation file entirely")
    ap.add_argument("--no-areas", action="store_true", help="ignore the dialect areas entirely")
    ap.add_argument(
        "--dry-run", action="store_true", help="report what would be tagged, write nothing"
    )
    a = ap.parse_args(argv)
    if not a.dry_run and os.path.abspath(a.infile) == os.path.abspath(a.outfile):
        ap.error("refusing to overwrite the input file")
    ws = cli.workspace(a)
    run(
        ws,
        registry.read(ws.dialects),
        a.infile,
        a.outfile,
        dry_run=a.dry_run,
        areas=_use(a.no_areas, a.areas),
        curation=_use(a.no_curation, a.curation),
    )
    return 0


def _use(switched_off: bool, named: str | None) -> Use:
    """What to do about an input the command line may switch off or name."""
    if switched_off:
        return Use.OFF
    return Use.IF_PRESENT if named is None else Use.REQUIRED
