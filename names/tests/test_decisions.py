"""The action table of the curation decisions (frasch.decisions).  What each
action makes of a row is covered through `apply`, in test_curate_apply.py."""

from __future__ import annotations

from frasch import decisions
from conftest import read_schema


def test_every_action_of_the_patch_schema_has_its_entry_in_the_table() -> None:
    actions = read_schema("curate-patch")["properties"]["action"]["enum"]
    assert sorted(decisions.ACTIONS) == sorted(actions)
