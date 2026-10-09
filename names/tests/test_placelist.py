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
from frasch.dialects import LOCAL_COLUMN, Dialect, Registry


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
    rows, fields = placelist.read(str(copy), registry_of(header))
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
    assert bool(re.search(schema, text)) == bool(refs.SLUG.fullmatch(text))


@pytest.mark.parametrize("text", QIDS)
def test_the_patch_schema_takes_the_wikidata_ids_the_name_list_takes(text: str) -> None:
    # the schema allows an empty cell, the name list leaves an empty one alone
    schema = _schema()["properties"]["wikidata"]["pattern"]
    assert bool(re.search(schema, text)) == bool(placelist.WIKIDATA_ID.fullmatch(text))
