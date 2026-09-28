"""names/work/candidates.jsonl -- every OSM object that could be a place,
as names/build_candidates.py writes it and names/match.py and the curation
export read it.

  first line  {"header": {"extracts": [{"file", "replication_timestamp"}, ...]}}
              -- the extracts it was built from (`read_header`)
  then        {"src","t","id","lon","lat","cls","tags":{...}}  per candidate
              (`read_records`)
"""
from __future__ import annotations

import json

from frasch.provenance import extract_stamp

# the `place` / `natural` values of an island
ISLAND_PLACES = {"island", "islet", "archipelago"}


def header(pbfs) -> dict:
    """The first line of candidates.jsonl: the extracts, in the order read."""
    return {"header": {"extracts": [extract_stamp(p) for p in pbfs]}}


def read_header(path) -> list[dict] | None:
    """The extracts a candidates.jsonl was built from, as `extract_stamp`
    gives them; None for a file written before it had a header."""
    with open(path, encoding="utf-8") as fh:
        first = fh.readline()
    if not first.strip():
        return None
    line = json.loads(first)
    return line["header"]["extracts"] if "header" in line else None


def read_records(path):
    """The candidate records of a candidates.jsonl, one at a time (the file
    is tens of megabytes), without its header."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if "header" not in rec:
                yield rec


def osm_key(rec):
    """A candidate record's (type, id), as `placelist.parse_osm` spells a
    reference: `("w", 28330569)`."""
    return rec["t"], rec["id"]


def decisive_tags(rec) -> str:
    """The tags that say what kind of thing a record is, `place=village;...`
    -- for the matcher's output and the curation view."""
    tags = rec["tags"]
    keys = ("place", "natural", "water", "waterway", "boundary", "admin_level",
            "landuse", "man_made", "historic", "highway", "type")
    return ";".join(f"{k}={tags[k]}" for k in keys if k in tags)
