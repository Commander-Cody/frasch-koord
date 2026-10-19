"""The action table of the curation decisions (frasch.decisions).  What each
action makes of a row is covered through `apply`, in test_curate_apply.py."""

from __future__ import annotations

from frasch import decisions, patch
from conftest import read_schema


def test_every_action_of_the_patch_schema_is_a_decision_or_about_a_created_place() -> None:
    actions = read_schema("curate-patch")["properties"]["action"]["enum"]
    assert sorted([*decisions.ACTIONS, *patch.PLACE_ACTIONS]) == sorted(actions)
