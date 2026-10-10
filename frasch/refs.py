"""The references of an `osm` cell: which objects a row of a hand-edited file
is about.

A cell holds one or more OSM references -- `node/123`, `way/1; way/2` -- or
ONE local reference `local/<slug>` for a place OSM does not have (see
names/README.md).  Parsed, a reference is a `(type, id)` pair: `("w", 12)`
for an OSM object, `("l", "westerheide-amrum")` for a local one.  The name
list, the map curation, the dialect area list and the objects file all spell
their references this way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from frasch.errors import Invalid

OSM_TYPES = {"node": "n", "way": "w", "relation": "r"}
# `local/<slug>`: not an OSM object but a place of our own, positioned in
# names/curation.csv.  Keyed like the others, with the slug as its id.
LOCAL_TYPE = "l"
TYPE_NAME = {v: k for k, v in OSM_TYPES.items()} | {LOCAL_TYPE: "local"}
# the shape of a local reference's slug (and of a row id of the name list)
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# One reference as `parse` returns it: `("w", 12)` for an OSM object,
# `("l", "westerheide-amrum")` for a local one.
Ref = tuple[str, int | str]
# one that names an OSM object: a node, way or relation id
OsmRef = tuple[str, int]


def parse(cell: str | None, where: str = "") -> list[Ref]:
    """`"way/12; way/13"` -> `[("w", 12), ("w", 13)]`;
    `"local/westerheide-amrum"` -> `[("l", "westerheide-amrum")]`.

    A local reference stands alone: it is the whole cell, never one of
    several."""
    out: list[Ref] = []
    for ref in (cell or "").split(";"):
        ref = ref.strip()
        if not ref:
            continue
        m = re.fullmatch(rf"(node|way|relation)/(\d+)|(local)/({SLUG.pattern})", ref)
        if not m:
            raise Invalid(
                where,
                f"bad reference {ref!r} (expected node/ID, "
                f"way/ID, relation/ID or local/slug with a slug "
                f"of lowercase letters, digits and hyphens)",
            )
        if m.group(3):
            out.append((LOCAL_TYPE, m.group(4)))
        else:
            out.append((OSM_TYPES[m.group(1)], int(m.group(2))))
    if len(out) > 1 and any(t == LOCAL_TYPE for t, _ in out):
        raise Invalid(
            where,
            f"a local reference stands alone, it cannot be "
            f"combined with other references: {cell!r}",
        )
    return out


def format(refs: Iterable[Ref]) -> str:
    """`[("w", 12), ("w", 13)]` -> `"way/12; way/13"`, as a cell spells them."""
    return "; ".join(f"{TYPE_NAME[t]}/{i}" for t, i in refs)


def as_osm_ref(ref: Ref) -> OsmRef | None:
    """The reference as one to an OSM object; None for a local one."""
    t, i = ref
    return (t, i) if isinstance(i, int) else None


def local_slug(ref: Ref) -> str | None:
    """The slug of a local reference; None for one to an OSM object."""
    _, i = ref
    return i if isinstance(i, str) else None


def osm_only(refs: Iterable[Ref]) -> list[OsmRef]:
    """The references to OSM objects among `refs` -- none for a local
    reference."""
    return [osm for ref in refs if (osm := as_osm_ref(ref))]


def local_of(refs: Iterable[Ref]) -> str | None:
    """The slug when `refs` are a local reference (`local/<slug>`), else None.

    Places OSM does not have (Harden, most Köge, vanished Halligen, a Warft
    nobody has mapped) get a reference of our own; names/curation.csv
    positions it and says how the map treats it, the injector adds the object,
    the search index takes the position from there, and the matcher leaves the
    row alone."""
    first = next(iter(refs), None)
    return local_slug(first) if first else None
