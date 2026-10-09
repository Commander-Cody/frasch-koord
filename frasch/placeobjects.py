"""The objects of the name list's rows: which references the objects file
(frasch.objects) has to be located for (`named`), what to do about one it
has no object for (`unlocated`, `require_located`), and the object a row's
search entry stands for (`for_row`) -- for a place OSM does not have, the
point the injector adds (`local_point`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from frasch import placelist, refs
from frasch.dialects import Registry
from frasch.errors import PipelineError, rebuild
from frasch.geo import LonLat
from frasch.objects import LocatedObject, Objects, point
from frasch.placelist import PlaceRow, Row
from frasch.refs import OsmRef


def named(rows: Iterable[PlaceRow], reg: Registry) -> dict[OsmRef, PlaceRow]:
    """The references the objects file is located for -- those to OSM objects
    (not the local ones) of the rows on the map -- each with the row that
    names it."""
    return {ref: row for row in rows if placelist.on_map(row, reg) for ref in row.osm_refs}


def unlocated(objects: Objects, rows: Mapping[OsmRef, PlaceRow]) -> list[str]:
    """What to do about each reference of `rows` ({reference: the row that
    names it}) the objects file has no object for, a line each.  One that was
    asked for in vain is the row's to correct; any other has yet to be
    located."""
    not_located = f"is not located yet -- locate it with {rebuild('objects')}"
    in_no_extract = "is in none of the extracts -- correct the `osm` cell of its row"
    return [
        f"{rows[ref]['id']} (line {rows[ref].line}): {refs.format([ref])} "
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


def for_row(
    objects: Objects, row: PlaceRow, local_points: Mapping[str, LonLat], reg: Registry
) -> LocatedObject | None:
    """The object a row's search entry stands for: the object of the first
    reference in its `osm` cell, or for a local reference the point the
    injector adds (`local_point`; `local_points`: the curation's position of
    each slug).  None for a row keyed by its QID alone."""
    slug = row.local
    if slug:
        if slug not in local_points:
            raise PipelineError(
                f"{row['id']} (line {row.line}): local/{slug} has no row with "
                f"lat/lon in the curation file"
            )
        return local_point(row, local_points[slug], reg)
    return objects.by_ref[row.osm_refs[0]] if row.osm_refs else None


def local_point(row: Row, position: LonLat, reg: Registry) -> LocatedObject:
    """The point the injector adds for a row OSM has no object for (a local
    reference): at its curation position, with the generic name the point
    gets (`placelist.point_name`)."""
    name = placelist.point_name(row, reg)
    return point(*position, name=name) if name else point(*position)
