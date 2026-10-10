"""The OSM tags the name pipeline reads, each list of them written once:
the name tags an object is found by, the tags that say what kind of thing
it is, and the `place` values of a settlement and of an island.

The candidate scan (frasch.build_candidates) keeps exactly these tags of an
object, the name index (frasch.nameindex) and the kind rules (frasch.kinds)
read them, and the curation view gets the lists with its worklist
(frasch.curate).
"""

from __future__ import annotations

from collections.abc import Mapping

Tags = Mapping[str, str]

# name tag -> how trustworthy an exact hit on it is (lower = better).  A hit on
# the OSM `name` itself beats a hit on `name:de`, which beats alt/old names:
# otherwise the Danish village Holme (name:de=Holm) outranks the North Frisian
# village Holm (name=Holm).
NAME_FIELD_RANK = {
    "name": 0,
    "name:de": 1,
    "official_name": 2,
    "name:da": 2,
    "short_name": 2,  # Stadt Wyk auf Föhr: short_name=Wyk
    "alt_name": 4,
    "old_name": 4,
}
NAME_FIELDS = tuple(NAME_FIELD_RANK)
UNRANKED = 99  # worse than any rank a name hit can have: not found yet

# The tags that say what kind of thing an object is, the most telling first:
# an island's coastline way (`place=island`, `natural=coastline`) is an island.
CLASS_KEYS = (
    "place",
    "natural",
    "boundary",
    "waterway",
    "landuse",
    "man_made",
    "highway",
    "water",
    "historic",
)


def class_of(tags: Tags) -> str:
    """What kind of thing an object is, in one word: the value of the first
    of its CLASS_KEYS (`village`, `river`), `""` when it has none."""
    return next((tags[key] for key in CLASS_KEYS if tags.get(key)), "")


# What narrows a class down: the level of a boundary, the type of a relation.
DETAIL_KEYS = ("admin_level", "type")
ITEM_KEY = "wikidata"  # the object's Wikidata item
# Every tag of an object the pipeline reads -- what a candidate record keeps.
KEPT_KEYS = CLASS_KEYS + DETAIL_KEYS + (ITEM_KEY,) + NAME_FIELDS


def decisive(tags: Tags) -> str:
    """The tags that say what kind of thing an object is, `place=village;...`
    -- for the matcher's output and the curation view."""
    return ";".join(f"{key}={tags[key]}" for key in CLASS_KEYS + DETAIL_KEYS if key in tags)


# ----------------------------------------------------------- place values ---
# The `place` values of a settlement.
SETTLEMENT_PLACES = frozenset(
    {
        "city",
        "town",
        "village",
        "hamlet",
        "isolated_dwelling",
        "locality",
        "suburb",
        "neighbourhood",
        "borough",
        "quarter",
        "farm",
        "municipality",
    }
)
# Those of them a location hint most plausibly names.
VILLAGE_PLACES = frozenset({"city", "town", "village", "hamlet"})
# The small ones: far from North Frisia, such a place is no plausible match.
MINOR_PLACES = SETTLEMENT_PLACES - {"city", "town", "village", "borough", "municipality"}
# What a Warft is mapped as, when it is mapped as a place.
WARFT_PLACES = frozenset(
    {"isolated_dwelling", "farm", "locality", "hamlet", "village", "neighbourhood"}
)
# What a settlement's own node is tagged: two such nodes apart are two places.
CORE_PLACES = (SETTLEMENT_PLACES - {"borough", "quarter", "municipality"}) | {"polder"}

# The `place` / `natural` values of an island.
ISLAND_PLACES = frozenset({"island", "islet", "archipelago"})


def is_island(tags: Tags) -> bool:
    """An island, or the peninsula one has become (Nordstrand)."""
    return tags.get("place") in ISLAND_PLACES or tags.get("natural") in ISLAND_PLACES | {
        "peninsula"
    }
