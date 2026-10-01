"""Print the stamp (frasch.provenance) of the files the search index and the
tiles are built from -- tiles/build.sh writes it into the archive's metadata.

CLI:  `names/provenance.py [--names ...] [--dialects ...] [--curation ...]
                           [--areas ...] [--objects ...]`
      prints `{"built_from": {...}}` for those files (default: the committed
      ones)
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from frasch import cli, paths, provenance


@cli.command
def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--names", default=paths.PLACES)
    ap.add_argument("--dialects", default=paths.DIALECTS)
    ap.add_argument("--curation", default=paths.CURATION)
    ap.add_argument("--areas", default=paths.DIALECT_AREAS)
    ap.add_argument("--objects", default=paths.OBJECTS)
    a = ap.parse_args(argv)
    print(
        json.dumps(
            {"built_from": provenance.stamp(a.names, a.dialects, a.curation, a.areas, a.objects)},
            separators=(",", ":"),
        )
    )
    return 0
