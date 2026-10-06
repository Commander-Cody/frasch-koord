"""What a generated file was built from.

Every output of the pipeline that someone might mistake for current records
its inputs in a `Stamp`:

* a committed input by its **git blob hash** (`git hash-object <file>`),
  computed from the file's content, so it also names an uncommitted state
  and `git log --find-object=<hash>` finds the commit that had it;
* an OSM extract by its file name and replication timestamp (the
  `osmosis_replication_timestamp` of its header, i.e. how current the data
  is -- Geofabrik's `-latest` files change every day).

A file carries its stamp as the `built_from` object
`{label: blob hash, ..., "extracts": [...]}`, where a file of its kind can:

  *.json     at the top level       web/public/data/names.json, names/osm_objects.json
  *.geojson  in its `properties`    names/dialect_areas*.geojson
  *.jsonl    as its `header` line   names/work/candidates.jsonl
  *.md       in a comment line      names/REPORT.md

`Stamp.read` reads it from any of them -- a file of another kind carries
none, as far as the pipeline can tell -- and `Stamp.other_than` says which
inputs a file is behind (frasch.pipeline asks, for `update` and
`check-outputs`).

The search index and the tiles share one stamp (`stamp`): the files both
are built from.  tiles/build.sh writes it into the archive's metadata, and
the frontend warns when the stamp of names.json differs from the tiles'.

`frasch provenance` prints that stamp, `{"built_from": {...}}`, for
tiles/build.sh.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict

from frasch import cli
from frasch.errors import PipelineError, rebuild
from frasch.paths import StrPath, Workspace


class ExtractStamp(TypedDict):
    """An OSM extract, as a stamp records it (`osmscan.extract_stamp`)."""

    file: str
    replication_timestamp: str


# `{label: blob hash, ..., "extracts": [ExtractStamp, ...]}`
BuiltFrom = dict[str, str | list[ExtractStamp]]


def blob_hash(path: StrPath) -> str:
    """The git blob hash of the file's content."""
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@dataclass(frozen=True)
class Stamp:
    """What a generated file was built from: each input file by a fixed label
    ("places.csv") and its git blob hash, and the OSM extracts.  `extracts`
    is None in a stamp of the current inputs where no extract is at hand (in
    CI): such a stamp is only compared with, never written."""

    inputs: Mapping[str, str]
    extracts: Sequence[ExtractStamp] | None

    @classmethod
    def of(cls, inputs: Mapping[str, StrPath], extracts: Sequence[ExtractStamp] | None) -> Stamp:
        """The stamp of a build from the files `inputs` (label -> the path
        actually read) and `extracts`."""
        hashes = {label: blob_hash(path) for label, path in inputs.items()}
        return cls(hashes, None if extracts is None else list(extracts))

    @classmethod
    def read(cls, path: StrPath) -> Stamp | None:
        """The stamp the generated file at `path` carries, where a file of
        its kind does (`_CARRIERS`); None for a file that has none, is not
        there, or is of no kind that carries one."""
        carrier = _CARRIERS.get(os.path.splitext(path)[1])
        built_from = carrier(path) if carrier and os.path.exists(path) else None
        return None if built_from is None else cls.from_json(built_from)

    @classmethod
    def from_json(cls, built_from: BuiltFrom) -> Stamp:
        """The stamp a `built_from` object records."""
        inputs = {label: found for label, found in built_from.items() if isinstance(found, str)}
        extracts = built_from.get("extracts", [])
        return cls(inputs, extracts if isinstance(extracts, list) else [])

    def other_than(self, current: Stamp) -> list[str]:
        """What this stamp names differently than `current`: the labels of
        those inputs, and "extracts" -- unless `current` has none at hand."""
        labels = dict.fromkeys([*current.inputs, *self.inputs])
        differing = [
            label for label in labels if self.inputs.get(label) != current.inputs.get(label)
        ]
        if current.extracts is not None and self.extracts != current.extracts:
            differing.append("extracts")
        return differing

    def as_json(self) -> BuiltFrom:
        """The `built_from` object a file records it as."""
        return {**self.inputs, "extracts": list(self.extracts or [])}

    def as_comment(self) -> str:
        """The line a Markdown file records it as."""
        return f"<!-- built_from: {json.dumps(self.as_json(), separators=(',', ':'))} -->"


def _in_json(path: StrPath) -> BuiltFrom | None:
    """`built_from` at the top level of a JSON object."""
    with open(path, encoding="utf-8") as fh:
        found: BuiltFrom | None = json.load(fh).get("built_from")
    return found


def _in_geojson(path: StrPath) -> BuiltFrom | None:
    """`built_from` in the `properties` of a FeatureCollection."""
    with open(path, encoding="utf-8") as fh:
        found: BuiltFrom | None = json.load(fh).get("properties", {}).get("built_from")
    return found


def _in_json_lines(path: StrPath) -> BuiltFrom | None:
    """The `header` of the first line."""
    with open(path, encoding="utf-8") as fh:
        first = fh.readline()
    found: BuiltFrom | None = json.loads(first).get("header") if first.strip() else None
    return found


_COMMENT = re.compile(r"^<!-- built_from: (.*) -->$", re.MULTILINE)


def _in_markdown(path: StrPath) -> BuiltFrom | None:
    """The comment `Stamp.as_comment` writes."""
    with open(path, encoding="utf-8") as fh:
        comment = _COMMENT.search(fh.read())
    found: BuiltFrom | None = json.loads(comment[1]) if comment else None
    return found


# where a generated file carries its stamp, by the file's suffix
_CARRIERS: dict[str, Callable[[StrPath], BuiltFrom | None]] = {
    ".json": _in_json,
    ".geojson": _in_geojson,
    ".jsonl": _in_json_lines,
    ".md": _in_markdown,
}


def unstamped(path: StrPath, output: str) -> PipelineError:
    """What stops a reader of the generated file at `path` -- the output of
    this name in the pipeline's table -- that needs its stamp and finds none."""
    return PipelineError(
        f"{path} does not say what it was built from -- build it with {rebuild(output)}"
    )


def stamp(ws: Workspace) -> Stamp:
    """What the search index and the tiles are built from: the name list,
    the dialect registry, the curation, the dialect areas and the located
    objects -- and, through the objects file, the extracts they were located
    in."""
    located = Stamp.read(ws.objects)
    if located is None:
        raise unstamped(ws.objects, "objects")
    return Stamp.of(
        {
            "places.csv": ws.names,
            "dialects.csv": ws.dialects,
            "curation.csv": ws.curation,
            "dialect_areas.geojson": ws.areas,
            "osm_objects.json": ws.objects,
        },
        located.extracts,
    )


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("provenance", __doc__)
    cli.add_workspace_options(ap, "names", "dialects", "curation", "areas", "objects")
    ws = cli.workspace(ap.parse_args(argv))
    print(json.dumps({"built_from": stamp(ws).as_json()}, separators=(",", ":")))
    return 0
