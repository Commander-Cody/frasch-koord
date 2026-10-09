"""refs.py: the references of an `osm` cell -- `node/1; way/2`, or one
`local/<slug>` for a place OSM does not have (README, the `osm` column)."""

from __future__ import annotations

import pytest

from frasch import refs
from frasch.errors import Invalid


def test_parse_reads_several_references_in_order() -> None:
    assert refs.parse("way/1347936331; node/1332249790") == [
        ("w", 1347936331),
        ("n", 1332249790),
    ]


def test_parse_does_not_need_a_space_after_the_semicolon() -> None:
    # places.csv has cells written that way (the Nordwarft on Ockholm)
    assert refs.parse("way/1347936331;node/1332249790") == [
        ("w", 1347936331),
        ("n", 1332249790),
    ]


def test_parse_of_an_empty_cell_is_no_reference() -> None:
    assert refs.parse("") == []
    assert refs.parse(None) == []


def test_parse_reads_a_local_reference() -> None:
    assert refs.parse("local/westerheide-amrum") == [("l", "westerheide-amrum")]


@pytest.mark.parametrize(
    "ref, osm, slug",
    [
        (("w", 12), ("w", 12), None),
        (("l", "westerheide-amrum"), None, "westerheide-amrum"),
    ],
)
def test_a_reference_is_either_an_osm_object_or_a_local_slug(
    ref: refs.Ref, osm: refs.OsmRef | None, slug: str | None
) -> None:
    assert refs.as_osm_ref(ref) == osm
    assert refs.local_slug(ref) == slug


@pytest.mark.parametrize(
    "cell",
    [
        "way/abc",  # not an id
        "Way/12",  # types are lowercase
        "w/12",  # the short type letter is internal only
        "https://www.openstreetmap.org/way/177387348",
        "local/Westerheide",  # slugs are lowercase
        "local/wester_heide",  # ... letters, digits and hyphens only
        "local/-westerheide",
    ],
)
def test_parse_refuses_a_bad_reference(cell: str) -> None:
    with pytest.raises(Invalid, match="bad reference"):
        refs.parse(cell, "places.csv:7")


def test_parse_error_says_where() -> None:
    with pytest.raises(Invalid, match="places.csv:7"):
        refs.parse("way/abc", "places.csv:7")


def test_a_local_reference_cannot_be_combined_with_others() -> None:
    with pytest.raises(Invalid, match="stands alone"):
        refs.parse("local/westerheide-amrum; node/6928685546")


def test_two_local_references_cannot_be_combined_either() -> None:
    with pytest.raises(Invalid, match="stands alone"):
        refs.parse("local/merlingmark; local/dreihardereck")


def test_format_writes_the_cell_spelling() -> None:
    assert refs.format([("w", 1347936331), ("n", 1332249790)]) == "way/1347936331; node/1332249790"
    assert refs.format([("r", 1420555)]) == "relation/1420555"
    assert refs.format([("l", "huelltoft")]) == "local/huelltoft"


@pytest.mark.parametrize(
    "cell",
    [
        "node/240102263",
        "way/44051131; way/44051132; way/628205597",
        "relation/5615880",
        "local/westerheide-amrum",
    ],
)
def test_format_round_trips_parse(cell: str) -> None:
    assert refs.format(refs.parse(cell)) == cell


def test_format_normalises_the_separator() -> None:
    assert (
        refs.format(refs.parse("way/1347936331;node/1332249790"))
        == "way/1347936331; node/1332249790"
    )
