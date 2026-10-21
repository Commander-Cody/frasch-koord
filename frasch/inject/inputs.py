"""Everything a run of the injector merges into the extract, loaded and
checked before anything is written (`load_inputs`): the name list, the dialect
areas, the curation and the objects file, and what two pre-passes read out
of the extract itself.  Every one of the files is needed; a missing one, or
one that does not fit the others, stops the run with a PipelineError."""

from __future__ import annotations

import os
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from frasch import curationlist, locate, osmscan, placelist, placenames, placeobjects, refs
from frasch.curationlist import Curation, LocalPoint
from frasch.dialect_areas import AreaIndex
from frasch.dialects import Registry
from frasch.errors import PipelineError
from frasch.inject.claims import Members, NameList, load_names, scan_waterways
from frasch.inject.synthetic import LocalPlace, local_places
from frasch.objects import LocatedObject, read_objects
from frasch.paths import Workspace
from frasch.placelist import PlaceRow
from frasch.refs import OsmRef, Ref

# OSM's own Frisian name, of no stated dialect
FRISIAN_KEY = "name:frr"


@dataclass(frozen=True)
class Inputs:
    """What a run merges into the extract."""

    reg: Registry
    names: NameList
    areas: AreaIndex
    curation: Curation
    # where the name list's objects lie, and what OSM says of them
    objects: dict[OsmRef, LocatedObject]
    # the places OSM does not have that a row uses, with their tags
    local_places: list[LocalPlace]
    # the pre-passes over the extract: the member ways of the claimed
    # waterway relations, and the local-name tags (`frasch:local` and
    # `frasch:dialect`) of the objects no row holds that have OSM's Frisian
    # name and lie in a Frisian or Low Saxon area
    members: Members
    osm_local: dict[OsmRef, dict[str, str]]


def load_inputs(ws: Workspace, reg: Registry, extract: str) -> Inputs:
    """The inputs of a run over `extract`, from the files of the workspace."""
    names = load_names(ws.names, reg)
    areas = AreaIndex.from_geojson(ws.areas)
    curation = _read_curation(ws.curation)
    _require_positions(names.by_id, curation.points, reg, ws)
    places = local_places(names.by_id, curation.points, areas, reg)
    return Inputs(
        reg=reg,
        names=names,
        areas=areas,
        curation=curation,
        objects=_read_objects(ws.objects, names.by_id),
        local_places=places,
        members=scan_waterways(extract, names.by_id),
        osm_local=scan_osm_local(extract, areas, names.by_id, reg),
    )


def local_keys(keys: Collection[Ref]) -> list[Ref]:
    """The local references among `keys`, in order."""
    return sorted(key for key in keys if key[0] == refs.LOCAL_TYPE)


def _read_curation(path: str) -> Curation:
    if not os.path.exists(path):
        raise PipelineError(f"curation file not found: {path}")
    return curationlist.read(path)


def _require_positions(
    by_id: Mapping[Ref, PlaceRow], points: Mapping[Ref, LocalPoint], reg: Registry, ws: Workspace
) -> None:
    """Stop on a local reference of the name list without a position.  A
    local reference is only as good as its curation row: the position lives
    there."""
    unplaced = [key for key in local_keys(by_id) if key not in points]
    if not unplaced:
        return
    lines = "\n".join(
        f"  {refs.format([key])}  {placelist.describe(by_id[key], reg)} "
        f"(places.csv line {by_id[key].line})"
        for key in unplaced
    )
    raise PipelineError(
        f"{len(unplaced)} local reference(s) in {ws.names} have no "
        f"row with lat/lon in {ws.curation}:\n{lines}"
    )


def _read_objects(path: str, by_id: Mapping[Ref, PlaceRow]) -> dict[OsmRef, LocatedObject]:
    """Where the name list's objects lie -- needed for every one of them:
    without a position an object would get no dialect, and the search index,
    which reads the same file, refuses it too."""
    objects = read_objects(path)
    located = {osm: row for key, row in by_id.items() if (osm := refs.as_osm_ref(key))}
    placeobjects.require_located(objects, path, located)
    return objects.by_ref


def scan_osm_local(
    extract: str, areas: AreaIndex, held: Collection[Ref], reg: Registry
) -> dict[OsmRef, dict[str, str]]:
    """The local-name tags (placenames.unclaimed_tags, #81) of every object
    of the extract that has OSM's own Frisian name (`name:frr`) and that no
    row holds by reference (`held`): OSM's name in the language of the area
    it lies in, written with that area -- its `name:frr` in a Frisian area,
    its `name:nds` (if it has one) in a Low Saxon one.  In a Synnejysk area
    and outside every area it has none.  An object a row holds has its names
    in the objects file.  Only `name:frr` is scanned for: an object in a Low
    Saxon area without one keeps its `name:nds`, which labels the local view
    anyway, the step of the label chain after `frasch:local`.

    One pass finds the objects that carry the tag, whatever they are (a
    place, a street, a station); frasch.locate then says where each lies,
    as it does for the objects of the name list: a node at its own location,
    a way or relation inside its polygon, else at its outline point."""
    named = set(osmscan.tagged(extract, FRISIAN_KEY)) - set(held)
    local = {
        ref: placenames.unclaimed_tags(obj, areas, reg)
        for ref, obj in locate.locate_in(extract, named).items()
    }
    return {ref: tags for ref, tags in local.items() if tags}
