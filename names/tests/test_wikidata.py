"""wikidata.py: the country items by German name, through the Wikidata API
(faked where a session sends its request) and the cache of its answers."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

import pytest
import requests

from frasch import wikidata


class Reply:
    """An answer of the API: its JSON."""

    def __init__(self, data: object) -> None:
        self.data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        return self.data


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """The API's answers, by the `action` asked for; none to begin with."""
    replies: dict[str, object] = {}

    def get(self: requests.Session, url: str, params: Mapping[str, str], timeout: int) -> Reply:
        return Reply(replies[params["action"]])

    monkeypatch.setattr(requests.Session, "get", get)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return replies


def instance_of(*classes: str) -> dict[str, object]:
    """An entity that is an instance of `classes`."""
    claims = [{"mainsnak": {"datavalue": {"value": {"id": c}}}} for c in classes]
    return {"claims": {"P31": claims}}


def test_the_first_hit_that_is_a_country_is_the_item(
    tmp_path: Path, api: dict[str, object]
) -> None:
    # Q756617 is the Danish Realm, the first hit for "Dänemark"; Q35 the country
    api["wbsearchentities"] = {"search": [{"id": "Q756617"}, {"id": "Q35"}]}
    api["wbgetentities"] = {
        "entities": {"Q756617": instance_of("Q1250464"), "Q35": instance_of("Q3624078", "Q6256")}
    }
    found = wikidata.countries(["Dänemark"], str(tmp_path / "countries.json"))
    assert found.qids == {"Dänemark": "Q35"}


def test_an_error_the_api_answers_with_is_a_failed_lookup(
    tmp_path: Path, api: dict[str, object]
) -> None:
    api["wbsearchentities"] = {"error": {"code": "maxlag"}}
    found = wikidata.countries(["Dänemark"], str(tmp_path / "countries.json"))
    assert found.failed == {"Dänemark"}


@pytest.fixture
def outage(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(self: requests.Session, *a: object, **kw: object) -> NoReturn:
        raise requests.ConnectionError("Wikidata is down")

    monkeypatch.setattr(requests.Session, "get", down)
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_a_failed_lookup_comes_back_as_a_warning(tmp_path: Path, outage: None) -> None:
    found = wikidata.countries(["Dänemark"], str(tmp_path / "countries.json"))
    assert found.warnings == ["wikidata lookup failed for Dänemark: Wikidata is down"]


def test_a_failed_lookup_prints_nothing(
    tmp_path: Path, outage: None, capsys: pytest.CaptureFixture[str]
) -> None:
    wikidata.countries(["Dänemark"], str(tmp_path / "countries.json"))
    assert capsys.readouterr() == ("", "")


def test_a_programming_error_is_no_failed_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: requests.Session, *a: object, **kw: object) -> NoReturn:
        raise KeyError("search")

    monkeypatch.setattr(requests.Session, "get", broken)
    with pytest.raises(KeyError):
        wikidata.countries(["Dänemark"], str(tmp_path / "countries.json"))


def test_user_agent_names_a_contact() -> None:
    assert "https://github.com/Commander-Cody/frasch-koord" in wikidata.USER_AGENT
