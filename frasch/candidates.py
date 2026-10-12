"""names/work/candidates.jsonl -- every OSM object that could be a place,
as frasch.build_candidates writes it and frasch.match reads it.

  first line  {"header": {"extracts": [{"file", "replication_timestamp"}, ...]}}
              -- the stamp of the extracts it was built from
              (`provenance.Stamp.read` reads it)
  then        {"src","t","id","lon","lat","tags":{...}}  per candidate
              (`read_records`)
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator, Sequence
from typing import TypedDict

from frasch.errors import PipelineError, rebuild
from frasch.paths import StrPath
from frasch.provenance import BuiltFrom, ExtractStamp, Stamp, unstamped
from frasch.refs import OsmRef


# Geofabrik's file of a region ends in the day it is of: `-latest`, or the
# day of a snapshot (`-260923`, see tiles/fetch.sh)
_DAY = re.compile(r"-(?:latest|\d{6})$")
_SH = "schleswig-holstein"


def source(extract: StrPath) -> str:
    """The `src` of the candidates found in an extract: its region, as
    Geofabrik's file names it, whatever day the file is of --
    `schleswig-holstein` for `schleswig-holstein-latest.osm.pbf`."""
    return _DAY.sub("", os.path.basename(extract).split(".")[0])


def is_sh(src: str) -> bool:
    """Whether a source is the extract the tiles are built from: only its
    objects can carry an injected name, so it is what "in Schleswig-Holstein"
    means for the curation view.  An object near the border can come from
    both extracts."""
    return src == _SH


class Candidate(TypedDict):
    """One candidate record.  `src` is the extract it was found in
    (`source`); `lon`/`lat` are None for an object the scan
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


def extracts(path: StrPath) -> Sequence[ExtractStamp]:
    """The extracts a candidates.jsonl was built from, as its header names
    them.  Stops when there is no file, or it does not name its extracts."""
    if not os.path.exists(path):
        raise PipelineError(f"{path} not found -- build it with {rebuild('candidates')}")
    stamp = Stamp.read(path)
    if stamp is None:
        raise unstamped(path, "candidates")
    return stamp.extracts or []


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
