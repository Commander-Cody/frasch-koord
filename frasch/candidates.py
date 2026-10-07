"""names/work/candidates.jsonl -- every OSM object that could be a place,
as frasch.build_candidates writes it and frasch.match and the curation
export (frasch.curate) read it.

  first line  {"header": {"extracts": [{"file", "replication_timestamp"}, ...]}}
              -- the stamp of the extracts it was built from
              (`provenance.Stamp.read` reads it)
  then        {"src","t","id","lon","lat","cls","tags":{...}}  per candidate
              (`read_records`)
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import TypedDict

from frasch.paths import StrPath
from frasch.placelist import OsmRef
from frasch.provenance import BuiltFrom, ExtractStamp, Stamp

# the `place` / `natural` values of an island
ISLAND_PLACES = {"island", "islet", "archipelago"}


class Candidate(TypedDict):
    """One candidate record.  `lon`/`lat` are None for an object the scan
    could not place; `cls` are the classes it was kept for (`place=village`,
    `wikidata`, ...); `tags` only the ones the pipeline reads."""

    src: str
    t: str
    id: int
    lon: float | None
    lat: float | None
    cls: list[str]
    tags: dict[str, str]


class HeaderLine(TypedDict):
    header: BuiltFrom


def header(extracts: Sequence[ExtractStamp]) -> HeaderLine:
    """The first line of candidates.jsonl: the extracts, in the order read."""
    return {"header": Stamp.of({}, extracts).as_json()}


def read_records(path: StrPath) -> Iterator[Candidate]:
    """The candidate records of a candidates.jsonl, one at a time (the file
    is tens of megabytes), without its header."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if "header" not in rec:
                yield rec


def osm_key(rec: Candidate) -> OsmRef:
    """A candidate record's (type, id), as `placelist.parse_osm` spells a
    reference: `("w", 28330569)`."""
    return rec["t"], rec["id"]


def decisive_tags(rec: Candidate) -> str:
    """The tags that say what kind of thing a record is, `place=village;...`
    -- for the matcher's output and the curation view."""
    tags = rec["tags"]
    keys = (
        "place",
        "natural",
        "water",
        "waterway",
        "boundary",
        "admin_level",
        "landuse",
        "man_made",
        "historic",
        "highway",
        "type",
    )
    return ";".join(f"{k}={tags[k]}" for k in keys if k in tags)
