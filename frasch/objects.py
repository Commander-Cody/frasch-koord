"""The objects file, names/osm_objects.json: where the objects of the name
list are, as frasch.locate worked it out.  The search index, the injector and
`frasch check-outputs` read it (and `just update`, to tell whether it is
stale).  Which objects the rows of the name list need, and what to do about
one the file lacks, is frasch.placeobjects'.

For every OSM reference in the `osm` column of a row that is on the map, the
file records

  lon, lat     where the object is: a node's own location; for a way or
               relation that closes into a polygon, a point *inside* that
               polygon (shapely's `representative_point`) -- an island is not
               where its coastline starts, and a vertex average can lie in the
               sea; for anything else, the relation's `label` / `admin_centre`
               member, else the first vertex
  outline      the second point for the dialect lookup, see
               `dialect_areas.dialect_at`
  admin_level  of an administrative boundary (see `locate.object_facts`)
  name_nds     OSM's Low Saxon name (see `locate.object_facts`)
  name         OSM's generic name (see `locate.object_facts`)
  name_frr     OSM's Frisian name (see `locate.object_facts`)

and, as `built_from`, the extracts it was read from (frasch.provenance).  A
reference that none of them holds is listed in `not_found` (left out when
there is none), so the file says what it was located for: the references it
has an object for and those.  It is stale when the rows on the map name
other ones (frasch.pipeline).

The file is **committed**, like names/dialect_areas.geojson: it is small, and
the search index can then be rebuilt -- and checked in CI -- without an
extract.  Rebuild it (`just rebuild objects`) when a row gets a new `osm`
reference; the search export and the injector stop on a reference it has no
object for, and say what helps (`placeobjects.unlocated`): locating it, or
-- when no extract holds it -- correcting the row.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from typing import NamedTuple, NotRequired, TypedDict, Unpack

from frasch import refs
from frasch.errors import PipelineError, rebuild
from frasch.provenance import Stamp, unstamped
from frasch.refs import OsmRef, Ref

ROUND = 6


class Facts(TypedDict, total=False):
    """See `locate.object_facts`."""

    admin_level: int
    name_nds: str
    name: str
    name_frr: str


class Point(TypedDict):
    lon: float
    lat: float
    outline: NotRequired[list[float]]


class LocatedObject(Point, Facts):
    """One object of the objects file: where it is (`lon`, `lat`, and for
    an area the `outline` point too) and its `locate.object_facts`."""


def point(lon: float, lat: float, **facts: Unpack[Facts]) -> LocatedObject:
    """An object that is a point, with what is known of it (`Facts`)."""
    at: Point = {"lon": lon, "lat": lat}
    return {**at, **facts}


class Objects(NamedTuple):
    """The objects file, read back: `by_ref` maps ('w', 12) to its object."""

    by_ref: dict[OsmRef, LocatedObject]
    stamp: Stamp  # the extracts it was read from
    # the references that were asked for and that none of the extracts holds
    not_found: frozenset[OsmRef] = frozenset()

    @property
    def asked(self) -> set[OsmRef]:
        """The references the file was located for."""
        return set(self.by_ref) | self.not_found

    def missing(self, wanted: Iterable[Ref]) -> list[OsmRef]:
        """The references to OSM objects among `wanted` that the file has no
        object for, in the file's order."""
        return sorted(
            (ref for ref in refs.osm_only(wanted) if ref not in self.by_ref), key=ref_order
        )


def read_objects(path: str) -> Objects:
    if not os.path.exists(path):
        raise PipelineError(f"{path} not found -- build it with {rebuild('objects')}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if "built_from" not in data:
        raise unstamped(path, "objects")
    by_ref = {_ref(key): obj for key, obj in data["objects"].items()}
    not_found = frozenset(map(_ref, data.get("not_found", [])))
    return Objects(by_ref, Stamp.from_json(data["built_from"]), not_found)


def _ref(spelled: str) -> OsmRef:
    """A reference as the file spells it: always one to an OSM object."""
    (ref,) = refs.osm_only(refs.parse(spelled))
    return ref


def objects_json(objects: Objects) -> str:
    """The file's text: one object per line, in reference order, so a re-run
    on a moved object is a one-line diff."""
    lines = [
        f"{json.dumps(refs.format([ref]))}:{_compact(_rounded(obj))}"
        for ref, obj in sorted(objects.by_ref.items(), key=lambda item: ref_order(item[0]))
    ]
    not_found = [refs.format([ref]) for ref in sorted(objects.not_found, key=ref_order)]
    return (
        f'{{"built_from":{_compact(objects.stamp.as_json())},\n'
        + (f'"not_found":{_compact(not_found)},\n' if not_found else "")
        + '"objects":{\n'
        + ",\n".join(lines)
        + "\n}}\n"
    )


def _compact(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def ref_order(ref: OsmRef) -> tuple[int, int]:
    """The order of the references in the file: nodes, ways, relations, each by id."""
    t, i = ref
    return "nwr".index(t), i


def _rounded(obj: LocatedObject) -> dict[str, object]:
    return {
        k: (
            round(v, ROUND)
            if isinstance(v, float)
            else [round(x, ROUND) for x in v]
            if isinstance(v, list)
            else v
        )
        for k, v in obj.items()
    }
