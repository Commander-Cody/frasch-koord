"""tiles/nametags.sh: Planetiler is told to carry every tag the injector
writes into the tiles -- by the frasch commands, so the list cannot fall
behind the table of tile keys (frasch.placenames)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from frasch import placenames
from conftest import REGISTRY, REGISTRY_CSV

TILES = Path(__file__).resolve().parent.parent
# the `frasch` command of the environment the tests run in
FRASCH = Path(sys.executable).with_name("frasch")


@pytest.fixture(scope="module")
def options(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list[str]]:
    """What `name_tag_options` tells Planetiler, for the registry of the
    tests: `{"--languages": [...], "--extra_name_tags": [...]}`."""
    dialects = tmp_path_factory.mktemp("nametags") / "dialects.csv"
    dialects.write_text(REGISTRY_CSV, encoding="utf-8")
    script = (
        f'source "{TILES / "workspace.sh"}" && source "{TILES / "nametags.sh"}" && '
        'name_tag_options "$1" && printf "%s\\n" "${NAME_TAG_OPTIONS[@]}"'
    )
    result = subprocess.run(
        ["bash", "-c", script, "bash", str(FRASCH)],
        capture_output=True,
        text=True,
        env={"DIALECTS": str(dialects)},
        check=True,
    )
    pairs = (line.split("=", 1) for line in result.stdout.splitlines())
    return {option: values.split(",") for option, values in pairs}


def carried(key: str, options: dict[str, list[str]]) -> bool:
    """Whether Planetiler carries a tag of the injected extract into the
    tiles: a name by its language, anything else by its key."""
    if key.startswith("name:"):
        return key.removeprefix("name:") in options["--languages"]
    return key in options["--extra_name_tags"]


@pytest.mark.parametrize(
    "key",
    [
        *placenames.TILE_KEY.values(),
        placenames.MINZOOM_KEY,
        placenames.MAXZOOM_KEY,
        *(placenames.dialect_key(tag) for tag in REGISTRY.tags),
    ],
)
def test_planetiler_carries_every_key_the_injector_writes(
    key: str, options: dict[str, list[str]]
) -> None:
    assert carried(key, options)
