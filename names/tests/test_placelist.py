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

from frasch import paths, placelist, refs
from frasch.paths import Workspace
from conftest import REGISTRY
from frasch.dialects import LOCAL_COLUMN, Dialect, Registry


# ------------------------------------------------------------------- rows ---
def place(**cells: str) -> placelist.PlaceRow:
    return placelist.PlaceRow({c: "" for c in placelist.columns(REGISTRY)} | cells, 2)


def test_a_row_knows_the_references_of_its_osm_cell() -> None:
    assert place(osm="way/7; node/1").refs == [("w", 7), ("n", 1)]


def test_a_rows_references_follow_its_osm_cell_when_it_is_rewritten() -> None:
    # the matcher and `curate apply` write the cell of a row they have read
    row = place(osm="way/7")
    _ = row.refs  # read once already
    row["osm"] = "node/5"
    assert row.refs == [("n", 5)]


def test_a_local_reference_is_none_of_a_rows_osm_objects() -> None:
    assert place(osm="local/westerheide-amrum").osm_refs == []


def test_a_row_for_a_place_osm_does_not_have_knows_its_slug() -> None:
    assert place(osm="local/westerheide-amrum").local == "westerheide-amrum"


# ----------------------------------------------------------------- claims ---
def test_a_row_claims_the_objects_of_its_osm_cell_and_its_wikidata_item() -> None:
    row = place(kind="island", mooring="Oomram", osm="relation/1; way/2", wikidata="Q24880")
    assert placelist.claims(row) == ([("r", 1), ("w", 2)], "Q24880")


def test_a_skipped_row_claims_nothing() -> None:
    row = place(kind="island", mooring="Oomram", osm="relation/1", wikidata="Q24880", status="skip")
    assert placelist.claims(row) == ([], "")


def test_a_row_that_is_not_a_place_still_claims_its_object() -> None:
    assert placelist.claims(place(kind="not_a_place", osm="way/2")).refs == [("w", 2)]


def test_a_row_without_a_frisian_name_still_claims_its_object() -> None:
    assert placelist.claims(place(kind="island", de="Amrum", osm="way/2")).refs == [("w", 2)]


def test_claims_are_spelled_as_the_list_spells_them() -> None:
    row = place(osm="relation/1; way/2", wikidata="Q24880")
    assert placelist.claims(row).keys == ["relation/1", "way/2", "Q24880"]


# ----------------------------------------------------------------- on_map ---
def test_a_place_with_a_frisian_name_that_claims_an_object_is_on_the_map() -> None:
    assert placelist.on_map(place(kind="island", mooring="Oomram", osm="relation/1"), REGISTRY)


def test_a_place_keyed_by_its_wikidata_item_alone_is_on_the_map() -> None:
    assert placelist.on_map(place(kind="country", mooring="Däänemark", wikidata="Q35"), REGISTRY)


@pytest.mark.parametrize(
    "cells",
    [
        {"kind": "island", "mooring": "Oomram", "osm": "relation/1", "status": "skip"},
        {"kind": "not_a_place", "mooring": "Oomram", "osm": "relation/1"},
        {"kind": "island", "de": "Amrum", "osm": "relation/1"},
        {"kind": "island", "mooring": "Oomram"},
    ],
    ids=["skipped", "not a place", "no Frisian name", "claims nothing"],
)
def test_a_row_that_puts_no_name_on_the_map_is_not_on_it(cells: dict[str, str]) -> None:
    assert not placelist.on_map(place(**cells), REGISTRY)


# --------------------------------------------------- the real name list ---
def registry_of(header: str) -> Registry:
    """A registry of the dialect columns a places.csv header has: those
    between `kind` and `de`, but for `local`."""
    columns = header.split(",")
    names = columns[columns.index("kind") + 1 : columns.index("de")]
    return Registry(
        [
            Dialect(tag=f"frr-x-{c}", column=c, label=c, status="living", view="no", note="")
            for c in names
            if c != LOCAL_COLUMN
        ]
    )


def test_real_name_list_round_trips_byte_identical(tmp_path: Path) -> None:
    """Reading and writing back the real places.csv changes nothing -- the
    guarantee that the matcher and the curation only ever touch the cells
    they mean to (a copy: the real file is never written).  It is read by
    the dialect columns of its own header."""
    copy = tmp_path / "places.csv"
    shutil.copyfile(Workspace.default().names, copy)
    before = copy.read_bytes()
    header = before.decode("utf-8").splitlines()[0]
    placelist.read(str(copy), registry_of(header)).write()
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
    assert bool(re.search(schema, text)) == bool(refs.SLUG.fullmatch(text))


@pytest.mark.parametrize("text", QIDS)
def test_the_patch_schema_takes_the_wikidata_ids_the_name_list_takes(text: str) -> None:
    # the schema allows an empty cell, the name list leaves an empty one alone
    schema = _schema()["properties"]["wikidata"]["pattern"]
    assert bool(re.search(schema, text)) == bool(placelist.WIKIDATA_ID.fullmatch(text))
