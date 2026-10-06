"""The objects file, names/osm_objects.json: where the objects of the name
list are, as frasch.locate worked it out.  The search index, the injector and
`frasch check-outputs` read it (and `just update`, to tell whether it is
stale).

For every OSM reference in the `osm` column of a row that is on the map, the
file records

  lon, lat     where the object is: a node's own location; for a way or
               relation that closes into a polygon, a point *inside* that
               polygon (shapely's `representative_point`) -- an island is not
               where its coastline starts, and a vertex average can lie in the
               sea; for anything else, the relation's `label` / `admin_centre`
               member, else the first vertex
  outline      the second point for the dialect lookup, see `dialect_at`
  admin_level  of an administrative boundary (see `locate.object_facts`)
  name_nds     OSM's Low Saxon name (see `locate.object_facts`)
  name         OSM's generic name (see `locate.object_facts`)
  name_frr     OSM's Frisian name (see `locate.object_facts`)

and, as `built_from`, the extracts it was read from (frasch.provenance).

The file is **committed**, like names/dialect_areas.geojson: it is small, and
the search index can then be rebuilt -- and checked in CI -- without an
extract.  Rebuild it (`just objects`) when a row gets a new `osm` reference;
the search export and the injector stop on a reference it does not know.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from typing import NamedTuple, NotRequired, TypedDict

from frasch import placelist
from frasch.dialects import AreaIndex
from frasch.errors import PipelineError, rebuild
from frasch.placelist import OsmRef, PlaceRow, Ref
from frasch.provenance import Stamp
from frasch.registry import Registry

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


# -------------------------------------------------------------- dialects ----
# OSM's admin_level of a German municipality; anything lower is a Kreis or an
# Amt, which spans several dialects
MUNICIPALITY_LEVEL = 8


def dialect_at(obj: LocatedObject, areas: AreaIndex | None) -> str | None:
    """The dialect spoken where an object of the objects file lies, or None:
    the area around its point, else the area around its outline point.

    The two points miss in opposite directions: an island's coastline runs
    outside the municipality boundaries the areas are cut from (Amrum), while
    an area may cover only part of an island (the Langeneß municipality holds
    only the south-west third of Oland), so the point inside the island falls
    outside it and a vertex still lands in it.  The first point that is in an
    area at all wins, so nothing that had a dialect can lose it.

    An administrative area above municipality level gets none: Kreis
    Nordfriesland would otherwise be "Nordergoesharde" because its interior
    point happens to lie there."""
    if areas is None or obj.get("admin_level", MUNICIPALITY_LEVEL) < MUNICIPALITY_LEVEL:
        return None
    points = [(obj["lon"], obj["lat"])]
    if "outline" in obj:
        points.append((obj["outline"][0], obj["outline"][1]))
    for lon, lat in points:
        tag = areas.lookup(lon, lat)
        if tag:
            return tag
    return None


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

    def missing(self, refs: Iterable[Ref]) -> list[OsmRef]:
        """The references to OSM objects among `refs` that the file has no
        object for, in the file's order."""
        osm_refs = (osm for ref in refs if (osm := placelist.as_osm_ref(ref)))
        return sorted((ref for ref in osm_refs if ref not in self.by_ref), key=ref_order)


def read_objects(path: str) -> Objects:
    if not os.path.exists(path):
        raise PipelineError(f"{path} not found -- build it with {rebuild('objects')}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    by_ref = {placelist.osm_refs(ref)[0]: obj for ref, obj in data["objects"].items()}
    not_found = placelist.osm_refs("; ".join(data.get("not_found", [])))
    return Objects(by_ref, Stamp.from_json(data["built_from"]), frozenset(not_found))


def named(rows: Iterable[PlaceRow], reg: Registry) -> dict[OsmRef, PlaceRow]:
    """The references the file is located for -- those to OSM objects (not
    the local ones) of the rows on the map -- each with the first row that
    names it."""
    found: dict[OsmRef, PlaceRow] = {}
    for row in rows:
        if placelist.on_map(row, reg):
            for ref in placelist.osm_refs(row["osm"]):
                found.setdefault(ref, row)
    return found


def unlocated(objects: Objects, rows: Mapping[OsmRef, PlaceRow]) -> list[str]:
    """What to do about each reference of `rows` ({reference: the row that
    names it}) the file has no object for, a line each.  One that was asked
    for in vain is the row's to correct; any other has yet to be located."""
    not_located = f"is not located yet -- locate it with {rebuild('objects')}"
    in_no_extract = "is in none of the extracts -- correct the `osm` cell of its row"
    return [
        f"{rows[ref]['id']} (line {rows[ref].line}): {placelist.format_osm([ref])} "
        + (in_no_extract if ref in objects.not_found else not_located)
        for ref in objects.missing(rows)
    ]


def require_located(objects: Objects, path: str, rows: Mapping[OsmRef, PlaceRow]) -> None:
    """Stop when a reference of `rows` (as for `unlocated`) has no object in
    the objects file at `path`."""
    lines = unlocated(objects, rows)
    if lines:
        raise PipelineError(
            f"{len(lines)} object(s) of the name list are not in {path}:\n"
            + "\n".join(f"  {line}" for line in lines)
        )


def objects_json(objects: Objects) -> str:
    """The file's text: one object per line, in reference order, so a re-run
    on a moved object is a one-line diff."""
    lines = [
        f"{json.dumps(placelist.format_osm([ref]))}:{_compact(_rounded(obj))}"
        for ref, obj in sorted(objects.by_ref.items(), key=lambda item: ref_order(item[0]))
    ]
    not_found = [placelist.format_osm([ref]) for ref in sorted(objects.not_found, key=ref_order)]
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
