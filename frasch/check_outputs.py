"""Are the committed build outputs what the committed inputs give?

    frasch check-outputs                         # `just check-outputs`, run in CI
    frasch check-outputs --extracts <pbf> ...    # `just check-full`

The generated files of the pipeline's table (frasch.pipeline) are committed,
all but the candidates, because the site and the tile build need them and
they take an OSM extract, or the whole pipeline, to make.  Each is checked
as far as it can be where it is checked:

  its stamp     must name the inputs that are there now; the objects file
                must be located for the references the rows on the map name
  a rebuild     into a temporary directory must give the same file, byte for
                byte -- where it can be rebuilt: the search index and the
                frontend's registry anywhere, the objects file and the
                dialect areas with `--extracts`, the matcher's report never
                (it takes the git-ignored candidates)

With `--extracts`, the stamp of a file built from them must name those
extracts as well, and the report's the extracts of the candidates, if there
are candidates.  Without, no extract is compared: what the check says then
depends on the committed files alone.  And a row on the map must not name an
object that no extract holds: the tile build stops on it.  Exits 1 on any of this and says which `just` recipe rebuilds the
file.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence

from frasch import cli, pipeline, placelist, registry
from frasch.objects import named, read_objects, unlocated
from frasch.pipeline import Extracts, Run


def problems(run: Run) -> list[str]:
    """What is wrong with the committed outputs of the run's workspace, one
    line each.  With extracts at hand, the outputs built from them are
    rebuilt and compared as well."""
    found = unlocated_problems(run)
    with tempfile.TemporaryDirectory() as scratch:
        for output in pipeline.OUTPUTS:
            if output.committed:
                found += output.problems(run, scratch)
    return found


def unlocated_problems(run: Run) -> list[str]:
    """Every OSM reference of a row on the map that the objects file has no
    object for -- the tile build stops on each of them, not only on a row's
    first one, the only one the search index needs."""
    if not os.path.exists(run.ws.objects):
        return []
    rows, _ = placelist.read(run.ws.names, run.reg)
    return unlocated(read_objects(run.ws.objects), named(rows, run.reg))


def run(run: Run) -> int:
    """Check the outputs of the run's workspace and print what is wrong with
    them; -> the exit status."""
    found = problems(run)
    for p in found:
        print(f"  ! {p}")
    if found:
        return 1
    print("the committed build outputs match their inputs")
    return 0


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("check-outputs", __doc__)
    cli.add_workspace_options(ap, *cli.WORKSPACE_FILES, cli.WORK)
    ap.add_argument(
        "--extracts",
        nargs="+",
        default=[],
        metavar="PBF",
        help="also rebuild names/osm_objects.json and the dialect "
        "areas from these extracts and compare them",
    )
    pipeline.add_area_extract_option(ap)
    a = ap.parse_args(argv)
    ws = cli.workspace(a)
    return run(Run(ws, registry.read(ws.dialects), Extracts.given(a.extracts, a.area_extract)))
