"""names/work/candidates.jsonl -- every OSM object that could be a place,
as frasch.build_candidates writes it and frasch.match and the curation
export (frasch.curate) read it.

  first line  {"header": {"extracts": [{"file", "replication_timestamp"}, ...]}}
              -- the stamp of the extracts it was built from
              (`provenance.Stamp.read` reads it)
  then        {"src","t","id","lon","lat","tags":{...}}  per candidate
              (`read_records`)
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import TypedDict

from frasch.paths import StrPath
from frasch.provenance import BuiltFrom, ExtractStamp, Stamp
from frasch.refs import OsmRef


class Candidate(TypedDict):
    """One candidate record.  `src` is the extract it was found in (its
    file name up to `-latest`); `lon`/`lat` are None for an object the scan
    could not place; `tags` are those of its tags the pipeline reads
    (frasch.osmtags.KEPT_KEYS)."""

    src: str
    t: str
    id: int
    lon: float | None
    lat: float | None
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
        next(fh, None)  # the header
        for line in fh:
            yield json.loads(line)


def osm_key(rec: Candidate) -> OsmRef:
    """A candidate record's (type, id), as `refs.parse` spells a
    reference: `("w", 28330569)`."""
    return rec["t"], rec["id"]
