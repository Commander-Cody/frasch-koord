"""The Wikidata items of countries, by German name.

A country is no OSM object the map labels, so the matcher (frasch.match)
finds a country row's item here: `countries` asks the Wikidata API
(wbsearchentities + wbgetentities) for the first item of that name that is a
country, and remembers every answer in names/work/wikidata-countries.json --
also "there is none", so that a name is looked up once.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, NamedTuple

from frasch import files
from frasch.errors import PipelineError

if TYPE_CHECKING:
    import requests

API = "https://www.wikidata.org/w/api.php"
# Wikimedia's User-Agent policy wants a way to reach the operator
USER_AGENT = (
    "frasch-maps name pipeline/0.1 (North Frisian map; "
    "https://github.com/Commander-Cody/frasch-koord/issues)"
)
# what a country is an instance of (P31): country, sovereign state, ...
COUNTRY_CLASSES = {"Q6256", "Q3624078", "Q1763527", "Q112099", "Q185441"}
PAUSE_S = 0.4  # between two lookups: be polite


class Countries(NamedTuple):
    """What `countries` found.  `qids[name]` is the QID, or `""` when Wikidata
    has no country item of that name; a name in `failed` has no answer at all
    (the lookup failed, or it was not to be made and is not cached) -- its
    row must keep what it has.  `warnings` say why a lookup failed."""

    qids: dict[str, str]
    failed: set[str]
    warnings: list[str]


def read_cache(cache_path: str) -> dict[str, str]:
    """The cached lookups, `{German name: QID or ""}` (`""` = the lookup worked
    and found no country item).  A damaged file stops the run: starting from
    an empty cache would look like "not found" for every country offline."""
    if not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError) as exc:
        raise PipelineError(
            f"{cache_path}: cannot read the Wikidata cache ({exc}) "
            f"-- delete the file to query Wikidata afresh"
        ) from None
    if not (
        isinstance(cache, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in cache.items())
    ):
        raise PipelineError(
            f"{cache_path}: not a {{name: QID}} object -- delete the file to query Wikidata afresh"
        )
    return cache


def countries(names: Iterable[str], cache_path: str, offline: bool = False) -> Countries:
    """The country items of the German `names`: from the cache, and for a
    name it does not have from the API -- unless `offline`."""
    cache = read_cache(cache_path)
    todo = [n for n in dict.fromkeys(names) if n and n not in cache]
    if offline or not todo:
        return Countries(cache, set(todo), [])
    problems = _look_up(todo, cache)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    files.atomic_write(cache_path, json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True))
    warnings = [f"wikidata lookup failed for {name}: {why}" for name, why in problems.items()]
    return Countries(cache, set(problems), warnings)


def _look_up(names: Iterable[str], cache: dict[str, str]) -> dict[str, str]:
    """Put the API's answer for each of `names` into `cache`; -> the names
    it gave none for, each with what went wrong."""
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    problems: dict[str, str] = {}
    for name in names:
        try:
            cache[name] = _country(session, name)
        except (requests.RequestException, RuntimeError) as exc:  # network trouble, API error
            problems[name] = str(exc)
            continue
        time.sleep(PAUSE_S)
    return problems


def _country(session: requests.Session, name: str) -> str:
    """The QID of the country item Wikidata finds for a German name, `""` when
    it finds none.  Raises when the lookup itself fails -- that is not the same
    as "no such country" and must not clear a row."""
    hits: list[str] = [
        hit["id"]
        for hit in _ask(
            session,
            "wbsearchentities",
            "search",
            {"search": name, "language": "de", "uselang": "de", "type": "item", "limit": "10"},
        )
    ]
    if not hits:
        return ""
    entities = _ask(
        session,
        "wbgetentities",
        "entities",
        {"ids": "|".join(hits), "props": "claims|labels", "languages": "de"},
    )
    return next((hit for hit in hits if _classes(entities.get(hit)) & COUNTRY_CLASSES), "")


def _ask(session: requests.Session, action: str, member: str, params: dict[str, str]) -> Any:
    """The `member` of the API's answer to `action`; raises when it sends an
    error instead."""
    reply = session.get(API, params={"action": action, **params, "format": "json"}, timeout=30)
    reply.raise_for_status()
    data = reply.json()
    if "error" in data or member not in data:
        raise RuntimeError(f"{action}: {data.get('error') or data}")
    return data[member]


def _classes(entity: Any) -> set[str]:
    """What an entity is an instance of (its P31 claims)."""
    classes: set[str] = set()
    for claim in (entity or {}).get("claims", {}).get("P31", []):
        try:
            classes.add(claim["mainsnak"]["datavalue"]["value"]["id"])
        except (KeyError, TypeError):
            pass  # novalue / somevalue
    return classes
