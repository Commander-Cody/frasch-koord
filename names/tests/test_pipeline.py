"""frasch.pipeline: the table of the generated files -- when each of them is
stale, and `frasch build <name>`, which builds one."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import NoReturn

import pytest
import requests

from frasch import pipeline
from frasch.__main__ import main
from frasch.errors import PipelineError
from frasch.objects import read_objects
from frasch.pipeline import Extracts, Run
from frasch.provenance import Stamp, blob_hash
from conftest import (
    AREA_LIST,
    REGISTRY,
    cand,
    path_options,
    places_text,
    write_candidates,
    write_sh_extract,
)
from conftest import workspace as workspace_of
from osm_fixture import write_extract

# a row on the map whose object the extract of `pipeline_world` holds
TOFTEM = {"id": "toftem", "kind": "settlement", "mooring": "Toftem", "de": "Toftum"} | {
    "osm": "node/240044107",
    "status": "ok",
}


@pytest.fixture
def world(pipeline_world: Path) -> Path:
    (pipeline_world / "places.csv").write_text(places_text([TOFTEM]), encoding="utf-8")
    return pipeline_world


def with_extracts(world: Path, *more: Path) -> Run:
    """A run on the workspace of `world` with its extract at hand, and `more`."""
    extract = str(world / "schleswig-holstein-latest.osm.pbf")
    return Run(workspace_of(world), REGISTRY, Extracts([extract, *map(str, more)], extract))


def without_extracts(world: Path) -> Run:
    """A run on the workspace of `world` with no extract at hand, as in CI."""
    return Run(workspace_of(world), REGISTRY)


def stale(name: str, run: Run) -> str | None:
    return pipeline.output(name).stale(run)


def build(name: str, run: Run) -> None:
    pipeline.output(name).build(run)


# --------------------------------------------------------------- candidates ---
def test_candidates_that_are_not_there_are_stale(world: Path) -> None:
    assert stale("candidates", with_extracts(world)) == (
        f"{workspace_of(world).candidates} is not there"
    )


def test_candidates_scanned_from_the_extracts_at_hand_are_not_stale(world: Path) -> None:
    build("candidates", with_extracts(world))
    assert stale("candidates", with_extracts(world)) is None


def test_candidates_are_stale_after_a_new_download_of_an_extract(world: Path) -> None:
    build("candidates", with_extracts(world))
    write_sh_extract(world, timestamp="2026-09-30T20:21:02Z")
    assert stale("candidates", with_extracts(world)) == (
        f"{workspace_of(world).candidates} was not built from the current extracts"
    )


def test_candidates_are_stale_when_scanned_from_another_set_of_extracts(
    world: Path, tmp_path: Path
) -> None:
    build("candidates", with_extracts(world))
    denmark = write_extract(tmp_path / "denmark-latest.osm.pbf", nodes={7: ((8.4, 55.4), {})})
    assert stale("candidates", with_extracts(world, denmark)) is not None


def test_candidates_from_before_their_header_are_stale(world: Path) -> None:
    write_candidates(Path(workspace_of(world).candidates), cand("n", 1, 8.83, 54.71, name="Toftum"))
    assert stale("candidates", with_extracts(world)) is not None


def test_candidates_cannot_be_scanned_without_an_extract(world: Path) -> None:
    with pytest.raises(PipelineError, match="candidates is built from OSM extracts"):
        build("candidates", without_extracts(world))


# ------------------------------------------------------------------ objects ---
def write_places(world: Path, *rows: dict[str, str]) -> None:
    (world / "places.csv").write_text(places_text(rows), encoding="utf-8")


def test_objects_located_for_the_rows_on_the_map_are_not_stale(world: Path) -> None:
    build("objects", with_extracts(world))
    assert stale("objects", with_extracts(world)) is None


def test_objects_are_stale_after_a_row_got_a_new_reference(world: Path) -> None:
    build("objects", with_extracts(world))
    write_places(world, TOFTEM | {"osm": "node/240044107; way/5"})
    assert stale("objects", with_extracts(world)) == (
        f"{workspace_of(world).objects} was located for other references than the rows on "
        "the map name now (1 new)"
    )


def test_objects_are_stale_after_a_row_went_off_the_map(world: Path) -> None:
    build("objects", with_extracts(world))
    write_places(world, TOFTEM | {"status": "skip"})
    reason = stale("objects", with_extracts(world))
    assert reason is not None and reason.endswith("(1 no longer named)")


def test_objects_are_not_located_again_for_a_reference_no_extract_holds(world: Path) -> None:
    write_places(world, TOFTEM | {"osm": "node/240044107; way/99"})
    build("objects", with_extracts(world))
    assert stale("objects", with_extracts(world)) is None


def test_objects_are_stale_after_a_new_download_of_an_extract(world: Path) -> None:
    build("objects", with_extracts(world))
    write_sh_extract(world, timestamp="2026-09-30T20:21:02Z")
    assert stale("objects", with_extracts(world)) == (
        f"{workspace_of(world).objects} was not built from the current extracts"
    )


def test_without_an_extract_at_hand_the_objects_are_judged_by_their_references(
    world: Path,
) -> None:
    build("objects", with_extracts(world))
    write_sh_extract(world, timestamp="2026-09-30T20:21:02Z")
    assert stale("objects", without_extracts(world)) is None


# -------------------------------------------------------------------- areas ---
def test_dialect_areas_built_from_the_inputs_at_hand_are_not_stale(world: Path) -> None:
    build("areas", with_extracts(world))
    assert stale("areas", with_extracts(world)) is None


def test_dialect_areas_are_stale_after_an_edit_to_the_area_list(world: Path) -> None:
    build("areas", with_extracts(world))
    (world / "dialect_areas.csv").write_text(
        AREA_LIST + "frr-x-fering,Wyk,relation/2,\n", encoding="utf-8"
    )
    assert stale("areas", with_extracts(world)) == (
        f"{workspace_of(world).areas} was not built from the current dialect_areas.csv"
    )


def test_dialect_areas_are_stale_after_an_edit_to_the_registry(world: Path) -> None:
    build("areas", with_extracts(world))
    text = (world / "dialects.csv").read_text(encoding="utf-8")
    (world / "dialects.csv").write_text(
        text.replace(",Mooring,", ",Mooring (edited),", 1), encoding="utf-8"
    )
    assert stale("areas", with_extracts(world)) == (
        f"{workspace_of(world).areas} was not built from the current dialects.csv"
    )


def test_dialect_areas_are_stale_when_one_of_the_two_files_is(world: Path) -> None:
    build("areas", with_extracts(world))
    parts = Path(workspace_of(world).parts)
    parts.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    assert stale("areas", with_extracts(world)) == (
        f"{parts} was not built from the current dialect_areas.csv, dialects.csv and extracts"
    )


def test_dialect_areas_are_built_from_the_area_extract_alone(world: Path, tmp_path: Path) -> None:
    denmark = write_extract(tmp_path / "denmark-latest.osm.pbf", nodes={7: ((8.4, 55.4), {})})
    build("areas", with_extracts(world, denmark))
    assert Stamp.read(workspace_of(world).areas) == Stamp(
        {
            "dialect_areas.csv": blob_hash(world / "dialect_areas.csv"),
            "dialects.csv": blob_hash(world / "dialects.csv"),
        },
        [
            {
                "file": "schleswig-holstein-latest.osm.pbf",
                "replication_timestamp": "2026-09-20T20:21:02Z",
            }
        ],
    )


# ------------------------------------------------------------------- report ---
@pytest.fixture
def matched(world: Path) -> Path:
    """`world` after a scan of its extract and a run of the matcher."""
    build("candidates", with_extracts(world))
    build("report", with_extracts(world))
    return world


def test_a_report_written_from_the_name_list_at_hand_is_not_stale(matched: Path) -> None:
    assert stale("report", without_extracts(matched)) is None


def test_a_report_is_stale_after_an_edit_to_the_name_list(matched: Path) -> None:
    write_places(matched, TOFTEM | {"mooring": "Toftem; Tuftem"})
    assert stale("report", without_extracts(matched)) == (
        f"{workspace_of(matched).report} was not built from the current places.csv"
    )


def test_a_match_that_cannot_finish_stops_the_build_of_the_report(
    world: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(self: requests.Session, *args: object, **kwargs: object) -> NoReturn:
        raise requests.ConnectionError("Wikidata is down")

    monkeypatch.setattr(requests.Session, "get", down)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    write_places(
        world, {"id": "danmark", "kind": "country", "mooring": "Danmark", "de": "Dänemark"}
    )
    build("candidates", with_extracts(world))
    with pytest.raises(PipelineError, match="the matcher could not finish"):
        build("report", with_extracts(world))


# -------------------------------------------------------- dialects and index ---
@pytest.fixture
def built(world: Path) -> Path:
    """`world` with every output the search index is built from."""
    for name in ("objects", "areas", "dialects", "index"):
        build(name, with_extracts(world))
    return world


def test_the_exported_registry_carries_no_stamp_to_be_stale_by(built: Path) -> None:
    text = (built / "dialects.csv").read_text(encoding="utf-8")
    (built / "dialects.csv").write_text(text.replace(",Mooring,", ",Mooring (edited),", 1))
    assert stale("dialects", without_extracts(built)) is None


def test_a_search_index_built_from_the_files_at_hand_is_not_stale(built: Path) -> None:
    assert stale("index", without_extracts(built)) is None


def test_a_search_index_is_stale_after_an_edit_to_the_name_list(built: Path) -> None:
    write_places(built, TOFTEM | {"mooring": "Toftem; Tuftem"})
    assert stale("index", without_extracts(built)) == (
        f"{workspace_of(built).index} was not built from the current places.csv"
    )


# ------------------------------------------------------------------ the table ---
def test_the_table_lists_the_outputs_in_the_order_they_are_built() -> None:
    assert [found.name for found in pipeline.OUTPUTS] == [
        "candidates",
        "report",
        "objects",
        "areas",
        "dialects",
        "index",
    ]


def test_only_the_candidates_are_not_committed() -> None:
    assert [found.name for found in pipeline.OUTPUTS if not found.committed] == ["candidates"]


# ---------------------------------------------------------------- the command ---
def test_the_command_builds_the_output_it_names(world: Path) -> None:
    ws = workspace_of(world)
    extract = str(world / "schleswig-holstein-latest.osm.pbf")
    assert (
        main(["build", "objects", extract, *path_options(ws, "names", "dialects", "objects")]) == 0
    )
    assert list(read_objects(ws.objects).by_ref) == [("n", 240044107)]


def test_the_command_lists_the_outputs_it_can_build(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["build", "--help"])
    listed = capsys.readouterr().out.split("outputs:\n")[1].splitlines()
    assert [line.split()[0] for line in listed] == [found.name for found in pipeline.OUTPUTS]


def test_the_command_says_which_recipe_names_the_extracts_it_was_not_given(
    world: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = path_options(workspace_of(world), "names", "dialects", "objects")
    assert main(["build", "objects", *files]) == 1
    assert capsys.readouterr().err == (
        "objects is built from OSM extracts: name them, or run `just rebuild objects`\n"
    )
