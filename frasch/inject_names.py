"""Copy an OSM PBF and add North Frisian name / curation tags to it.

    frasch inject <in.osm.pbf> <out.osm.pbf> [--dry-run]

Four files are merged into the extract, and every one of them must be
there: the name list (`names/places.csv`), the dialect areas
(`names/dialect_areas.geojson`), the objects file (`names/osm_objects.json`,
which says where each object of the name list lies) and the curation
(`names/curation.csv`).  The dialect registry (`names/dialects.csv`) says
which `name:<tag>` there are.  tiles/README.md says which tags an object gets
from them and why; names/README.md describes the files.

An object of the extract gets, in this order: the names and attributes its
row of the name list gives it (frasch.placenames, the rule the search index
is built by too; which row holds it is frasch.inject.claims') -- or, when no
row holds it and it lies in a dialect area, OSM's own `name:frr` as
`frasch:local` -- and then the `set_tags` and zooms of its curation row,
verbatim, so they may override `frasch:kind` or `place`.  All other tags
are preserved (`o.replace(tags=...)`), as are all objects no file mentions.
The places OSM does not have and the synthetic squares are added in between
(frasch.inject.synthetic).

Tag values are strings: the `frasch:*` tags reach the tiles because
tiles/build.sh passes them to Planetiler via `--extra_name_tags`.

Used by tiles/build.sh before Planetiler runs.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence

import osmium

from frasch import cli, dialects, locate, placenames
from frasch.dialects import Registry
from frasch.inject import report
from frasch.inject.claims import Claim, Claims
from frasch.inject.inputs import Inputs, load_inputs
from frasch.inject.report import Report
from frasch.inject.stats import Stats
from frasch.inject.synthetic import SyntheticObjects
from frasch.inject.writer import Writer, copy_of
from frasch.objects import LocatedObject, point
from frasch.paths import Workspace
from frasch.placenames import LOCAL_KEY
from frasch.refs import OsmRef

# an object of the extract the injector copies
_OsmObject = osmium.osm.Node | osmium.osm.Way | osmium.osm.Relation


class Injector:
    """Copies the objects of the extract to `writer` as they stream past,
    each with its tags (`handle`); what it does goes into `stats`."""

    def __init__(self, writer: Writer, inputs: Inputs, stats: Stats):
        self._writer = writer
        self._inputs = inputs
        self._stats = stats
        self._claims = Claims(inputs.names, inputs.members, stats)
        self._synthetic = SyntheticObjects(writer, inputs.local_places, stats)

    def handle(self, o: _OsmObject) -> None:
        """Copy one object of the extract, with the tags it gets; an object
        that gets none is copied as it is."""
        key = (o.type_str(), o.id)
        self._stats.scanned += 1
        self._synthetic.passing(key)
        added = self._added_tags(key, o)
        # curation puts a synthetic square around a node only
        node = o if isinstance(o, osmium.osm.Node) else None
        square = self._inputs.curation.squares.get(key) if node is not None else None
        if not added and square is None:
            self._writer.add(o)
            return
        tags = dict(o.tags) | added
        if node is not None and square is not None:
            # the square inherits the node's names; the node keeps its own tags
            centre = (node.location.lon, node.location.lat)
            self._synthetic.add_square(key, square, centre, tags)
        self._writer.add(o.replace(tags=tags))

    def finish(self) -> None:
        """The extract has ended."""
        self._synthetic.finish()

    def _added_tags(self, key: OsmRef, o: _OsmObject) -> dict[str, str]:
        """The tags this object gets: its row's -- or, when no row claims
        it, OSM's Frisian name as its local one (#81) -- and then the
        curation's, which win."""
        tags: dict[str, str] = {}
        claim = self._claims.row_for(key, o.tags)
        if claim is not None:
            tags = self._row_tags(claim, o)
            self._stats.tag(key[0], tags)
        elif local := self._inputs.osm_local.get(key):
            self._stats.osm_local_unclaimed += 1
            tags[LOCAL_KEY] = local
        tuning = self._inputs.curation.objects.get(key)
        if tuning is not None:
            self._stats.curated.add(key)
            tags.update(tuning["tags"])
        return tags

    def _row_tags(self, claim: Claim, o: _OsmObject) -> dict[str, str]:
        """The tags the row claiming this object gives it (placenames.resolve)."""
        obj = self._located(claim.located_as, o)
        names = placenames.resolve(claim.row, obj, self._inputs.areas, self._inputs.reg)
        if names.local_from_osm:
            self._stats.osm_local_claimed += 1
        return placenames.as_tags(names)

    def _located(self, key: OsmRef, o: _OsmObject) -> LocatedObject | None:
        """Where the object of `key` lies and what OSM says of it: from the
        objects file (`frasch build objects`), which the search index reads
        too.  A node found only through its QID is asked itself; a way or
        relation found that way has no position, and so no dialect."""
        if key in self._inputs.objects:
            return self._inputs.objects[key]
        if isinstance(o, osmium.osm.Node) and o.location.valid():
            return point(o.location.lon, o.location.lat, **locate.object_facts(dict(o.tags)))
        return None


def run(ws: Workspace, reg: Registry, inp: str, out: str, *, dry_run: bool = False) -> Report:
    """Copy the extract `inp` to `out` with the workspace's names, dialect
    areas and curation as tags (see the module docstring); -> what was
    tagged.  `dry_run`: report only, write nothing."""
    loaded = load_inputs(ws, reg, inp)
    started = time.time()
    stats = _inject(inp, None if dry_run else out, loaded)
    wrote = (
        "(dry run -- nothing written)"
        if dry_run
        else f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)"
    )
    log = [
        *report.input_lines(loaded, ws),
        *report.result_lines(stats, loaded, inp, time.time() - started),
        "",
        wrote,
    ]
    return Report(stats, log)


def _inject(inp: str, out: str | None, loaded: Inputs) -> Stats:
    """Copy `inp` to `out` with the tags added (`out` None: a dry run that
    only counts); -> the counts."""
    stats = Stats()
    copy = copy_of(inp, out)
    injector = Injector(copy, loaded, stats)
    for o in osmium.FileProcessor(inp):
        if isinstance(o, (osmium.osm.Node, osmium.osm.Way, osmium.osm.Relation)):
            injector.handle(o)
    injector.finish()
    copy.close()
    return stats


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = cli.parser("inject", __doc__)
    ap.add_argument("infile")
    ap.add_argument("outfile")
    cli.add_workspace_options(ap, "names", "dialects", "areas", "objects", "curation")
    ap.add_argument(
        "--dry-run", action="store_true", help="report what would be tagged, write nothing"
    )
    a = ap.parse_args(argv)
    if not a.dry_run and os.path.abspath(a.infile) == os.path.abspath(a.outfile):
        ap.error("refusing to overwrite the input file")
    ws = cli.workspace(a)
    found = run(ws, dialects.read(ws.dialects), a.infile, a.outfile, dry_run=a.dry_run)
    cli.say(found.log)
    return 0
