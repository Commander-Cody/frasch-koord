"""Which names and attributes a place gets -- the one rule the tiles
(frasch.inject_names) and the search index (frasch.searchindex) are built by,
so a map label and its search entry cannot disagree -- and the table of the
tile keys they are written under.

    frasch tile-keys

prints the attribute keys of that table, comma-separated: what Planetiler has
to pass through into the tiles (`--extra_name_tags`, tiles/nametags.sh).

`resolve` holds the rule (names/README.md, "The shared name logic"):

* the name of a place in dialect T is its column, else -- if T is the dialect
  of the area the place lies in -- its `local` column
* the local name, what the people of the place itself call it, is the `local`
  column, else the name in the dialect of the area, else OSM's own `name:frr`
  of the object, inside a dialect area only
* the variety is the bracket remark on the primary `local` variant

Where the place lies is its object's position (frasch.objects), which
dialect is spoken there the dialect areas' answer (`dialect_areas.dialect_at`).
`as_tags` writes the result as the tags of a tile feature, `as_entry` as an
entry of the search index; `TILE_KEY` says which field of an entry is which
tile key, and `frasch check-tiles` compares the two by it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import NamedTuple, NotRequired, TypedDict

from frasch import cli, namecell
from frasch.dialect_areas import AreaIndex, dialect_at
from frasch.dialects import LOCAL_COLUMN, Registry
from frasch.objects import LocatedObject
from frasch.placelist import Row

# ------------------------------------------------------------ tile keys ----
GERMAN_KEY = "name:de"
KIND_KEY = "frasch:kind"
DIALECT_KEY = "frasch:dialect"
LOCAL_KEY = "frasch:local"
VARIETY_KEY = "frasch:variety"
# the row a label comes from: its `id`.  The injector writes it; a curation
# row may set it by hand (frasch.check_inputs makes sure it names a row)
REF_KEY = "frasch:ref"
# not a place's names: the zooms names/curation.csv gives a feature
MINZOOM_KEY = "frasch:minzoom"
MAXZOOM_KEY = "frasch:maxzoom"
# a name in one language, `name:de`: Planetiler carries these by language
# (its --languages), every other key by name (--extra_name_tags)
LANGUAGE_PREFIX = "name:"

# field of a search entry (and of `PlaceNames`) -> the tile key it is written
# under.  The entry's `names` are not in it: one key per dialect, `dialect_key`.
TILE_KEY = {
    "id": REF_KEY,
    "kind": KIND_KEY,
    "name_de": GERMAN_KEY,
    "dialect": DIALECT_KEY,
    "local": LOCAL_KEY,
    "variety": VARIETY_KEY,
}


def dialect_key(tag: str) -> str:
    """The tile key of a place's name in one dialect: `name:frr-x-mooring`."""
    return LANGUAGE_PREFIX + tag


def attribute_keys() -> list[str]:
    """The tile keys that are no name in a language -- the `frasch:*` ones."""
    keys = [*TILE_KEY.values(), MINZOOM_KEY, MAXZOOM_KEY]
    return [key for key in keys if not key.startswith(LANGUAGE_PREFIX)]


# ------------------------------------------------------------- the rule ----
class PlaceNames(NamedTuple):
    """The names and attributes of a place; `""` for what it has none of.
    The fields `TILE_KEY` lists are named as in a search entry."""

    id: str  # of the name-list row the place is
    kind: str
    names: dict[str, str]  # dialect tag -> name
    name_de: str
    dialect: str  # of the area the place lies in
    local: str
    variety: str
    # whether `local` is OSM's `name:frr`, not the list's (the injector counts them)
    local_from_osm: bool


def resolve(
    rows: Sequence[Row], obj: LocatedObject | None, areas: AreaIndex | None, reg: Registry
) -> PlaceNames:
    """The names of the place `rows` give an object: the name-list rows that
    claim it, in file order -- the first non-empty value wins, and the first
    row is the one the place is named by.  `obj` is where the object lies and
    what OSM says of it; None for one of unknown position, which is in no
    dialect area."""
    area_tag = dialect_at(obj, areas) if obj else None
    names = {
        d["tag"]: name
        for d in reg
        if (name := _first(_dialect_name(row, d["tag"], area_tag, reg) for row in rows))
    }
    listed_local = _first(_local_name(row, area_tag, reg) for row in rows)
    osm_local = _osm_local_name(obj, area_tag)
    return PlaceNames(
        id=rows[0]["id"],
        kind=_first(row["kind"] for row in rows),
        names=names,
        name_de=_first(namecell.primary(row["de"]) for row in rows),
        dialect=area_tag or "",
        local=listed_local or osm_local,
        variety=_first(_variety(row) for row in rows),
        local_from_osm=bool(osm_local) and not listed_local,
    )


def unclaimed_local(obj: LocatedObject, areas: AreaIndex | None) -> str:
    """The local name of an object no row of the name list claims -- a Warft,
    a street, a station: OSM's own Frisian name, inside a dialect area."""
    return _osm_local_name(obj, dialect_at(obj, areas))


def _first(values: Iterable[str]) -> str:
    """The first non-empty value, or `""`."""
    return next(filter(None, values), "")


def _dialect_name(row: Row, tag: str, area_tag: str | None, reg: Registry) -> str:
    """The name of a place in one dialect, with one fallback: the dialect of
    the place's own area falls back to the `local` column -- a sub-dialect
    form such as Fahretoft's `Brouersweerw` IS the name in the area's
    dialect, it is just not the form the rest of the area uses."""
    name = namecell.primary(row.get(reg.column_of(tag)))
    if not name and area_tag == tag:
        name = namecell.primary(row.get(LOCAL_COLUMN))
    return name


def _local_name(row: Row, area_tag: str | None, reg: Registry) -> str:
    """What the people of the place themselves call it: the `local` column,
    or -- when it is empty -- the name in the dialect of the area the place
    lies in.  This is what the "local dialect" map view labels with."""
    name = namecell.primary(row.get(LOCAL_COLUMN))
    if not name and area_tag:
        name = _dialect_name(row, area_tag, area_tag, reg)
    return name


def _osm_local_name(obj: LocatedObject | None, area_tag: str | None) -> str:
    """OSM's own Frisian name (`name:frr`) as the local name of an object
    the name list gives none -- inside a dialect area only.  There it is
    almost always the form the place itself uses; outside it is a Frisian
    exonym (Pinneberg -> Pinebärj), which the local view must not show (#81)."""
    return obj.get("name_frr", "") if obj and area_tag else ""


def _variety(row: Row) -> str:
    """The remark on the primary `local` variant -- the name of the local
    variety (`Brouersweerw (Foortuftinge)` -> `Foortuftinge`), which the UI
    can show next to the name.  `""` when there is none."""
    return namecell.remark(row.get(LOCAL_COLUMN))


# ------------------------------------------------------------ as tags ----
def as_tags(names: PlaceNames) -> dict[str, str]:
    """The tags of a tile feature of the place: a `name:<tag>` per dialect
    that has a name for it, and the fields of `TILE_KEY` it has a value for
    (so `name:de` only where the list has a German name: OSM's stays where
    it has none, #61)."""
    tags = {dialect_key(tag): name for tag, name in names.names.items()}
    tags |= {key: getattr(names, field) for field, key in TILE_KEY.items()}
    return {key: value for key, value in tags.items() if value}


# ----------------------------------------------------------- as entry ----
class SearchEntry(TypedDict):
    """One place of the search index, as names/search-index.schema.json
    defines it (web/src/names.ts reads it); the optional fields are left out
    when empty."""

    id: str
    names: dict[str, str]  # dialect tag -> name
    name_de: str
    lon: float
    lat: float
    kind: str
    local: NotRequired[str]
    dialect: NotRequired[str]
    variety: NotRequired[str]
    name_nds: NotRequired[str]
    name_osm: NotRequired[str]
    name_da: NotRequired[str]
    osm: NotRequired[str]
    wikidata: NotRequired[str]


def as_entry(names: PlaceNames, obj: LocatedObject, row: Row) -> SearchEntry:
    """The search-index entry of the place of one row, whose object is `obj`:
    its names, where the object lies, OSM's names of the object the label
    chain needs (`name_nds`, `name_osm`), and the row's Danish name and
    references."""
    out: SearchEntry = {
        "id": names.id,
        "names": names.names,
        "name_de": names.name_de,
        "lon": round(float(obj["lon"]), 5),
        "lat": round(float(obj["lat"]), 5),
        "kind": names.kind,
    }
    if names.local:
        out["local"] = names.local
    if names.dialect:
        out["dialect"] = names.dialect
    if names.variety:
        out["variety"] = names.variety
    if name_nds := obj.get("name_nds"):
        out["name_nds"] = name_nds
    if name_osm := obj.get("name"):
        out["name_osm"] = name_osm
    if name_da := namecell.primary(row["da"]):
        out["name_da"] = name_da
    if row["osm"]:
        out["osm"] = row["osm"]
    if row["wikidata"]:
        out["wikidata"] = row["wikidata"]
    return out


# ---------------------------------------------------------- the command ----
@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    cli.parser("tile-keys", __doc__).parse_args(argv)
    print(",".join(attribute_keys()))
    return 0
