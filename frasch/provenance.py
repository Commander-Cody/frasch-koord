"""What a generated file was built from.

Every output of the pipeline that someone might mistake for current --
web/public/data/names.json, the tiles, names/osm_objects.json,
names/dialect_areas.geojson -- records its inputs in a `built_from` object:

* a committed input by its **git blob hash** (`git hash-object <file>`),
  computed from the file's content, so it also names an uncommitted state
  and `git log --find-object=<hash>` finds the commit that had it;
* an OSM extract by its file name and replication timestamp (the
  `osmosis_replication_timestamp` of its header, i.e. how current the data
  is -- Geofabrik's `-latest` files change every day).

The search index and the tiles share one stamp (`stamp`): the files both
are built from.  tiles/build.sh writes it into the archive's metadata
(`provenance.py` prints it), and the frontend warns when the stamp of
names.json differs from the tiles'.

CLI:  `names/provenance.py [--names ...] [--dialects ...] [--curation ...]
                           [--areas ...] [--objects ...]`
      prints `{"built_from": {...}}` for those files (default: the committed
      ones)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from typing import TypedDict

import osmium

from frasch import cli, paths
from frasch.paths import StrPath


class ExtractStamp(TypedDict):
    """An OSM extract, as a `built_from` records it."""
    file: str
    replication_timestamp: str


# `{label: blob hash, ..., "extracts": [ExtractStamp, ...]}`
BuiltFrom = dict[str, str | list[ExtractStamp]]


def blob_hash(path: StrPath) -> str:
    """The git blob hash of the file's content."""
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def extract_stamp(pbf: StrPath) -> ExtractStamp:
    """`{"file", "replication_timestamp"}` of an OSM extract; the timestamp is
    `""` when the header has none."""
    reader = osmium.io.Reader(str(pbf))
    try:
        timestamp = reader.header().get("osmosis_replication_timestamp") or ""
    finally:
        reader.close()
    return {"file": os.path.basename(pbf), "replication_timestamp": timestamp}


def built_from(inputs: Mapping[str, StrPath], extracts: list[ExtractStamp]) -> BuiltFrom:
    """The stamp: `{label: blob hash}` for each input file (`inputs` maps a
    fixed label such as "places.csv" to the path actually read), plus the
    OSM extracts."""
    hashes: BuiltFrom = {label: blob_hash(path) for label, path in inputs.items()}
    return hashes | {"extracts": extracts}


def stamp(places: StrPath, dialects: StrPath, curation: StrPath, areas: StrPath,
          objects: StrPath) -> BuiltFrom:
    """What the search index and the tiles are built from: the name list,
    the dialect registry, the curation, the dialect areas and the located
    objects -- and, through the objects file, the extracts they were located
    in."""
    with open(objects, encoding="utf-8") as fh:
        extracts: list[ExtractStamp] = json.load(fh)["built_from"]["extracts"]
    return built_from({"places.csv": places, "dialects.csv": dialects,
                       "curation.csv": curation, "dialect_areas.geojson": areas,
                       "osm_objects.json": objects}, extracts)


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=paths.PLACES)
    ap.add_argument("--dialects", default=paths.DIALECTS)
    ap.add_argument("--curation", default=paths.CURATION)
    ap.add_argument("--areas", default=paths.DIALECT_AREAS)
    ap.add_argument("--objects", default=paths.OBJECTS)
    a = ap.parse_args(argv)
    print(json.dumps({"built_from": stamp(a.names, a.dialects, a.curation, a.areas,
                                          a.objects)}, separators=(",", ":")))
    return 0

