"""`frasch curate apply` inserts the places the curation view created, keys
their decisions to the new rows, and refuses a place as a whole (#113)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from frasch import curate
from frasch.paths import Workspace
from conftest import REGISTRY, places_text, workspace

ROWS = [
    {"id": "taarep", "kind": "settlement", "mooring": "Taarep", "de": "Dorf"},  # line 2
    {"id": "hoorn", "kind": "warft", "mooring": "Hoorn", "de": "Horn"},  # line 3
    {"id": "fuar", "kind": "island", "fering": "Föör", "de": "Föhr"},  # line 4
]

KEY = "new:3f9c0a"


def create(**kw: Any) -> dict[str, Any]:
    """The `create` of the place KEY, a warft unless `kw` says otherwise."""
    return {
        "id": KEY,
        "action": "create",
        "kind": "warft",
        "names": {"mooring": "Hoorne", "de": "Horne"},
        **kw,
    }


def append(ws: Workspace, *entries: object) -> None:
    with open(ws.patch, "a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def rows(ws: Workspace) -> list[dict[str, str]]:
    with open(ws.names, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def kept(ws: Workspace) -> list[Any]:
    """The entries apply appended back to the patch."""
    with open(ws.patch, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def apply(ws: Workspace) -> curate.ApplyReport:
    return curate.apply(ws, REGISTRY)


@pytest.fixture
def ws(world: Path) -> Workspace:
    (world / "places.csv").write_text(places_text(ROWS), encoding="utf-8")
    return workspace(world)


def test_a_created_place_becomes_a_row_with_its_cells(ws: Workspace) -> None:
    append(ws, create(note="from the 1920 map"))
    apply(ws)
    (new,) = (r for r in rows(ws) if r["mooring"] == "Hoorne")
    assert {k: v for k, v in new.items() if v} == {
        "kind": "warft",
        "mooring": "Hoorne",
        "de": "Horne",
        "note": "from the 1920 map",
        "id": "hoorne",
    }


def test_a_created_place_comes_after_the_last_row_of_its_kind(ws: Workspace) -> None:
    append(ws, create(kind="settlement"))
    apply(ws)
    assert [r["id"] for r in rows(ws)] == ["taarep", "hoorne", "hoorn", "fuar"]


def test_a_created_place_of_a_kind_no_row_has_comes_last(ws: Workspace) -> None:
    append(ws, create(kind="hallig"))
    apply(ws)
    assert [r["id"] for r in rows(ws)][-1] == "hoorne"


def test_a_created_place_gets_an_id_no_row_has(ws: Workspace) -> None:
    append(ws, create(names={"mooring": "Hoorn"}))
    apply(ws)
    assert [r["id"] for r in rows(ws)] == ["taarep", "hoorn", "hoorn-2", "fuar"]


def test_the_log_names_the_line_a_created_place_is_written_at(ws: Workspace) -> None:
    append(ws, create(kind="settlement"))
    assert f"  {ws.names}:3 Hoorne (Horne): new settlement row, id = hoorne" in apply(ws).log


def test_a_row_after_a_created_place_is_logged_at_the_line_it_moves_to(ws: Workspace) -> None:
    append(ws, create(kind="settlement"), {"id": "hoorn", "line": 3, "action": "skip"})
    assert any(line.startswith(f"  {ws.names}:4 Hoorn (Horn): ") for line in apply(ws).log)


def osm(ref: str, key: str = KEY) -> dict[str, Any]:
    """An `osm` decision for the place or row `key`."""
    return {"id": key, "action": "osm", "osm": ref}


def test_the_decision_of_a_created_place_goes_into_its_row(ws: Workspace) -> None:
    append(ws, create(), osm("node/7"))
    apply(ws)
    (new,) = (r for r in rows(ws) if r["id"] == "hoorne")
    assert (new["osm"], new["status"]) == ("node/7", "ok")


def test_a_created_place_without_a_frisian_name_can_be_located(ws: Workspace) -> None:
    append(ws, create(names={"de": "Horne"}), osm("node/7"))
    apply(ws)
    (new,) = (r for r in rows(ws) if r["id"] == "horne")
    assert new["osm"] == "node/7"


def test_a_row_of_the_list_without_a_frisian_name_still_cannot_be(ws: Workspace) -> None:
    Path(ws.names).write_text(
        places_text([{"id": "horne", "kind": "warft", "de": "Horne"}]), encoding="utf-8"
    )
    append(ws, osm("node/7", key="horne"))
    assert len(apply(ws).refused) == 1


def refusals(report: curate.ApplyReport) -> list[str]:
    return [refusal.why for refusal in report.refused]


def test_a_created_place_of_an_unknown_kind_is_refused(ws: Workspace) -> None:
    append(ws, create(kind="castle"))
    assert refusals(apply(ws)) == ["unknown kind 'castle'"]


def test_a_created_place_breaking_the_name_cell_rules_is_refused(ws: Workspace) -> None:
    append(ws, create(names={"mooring": "Hoorne?"}))
    assert refusals(apply(ws)) == [
        "mooring: `?` in 'Hoorne?' -- say `uncertain` in `note` instead: 'Hoorne?'"
    ]


def test_a_created_place_with_a_column_the_list_has_not_is_refused(ws: Workspace) -> None:
    append(ws, create(names={"halunder": "Hörn"}))
    assert refusals(apply(ws)) == [f"no name column halunder in {ws.names}"]


def test_the_decision_of_a_refused_place_is_refused_with_it(ws: Workspace) -> None:
    append(ws, create(kind="castle"), osm("node/7"))
    assert refusals(apply(ws))[1] == f"its place {KEY} is refused"


def test_a_place_whose_decision_is_refused_is_not_created(ws: Workspace) -> None:
    Path(ws.names).write_text(places_text([*ROWS[:2], {**ROWS[2], "osm": "node/7"}]), "utf-8")
    append(ws, create(), osm("node/7"))
    apply(ws)
    assert [r["id"] for r in rows(ws)] == ["taarep", "hoorn", "fuar"]


def test_a_refused_place_is_kept_in_the_patch_with_its_decision(ws: Workspace) -> None:
    append(ws, create(kind="castle"), osm("node/7"))
    apply(ws)
    assert [e["action"] for e in kept(ws)] == ["create", "osm"]


def test_a_decision_for_a_place_the_patch_does_not_create_is_refused(ws: Workspace) -> None:
    append(ws, osm("node/7"))
    assert refusals(apply(ws)) == [
        f"no place {KEY} is created in the patch (applied or discarded already?)"
    ]


def test_a_discarded_place_is_not_created(ws: Workspace) -> None:
    append(ws, create(), osm("node/7"), {"id": KEY, "action": "discard"})
    apply(ws)
    assert len(rows(ws)) == len(ROWS)


def test_a_create_under_a_row_id_is_refused_without_the_rows_decision(ws: Workspace) -> None:
    append(ws, create(id="hoorn"), osm("node/7", key="hoorn"))
    apply(ws)
    assert [r["osm"] for r in rows(ws) if r["id"] == "hoorn"] == ["node/7"]
