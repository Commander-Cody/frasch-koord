"""The kinds of the name list (`kind` in names/places.csv), and what each
means to the pipeline: one `KindRule` per kind, in RULES.

Whatever depends on a row's kind reads its rule (`rule`): the name list
which kinds there are, the matcher which OSM objects can be the feature and
which of them carries the name, the injector what a place OSM does not have
is added as, and the curation view the order to walk the kinds in.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import NamedTuple, TypeVar

from frasch.candidates import Candidate
from frasch.osmtags import ISLAND_PLACES, SETTLEMENT_PLACES, WARFT_PLACES, Tags, is_island

TagTest = Callable[[Tags], bool]
RecTest = Callable[[Candidate], bool]
C = TypeVar("C", bound=Candidate)

NOT_A_PLACE = "not_a_place"  # a dictionary-only row: never put on the map


def tag(key: str, *values: str) -> TagTest:
    """The tag `key` -- with one of `values`, where any are given."""
    if values:
        return lambda tags: tags.get(key) in values
    return lambda tags: bool(tags.get(key))


def admin_boundary(levels: Iterable[int]) -> TagTest:
    """An administrative boundary of one of the `admin_level`s."""
    allowed = {str(level) for level in levels}
    return lambda tags: (
        tags.get("boundary") == "administrative" and tags.get("admin_level") in allowed
    )


def anything(tags: Tags) -> bool:
    return True


def on(types: str, *tests: TagTest) -> RecTest:
    """An object of one of `types` (of the letters n, w, r) whose tags pass
    one of `tests` -- any object of such a type, where none is given."""
    return lambda rec: rec["t"] in types and (not tests or any(test(rec["tags"]) for test in tests))


def is_waterway_relation(rec: Candidate) -> bool:
    """A `type=waterway` relation: the whole river, grouping its ways."""
    return rec["t"] == "r" and rec["tags"].get("type") == "waterway"


# A feature is split over several objects, or mapped more than once: rivers
# into dozens of `waterway=river` ways, and an island has a coastline way and
# several place nodes.  Where OSM has the object that *is* the feature, only
# that is considered (`KindRule.canonical`).
PLACE = (on("nwr", tag("place")),)  # whatever is mapped as a place
OUTLINE = (on("wr", is_island),)  # the area of an island
WATER_BODY = (
    lambda rec: is_waterway_relation(rec) or rec["tags"].get("place") == "sea",
    on("wr", tag("natural", "water"), tag("water")),
)


class Fit(NamedTuple):
    """How well an object suits to carry a kind's name, in points: those of
    the first of `tests` it passes, `otherwise` when it passes none."""

    tests: tuple[tuple[RecTest, int], ...]
    otherwise: int


PLACE_FIT = Fit(
    (
        (on("n", tag("place")), 30),  # OpenMapTiles labels settlements from the place node
        (on("r", tag("boundary", "administrative")), 12),
        (on("w", tag("place")), 8),
    ),
    otherwise=2,
)
OUTLINE_FIT = Fit(
    (
        (on("wr", is_island), 30),
        (on("n", tag("place")), 18),
    ),
    otherwise=4,
)
WATER_FIT = Fit(
    (
        (on("wr", tag("natural"), tag("water"), tag("place", "sea")), 25),
        (on("nwr", tag("waterway")), 20),
    ),
    otherwise=6,
)
LANDSCAPE_FIT = Fit(
    (
        (on("r", tag("boundary"), tag("place")), 25),
        (on("n", tag("place"), tag("natural")), 22),
    ),
    otherwise=6,
)
ROAD_FIT = Fit(((on("w"), 20),), otherwise=4)
NODE_FIT = Fit(((on("n"), 10),), otherwise=6)  # a kind without a rule of its own

# What else makes an object the one to carry the name (frasch.match): its own
# Wikidata item, a German name of its own, and being nearer to North Frisia
# -- a point per KM_PER_POINT, an object without a position counting as
# UNPLACED_KM away.
WIKIDATA_BONUS = 8
GERMAN_NAME_BONUS = 4
KM_PER_POINT = 200
UNPLACED_KM = 500


class Boundary(enum.Enum):
    """What an administrative boundary without a `place` is among the
    candidates of a kind."""

    FEATURE = enum.auto()  # it can be the feature itself: a Harde, a country
    YIELDS = enum.auto()  # never the feature beside another: the place node is labelled
    YIELDS_TO_NODE = enum.auto()  # the feature (a Kreis), unless a place node is there


def nothing(rec: Candidate) -> bool:
    return False


@dataclass(frozen=True)
class KindRule:
    """What a kind means to the pipeline.

    name      the kind, as the `kind` column spells it
    accepted  what an OSM object can be tagged to be a feature of the kind:
              any one of these (`accepts`)
    canonic   what the object that is the feature itself looks like, the
              likeliest first (`canonical`)
    fit       which object of a feature suits best to carry the name
              (`bonus`)
    whole     an object that is one whole feature of the kind though its
              tags do not show it (`covers`)
    boundary  what a bare administrative boundary is among its candidates
    nf_only   the kind exists only in North Frisia: a match elsewhere is
              wrong
    by_item   a feature of the kind is found by its Wikidata item, not as
              an OSM object (a country: the matcher asks Wikidata)
    point_place
              the `place=` of the node the injector adds for a local
              reference -- only where the OSM equivalent is unambiguous; any
              other kind needs `place=...` in the curation row's `set_tags`.
              OpenMapTiles has no `place=locality` at all, and
              `isolated_dwelling` nodes only from z14 while `hamlet` nodes
              come at z11: so a Warft is a hamlet, as OSM's own Hallig
              Warften are
    polygon_capable
              the kind is an area: its local reference can be a square of
              one (`polygon_km2`) instead of a node
    """

    name: str
    accepted: tuple[TagTest, ...]
    canonic: tuple[RecTest, ...] = ()
    fit: Fit = NODE_FIT
    whole: RecTest = nothing
    boundary: Boundary = Boundary.FEATURE
    nf_only: bool = False
    by_item: bool = False
    point_place: str | None = None
    polygon_capable: bool = False

    def accepts(self, tags: Tags) -> bool:
        """Whether an object with `tags` can be a feature of the kind."""
        return any(test(tags) for test in self.accepted)

    def canonical(self, cands: list[C]) -> list[C]:
        """`cands` narrowed to the object(s) that really are the feature,
        all of them where none is."""
        for test in self.canonic:
            if found := [c for c in cands if test(c)]:
                return found
        return cands

    def bonus(self, rec: Candidate) -> int:
        """How well `rec` suits to carry the name of a feature of the kind."""
        return next((points for test, points in self.fit.tests if test(rec)), self.fit.otherwise)

    def covers(self, rec: Candidate) -> bool:
        """Whether `rec` can be a feature of the kind, or a part of one."""
        return self.accepts(rec["tags"]) or self.whole(rec)


# In the order the curation view walks the kinds in: those a human decides
# quickly first (a village is either there or it is not), the vague ones last.
RULES = (
    KindRule(
        "settlement",
        accepted=(tag("place", *SETTLEMENT_PLACES), admin_boundary(range(6, 12))),
        canonic=PLACE,
        fit=PLACE_FIT,
        boundary=Boundary.YIELDS,
        point_place="hamlet",
    ),
    KindRule(
        "island",
        accepted=(is_island, admin_boundary(range(8, 12))),
        canonic=OUTLINE,
        fit=OUTLINE_FIT,
        boundary=Boundary.YIELDS,
        point_place="island",
        polygon_capable=True,
    ),
    KindRule(
        "hallig",
        # some Halligen are mapped as the one dwelling on them
        accepted=(is_island, tag("place", *SETTLEMENT_PLACES), admin_boundary(range(8, 12))),
        canonic=OUTLINE,
        fit=OUTLINE_FIT,
        boundary=Boundary.YIELDS,
        nf_only=True,
        point_place="island",
        polygon_capable=True,
    ),
    KindRule(
        "helgoland",
        accepted=(
            tag("place"),
            tag("natural"),
            tag("man_made"),
            tag("historic"),
            tag("water"),
            tag("waterway"),
        ),
        boundary=Boundary.YIELDS,
    ),
    KindRule(
        "sand",
        accepted=(
            tag("natural", "sand", "shoal", "beach", "mud", "reef", "wetland"),
            tag("place", *ISLAND_PLACES, "locality"),
        ),
        canonic=OUTLINE,
        fit=OUTLINE_FIT,
        boundary=Boundary.YIELDS,
        nf_only=True,
        polygon_capable=True,
    ),
    KindRule(
        "landscape",
        accepted=(
            tag(
                "place",
                "region",
                "county",
                "state",
                "district",
                "province",
                "island",
                "archipelago",
            ),
            tag("natural", "peninsula", "ridge", "hill", "archipelago"),
            tag("boundary", "administrative", "historic", "political"),
        ),
        fit=LANDSCAPE_FIT,
        boundary=Boundary.YIELDS_TO_NODE,
        polygon_capable=True,
    ),
    KindRule(
        "water",
        accepted=(
            tag("natural", "water", "bay", "strait", "wetland", "spring", "sand"),
            tag("water"),
            tag("waterway"),
            tag("place", "sea"),
            tag("boundary", "maritime", "place"),
        ),
        canonic=WATER_BODY,
        fit=WATER_FIT,
        # the relation carries no `waterway` tag of its own
        whole=is_waterway_relation,
    ),
    KindRule(
        "harde",
        accepted=(
            tag("boundary", "historic", "political", "administrative"),
            tag("place", "region"),
        ),
        nf_only=True,
        polygon_capable=True,
    ),
    KindRule("road", accepted=(tag("highway"),), fit=ROAD_FIT),
    KindRule("country", accepted=(admin_boundary([2]),), by_item=True),
    KindRule(
        "koog",
        accepted=(
            tag("place", *SETTLEMENT_PLACES, "polder"),
            tag("boundary", "administrative", "protected_area"),
            tag("landuse"),
            tag("natural", "water", "wetland"),
        ),
        canonic=PLACE,
        fit=PLACE_FIT,
        boundary=Boundary.YIELDS,
        nf_only=True,
        polygon_capable=True,
    ),
    KindRule(
        "warft",
        accepted=(
            tag("place", *WARFT_PLACES),
            tag("landuse", "residential", "farmyard", "meadow"),
            tag("man_made"),
            tag("historic"),
        ),
        canonic=PLACE,
        fit=PLACE_FIT,
        boundary=Boundary.YIELDS,
        nf_only=True,
        point_place="hamlet",
    ),
    KindRule(NOT_A_PLACE, accepted=(anything,)),
)
_BY_NAME = {rule.name: rule for rule in RULES}

KIND_ORDER = [rule.name for rule in RULES]
KINDS = frozenset(KIND_ORDER)
POLYGON_KINDS = [rule.name for rule in RULES if rule.polygon_capable]


def rule(kind: str) -> KindRule:
    """The rule of a kind of the name list."""
    return _BY_NAME[kind]
