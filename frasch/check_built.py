#!/usr/bin/env python3
"""Are the committed build outputs what the committed inputs give?

    names/check_built.py                         # `just check`, run in CI
    names/check_built.py --extracts <pbf> ...    # `just check-full`

Five generated files are committed, because the site and the tile build need
them and they take an OSM extract (or the whole pipeline) to make.  Each is
checked the only way it can be where it is checked:

  web/public/data/names.json      regenerated from the committed files into a
  web/src/generated/dialects.json temporary directory and compared byte for
                                  byte -- neither needs an extract
  names/dialect_areas*.geojson    their `built_from` stamp must name the
                                  current dialect_areas.csv and dialects.csv
  names/osm_objects.json          every OSM reference of a row on the map must
                                  be in it -- the injector's rule

With `--extracts`, the extract-derived files are regenerated as well, each
from the extracts its stamp names (found among the given ones by file name),
and compared.  Exits 1 on any difference and says which `just` recipe
rebuilds the file.
"""
from __future__ import annotations

import argparse
import contextlib
import filecmp
import io
import json
import os
import tempfile

from frasch import (
    build_dialect_areas,
    cli,
    dialects,
    locate,
    paths,
    placelist,
    provenance,
    registry,
    searchindex,
)
from frasch.errors import PipelineError

DEFAULT_PARTS = paths.DIALECT_AREA_PARTS
DEFAULT_REGISTRY_JSON = paths.REGISTRY_JSON


def regenerated_problems(a, tmp) -> list[str]:
    """names.json and dialects.json, rebuilt into `tmp` and compared."""
    problems = []
    index = os.path.join(tmp, "names.json")
    try:
        searchindex.write(searchindex.build(
            a.names, a.dialects, a.curation, a.areas, a.objects), index)
    except PipelineError as stop:
        problems.append(f"the search index cannot be rebuilt: {stop}")
    else:
        problems += differs(a.index, index, "just index")
    exported = os.path.join(tmp, "dialects.json")
    dialects.export_json(registry.read(a.dialects), exported)
    problems += differs(a.registry_json, exported, "just dialects")
    return problems


def unlocated_problems(a) -> list[str]:
    """Every OSM reference of a row on the map that the objects file lacks --
    the tile build stops on each of them, not only on a row's first one, the
    only one the search index needs."""
    reg = registry.read(a.dialects)
    rows, _ = placelist.read(a.names, reg)
    objects = locate.read_objects(a.objects).by_ref
    problems = []
    for row in (r for r in rows if placelist.on_map(r, reg)):
        missing = [ref for ref in placelist.parse_osm(row["osm"])
                   if ref[0] != placelist.LOCAL_TYPE and ref not in objects]
        if missing:
            problems.append(f"{row['id']}: {placelist.format_osm(missing)} not in "
                            f"{a.objects} -- locate it with `just objects`")
    return problems


def stamp_problems(a) -> list[str]:
    """The dialect areas, by the inputs their stamp names."""
    current = {"dialect_areas.csv": provenance.blob_hash(a.area_list),
               "dialects.csv": provenance.blob_hash(a.dialects)}
    problems = []
    for path in (a.areas, a.parts):
        with open(path, encoding="utf-8") as fh:
            stamp = json.load(fh).get("properties", {}).get("built_from", {})
        stale = [k for k, v in current.items() if stamp.get(k) != v]
        if stale:
            problems.append(f"{path} was built from another {' and '.join(stale)} "
                            f"-- rebuild it with `just areas`")
    return problems


def extract_problems(a, tmp) -> list[str]:
    """The objects file and the dialect areas, each rebuilt from the
    extracts its own stamp names (the areas need only Schleswig-Holstein)."""
    objects = os.path.join(tmp, "osm_objects.json")
    areas = os.path.join(tmp, "dialect_areas.geojson")
    parts = os.path.join(tmp, "dialect_areas_parts.geojson")
    try:
        objects_from, areas_from = stamped_extracts(a.objects, a), stamped_extracts(a.areas, a)
    except LookupError as missing:
        return [str(missing)]
    # the two commands themselves, as `just objects` and `just areas` run
    # them; a failure is on stderr already
    with contextlib.redirect_stdout(io.StringIO()):
        if locate.main(objects_from + ["--names", a.names, "--out", objects]):
            return [f"{a.objects} cannot be rebuilt (see above)"]
        if build_dialect_areas.main(areas_from + ["--areas", a.area_list,
                                                  "--registry", a.dialects,
                                                  "--out", areas, "--parts-out", parts]):
            return [f"{a.areas} cannot be rebuilt (see above)"]
    return (differs(a.objects, objects, "just objects")
            + differs(a.areas, areas, "just areas")
            + differs(a.parts, parts, "just areas"))


def stamped_extracts(path, a) -> list[str]:
    """The paths among `--extracts` of the extracts `path` was built from,
    in the stamp's order; a LookupError names one that was not given."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    stamp = (data.get("properties") or data)["built_from"]
    given = {os.path.basename(p): p for p in a.extracts}
    names = [e["file"] for e in stamp["extracts"]]
    absent = [n for n in names if n not in given]
    if absent:
        raise LookupError(f"{path} was built from {', '.join(absent)}, which "
                          f"--extracts does not name")
    return [given[n] for n in names]


def differs(committed, regenerated, recipe) -> list[str]:
    if os.path.exists(committed) and filecmp.cmp(committed, regenerated, shallow=False):
        return []
    return [f"{committed} is not what its inputs give -- rebuild it with `{recipe}`"]


@cli.command
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", default=placelist.DEFAULT_PATH)
    ap.add_argument("--dialects", default=paths.DIALECTS)
    ap.add_argument("--curation", default=paths.CURATION)
    ap.add_argument("--area-list", default=dialects.AREA_LIST_PATH)
    ap.add_argument("--areas", default=dialects.DEFAULT_AREAS)
    ap.add_argument("--parts", default=DEFAULT_PARTS)
    ap.add_argument("--objects", default=locate.DEFAULT_OUT)
    ap.add_argument("--index", default=paths.SEARCH_INDEX)
    ap.add_argument("--registry-json", default=DEFAULT_REGISTRY_JSON)
    ap.add_argument("--extracts", nargs="+", default=[], metavar="PBF",
                    help="also rebuild names/osm_objects.json and the dialect "
                         "areas from these extracts and compare them")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        problems = (unlocated_problems(a) + regenerated_problems(a, tmp)
                    + stamp_problems(a))
        if a.extracts:
            problems += extract_problems(a, tmp)
    for p in problems:
        print(f"  ! {p}")
    if problems:
        return 1
    print("the committed build outputs match their inputs")
    return 0

