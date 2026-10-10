"""placeobjects.py: the object a row of the name list stands for -- the one
of its first reference, or the point the injector adds for a place OSM does
not have."""

from __future__ import annotations

import pytest

from frasch import placelist, placeobjects
from frasch.errors import PipelineError
from frasch.objects import LocatedObject, Objects
from frasch.provenance import Stamp
from conftest import REGISTRY

NAIBEL: LocatedObject = {"lon": 8.83, "lat": 54.79}
NO_EXTRACTS = Stamp({}, [])


def place(**cells: str) -> placelist.PlaceRow:
    return placelist.PlaceRow({c: "" for c in placelist.columns(REGISTRY)} | cells, 2)


NORDWARW = place(id="nordwarw", kind="warft", mooring="Nordwärw", osm="way/7; node/1")
OCKHOLM: LocatedObject = {"lon": 8.84, "lat": 54.67}
LOCATED = Objects({("n", 1): NAIBEL, ("w", 7): OCKHOLM}, NO_EXTRACTS)


def test_the_object_of_a_row_is_that_of_its_first_reference() -> None:
    assert placeobjects.for_row(LOCATED, NORDWARW, {}, REGISTRY) == OCKHOLM


WAASTERHIAS = place(
    id="waasterhias",
    kind="settlement",
    oomrang="Waasterhias",
    de="Westerheide",
    osm="local/westerheide-amrum",
)


def test_the_object_of_a_place_osm_does_not_have_is_the_point_the_injector_adds() -> None:
    # at its curation position, with the generic name the point gets: the German one
    positions = {"westerheide-amrum": (8.34019, 54.65097)}
    assert placeobjects.for_row(LOCATED, WAASTERHIAS, positions, REGISTRY) == {
        "lon": 8.34019,
        "lat": 54.65097,
        "name": "Westerheide",
    }


def test_a_place_osm_does_not_have_needs_a_position_in_the_curation() -> None:
    with pytest.raises(PipelineError, match=r"waasterhias \(line 2\): local/westerheide-amrum"):
        placeobjects.for_row(LOCATED, WAASTERHIAS, {}, REGISTRY)


def test_a_row_keyed_by_its_wikidata_id_alone_has_no_object() -> None:
    denmark = place(id="daanemark", kind="country", mooring="Däänemark", wikidata="Q35")
    assert placeobjects.for_row(LOCATED, denmark, {}, REGISTRY) is None
