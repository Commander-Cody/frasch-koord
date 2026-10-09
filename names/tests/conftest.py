"""Shared fixtures for the name-pipeline tests: a throwaway workspace in a
temp directory (`ws`; `world` is its names/ with places.csv, curation.csv,
dialects.csv and work/), and the dialect registry the tests work with -- one
of their own, so that an edit to names/dialects.csv changes no test."""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from frasch import candidates, curationlist, paths, placelist
from frasch.candidates import Candidate
from frasch.paths import Workspace
from frasch.provenance import ExtractStamp
from frasch.registry import Dialect, Registry
from osm_fixture import Nodes, ring, write_extract

# the dialects of the tests: (column, label, status, view)
_DIALECTS = [
    ("mooring", "Mooring", "living", "yes"),
    ("wieding", "Wiedingharder", "living", "no"),
    ("nordgoes", "Nordergoesharder", "living", "no"),
    ("suedgoes", "Südergoesharder", "extinct", "no"),
    ("fering", "Fering", "living", "no"),
    ("oomrang", "Öömrang", "living", "no"),
    ("solring", "Sölring", "living", "no"),
    ("hallig", "Halligfriesisch", "living", "no"),
]
REGISTRY = Registry(
    [
        Dialect(
            tag=f"frr-x-{column}", column=column, label=label, status=status, view=view, note=""
        )
        for column, label, status, view in _DIALECTS
    ]
)
# the same registry as a dialects.csv
REGISTRY_CSV = "tag,column,label,status,view,note\n" + "".join(
    f"{d['tag']},{d['column']},{d['label']},{d['status']},{d['view']},\n" for d in REGISTRY
)


def read_schema(name: str) -> dict[str, Any]:
    """names/<name>.schema.json, the contract of a file both Python and the
    web app handle."""
    with open(os.path.join(paths.ROOT, "names", f"{name}.schema.json"), encoding="utf-8") as fh:
        schema: dict[str, Any] = json.load(fh)
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def schema_problems(value: object, schema: str) -> list[str]:
    """What breaks names/<schema>.schema.json in `value`, a file as its
    writer builds it: one line per problem, none for a value that keeps it."""
    errors = jsonschema.Draft202012Validator(read_schema(schema)).iter_errors(value)
    return sorted(f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in errors)


def places_text(rows: Iterable[Mapping[str, str]]) -> str:
    """A places.csv with the header REGISTRY gives it; `rows` are dicts of the
    cells that are not empty.  A row without an `id` key gets `row-<n>` (n
    counting from 1); pass `id` explicitly -- even empty -- to control it."""
    columns = placelist.columns(REGISTRY)
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for n, r in enumerate(rows, start=1):
        r = {"id": f"row-{n}", **r}
        w.writerow({k: r.get(k, "") for k in columns})
    return buf.getvalue()


# a row of the name list, as several tests need one
TOFTUM = {
    "kind": "settlement",
    "mooring": "Toftem",
    "de": "Toftum",
    "osm": "node/240044107",
    "status": "ok",
}


def cand(
    t: str,
    id: int,
    lon: float | None,
    lat: float | None,
    src: str = "schleswig-holstein",
    **tags: str,
) -> Candidate:
    """One candidates.jsonl record (build_candidates.py's format).  Tag keys
    with a colon are passed with a double underscore (`name__de`)."""
    tags = {k.replace("__", ":"): v for k, v in tags.items()}
    cls = [
        f"{k}={tags[k]}"
        for k in ("place", "natural", "boundary", "highway", "man_made")
        if k in tags
    ]
    if "wikidata" in tags:
        cls.append("wikidata")
    return {"src": src, "t": t, "id": id, "lon": lon, "lat": lat, "cls": cls, "tags": tags}


def write_candidates(path: Path, *recs: Candidate, extracts: Sequence[ExtractStamp] = ()) -> Path:
    """Write `recs` as a candidates.jsonl to `path`, under the header of a
    scan of `extracts`, and return it."""
    lines = [candidates.header(extracts), *recs]
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines), encoding="utf-8"
    )
    return path


CURATION_HEADER = "osm,name,lat,lon,set_tags,minzoom,maxzoom,polygon_km2,note\n"
AREA_LIST_HEADER = "dialect,name,osm,note\n"


def curation_file(directory: Path, *rows: Mapping[str, str]) -> str:
    """Write a curation.csv of `rows` (dicts of the cells that are not empty)
    into `directory` and return its path."""
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=curationlist.COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in curationlist.COLUMNS})
    path = directory / "curation.csv"
    path.write_text(buf.getvalue(), encoding="utf-8")
    return str(path)


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    """A workspace in `tmp_path`, with the dialect registry REGISTRY, an
    empty curation, an empty dialect area list and its work directory."""
    workspace = Workspace.at(tmp_path)
    os.makedirs(os.path.dirname(workspace.lock))
    Path(workspace.curation).write_text(CURATION_HEADER, encoding="utf-8")
    Path(workspace.dialects).write_text(REGISTRY_CSV, encoding="utf-8")
    Path(workspace.area_list).write_text(AREA_LIST_HEADER, encoding="utf-8")
    return workspace


def workspace(world: Path) -> Workspace:
    """The workspace whose names/ directory `world` is."""
    return Workspace.at(world.parent)


def flat_workspace(directory: Path) -> Workspace:
    """A workspace whose name files all lie in `directory` itself, as the
    tile-build tests lay theirs out (the dialect areas as areas.geojson);
    writes its dialect registry, REGISTRY."""
    (directory / "dialects.csv").write_text(REGISTRY_CSV, encoding="utf-8")
    return dataclasses.replace(
        Workspace.at(directory),
        names=str(directory / "places.csv"),
        dialects=str(directory / "dialects.csv"),
        curation=str(directory / "curation.csv"),
        areas=str(directory / "areas.geojson"),
        objects=str(directory / "osm_objects.json"),
        index=str(directory / "names.json"),
    )


def path_options(ws: Workspace, *names: str) -> list[str]:
    """What points a command at the files `names` of `ws`: the path option of
    each (`work`: of its scratch directory)."""
    paths = {"work": os.path.dirname(ws.lock)}
    return [
        arg
        for name in names
        for arg in ("--" + name.replace("_", "-"), paths.get(name) or getattr(ws, name))
    ]


@pytest.fixture
def world(ws: Workspace) -> Path:
    """The names/ directory of `ws`: places.csv, curation.csv, dialects.csv,
    work/."""
    return Path(ws.names).parent


# ------------------------------------------- a world to run the pipeline on ---
AREA_LIST = "dialect,name,osm,note\nfrr-x-mooring,Niebüll,relation/1,\n"
# a village inside the Mooring area of the extract `write_sh_extract` writes
TOFTUM_NODE = ((8.83, 54.71), {"name": "Toftum", "place": "village"})


def write_sh_extract(
    world: Path, timestamp: str = "2026-09-20T20:21:02Z", more_nodes: Nodes | None = None
) -> Path:
    """Write the extract of `pipeline_world`: the Mooring area of AREA_LIST
    and Toftum."""
    area, way = ring(10, (8.7, 54.6), (8.9, 54.6), (8.9, 54.8), (8.7, 54.8))
    nodes: Nodes = {**area, 240044107: TOFTUM_NODE, **(more_nodes or {})}
    return write_extract(
        world / "schleswig-holstein-latest.osm.pbf",
        nodes,
        {5: (way, {})},
        {1: ([("w", 5, "outer")], {"boundary": "administrative"})},
        timestamp=timestamp,
    )


@pytest.fixture
def pipeline_world(world: Path) -> Path:
    """`world` with the rest of the pipeline's inputs: one dialect area, and
    an extract holding it and one village."""
    (world / "dialect_areas.csv").write_text(AREA_LIST, encoding="utf-8")
    write_sh_extract(world)
    return world
