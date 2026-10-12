"""names/work/matches.jsonl -- what the last `frasch match` made of every row
it owns, as frasch.match writes it and the curation export (frasch.worklist)
reads it.  Git-ignored: it says what a run did, a dry run included, and is
thrown away with the next.

One line per row, a JSON object:

  id          the row's id in places.csv
  result      `matched`, `ambiguous`, `not_found` or `lookup_failed`
              (`matchresult.Outcome`)
  why         the matcher's remark: how it came to the match, or why there
              is none
  osm, wikidata
              the reference a matched row gets, as its cells spell it
  match_name, match_tags, lon, lat
              the object that was chosen: its name, its decisive tags and
              where it is (null for one the scan could not place)
  hint_point  where the row's location hint points: lon, lat, radius in km;
              null for a row without a hint, or with one nothing resolves
  candidates  the objects a reviewer should see, the best first
              (`ListedCandidate`)
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from typing import NotRequired, TypedDict

from frasch import candidates, files, matchresult, osmtags, refs
from frasch.candidates import osm_key
from frasch.errors import PipelineError
from frasch.hints import Circle
from frasch.matchresult import MatchResult, RankedCandidate
from frasch.nameindex import NameIndex
from frasch.paths import StrPath

# One candidate of a row (`class` is a keyword):
#   ref     the object, `node/123`
#   name, class, km
#           its name, what it is in one word and its distance from the
#           centre of North Frisia (`matchresult.summary`); `km` is null for
#           an object without a position
#   lon, lat, tags
#           where it is, and its decisive tags (`osmtags.decisive`)
#   in_sh   whether it is in the Schleswig-Holstein extract
#   rank    how good the name hit is that found it (lower = better)
#   wikidata
#           its `wikidata` tag, left out when it has none
ListedCandidate = TypedDict(
    "ListedCandidate",
    {
        "ref": str,
        "name": str,
        "class": str,
        "km": int | None,
        "lon": float | None,
        "lat": float | None,
        "tags": str,
        "in_sh": bool,
        "rank": int,
        "wikidata": NotRequired[str],
    },
)


class Entry(TypedDict):
    """One line of the file: a row's id and what the run made of it."""

    id: str
    result: str
    why: str
    osm: str
    wikidata: str
    match_name: str
    match_tags: str
    lon: float | None
    lat: float | None
    hint_point: list[float] | None
    candidates: list[ListedCandidate]


def entry(row_id: str, result: MatchResult, hint_point: Circle | None, index: NameIndex) -> Entry:
    """The line of the row `row_id`: its `result`, where its hint points, and
    its candidates as records of `index`, the candidates the run matched
    against."""
    lon, lat = result.lonlat or (None, None)
    return {
        "id": row_id,
        "result": result.result.value,
        "why": result.why,
        "osm": refs.format(result.refs),
        "wikidata": result.wikidata,
        "match_name": result.match_name,
        "match_tags": result.match_tags,
        "lon": lon,
        "lat": lat,
        "hint_point": list(hint_point) if hint_point else None,
        "candidates": [_listed(c, index) for c in result.candidates],
    }


def _listed(c: RankedCandidate, index: NameIndex) -> ListedCandidate:
    """A candidate as the file lists it."""
    tags = c["tags"]
    name, what, km = matchresult.summary(c)
    listed: ListedCandidate = {
        "ref": refs.format([osm_key(c)]),
        "name": name,
        "class": what,
        "km": km,
        "lon": c["lon"],
        "lat": c["lat"],
        "tags": osmtags.decisive(tags),
        "in_sh": any(map(candidates.is_sh, index.sources.get(osm_key(c), ()))),
        "rank": c["rank"],
    }
    if tags.get(osmtags.ITEM_KEY):
        listed["wikidata"] = tags[osmtags.ITEM_KEY]
    return listed


def write(path: str, entries: Iterable[Entry]) -> None:
    """Write the file in one step: a run that fails leaves the last one."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with files.replacing(path, text=True) as fh:
        for line in entries:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def read(path: StrPath) -> list[Entry]:
    """The file's lines, in the order of the name list the run read.  Stops
    when there is no file: the matcher has not run."""
    if not os.path.exists(path):
        raise PipelineError(f"{path} not found -- run `frasch match` first")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]
