"""A Wikidata failure must not clear the country rows (#21, H4)."""
from __future__ import annotations

import json

import pytest
import requests

import match
from conftest import places_text

COUNTRIES = [
    {"kind": "country", "mooring": "Däänemark", "de": "Dänemark",
     "wikidata": "Q35", "status": "auto"},
    {"kind": "country", "mooring": "Holönj", "de": "Niederlande",
     "wikidata": "Q55", "status": "auto"},
]


@pytest.fixture
def run(world):
    places = world / "places.csv"
    places.write_text(places_text(COUNTRIES), encoding="utf-8")
    (world / "work" / "candidates.jsonl").write_text("", encoding="utf-8")
    cache = world / "work" / "wikidata-countries.json"

    def run_match(*extra):
        return match.main(["--names", str(places),
                           "--candidates", str(world / "work" / "candidates.jsonl"),
                           "--matches", str(world / "work" / "matches.csv"),
                           "--report", str(world / "REPORT.md"),
                           "--wikidata-cache", str(cache), *extra])

    return run_match, places, cache


@pytest.fixture
def outage(monkeypatch):
    calls = []

    def down(self, *a, **kw):
        calls.append(a)
        raise requests.ConnectionError("Wikidata is down")

    monkeypatch.setattr(requests.Session, "get", down)
    monkeypatch.setattr(match.time, "sleep", lambda s: None)
    return calls


def test_outage_keeps_the_country_rows_and_fails(run, outage):
    run_match, places, _cache = run
    before = places.read_bytes()
    assert run_match() == 1
    assert outage, "the lookup was not even tried"
    assert places.read_bytes() == before


def test_outage_does_not_poison_the_cache(run, outage):
    run_match, _places, cache = run
    run_match()
    assert json.loads(cache.read_text(encoding="utf-8")) == {}


def test_offline_without_cache_keeps_the_country_rows_and_fails(run, outage):
    run_match, places, _cache = run
    before = places.read_bytes()
    assert run_match("--offline") == 1
    assert not outage, "--offline must not call the API"
    assert places.read_bytes() == before


def test_not_found_is_still_not_found(run, outage):
    """The distinction cuts both ways: a cached "no country item" answer
    still clears the row the matcher filled earlier."""
    run_match, places, cache = run
    cache.write_text(json.dumps({"Dänemark": "", "Niederlande": "Q55"}),
                     encoding="utf-8")
    assert run_match("--offline") == 0
    text = places.read_text(encoding="utf-8")
    assert "Q35" not in text
    assert "Q55" in text


def test_corrupt_cache_fails_instead_of_starting_empty(run, outage):
    run_match, places, cache = run
    before = places.read_bytes()
    cache.write_text('{"Dänemark": "Q35", ', encoding="utf-8")
    with pytest.raises(SystemExit, match="Wikidata cache"):
        run_match("--offline")
    assert places.read_bytes() == before


def test_cache_of_the_wrong_shape_fails(run, outage):
    run_match, _places, cache = run
    cache.write_text('["Q35"]', encoding="utf-8")
    with pytest.raises(SystemExit, match="delete the file"):
        run_match("--offline")


def test_user_agent_names_a_contact():
    assert "https://github.com/Commander-Cody/frasch-koord" in match.WD_USER_AGENT
