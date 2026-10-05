"""placelist.py: the cell conventions of places.csv (README "Conventions that
apply to every name cell", the `osm` column, curation positions) and a
read/write round trip of the real name list.

Malformed name cells (unbalanced brackets, `?`, `;` without a space) are
deliberately not pinned down here: `frasch check-inputs` owns them."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from frasch import paths, placelist, registry
from frasch.paths import Workspace
from frasch.errors import ValidationError


# ------------------------------------------------------------- name cells ---
def test_parts_splits_variants_and_keeps_each_remark() -> None:
    assert placelist.parts("Rübel; Rübbel (wisinge)") == [("Rübel", ""), ("Rübbel", "wisinge")]


def test_semicolon_inside_a_remark_does_not_split() -> None:
    # the README's own example: two names, the remark lists two varieties
    assert placelist.parts("Huađer; Huuger (Sölring; Wisinge)") == [
        ("Huađer", ""),
        ("Huuger", "Sölring; Wisinge"),
    ]


def test_several_remarks_on_one_variant_are_joined() -> None:
    assert placelist.parts("Brouersweerw (Foortuftinge) (Nickelsen 1982)") == [
        ("Brouersweerw", "Foortuftinge; Nickelsen 1982")
    ]


def test_empty_and_missing_cells_have_no_parts() -> None:
    assert placelist.parts("") == []
    assert placelist.parts(None) == []


def test_variants_strip_the_remarks() -> None:
    assert placelist.variants("Huađer; Huuger (Sölring; Wisinge)") == ["Huađer", "Huuger"]


def test_variants_list_a_name_once() -> None:
    # the same spelling with and without a source remark is one name
    assert placelist.variants("Hulm; Hulm (Wisinge)") == ["Hulm"]


def test_primary_is_the_first_variant_without_its_remark() -> None:
    assert placelist.primary("Lätj-Jäns-Weerw (Foortuftinge); Latj-Jäns-Wärw") == "Lätj-Jäns-Weerw"


def test_primary_of_an_empty_cell_is_empty() -> None:
    assert placelist.primary("") == ""
    assert placelist.primary(None) == ""


def test_remark_is_that_of_the_primary_variant() -> None:
    assert placelist.remark("Brouersweerw (Foortuftinge)") == "Foortuftinge"


def test_remark_of_a_later_variant_is_not_the_cells_remark() -> None:
    assert placelist.remark("Huađer; Huuger (Sölring; Wisinge)") == ""


# ------------------------------------------------------------- osm column ---
def test_parse_osm_reads_several_references_in_order() -> None:
    assert placelist.parse_osm("way/1347936331; node/1332249790") == [
        ("w", 1347936331),
        ("n", 1332249790),
    ]


def test_parse_osm_does_not_need_a_space_after_the_semicolon() -> None:
    # places.csv has cells written that way (the Nordwarft on Ockholm)
    assert placelist.parse_osm("way/1347936331;node/1332249790") == [
        ("w", 1347936331),
        ("n", 1332249790),
    ]


def test_parse_osm_of_an_empty_cell_is_no_reference() -> None:
    assert placelist.parse_osm("") == []
    assert placelist.parse_osm(None) == []


def test_parse_osm_reads_a_local_reference() -> None:
    assert placelist.parse_osm("local/westerheide-amrum") == [("l", "westerheide-amrum")]


@pytest.mark.parametrize(
    "ref, osm, slug",
    [
        (("w", 12), ("w", 12), None),
        (("l", "westerheide-amrum"), None, "westerheide-amrum"),
    ],
)
def test_a_reference_is_either_an_osm_object_or_a_local_slug(
    ref: placelist.Ref, osm: placelist.OsmRef | None, slug: str | None
) -> None:
    assert placelist.as_osm_ref(ref) == osm
    assert placelist.local_slug(ref) == slug


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
def test_parse_osm_refuses_a_bad_reference(cell: str) -> None:
    with pytest.raises(ValidationError, match="bad reference"):
        placelist.parse_osm(cell, "places.csv:7")


def test_parse_osm_error_says_where() -> None:
    with pytest.raises(ValidationError, match="places.csv:7"):
        placelist.parse_osm("way/abc", "places.csv:7")


def test_a_local_reference_cannot_be_combined_with_others() -> None:
    with pytest.raises(ValidationError, match="stands alone"):
        placelist.parse_osm("local/westerheide-amrum; node/6928685546")


def test_two_local_references_cannot_be_combined_either() -> None:
    with pytest.raises(ValidationError, match="stands alone"):
        placelist.parse_osm("local/merlingmark; local/dreihardereck")


def test_format_osm_writes_the_cell_spelling() -> None:
    assert (
        placelist.format_osm([("w", 1347936331), ("n", 1332249790)])
        == "way/1347936331; node/1332249790"
    )
    assert placelist.format_osm([("r", 1420555)]) == "relation/1420555"
    assert placelist.format_osm([("l", "huelltoft")]) == "local/huelltoft"


@pytest.mark.parametrize(
    "cell",
    [
        "node/240102263",
        "way/44051131; way/44051132; way/628205597",
        "relation/5615880",
        "local/westerheide-amrum",
    ],
)
def test_format_osm_round_trips_parse_osm(cell: str) -> None:
    assert placelist.format_osm(placelist.parse_osm(cell)) == cell


def test_format_osm_normalises_the_separator() -> None:
    assert (
        placelist.format_osm(placelist.parse_osm("way/1347936331;node/1332249790"))
        == "way/1347936331; node/1332249790"
    )


# --------------------------------------------------- the real name list ---
def test_real_name_list_round_trips_byte_identical(tmp_path: Path) -> None:
    """Reading and writing back the real places.csv changes nothing -- the
    guarantee that the matcher and the curation only ever touch the cells
    they mean to (a copy: the real file is never written).  The one test of
    the real files: it reads the list by the real dialect registry."""
    real = Workspace.default()
    copy = tmp_path / "places.csv"
    shutil.copyfile(real.names, copy)
    before = copy.read_bytes()
    rows, fields = placelist.read(str(copy), registry.read(real.dialects))
    placelist.write(rows, str(copy), fields)
    assert copy.read_bytes() == before


# ------------------------------------------------------------------- slug ---
@pytest.mark.parametrize(
    "name, slug",
    [
        ("Schörkewärw", "schorkewarw"),
        ("Hamborjer Håli", "hamborjer-hali"),
        ("Straße", "strasse"),
        ("Æ Løkke", "ae-lokke"),
        ("Rudbøl", "rudbol"),
        ("Huađer", "huader"),
        ("Friedrich-Wilhelm-Lübke-Kuuch", "friedrich-wilhelm-lubke-kuuch"),
    ],
)
def test_slug_folds_a_name_to_lowercase_ascii(name: str, slug: str) -> None:
    assert placelist.slug(name) == slug


# ------------------------------------------------ the patch schema agrees ---
def _schema() -> Any:
    with open(paths.PATCH_SCHEMA, encoding="utf-8") as fh:
        return json.load(fh)


SLUGS = [
    "taarep",
    "westerheide-amrum",
    "a1",
    "hus-2",
    "",
    "Taarep",
    "wester_heide",
    "-westerheide",
    "westerheide-",
    "wester--heide",
    "wester heide",
    "hüs",
]
QIDS = ["Q35", "Q21003", "Q1", "q35", "Q", "35", "Q35;Q36", "Q3 5", "QQ35"]


@pytest.mark.parametrize("text", SLUGS)
def test_the_patch_schema_takes_the_slugs_the_name_list_takes(text: str) -> None:
    # curate.py apply checks a slug by the schema and writes `local/<slug>`,
    # which placelist.read checks by SLUG: the two must never disagree
    schema = _schema()["$defs"]["slug"]["pattern"]
    assert bool(re.search(schema, text)) == bool(placelist.SLUG.fullmatch(text))


@pytest.mark.parametrize("text", QIDS)
def test_the_patch_schema_takes_the_wikidata_ids_the_name_list_takes(text: str) -> None:
    # the schema allows an empty cell, the name list leaves an empty one alone
    schema = _schema()["properties"]["wikidata"]["pattern"]
    assert bool(re.search(schema, text)) == bool(placelist.WIKIDATA_ID.fullmatch(text))
