"""What a decision of the curation view makes of a row of the name list.

An entry of the patch (frasch.patch) names an action; `ACTIONS` says what
each makes of an entry for its row: the row's new reference, for a place OSM
does not have the curation row that positions it, and what the log says.
names/curate-patch.schema.json says which fields an action's entry has; the
rules here are those that need the lists -- the row must be the matcher's to
fill (`owner_problem`), and nothing another row holds can be taken.

Nothing here writes: `frasch curate apply` (frasch.curate) does, with what an
action returns.  A new action is one entry of `ACTIONS` and its branch of the
schema.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Collection, Mapping
from typing import NamedTuple

from frasch import curationlist, errors, kinds, placelist, refs
from frasch.dialects import Registry
from frasch.patch import PatchEntry
from frasch.placelist import PlaceList, PlaceRow, Reference, Row


class Refused(Exception):
    """A decision that cannot be applied to its row; its message says why."""


@dataclasses.dataclass(frozen=True)
class Standing:
    """How the lists stand when a decision is made: what it is checked
    against, and what its log line names."""

    reg: Registry
    curation: str  # the curation file
    claimed: Mapping[str, int]  # what the other rows hold: claim -> its row's line
    slugs: Collection[str]  # the local references there are


class Decision(NamedTuple):
    """What an action makes of an entry for its row."""

    # the row's reference from now on -- all of it: nothing of what the
    # matcher gave the row stays
    reference: Reference
    curation: dict[str, str] | None = None  # the curation row that positions the place
    remark: str = ""  # what the log says besides the reference

    @property
    def text(self) -> str:
        """What the decision changes, for the log: every cell of the
        reference, an empty one as `-`, since a decision leaves nothing of an
        older reference."""
        osm, wikidata, status = (cell or "-" for cell in self.reference)
        return f"osm = {osm}, wikidata = {wikidata}, status = {status}{self.remark}"


Action = Callable[[PatchEntry, PlaceRow, Standing], Decision]


def owner_problem(row: PlaceRow, names: PlaceList) -> str | None:
    """Why apply refuses an entry's row of the list `names` before looking
    at its decision, or None: the row must be the matcher's to fill."""
    state = placelist.state(row, names.reg)
    if not state.matchers:
        return (
            f"{names.path}:{row.line} is not the matcher's to fill "
            f"({state.label}: status={row['status'] or 'empty'}, osm={row['osm'] or '-'})"
        )
    return None


def _osm(entry: PatchEntry, row: PlaceRow, standing: Standing) -> Decision:
    """The row is these OSM objects -- none of which another row claims."""
    try:
        chosen = refs.parse(entry["osm"])
    except errors.Invalid as exc:
        raise Refused(str(exc)) from None
    if not chosen:
        raise Refused("`osm` names no object")
    if any(t == refs.LOCAL_TYPE for t, _ in chosen):
        raise Refused("a local reference is action=local, not action=osm")
    picked = Reference.checked(chosen, entry.get("wikidata", ""))
    taken = placelist.claim_problems(
        placelist.Claims(chosen, picked.wikidata).keys, standing.claimed
    )
    if taken:
        raise Refused("; ".join(taken))
    return Decision(picked)


def _local(entry: PatchEntry, row: PlaceRow, standing: Standing) -> Decision:
    """A place OSM does not have: a local reference, and the curation row
    that positions it."""
    slug = entry["slug"]
    if slug in standing.slugs:
        raise Refused(f"local/{slug} is already taken")
    reference = Reference.local(slug)
    lat, lon = fmt_deg(entry["lat"]), fmt_deg(entry["lon"])
    cur = dict.fromkeys(curationlist.COLUMNS, "") | {
        "osm": reference.osm,
        "name": curation_name(row, standing.reg),
        "lat": lat,
        "lon": lon,
        "note": entry.get("note", "").strip(),
    }
    remark = f"; {standing.curation} += {lat}/{lon}"
    if (km2 := entry.get("polygon_km2")) is not None:
        # the README's Koog route: no labelled node, only a square of that
        # area -- and OpenMapTiles labels a polygon only as island
        cur.update(polygon_km2=f"{km2:g}", set_tags="place=island")
        remark += f", polygon_km2 = {km2:g}"
    elif not kinds.rule(row["kind"]).point_place:
        remark += (
            f"\n    warning: kind={row['kind']} has no default `place=` "
            f"(`point_place` in frasch/kinds.py) -- put one into the curation row's "
            f"`set_tags` before the next build"
        )
    return Decision(reference, cur, remark)


def _skip(entry: PatchEntry, row: PlaceRow, standing: Standing) -> Decision:
    """The row is never on the map."""
    return Decision(Reference.skipped())


# What each action of the patch schema makes of an entry -- the one place
# that tells the actions apart.  None: nothing to write (`clear` withdraws
# the row's earlier decision, and reading the patch has done that already).
ACTIONS: Mapping[str, Action | None] = {
    "osm": _osm,
    "local": _local,
    "skip": _skip,
    "clear": None,
}


def curation_name(row: Row, reg: Registry) -> str:
    """The free-text label of the appended curation row -- German, else Danish,
    else Frisian, plus the hint, so the file stays readable by a human."""
    name = placelist.point_name(row, reg)
    return f"{name} ({row['hint']})" if row["hint"] else name


def fmt_deg(v: float) -> str:
    return f"{v:.6f}".rstrip("0").rstrip(".")
