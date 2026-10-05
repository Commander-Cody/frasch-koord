"""Are the committed build outputs what the committed inputs give?

    frasch check-outputs                         # `just check-outputs`, run in CI
    frasch check-outputs --extracts <pbf> ...    # `just check-full`

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

import filecmp
import os
import tempfile
from collections.abc import Sequence

from frasch import (
    build_dialect_areas,
    cli,
    files,
    locate,
    placelist,
    provenance,
    registry,
    searchindex,
)
from frasch.errors import PipelineError
from frasch.objects import objects_json, read_objects
from frasch.paths import Workspace
from frasch.registry import Registry


def problems(ws: Workspace, reg: Registry, extracts: Sequence[str] = ()) -> list[str]:
    """What is wrong with the committed outputs of the workspace, one line
    each.  With `extracts`, the objects file and the dialect areas are
    rebuilt from them and compared as well."""
    with tempfile.TemporaryDirectory() as tmp:
        # the same workspace, with its outputs rebuilt in a temporary directory
        rebuilt = Workspace.at(tmp)
        found = unlocated_problems(ws, reg) + regenerated_problems(ws, reg, rebuilt)
        found += stamp_problems(ws)
        if extracts:
            found += extract_problems(ws, reg, extracts, rebuilt)
    return found


def regenerated_problems(ws: Workspace, reg: Registry, rebuilt: Workspace) -> list[str]:
    """names.json and dialects.json, rebuilt as the files of `rebuilt` and
    compared."""
    found = []
    try:
        searchindex.write(searchindex.build(ws, reg), rebuilt.index)
    except PipelineError as stop:
        found.append(f"the search index cannot be rebuilt: {stop}")
    else:
        found += differs(ws.index, rebuilt.index, "just index")
    registry.export_json(reg, rebuilt.registry_json)
    found += differs(ws.registry_json, rebuilt.registry_json, "just dialects")
    return found


def unlocated_problems(ws: Workspace, reg: Registry) -> list[str]:
    """Every OSM reference of a row on the map that the objects file lacks --
    the tile build stops on each of them, not only on a row's first one, the
    only one the search index needs."""
    rows, _ = placelist.read(ws.names, reg)
    objects = read_objects(ws.objects).by_ref
    found = []
    for row in (r for r in rows if placelist.on_map(r, reg)):
        missing = [
            ref
            for ref in placelist.parse_osm(row["osm"])
            if ref[0] != placelist.LOCAL_TYPE and ref not in objects
        ]
        if missing:
            found.append(
                f"{row['id']}: {placelist.format_osm(missing)} not in "
                f"{ws.objects} -- locate it with `just objects`"
            )
    return found


def stamp_problems(ws: Workspace) -> list[str]:
    """The dialect areas, by the inputs their stamp names."""
    current = {
        label: provenance.blob_hash(path)
        for label, path in build_dialect_areas.stamp_inputs(ws).items()
    }
    found = []
    for path in (ws.areas, ws.parts):
        stamp = provenance.recorded(path)
        stale = [k for k, v in current.items() if stamp.get(k) != v]
        if stale:
            found.append(
                f"{path} was built from another {' and '.join(stale)} "
                f"-- rebuild it with `just areas`"
            )
    return found


def extract_problems(
    ws: Workspace, reg: Registry, extracts: Sequence[str], rebuilt: Workspace
) -> list[str]:
    """The objects file and the dialect areas, each rebuilt as a file of
    `rebuilt` from the extracts its own stamp names (the areas need only
    Schleswig-Holstein), and compared."""
    try:
        objects_from = stamped_extracts(ws.objects, extracts)
        areas_from = stamped_extracts(ws.areas, extracts)
    except LookupError as missing:
        return [str(missing)]
    try:
        objects = locate.build(ws, reg, objects_from)
    except PipelineError as stop:
        return [f"{ws.objects} cannot be rebuilt: {stop}"]
    try:
        areas = build_dialect_areas.build(ws, reg, areas_from)
    except PipelineError as stop:
        return [f"{ws.areas} cannot be rebuilt: {stop}"]
    os.makedirs(os.path.dirname(rebuilt.objects), exist_ok=True)
    files.atomic_write(rebuilt.objects, objects_json(objects))
    build_dialect_areas.write_geojson(rebuilt.areas, areas.dialects)
    if areas.parts is not None:
        build_dialect_areas.write_geojson(rebuilt.parts, areas.parts.fc)
    return (
        differs(ws.objects, rebuilt.objects, "just objects")
        + differs(ws.areas, rebuilt.areas, "just areas")
        + differs(ws.parts, rebuilt.parts, "just areas")
    )


def stamped_extracts(path: str, given: Sequence[str]) -> list[str]:
    """The paths among the extracts `given` of those `path` was built from,
    in the stamp's order; a LookupError names one that was not given."""
    stamp = provenance.recorded(path)
    by_name = {os.path.basename(p): p for p in given}
    extracts = stamp.get("extracts")
    if not isinstance(extracts, list):
        raise LookupError(f"{path} names no extracts it was built from")
    names = [e["file"] for e in extracts]
    absent = [n for n in names if n not in by_name]
    if absent:
        raise LookupError(
            f"{path} was built from {', '.join(absent)}, which --extracts does not name"
        )
    return [by_name[n] for n in names]


def differs(committed: str, regenerated: str, recipe: str) -> list[str]:
    if os.path.exists(committed) and filecmp.cmp(committed, regenerated, shallow=False):
        return []
    return [f"{committed} is not what its inputs give -- rebuild it with `{recipe}`"]


def run(ws: Workspace, reg: Registry, extracts: Sequence[str] = ()) -> int:
    """Check the workspace's outputs and print what is wrong with them; ->
    the exit status."""
    found = problems(ws, reg, extracts)
    for p in found:
        print(f"  ! {p}")
    if found:
        return 1
    print("the committed build outputs match their inputs")
    return 0


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("check-outputs", __doc__)
    cli.add_workspace_options(
        ap,
        "names",
        "dialects",
        "curation",
        "area_list",
        "areas",
        "parts",
        "objects",
        "index",
        "registry_json",
    )
    ap.add_argument(
        "--extracts",
        nargs="+",
        default=[],
        metavar="PBF",
        help="also rebuild names/osm_objects.json and the dialect "
        "areas from these extracts and compare them",
    )
    a = ap.parse_args(argv)
    ws = cli.workspace(a)
    return run(ws, registry.read(ws.dialects), a.extracts)
