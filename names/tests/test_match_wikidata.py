"""A Wikidata failure must not clear the country rows (#21, H4)."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import NoReturn, Protocol

import pytest
import requests

from frasch import match
from frasch.errors import PipelineError
from conftest import REGISTRY, places_text, workspace

COUNTRIES = [
    {
        "kind": "country",
        "mooring": "Däänemark",
        "de": "Dänemark",
        "wikidata": "Q35",
        "status": "auto",
    },
    {
        "kind": "country",
        "mooring": "Holönj",
        "de": "Niederlande",
        "wikidata": "Q55",
        "status": "auto",
    },
]


class RunMatch(Protocol):
    def __call__(self, offline: bool = False) -> int: ...


# the `outage` fixture: the positional arguments of every Session.get call
Calls = list[tuple[object, ...]]


@pytest.fixture
def run(world: Path) -> tuple[RunMatch, Path, Path]:
    places = world / "places.csv"
    places.write_text(places_text(COUNTRIES), encoding="utf-8")
    (world / "work" / "candidates.jsonl").write_text("", encoding="utf-8")
    cache = world / "work" / "wikidata-countries.json"

    def run_match(offline: bool = False) -> int:
        return match.run(workspace(world), REGISTRY, offline=offline)

    return run_match, places, cache


@pytest.fixture
def outage(monkeypatch: pytest.MonkeyPatch) -> Calls:
    calls: Calls = []

    def down(self: requests.Session, *a: object, **kw: object) -> NoReturn:
        calls.append(a)
        raise requests.ConnectionError("Wikidata is down")

    monkeypatch.setattr(requests.Session, "get", down)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return calls


def test_outage_keeps_the_country_rows_and_fails(
    run: tuple[RunMatch, Path, Path], outage: Calls
) -> None:
    run_match, places, _cache = run
    before = places.read_bytes()
    assert run_match() == 1
    assert outage, "the lookup was not even tried"
    assert places.read_bytes() == before


def test_outage_does_not_poison_the_cache(run: tuple[RunMatch, Path, Path], outage: Calls) -> None:
    run_match, _places, cache = run
    run_match()
    assert json.loads(cache.read_text(encoding="utf-8")) == {}


def test_offline_without_cache_keeps_the_country_rows_and_fails(
    run: tuple[RunMatch, Path, Path], outage: Calls
) -> None:
    run_match, places, _cache = run
    before = places.read_bytes()
    assert run_match(offline=True) == 1
    assert not outage, "--offline must not call the API"
    assert places.read_bytes() == before


def test_not_found_is_still_not_found(run: tuple[RunMatch, Path, Path], outage: Calls) -> None:
    """The distinction cuts both ways: a cached "no country item" answer
    still clears the row the matcher filled earlier."""
    run_match, places, cache = run
    cache.write_text(json.dumps({"Dänemark": "", "Niederlande": "Q55"}), encoding="utf-8")
    assert run_match(offline=True) == 0
    text = places.read_text(encoding="utf-8")
    assert "Q35" not in text
    assert "Q55" in text


def test_corrupt_cache_fails_instead_of_starting_empty(
    run: tuple[RunMatch, Path, Path], outage: Calls
) -> None:
    run_match, places, cache = run
    before = places.read_bytes()
    cache.write_text('{"Dänemark": "Q35", ', encoding="utf-8")
    with pytest.raises(PipelineError, match="Wikidata cache"):
        run_match(offline=True)
    assert places.read_bytes() == before


def test_cache_of_the_wrong_shape_fails(run: tuple[RunMatch, Path, Path], outage: Calls) -> None:
    run_match, _places, cache = run
    cache.write_text('["Q35"]', encoding="utf-8")
    with pytest.raises(PipelineError, match="delete the file"):
        run_match(offline=True)


def test_user_agent_names_a_contact() -> None:
    assert "https://github.com/Commander-Cody/frasch-koord" in match.WD_USER_AGENT


def test_each_country_answer_shows_in_matches_csv_and_the_summary(
    world: Path, outage: Calls, capsys: pytest.CaptureFixture[str]
) -> None:
    """A cached item matches, a cached "no item" clears, no answer at all
    leaves the row and fails the run."""
    sweden = {"kind": "country", "mooring": "Swäärje", "de": "Schweden"}
    places = world / "places.csv"
    places.write_text(places_text(COUNTRIES + [sweden]), encoding="utf-8")
    (world / "work" / "candidates.jsonl").write_text("", encoding="utf-8")
    cache = world / "work" / "wikidata-countries.json"
    cache.write_text(json.dumps({"Dänemark": "Q35", "Niederlande": ""}), encoding="utf-8")
    matches = world / "work" / "matches.csv"
    code = match.run(workspace(world), REGISTRY, offline=True)
    assert code == 1
    with open(matches, encoding="utf-8", newline="") as fh:
        got = [
            (m["de"], m["wikidata"], m["result"], m["match_name"], m["match_tags"], m["note"])
            for m in csv.DictReader(fh)
        ]
    assert got == [
        ("Dänemark", "Q35", "matched", "Dänemark", "wikidata", "auto: wikidata"),
        ("Niederlande", "", "not_found", "", "", "no Wikidata country item found"),
        ("Schweden", "", "lookup_failed", "", "", "Wikidata lookup failed -- row left unchanged"),
    ]
    out, err = capsys.readouterr()
    assert "matcher owns 3 of 3 rows: 1 matched, 1 not_found, 1 lookup_failed" in out.splitlines()
    assert "places.csv: 0 rows filled, 1 cleared, 0 changed" in out.splitlines()
    assert err.splitlines()[-1] == (
        "error: no Wikidata answer for 1 country row(s) (--offline and not in the cache)"
        " -- left unchanged: Swäärje (Schweden)"
    )
